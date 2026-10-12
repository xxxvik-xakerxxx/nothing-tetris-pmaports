#!/usr/bin/env python3
"""Generate default-off CAMISP resources from frozen, git-show-traced B4.1 facts."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEVICE_COMMIT = "ee2be53cb75670b548948636a0db1d1ff112bf12"
CAMERA_COMMIT = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
KERNEL_COMMIT = "d84b264a54a37611f2f46bc19363cb9b41606205"
PACKAGE = "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/"
PARENT_INPUTS = tuple(PACKAGE + name for name in (
    "0018-pmdomain-mediatek-mt6878-audio.patch",
    "0058-arm64-dts-mediatek-add-opt-in-MT6878-display-power.patch",
    "0071-arm64-dts-mediatek-add-MT6878-display-DMA.patch",
    "0092-clk-mediatek-mt6878-camera-main.patch",
    "0108-regulator-mt6315-board-mode-mask.patch",
    "0110-regulator-mt6315-register-described-rails.patch",
    "0112-arm64-dts-tetris-disabled-gpu-supplies.patch",
    "0113-regulator-mt6315-reject-unowned-phase-mask.patch",
    "0114-regulator-mt6315-read-only-vgpu-observer.patch",
)) + ("patches/camera-camisp/native-integration/mt6878-native-vmm.inc",)
NATIVE_INPUTS = (
    "include/dt-bindings/clock/mediatek,mt6878-clock.h",
    "include/dt-bindings/spmi/spmi.h",
    "Documentation/devicetree/bindings/regulator/mt6315-regulator.yaml",
)
INPUTS = (
    ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE_COMMIT,
     "drivers/clk/mediatek/clk-mt6878-cam.c"),
    ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE_COMMIT,
     "include/dt-bindings/clock/mt6878-clk.h"),
    ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE_COMMIT,
     "arch/arm64/boot/dts/mediatek/mt6878.dts"),
    ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE_COMMIT,
     "include/dt-bindings/memory/mt6878-larb-port.h"),
    ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE_COMMIT,
     "include/dt-bindings/memory/mtk-memory-port.h"),
    ("android_kernel_modules_nothing_mt6878", CAMERA_COMMIT,
     "mtkcam/camsys/isp7sp/cam/mtk_cam-larb.c"),
    ("android_kernel_modules_nothing_mt6878", CAMERA_COMMIT,
     "mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c"),
    ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE_COMMIT,
     "drivers/soc/mediatek/mtk-scpsys-mt6878.c"),
    ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE_COMMIT,
     "include/dt-bindings/power/mt6878-power.h"),
)
NODE_NAMES = (
    "camsys_main_clk", "camsys_mraw_clk", "cam_vcore_clk",
    "smi_cam_vcore_2x1_sub_comm0", "smi_cam_4x1_sub_comm0", "smi_cam_4x1_sub_comm1",
    "smi_larb13", "smi_larb14", "camisp-l13-1", "camisp-l14-1",
)
ALIASES = {"camsys_main_clk": "cam_main", "camsys_mraw_clk": "cam_mraw",
           "cam_vcore_clk": "cam_vcore", "camisp-l13-1": "camisp_l13",
           "camisp-l14-1": "camisp_l14"}
PARENTS = {"top_cam_ck": "cam_sel", "top_camtm_ck": "camtm_sel"}
DESTINATIONS = {
    "clk-mt6878-camisp-resources.c": "drivers/clk/mediatek/clk-mt6878-camisp-resources.c",
    "mediatek,mt6878-camisp-clock.h": "include/dt-bindings/clock/mediatek,mt6878-camisp-clock.h",
    "mt6878-camisp-resources-disabled.dtsi": "arch/arm64/boot/dts/mediatek/mt6878-camisp-resources-disabled.dtsi",
    "mt6878-camisp-native-power-disabled.dtsi": "arch/arm64/boot/dts/mediatek/mt6878-camisp-native-power-disabled.dtsi",
    "mt6878-nothing-tetris-camisp-disabled.dts": "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-camisp-disabled.dts",
}
RESOURCE_FILES = tuple(DESTINATIONS)[:3]


def nested_body(source, marker):
    if source.count(marker) != 1:
        raise ValueError("absent/ambiguous nested source context: " + marker)
    start = source.index("{", source.index(marker)) + 1
    depth = 1
    for end in range(start, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return source[start:end]
    raise ValueError("unterminated source context: " + marker)


def power_trace(dts, soc, header, native_clock):
    controller = node_body(dts, "scpsys")
    clocks = re.findall(r"<&(\w+) (CLK_\w+)>", controller.split("clock-names")[0])
    names = re.findall(r'"([^"]+)"', one(r"clock-names = (.*?);", controller))
    if len(clocks) != len(names) or len(names) != len(set(names)):
        raise ValueError("ambiguous B4.1 power clock array")
    selected = []
    for name in ["cam"] + [f"cam_main-{i}" for i in range(8)]:
        owner, symbol = clocks[names.index(name)]
        native_owner = "topckgen" if owner == "topckgen_clk" else ALIASES[owner]
        native_id = int(one(r"^#define " + symbol + r"\s+(\d+)\s*$", native_clock)) if native_owner != "cam_mraw" else None
        selected.append({"name": name, "owner": native_owner, "symbol": symbol,
                         "native_id": native_id})
    domains = {name: int(one(r"^#define MT6878_POWER_DOMAIN_" + name + r"\s+(\d+)\s*$", header))
               for name in ("MM_INFRA", "CAM_VCORE", "CAM_MAIN", "ISP_VCORE")}
    edges = [["MM_INFRA", "CAM_VCORE"], ["CAM_VCORE", "CAM_MAIN"], ["MM_INFRA", "ISP_VCORE"]]
    for parent, child in edges:
        if f"{{MT6878_POWER_DOMAIN_{parent}, MT6878_POWER_DOMAIN_{child}}}" not in soc:
            raise ValueError("B4.1 CAM/ISP domain edge changed")
    pmic = nested_body(dts, "mt6319_6: mt6319@6")
    regulator = nested_body(pmic, "mt6319_6_regulator: mt6319-6-regulator")
    if "reg = <0x6 SPMI_USID>;" not in pmic or 'compatible = "mediatek,mt6315_6-regulator";' not in regulator:
        raise ValueError("B4.1 USID6 provider identity changed")
    rails = {}
    for index in (1, 2, 4):
        body = nested_body(regulator, f"mt6319_6_vbuck{index}: 6-vbuck{index}")
        if f'regulator-compatible = "vbuck{index}";' not in body:
            raise ValueError("B4.1 rail identity changed")
        rails[str(index)] = {prop: int(one(re.escape(prop) + r" = <(\d+)>;", body))
                             for prop in ("regulator-min-microvolt", "regulator-max-microvolt", "regulator-enable-ramp-delay")}
        rails[str(index)]["always_on"] = "regulator-always-on;" in body
    for prop in ("cam-vcore-supply", "isp-vcore-supply"):
        if one(re.escape(prop) + r" = <&(\w+)>;", controller) != "mt6319_6_vbuck1":
            raise ValueError("B4.1 paired rail changed")
    if dts.count("vmm-pmic-supply = <&mt6319_6_vbuck1>;") != 2:
        raise ValueError("B4.1 competing rail users changed")
    return {"domains": domains, "edges": edges, "clocks": selected, "usid": 6,
            "buck1_mode_mask": int(one(r"buck1-modeset-mask = <(0x[0-9a-f]+)>;", regulator), 16),
            "rails": rails, "other_vbuck1_users": ["vmmspm", "mmdvfs debug"],
            "activation": "disabled; firmware/MMUP ownership, voltage/rate policy and cold lifecycle unresolved"}


def one(pattern, text):
    matches = re.findall(pattern, text, re.S | re.M)
    if len(matches) != 1:
        raise ValueError("absent/ambiguous B4.1 context: " + pattern)
    return matches[0]


def node_body(source, name):
    # These resource nodes have no children. Refuse nesting rather than silently
    # misreading a changed vendor topology.
    start = one(r"^\s*(?:" + re.escape(name) + r":\s*[^\s{]+|" +
                re.escape(name) + r")\s*\{([^{}]*)\};", source)
    return start


def trace(upstream):
    sources, provenance = [], []
    for repo, commit, path in INPUTS:
        content = subprocess.check_output(["git", "-C", str(upstream / repo),
                                           "show", commit + ":" + path])
        sources.append(content.decode())
        provenance.append({"repository": repo, "commit": commit, "path": path,
                           "sha256": hashlib.sha256(content).hexdigest()})
    clock, header, dts, memory, memory_api, larb, sv, soc, power_header = sources
    native = {}
    with tarfile.open(upstream / ("linux-" + KERNEL_COMMIT + ".tar.gz")) as archive:
        for path in NATIVE_INPUTS:
            content = archive.extractfile("linux-" + KERNEL_COMMIT + "/" + path).read()
            native[path] = content.decode()
            provenance.append({"repository": "MT6878-mainline/linux", "commit": KERNEL_COMMIT,
                               "path": path, "sha256": hashlib.sha256(content).hexdigest()})
    banks = {}
    for bank, macro, prefix, count in (("mraw", "CAM_MR", "CLK_CAM_MR", 9),
                                       ("vcore", "CAM_VCORE", "CLK_CAM_VCORE", 2)):
        vendor = "cam_mr" if bank == "mraw" else "cam_vcore"
        registers = one(r"static const struct mtk_gate_regs " + vendor +
                        r"_cg_regs = \{(.*?)\};", clock)
        offsets = {key: int(one(r"\." + key + r"\s*=\s*(0x[0-9a-fA-F]+)", registers), 16)
                   for key in ("set_ofs", "clr_ofs", "sta_ofs")}
        operations = one(r"#define GATE_" + macro + r"\(.*?\.ops = &(\w+),", clock)
        body = one(r"static const struct mtk_gate " + vendor + r"_clks\[\] = \{(.*?)\};", clock)
        gates = []
        for symbol, name, parent, shift in re.findall(
                r"GATE_" + macro + r'\((\w+),\s*"([^"]+)",\s*"([^"]+)"/\* parent \*/,\s*(\d+)\)', body):
            gates.append({"symbol": symbol, "id": int(one(r"^#define " + symbol + r"\s+(\d+)\s*$", header)),
                          "name": name, "vendor_parent": parent, "parent": PARENTS[parent],
                          "shift": int(shift)})
        if len(gates) != count:
            raise ValueError("incomplete B4.1 gate bank")
        banks[bank] = {"registers": offsets, "operations": operations, "gates": gates,
                       "count_symbol": prefix + "_NR_CLK",
                       "count": int(one(r"^#define " + prefix + r"_NR_CLK\s+(\d+)\s*$", header))}
    nodes = {}
    for name in NODE_NAMES:
        body = node_body(dts, name)
        properties = {}
        for key, value in re.findall(r"([#\w,\-]+)\s*=\s*([^;]+);", body):
            properties[key] = " ".join(value.split())
        nodes[name] = properties
    ports = {}
    for name in ("camisp-l13-1", "camisp-l14-1"):
        for symbol in re.findall(r"<&disp_iommu (\w+)>", nodes[name]["iommus"]):
            larbid, port = one(r"^#define " + symbol +
                              r"\s+MTK_M4U_PORT_ID\(MM_TAB, NORMAL_DOM,\s*(\d+),\s*(\d+)\)", memory)
            ports[symbol] = (int(larbid) << 5) | int(port)
    for symbol in ("MM_TAB", "NORMAL_DOM"):
        if one(r"^#define " + symbol + r"\s+\((\d+)\)", memory) != "0":
            raise ValueError("nonzero vendor IOMMU table/domain requires a native mapping")
    if "((larb & 0x3f) << 5) | (port & 0x1f)" not in memory_api:
        raise ValueError("vendor IOMMU port encoding changed")
    for required in ('"mediatek,camisp-larb"', "DMA_BIT_MASK(34)", '"mediatek,larb-id"'):
        if required not in larb:
            raise ValueError("camera module larb contract changed")
    for required in ('"mediatek,larb-node-names"', '"iommus", "#iommu-cells"',
                     "DL_FLAG_PM_RUNTIME | DL_FLAG_STATELESS"):
        if required not in sv:
            raise ValueError("camera module CAMSV contract changed")
    power = power_trace(dts, soc, power_header, native[NATIVE_INPUTS[0]])
    for row in power["clocks"]:
        if row["owner"] == "cam_mraw":
            row["native_id"] = int(one(r"^#define " + row["symbol"] + r"\s+(\d+)\s*$", header))
    symbols = set(re.findall(r"CLK_\w+", " ".join(node.get("clocks", "") for node in nodes.values())))
    symbols.update(row["symbol"] for row in power["clocks"])
    clock_ids = {}
    for symbol in sorted(symbols):
        source = header if symbol.startswith(("CLK_CAM_MR_", "CLK_CAM_VCORE_")) else native[NATIVE_INPUTS[0]]
        clock_ids[symbol] = int(one(r"^#define " + symbol + r"\s+(\d+)\s*$", source))
    return {"release": "Nothing OS B4.1", "provenance": provenance, "banks": banks,
            "nodes": nodes, "ports": ports,
            "logical_dma_bits": 34,
            "power": power,
            "native_clock_ids": clock_ids,
            "parent_input_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                    for path in PARENT_INPUTS},
            "power_owner": "Native provider graph described disabled; physical VMM ownership/policy unproven"}


def provider(data):
    code = """// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (c) 2023 MediaTek Inc.
 * B4.1 gate data adapted to the native Linux MediaTek clock API.
 * Clock gates only: this driver does not implement CAM/VMM power ownership.
 */
