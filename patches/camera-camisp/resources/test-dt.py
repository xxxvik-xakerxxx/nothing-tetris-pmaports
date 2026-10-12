#!/usr/bin/env python3
"""Exercise compiled-tree guards with synthetic data, without invoking dtc."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("camisp_dt_check", HERE / "check-dt.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
u32, strings = check.u32, check.strings
SOC = "/soc@0"
SPM = SOC + "/syscon@1c001000/power-controller"
MM = SPM + "/power-domain@7"
PMIC = SOC + "/spmi@1cc04000/pmic@6"
REGS = PMIC + "/regulators"
IOMMU = SOC + "/iommu@1e802000"
TOP = SOC + "/syscon@10000000"
COMMON = SOC + "/smi@1e801000"
LARB0 = SOC + "/smi@1401e000"


def fixture(data):
    base = {
        "/": {"compatible": strings("nothing,tetris", "mediatek,mt6878")},
        SPM: {"compatible": strings("mediatek,mt6878-power-controller"), "#power-domain-cells": u32(1), "phandle": u32(1)},
        MM: {"reg": u32(7), "clocks": u32(2, 0), "clock-names": strings("mm_infra"), "mediatek,hardware-voter": u32(7)},
        TOP: {"compatible": strings("mediatek,mt6878-topckgen"), "#clock-cells": u32(1), "phandle": u32(2)},
        SOC + "/hw-voter": {"phandle": u32(7)},
        PMIC: {"compatible": strings("mediatek,mt6319-regulator", "mediatek,mt6315-regulator"),
               "reg": u32(6, 0), "mediatek,buck1-mode-mask": u32(1), "status": strings("disabled"),
               "mediatek,observe-vgpu-only": b""},
        REGS: {}, REGS + "/vbuck2": {"status": strings("disabled"), "regulator-name": strings("mt6319-vgpu")},
        COMMON: {"reg": u32(0x1e801000, 0x1000), "phandle": u32(3)},
        LARB0: {"reg": u32(0x1401e000, 0x1000), "mediatek,larb-id": u32(0), "phandle": u32(4)},
        IOMMU: {"compatible": strings("mediatek,mt6878-disp-iommu"), "#iommu-cells": u32(1),
                "phandle": u32(5), "status": strings("okay"), "mediatek,larbs": u32(4)},
    }
    tree = copy.deepcopy(base)
    paths = {"spm": SPM, "topckgen": TOP, "disp_iommu": IOMMU, "smi_disp_common": COMMON}
    aliases = {"camsys_main_clk": "cam_main", "camsys_mraw_clk": "cam_mraw", "cam_vcore_clk": "cam_vcore",
               "camisp-l13-1": "camisp_l13", "camisp-l14-1": "camisp_l14"}
    for i, (name, props) in enumerate(data["nodes"].items(), 10):
        address = int(props["reg"].strip("<>").split()[1], 0) if "reg" in props else None
        node = ("clock-controller" if "#clock-cells" in props else "smi") + f"@{address:x}" if address else name
        paths[aliases.get(name, name)] = SOC + "/" + node
        tree[SOC + "/" + node] = {"phandle": u32(i), "status": strings("disabled")}
    def refs(pairs):
        return b"".join(tree[paths[aliases.get(owner, owner)]]["phandle"] + u32(index) for owner, index in pairs)
    for name, props in data["nodes"].items():
        target = tree[paths[aliases.get(name, name)]]
        compat = props["compatible"].split(", ")[0].strip('"')
        if name == "camsys_main_clk":
            compat = "mediatek,mt6878-camsys"
        elif name in ("smi_larb13", "smi_larb14"):
            compat = "mediatek,mt6878-smi-larb"
        target["compatible"] = strings(compat)
        for key in ("#clock-cells", "mediatek,common-id", "mediatek,larb-id"):
            if key in props:
                target[key] = u32(int(props[key].strip("<>")))
        if "reg" in props:
            cells = props["reg"].strip("<>").split()
            target["reg"] = u32(int(cells[1], 0), int(cells[3], 0))
        if "clocks" in props:
            target["clocks"] = refs([(owner, data["native_clock_ids"][symbol]) for owner, symbol in
                                      re.findall(r"<&(\w+) (CLK_\w+)>", props["clocks"])])
            target["clock-names"] = strings(*re.findall(r'"([^"]+)"', props["clock-names"]))
        if "iommus" in props:
            target["iommus"] = refs([("disp_iommu", data["ports"][symbol]) for symbol in re.findall(r"<&disp_iommu (\w+)>", props["iommus"])])
        if "power-domains" in props:
            domain = props["power-domains"].split("MT6878_POWER_DOMAIN_")[1].split(">")[0]
            target["power-domains"] = u32(1, data["power"]["domains"][domain])
        if "mediatek,smi-supply" in props:
            owner = re.fullmatch(r"<&(\w+) 0>", props["mediatek,smi-supply"]).group(1)
            target["mediatek,smi"] = tree[paths[owner]]["phandle"]
            if name == "smi_cam_vcore_2x1_sub_comm0":
                target["mediatek,smi-supply"] = target["mediatek,smi"]
    for index in (1, 4):
        target = {"status": strings("disabled"), "regulator-name": strings(f"6_vbuck{index}")}
        for key, value in data["power"]["rails"][str(index)].items():
            if key != "always_on":
                target[key] = u32(value)
            elif value:
                target["regulator-always-on"] = b""
        if index == 1:
            target["phandle"] = u32(30)
        tree[REGS + f"/vbuck{index}"] = target
    tree[SPM].update({"status": strings("disabled"), "cam-vcore-supply": u32(30), "isp-vcore-supply": u32(30)})
    tree[MM]["status"] = strings("disabled")
    for name, path in (("CAM_VCORE", MM + "/power-domain@a"), ("CAM_MAIN", MM + "/power-domain@a/power-domain@d"), ("ISP_VCORE", MM + "/power-domain@10")):
        target = {"reg": u32(data["power"]["domains"][name]), "#power-domain-cells": u32(0), "status": strings("disabled")}
        if name == "CAM_VCORE":
            target.update({"#address-cells": u32(1), "#size-cells": u32(0)})
        elif name == "CAM_MAIN":
            target["clocks"] = refs([(row["owner"], row["native_id"]) for row in data["power"]["clocks"]])
            target["clock-names"] = strings(*(row["name"] for row in data["power"]["clocks"]))
        tree[path] = target
    tree[IOMMU].update({"status": strings("disabled"), "mediatek,larbs": u32(4) +
                       tree[paths["smi_larb13"]]["phandle"] + tree[paths["smi_larb14"]]["phandle"]})
    return base, tree


class CompiledTreeGuards(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "evidence.json").read_text())
        self.base, self.tree = fixture(self.data)

    def test_valid_shape(self):
        check.validate(self.base, self.tree, self.data)

    def test_literal_hwid_is_not_an_incidental_phandle(self):
        consys = "/consys@18000000"
        for tree in (self.base, self.tree):
            tree[consys] = {"hwid-node": u32(92)}
        self.base["/unrelated-a"] = {"phandle": u32(92)}
        self.base["/unrelated-b"] = {"phandle": u32(93)}
        self.tree["/unrelated-a"] = {"phandle": u32(93)}
        self.tree["/unrelated-b"] = {"phandle": u32(92)}
        check.validate(self.base, self.tree, self.data)
        self.tree[consys]["hwid-node"] = u32(93)
        with self.assertRaisesRegex(ValueError, "Base property changed"):
            check.validate(self.base, self.tree, self.data)

    def test_every_new_node_and_owner_must_stay_disabled(self):
        for path in set(self.tree) - set(self.base) | {SPM, MM, PMIC}:
            tree = copy.deepcopy(self.tree)
            tree[path]["status"] = strings("okay")
            with self.subTest(path=path), self.assertRaises(ValueError):
                check.validate(self.base, tree, self.data)

    def test_protection_clocks_cannot_swap(self):
        path = MM + "/power-domain@a/power-domain@d"
        raw = self.tree[path]["clocks"]
        self.tree[path]["clocks"] = raw[:8] + raw[16:24] + raw[8:16] + raw[24:]
        with self.assertRaisesRegex(ValueError, "ordered CAM_MAIN clocks"):
            check.validate(self.base, self.tree, self.data)

    def test_supply_pair_cannot_use_gpu_buck(self):
        self.tree[REGS + "/vbuck2"]["phandle"] = u32(31)
        self.tree[SPM]["isp-vcore-supply"] = u32(31)
        with self.assertRaisesRegex(ValueError, "supply pair"):
            check.validate(self.base, self.tree, self.data)

    def test_preserve_other_rails_and_hwv(self):
        for path, prop in ((REGS + "/vbuck2", "regulator-name"), (MM, "mediatek,hardware-voter")):
            tree = copy.deepcopy(self.tree)
            tree[path][prop] = strings("changed")
            with self.subTest(path=path), self.assertRaises(ValueError):
                check.validate(self.base, tree, self.data)

    def test_vgpu_observer_policy_cannot_be_removed(self):
        self.tree[PMIC].pop("mediatek,observe-vgpu-only")
        with self.assertRaisesRegex(ValueError, "Removed base property"):
            check.validate(self.base, self.tree, self.data)

    def test_buck4_always_on_cannot_disappear(self):
        self.tree[REGS + "/vbuck4"].pop("regulator-always-on")
        with self.assertRaisesRegex(ValueError, "rail policy"):
            check.validate(self.base, self.tree, self.data)

    def test_duplicate_spm_is_rejected(self):
        self.tree[SOC + "/fake-spm"] = dict(self.tree[SPM], phandle=u32(40))
        with self.assertRaisesRegex(ValueError, "unique diagnostic SPM"):
            check.validate(self.base, self.tree, self.data)

    def test_unexpected_voltage_policy_is_rejected(self):
        self.tree[REGS + "/vbuck1"]["regulator-init-microvolt"] = u32(700000)
        with self.assertRaisesRegex(ValueError, "rail policy"):
            check.validate(self.base, self.tree, self.data)

    def test_logical_camisp_cannot_acquire_registers(self):
        self.tree[SOC + "/camisp-l13-1"]["reg"] = u32(0x1a001000, 0x1000)
        with self.assertRaisesRegex(ValueError, "property inventory"):
            check.validate(self.base, self.tree, self.data)


if __name__ == "__main__":
    unittest.main()
