#!/usr/bin/env python3
"""CI consumer: check compiled disabled board against its compiled native base."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "patches/modem"))
from check_preflight_dt import cells, compatible, phandle_owners, read_tree, reference_value, require


def u32(*values):
    return b"".join(value.to_bytes(4, "big") for value in values)


def strings(*values):
    return b"".join(value.encode() + b"\0" for value in values)


def unique(tree, predicate, description):
    matches = [path for path, props in tree.items() if predicate(path, props)]
    require(len(matches) == 1, "Expected unique " + description)
    return matches[0]


def validate(base, tree, data, profile="disabled"):
    require(profile in ("disabled", "supplier", "ownership-blocked"), "Unknown board profile")
    owners = phandle_owners(tree)
    base_owners = phandle_owners(base)
    spm = unique(base, lambda p, v: b"mediatek,mt6878-power-controller" in compatible(v), "native SPM")
    require(unique(tree, lambda p, v: b"mediatek,mt6878-power-controller" in compatible(v), "diagnostic SPM") == spm,
            "Native SPM replaced")
    mm = unique(base, lambda p, v: p.startswith(spm + "/") and v.get("reg") == u32(7), "MM_INFRA")
    pmic = unique(base, lambda p, v: b"mediatek,mt6315-regulator" in compatible(v) and
                  v.get("reg") == u32(6, 0), "native USID6 PMIC")
    require(unique(tree, lambda p, v: b"mediatek,mt6315-regulator" in compatible(v) and
                   v.get("reg") == u32(6, 0), "diagnostic USID6 PMIC") == pmic, "PMIC duplicated")
    regulators = pmic + "/regulators"
    require(regulators in base and base[pmic].get("mediatek,buck1-mode-mask") == u32(1), "Existing USID6 phase mask")
    top = unique(base, lambda p, v: b"mediatek,mt6878-topckgen" in compatible(v), "real TOPCKGEN")
    iommu = unique(base, lambda p, v: b"mediatek,mt6878-disp-iommu" in compatible(v), "display IOMMU")
    require(unique(tree, lambda p, v: p.startswith(spm + "/") and v.get("reg") == u32(7), "diagnostic MM_INFRA") == mm,
            "MM_INFRA duplicated")
    soc = pmic.rsplit("/spmi@", 1)[0]
    paths = {"topckgen": top, "spm": spm, "disp_iommu": iommu}
    added = {regulators + "/vbuck1", regulators + "/vbuck4",
             mm + "/power-domain@a", mm + "/power-domain@a/power-domain@d", mm + "/power-domain@10"}
    for name, props in data["nodes"].items():
        label = {"camsys_main_clk": "cam_main", "camsys_mraw_clk": "cam_mraw",
                 "cam_vcore_clk": "cam_vcore", "camisp-l13-1": "camisp_l13", "camisp-l14-1": "camisp_l14"}.get(name, name)
        if "reg" in props:
            address = int(props["reg"].strip("<>").split()[1], 0)
            prefix = "clock-controller" if "#clock-cells" in props else "smi"
            path = f"{soc}/{prefix}@{address:x}"
            require(tree.get(path, {}).get("reg") == u32(address, int(props["reg"].strip("<>").split()[3], 0)),
                    "Camera resource address: " + path)
        else:
            path = soc + "/" + name
        paths[label] = path
        added.add(path)
    require(set(base) <= set(tree) and set(tree) - set(base) == added, "Exact additive board node inventory")
    # Compare references by actual owner path, not incidental phandle numbers.
    changes = {spm: {"status", "cam-vcore-supply", "isp-vcore-supply"}, mm: {"status"},
               iommu: {"status", "mediatek,larbs"}}
    removals = {}
    if profile != "disabled":
        require({b"nothing,tetris", b"mediatek,mt6878"} <= set(compatible(base.get("/", {}))),
                "Wrong native base identity")
        for path in (spm, mm, iommu):
            require(base[path].get("status", b"okay\0") in (b"okay\0", b"ok\0"),
                    "Supplier base must preserve available display owners: " + path)
        require({"clocks", "clock-names", "mediatek,hardware-voter"} <= base[mm].keys(),
                "Supplier base lacks real MM_INFRA clocks/HWV")
        require(base[pmic].get("status") == b"disabled\0" and
                base[pmic].get("mediatek,observe-vgpu-only") == b"", "Expected dormant observer baseline")
        require(not ({"cam-vcore-supply", "isp-vcore-supply"} & base[spm].keys()),
                "Baseline already opts into native VMM")
        changes = {}
        if profile == "ownership-blocked":
            changes = {spm: {"cam-vcore-supply", "isp-vcore-supply"}, pmic: {"mediatek,observe-vgpu-only"}}
            removals = {pmic: {"mediatek,observe-vgpu-only"}}
            require("mediatek,observe-vgpu-only" not in tree[pmic], "Blocked migration must remove observer")
    for path, props in base.items():
        allowed = changes.get(path, set())
        require(set(tree[path]) - set(props) <= allowed | {"phandle", "linux,phandle"}, "Unexpected base property: " + path)
        require(set(props) - set(tree[path]) <= removals.get(path, set()) | {"phandle", "linux,phandle"},
                "Removed base property: " + path)
        for prop, value in props.items():
            if prop in allowed or prop in ("phandle", "linux,phandle"):
                continue
            require(reference_value(base, base_owners, prop, value) ==
                    reference_value(tree, owners, prop, tree[path][prop]), "Base property changed: " + path + "/" + prop)
    for path in added | ({spm, mm, pmic, iommu} if profile == "disabled" else {pmic}):
        require(tree[path].get("status") == b"disabled\0", "All candidate hardware must stay disabled: " + path)
    rail = regulators + "/vbuck1"
    for prop in ("cam-vcore-supply", "isp-vcore-supply"):
        if profile == "supplier":
            require(prop not in tree[spm], "Dormant supplier must not opt into native VMM")
        else:
            require(reference_value(tree, owners, prop, tree[spm].get(prop, b"")) == ((rail, ()),), "Real equal supply pair")
    if profile != "disabled":
        for path, props in tree.items():
            # Match the native guard's node-local availability rule for supplies.
            for prop, value in props.items():
                if prop.endswith("-supply") and props.get("status", b"okay\0") in (b"okay\0", b"ok\0"):
                    refs = reference_value(tree, owners, prop, value)
                    require((rail, ()) not in refs or (profile == "ownership-blocked" and path == spm and
                            prop in ("cam-vcore-supply", "isp-vcore-supply")), "Competing available VBUCK1 user")
            if path.startswith(spm + "/") and props.get("reg") in map(u32, (3, 10, 11, 12, 13, 14, 15, 16, 17, 18)):
                require(props.get("status") == b"disabled\0", "Camera/unsupported domain must stay disabled")
    for index in (1, 4):
        props = tree[f"{regulators}/vbuck{index}"]
        expected = {"regulator-name": strings(f"6_vbuck{index}"), "status": b"disabled\0"}
        for prop, value in data["power"]["rails"][str(index)].items():
            if prop != "always_on":
                expected[prop] = u32(value)
            elif value:
                expected["regulator-always-on"] = b""
        require({k: v for k, v in props.items() if k not in ("phandle", "linux,phandle")} == expected,
                "Exact disabled source rail policy")
    for name, path in (("CAM_VCORE", mm + "/power-domain@a"), ("CAM_MAIN", mm + "/power-domain@a/power-domain@d"),
                       ("ISP_VCORE", mm + "/power-domain@10")):
        props = tree[path]
        expected = {"reg": u32(data["power"]["domains"][name]), "#power-domain-cells": u32(0), "status": b"disabled\0"}
        if name == "CAM_VCORE":
            expected.update({"#address-cells": u32(1), "#size-cells": u32(0)})
        if name == "CAM_MAIN":
            expected.update({k: props[k] for k in ("clocks", "clock-names")})
            refs = tuple((paths[row["owner"]], (row["native_id"],)) for row in data["power"]["clocks"])
            require(reference_value(tree, owners, "clocks", props["clocks"]) == refs, "Nine real ordered CAM_MAIN clocks")
            require(props["clock-names"] == strings(*(row["name"] for row in data["power"]["clocks"])), "Ordered CAM_MAIN names")
        require({k: v for k, v in props.items() if k not in ("phandle", "linux,phandle")} == expected, "Exact native domain descriptor")
    for name, props in data["nodes"].items():
        label = {"camsys_main_clk": "cam_main", "camsys_mraw_clk": "cam_mraw", "cam_vcore_clk": "cam_vcore",
                 "camisp-l13-1": "camisp_l13", "camisp-l14-1": "camisp_l14"}.get(name, name)
        path = paths[label]
        domain = props.get("power-domains")
        if domain:
            domain_name = domain.split("MT6878_POWER_DOMAIN_")[1].split(">")[0]
            require(reference_value(tree, owners, "power-domains", tree[path]["power-domains"]) ==
                    ((spm, (data["power"]["domains"][domain_name],)),), "Real onecell camera resource dependency")
        else:
            require("power-domains" not in tree[path], "No invented gate-provider dependency")
        expected_keys = {"compatible", "status"}
        actual = tree[path]
        compat = props["compatible"].split(", ")[0].strip('"')
        if name == "camsys_main_clk":
            compat = "mediatek,mt6878-camsys"
        elif name in ("smi_larb13", "smi_larb14"):
            compat = "mediatek,mt6878-smi-larb"
        require(actual.get("compatible") == strings(compat), "Native camera compatible")
        for key in ("reg", "#clock-cells", "mediatek,common-id", "mediatek,larb-id", "clocks", "clock-names", "iommus"):
            if key not in props:
                continue
            expected_keys.add(key)
            if key in ("#clock-cells", "mediatek,common-id", "mediatek,larb-id"):
                require(actual.get(key) == u32(int(props[key].strip("<>"))), "Resource cell: " + key)
            elif key == "clock-names":
                require(actual.get(key) == strings(*re.findall(r'"([^"]+)"', props[key])), "Resource clock names")
            elif key == "clocks":
                refs = []
                aliases = {"camsys_main_clk": "cam_main", "camsys_mraw_clk": "cam_mraw", "cam_vcore_clk": "cam_vcore"}
                for owner, symbol in re.findall(r"<&(\w+) (CLK_\w+)>", props[key]):
                    refs.append((paths[aliases.get(owner, owner)], (data["native_clock_ids"][symbol],)))
                require(reference_value(tree, owners, key, actual[key]) == tuple(refs), "Real resource clock refs")
            elif key == "iommus":
                refs = tuple((iommu, (data["ports"][symbol],)) for symbol in re.findall(r"<&disp_iommu (\w+)>", props[key]))
                require(reference_value(tree, owners, key, actual[key]) == refs, "Logical CAMISP IOMMU ports")
        if domain:
            expected_keys.add("power-domains")
        if "mediatek,smi-supply" in props:
            parent = re.fullmatch(r"<&(\w+) 0>", props["mediatek,smi-supply"]).group(1)
            supplier = paths.get(parent)
            if parent == "smi_disp_common":
                supplier = unique(base, lambda p, v: v.get("reg") == u32(0x1e801000, 0x1000), "display common")
            expected_keys.add("mediatek,smi")
            require(reference_value(tree, owners, "mediatek,smi", actual["mediatek,smi"]) == ((supplier, ()),), "Physical SMI supplier")
            if name == "smi_cam_vcore_2x1_sub_comm0":
                expected_keys.add("mediatek,smi-supply")
                require(reference_value(tree, owners, "mediatek,smi-supply", actual["mediatek,smi-supply"]) ==
                        ((supplier, ()),), "Common31 reset supplier")
        require(set(actual) - {"phandle", "linux,phandle"} == expected_keys, "Exact resource property inventory")
    larb0 = unique(base, lambda p, v: v.get("mediatek,larb-id") == u32(0) and "reg" in v, "display larb0")
    expected_larbs = (tuple((path, ()) for path in (larb0, paths["smi_larb13"], paths["smi_larb14"]))
                      if profile == "disabled" else
                      reference_value(base, base_owners, "mediatek,larbs", base[iommu]["mediatek,larbs"]))
    require((larb0, ()) in expected_larbs, "Baseline IOMMU must contain display larb0")
    require(reference_value(tree, owners, "mediatek,larbs", tree[iommu]["mediatek,larbs"]) == expected_larbs,
            "IOMMU retains physical display larb")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--profile", choices=("disabled", "supplier", "ownership-blocked"), default="disabled")
    args = parser.parse_args()
    validate(read_tree(args.base), read_tree(args.fixture), json.loads((HERE / "evidence.json").read_text()), args.profile)
    print("PASS: compiled " + args.profile + " exact DT delta/resources; no runtime ownership claim")