#include <dt-bindings/clock/mediatek,mt6878-camisp-clock.h>
#include <linux/clk-provider.h>
#include <linux/module.h>
#include <linux/platform_device.h>

#include "clk-gate.h"
#include "clk-mtk.h"

"""
    for bank, values in data["banks"].items():
        code += f"static const struct mtk_gate_regs cam_{bank}_regs = {{\n"
        for key, value in values["registers"].items():
            code += f"\t.{key} = 0x{value:x},\n"
        code += "};\n\n"
        code += f"#define GATE_CAM_{bank.upper()}(_id, _name, _parent, _shift) \\\n"
        code += f"\tGATE_MTK(_id, _name, _parent, &cam_{bank}_regs, _shift, \\\n"
        code += f"\t\t &{values['operations']})\n\n"
        code += f"static const struct mtk_gate cam_{bank}_clks[] = {{\n"
        for gate in values["gates"]:
            code += (f"\tGATE_CAM_{bank.upper()}({gate['symbol']}, \"{gate['name']}\",\n"
                     f"\t\t\t \"{gate['parent']}\", {gate['shift']}),\n")
        code += "};\n\n"
        code += (f"static const struct mtk_clk_desc cam_{bank}_desc = {{\n"
                 f"\t.clks = cam_{bank}_clks,\n\t.num_clks = ARRAY_SIZE(cam_{bank}_clks),\n}};\n\n")
    code += """static const struct of_device_id camisp_resource_match[] = {
\t{ .compatible = "mediatek,mt6878-camsys_mraw", .data = &cam_mraw_desc },
\t{ .compatible = "mediatek,mt6878-cam_vcore", .data = &cam_vcore_desc },
\t{ }
};
MODULE_DEVICE_TABLE(of, camisp_resource_match);

static struct platform_driver camisp_resource_driver = {
\t.probe = mtk_clk_simple_probe,
\t.remove = mtk_clk_simple_remove,
\t.driver = {
\t\t.name = "clk-mt6878-camisp-resources",
\t\t.of_match_table = camisp_resource_match,
\t},
};
module_platform_driver(camisp_resource_driver);
MODULE_DESCRIPTION("MediaTek MT6878 MRAW and CAM_VCORE gates");
MODULE_LICENSE("GPL");
"""
    return code


def binding(data):
    code = """/* SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause) */
/* B4.1 IDs are local to each clock bank, not the CAM_MAIN bank. */
#ifndef _DT_BINDINGS_CLK_MT6878_CAMISP_H
#define _DT_BINDINGS_CLK_MT6878_CAMISP_H

"""
    for bank in data["banks"].values():
        for gate in bank["gates"]:
            code += f"#define {gate['symbol']}\t{gate['id']}\n"
        code += f"#define {bank['count_symbol']}\t{bank['count']}\n\n"
    return code + "#endif\n"


def fragment(data):
    code = """// SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
/* Review fixture only; no shipping board includes this file.
 * Native CAM/ISP graph is supplied by the paired disabled diagnostic fixture.
 * Physical VMM ownership/policy remain unproven. Every device stays disabled.
 */
#include <dt-bindings/clock/mediatek,mt6878-clock.h>
#include <dt-bindings/clock/mediatek,mt6878-camisp-clock.h>
#include <dt-bindings/power/mediatek,mt6878-power.h>

&soc {
"""
    for name, props in data["nodes"].items():
        label = ALIASES.get(name, name)
        logical = name.startswith("camisp-")
        values = {}
        if "reg" in props:
            cells = props["reg"].strip("<>").split()
            if len(cells) != 4 or cells[0] != "0" or cells[2] != "0":
                raise ValueError("unexpected B4.1 register cells")
            address, size = int(cells[1], 0), int(cells[3], 0)
            node = ("clock-controller" if "#clock-cells" in props else "smi") + f"@{address:x}"
            values["reg"] = f"<0x{address:x} 0x{size:x}>"
        else:
            node = name
        compatible = props["compatible"].split(", ")[0]
        if name == "camsys_main_clk":
            compatible = '"mediatek,mt6878-camsys"'
        elif name in ("smi_larb13", "smi_larb14"):
            compatible = '"mediatek,mt6878-smi-larb"'
        values = {"compatible": compatible, **values}
        for key in ("#clock-cells", "mediatek,common-id", "mediatek,larb-id", "clocks", "clock-names", "iommus"):
            if key in props:
                value = props[key]
                for old, new in ALIASES.items():
                    value = value.replace("&" + old + " ", "&" + new + " ")
                if key == "iommus":
                    for symbol, port in data["ports"].items():
                        value = value.replace(symbol, str(port))
                values[key] = value
        if "mediatek,smi-supply" in props:
            supplier = one(r"<&(\w+) 0>", props["mediatek,smi-supply"])
            values["mediatek,smi"] = f"<&{supplier}>"
            # The existing common31 reset owner and IOMMU walker use both APIs.
            if name == "smi_cam_vcore_2x1_sub_comm0":
                values["mediatek,smi-supply"] = f"<&{supplier}>"
        if logical and set(values) != {"compatible", "mediatek,larb-id", "iommus"}:
            raise ValueError("logical CAMISP must never own physical resources")
        if "power-domains" in props:
            domain = one(r"<&scpsys MT6878_POWER_DOMAIN_(\w+)>", props["power-domains"])
            if domain not in ("CAM_MAIN", "CAM_VCORE"):
                raise ValueError("unsupported native camera domain")
            values["power-domains"] = f"<&spm MT6878_POWER_DOMAIN_{domain}>"
        values["status"] = '"disabled"'
        code += f"\t{label}: {node} {{\n"
        for key, value in values.items():
            if key in ("clocks", "iommus"):
                value = value.replace(">, <", ">,\n\t\t\t <")
            code += f"\t\t{key} = {value};\n"
        code += "\t};\n\n"
    code += """};

/* Reference membership retains the display larb; neither IOMMU nor camera is
 * activated. Do not include this fixture in a shipping board description.
 */
&disp_iommu {
\tmediatek,larbs = <&smi_larb0>, <&smi_larb13>, <&smi_larb14>;
\tstatus = "disabled";
};
"""
    return code


def power_fragment(data):
    code = """// SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
/* Include ONLY in the isolated diagnostic board, after native-display and
 * GPU-supplies. Extend the existing controller/USID6, never duplicate them.
 * Source bounds are not an operating point. No rail/clock request is enabled.
 */
#include <dt-bindings/spmi/spmi.h>
#include <dt-bindings/power/mediatek,mt6878-power.h>

&mt6319_gpu {
\tstatus = "disabled";
\tregulators {
"""
    for index in (1, 4):
        rail = data["power"]["rails"][str(index)]
        code += f"\t\tmt6319_6_vbuck{index}: vbuck{index} {{\n"
        code += f'\t\t\tregulator-name = "6_vbuck{index}";\n'
        for prop, value in rail.items():
            if prop != "always_on":
                code += f"\t\t\t{prop} = <{value}>;\n"
        if rail["always_on"]:
            code += "\t\t\tregulator-always-on;\n"
        code += '\t\t\tstatus = "disabled";\n\t\t};\n'
    code += """\t};
};

/* Supply pair is inert because THIS diagnostic board disables the real SPM.
 * Never copy these properties into the active shipping controller.
 */
&spm {
\tcam-vcore-supply = <&mt6319_6_vbuck1>;
\tisp-vcore-supply = <&mt6319_6_vbuck1>;
\tstatus = "disabled";
};

&mm_infra {
\tstatus = "disabled";
"""
    for name in ("CAM_VCORE", "ISP_VCORE"):
        label = "cam_vcore_pd" if name == "CAM_VCORE" else "isp_vcore_pd"
        code += f"\t{label}: power-domain@{data['power']['domains'][name]:x} {{\n"
        code += f"\t\treg = <MT6878_POWER_DOMAIN_{name}>;\n"
        code += '\t\t#power-domain-cells = <0>;\n\t\tstatus = "disabled";\n'
        if name == "CAM_VCORE":
            code += "\t\t#address-cells = <1>;\n\t\t#size-cells = <0>;\n"
            code += f"\t\tcam_main_pd: power-domain@{data['power']['domains']['CAM_MAIN']:x} {{\n"
            code += "\t\t\treg = <MT6878_POWER_DOMAIN_CAM_MAIN>;\n\t\t\t#power-domain-cells = <0>;\n"
            refs = [f"<&{row['owner']} {row['symbol']}>" for row in data["power"]["clocks"]]
            names = ['"' + row["name"] + '"' for row in data["power"]["clocks"]]
            code += "\t\t\tclocks = " + ",\n\t\t\t\t ".join(refs) + ";\n"
            code += "\t\t\tclock-names = " + ", ".join(names) + ";\n"
            code += '\t\t\tstatus = "disabled";\n\t\t};\n'
        code += "\t};\n"
    return code + "};\n"


def board_fixture():
    return """// SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
/* Compile-only diagnostic board: NOT a boot/install/activation artifact.
 * Existing SPM/MM_INFRA are disabled, so this would break native display PM.
 */
#include "mt6878-nothing-tetris-native.dts"
#include "mt6878-camisp-resources-disabled.dtsi"
#include "mt6878-camisp-native-power-disabled.dtsi"
"""


def outputs(data):
    files = {"clk-mt6878-camisp-resources.c": provider(data),
             "mediatek,mt6878-camisp-clock.h": binding(data),
             "mt6878-camisp-resources-disabled.dtsi": fragment(data),
             "mt6878-camisp-native-power-disabled.dtsi": power_fragment(data),
             "mt6878-nothing-tetris-camisp-disabled.dts": board_fixture()}
    patches = {}
    for output, names in (("clock-providers.patch", tuple(files)[:2]),
                          ("disabled-description.patch", tuple(files)[2:])):
        code = ""
        for name in names:
            destination = DESTINATIONS[name]
            code += f"diff --git a/{destination} b/{destination}\nnew file mode 100644\n"
            code += "".join(difflib.unified_diff([], files[name].splitlines(True),
                                              fromfile="/dev/null", tofile="b/" + destination))
        patches[output] = code
    return {**files, **patches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT.parent)
    parser.add_argument("--refresh-evidence", action="store_true")
    parser.add_argument("--verify-vendor", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.refresh_evidence and args.check:
        parser.error("--check must not rewrite evidence")
    if args.refresh_evidence:
        (HERE / "evidence.json").write_text(json.dumps(trace(args.upstream), indent=2) + "\n")
    data = json.loads((HERE / "evidence.json").read_text())
    if args.verify_vendor and data != trace(args.upstream):
        raise ValueError("frozen resource evidence differs from pinned git objects")
    for name, content in outputs(data).items():
        if args.check:
            if (HERE / name).read_text() != content:
                raise ValueError("generated resource drift: " + name)
        else:
            (HERE / name).write_text(content)
    print("CAMISP resource generation/evidence PASS; no compilation or activation")


if __name__ == "__main__":
    main()
