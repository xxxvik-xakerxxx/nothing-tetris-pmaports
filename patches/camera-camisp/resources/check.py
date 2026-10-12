#!/usr/bin/env python3
"""Guard real gate semantics, disabled topology and isolated CI closure."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("camisp_resources_generate", HERE / "generate.py")
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)
TRACE_SHA256 = "30d938c9ae942ceac24bc8f1e0c8c43b0a8d3c066b51cbe1bc1ba06bd0b96453"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def evidence_contract(data):
    require([(row["repository"], row["commit"], row["path"]) for row in data["provenance"]]
            == list(generate.INPUTS), "pinned source provenance")
    require(all(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in data["provenance"]),
            "source identity")
    for bank, count, regs, ops in (
            ("mraw", 9, {"set_ofs": 4, "clr_ofs": 8, "sta_ofs": 0}, "mtk_clk_gate_ops_setclr"),
            ("vcore", 2, {"set_ofs": 44, "clr_ofs": 44, "sta_ofs": 44}, "mtk_clk_gate_ops_no_setclr_inv")):
        values = data["banks"][bank]
        require(values["registers"] == regs and values["operations"] == ops, "B4.1 gate semantics")
        require(values["count"] == count and len(values["gates"]) == count, "B4.1 gate count")
        require([g["id"] for g in values["gates"]] == list(range(count)), "bank-local ABI")
        require([g["shift"] for g in values["gates"]] == list(range(count)), "B4.1 gate shifts")
        for gate in values["gates"]:
            parent = "camtm_sel" if gate["symbol"] == "CLK_CAM_MR_CAMTG" else "cam_sel"
            require(gate["parent"] == parent, "native clock parent")
            require(generate.PARENTS[gate["vendor_parent"]] == parent, "vendor clock parent")
    require(sorted(data["ports"].values()) == [416, 417, 448, 449], "CAMSV IOMMU ports")
    require(data["logical_dma_bits"] == 34, "camera DMA width")
    for name, domain in (("smi_cam_vcore_2x1_sub_comm0", "CAM_VCORE"),
                         ("smi_cam_4x1_sub_comm0", "CAM_MAIN"),
                         ("smi_cam_4x1_sub_comm1", "CAM_MAIN"),
                         ("smi_larb13", "CAM_MAIN"), ("smi_larb14", "CAM_MAIN")):
        require(data["nodes"][name]["power-domains"] == f"<&scpsys MT6878_POWER_DOMAIN_{domain}>",
                "unresolved vendor power dependency")
    require(set(data["nodes"]) == set(generate.NODE_NAMES), "complete resource topology")
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(digest == TRACE_SHA256, "frozen B4.1 trace identity")


def source_contract(code, header, fixture, data):
    # Byte regeneration supplements semantic checks: neither stale diffs nor a
    # different register operation may be blessed by simply changing a manifest.
    evidence_contract(data)
    for bank in ("mraw", "vcore"):
        regs = generate.one(r"static const struct mtk_gate_regs cam_" + bank + r"_regs = \{(.*?)\};", code)
        actual = {key: int(generate.one(r"\." + key + r"\s*=\s*(0x[0-9a-f]+)", regs), 16)
                  for key in ("set_ofs", "clr_ofs", "sta_ofs")}
        require(actual == data["banks"][bank]["registers"], "gate register offsets")
        operations = generate.one(r"#define GATE_CAM_" + bank.upper() +
                                  r"\(.*?&(mtk_clk_gate_ops_\w+)\)", code)
        require(operations == data["banks"][bank]["operations"], "gate polarity and operation")
    require(".probe = mtk_clk_simple_probe" in code and ".remove = mtk_clk_simple_remove" in code,
            "native provider registration/removal")
    for forbidden in ("writel(", "readl(", "ioremap", "pm_runtime", "genpd", "arm_smccc", "CLK_IS_CRITICAL"):
        require(forbidden not in code, "gate-only provider: " + forbidden)
    clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", fixture, flags=re.S)
    require("power-domains" not in clean and "resets" not in clean, "no invented power/reset owner")
    require('"okay"' not in clean and '"ok"' not in clean, "no resource activation")
    for name in generate.NODE_NAMES:
        label = generate.ALIASES.get(name, name)
        body = generate.node_body(clean, label)
        require(body.count('status = "disabled";') == 1, "default-disabled resource: " + label)
        if name.startswith("camisp-"):
            require(set(re.findall(r"([#\w,\-]+)\s*=", body)) ==
                    {"compatible", "mediatek,larb-id", "iommus", "status"},
                    "logical port cannot own physical resources")
    for name, parent in (("smi_larb13", "smi_cam_4x1_sub_comm0"),
                         ("smi_larb14", "smi_cam_4x1_sub_comm1")):
        body = generate.node_body(clean, name)
        require('compatible = "mediatek,mt6878-smi-larb";' in body, "physical larb compatible")
        require(f"mediatek,smi = <&{parent}>;" in body, "physical PM supplier")
    common = generate.node_body(clean, "smi_cam_vcore_2x1_sub_comm0")
    require("mediatek,smi = <&smi_disp_common>;" in common and
            "mediatek,smi-supply = <&smi_disp_common>;" in common, "common31 root links")
    for name in ("smi_cam_4x1_sub_comm0", "smi_cam_4x1_sub_comm1"):
        body = generate.node_body(clean, name)
        require(len(re.findall(r"<&[\w]+ CLK_\w+>", body)) == 7, "seven subcommon clocks")
        require("mediatek,smi = <&smi_cam_vcore_2x1_sub_comm0>;" in body, "subcommon PM supplier")
    iommu = generate.one(r"&disp_iommu\s*\{([^{}]*)\};", clean)
    require('status = "disabled";' in iommu, "IOMMU remains disabled")
    require("mediatek,larbs = <&smi_larb0>, <&smi_larb13>, <&smi_larb14>;" in iommu,
            "physical IOMMU membership retains display")
    expected = generate.outputs(data)
    for name, contents in (("clk-mt6878-camisp-resources.c", code),
                           ("mediatek,mt6878-camisp-clock.h", header),
                           ("mt6878-camisp-resources-disabled.dtsi", fixture)):
        require(contents == expected[name], "generated source drift: " + name)


def staging_contract(plan):
    directory = "drivers/clk/mediatek/tetris-camisp-resource-smoke"
    prefix = "patches/camera-camisp/resources/"
    expected = {prefix + name: (directory + "/" + name if name.endswith(".c") else destination)
                for name, destination in generate.DESTINATIONS.items()}
    require(plan["sources"] == expected, "isolated resource source closure")
    require(plan["research_objects"] == [directory + "/clk-mt6878-camisp-resources.o"],
            "isolated resource object")
    require(plan["include_directory"] == "drivers/clk/mediatek", "native clock header directory")
    require(plan["required_enabled"] == ["COMMON_CLK", "OF", "PM"] and
            plan["required_reachable"] == ["COMMON_CLK_MEDIATEK", "COMMON_CLK_MT6878"],
            "native clock dependencies")
    require(plan["config_variants"] == [{"KUNIT": "y"}, {"KUNIT": "n"}] and
            plan["runtime_activation"] == "disabled", "disabled dual-config scope")


def check(root=ROOT, staged=None, kernel=None):
    here = root / "patches/camera-camisp/resources"
    data = json.loads((here / "evidence.json").read_text())
    source_contract(*( (here / name).read_text() for name in generate.DESTINATIONS), data)
    plan = json.loads((here / "STAGING.json").read_text())
    staging_contract(plan)
    outputs = generate.outputs(data)
    for name in ("clock-providers.patch", "disabled-description.patch"):
        require((here / name).read_text() == outputs[name], "generated patch drift: " + name)
    # Apply additive review patches in a fresh tree; never modify a kernel tree.
    with tempfile.TemporaryDirectory(prefix="camisp-resource-apply-") as name:
        tree = Path(name)
        for patch in ("clock-providers.patch", "disabled-description.patch"):
            subprocess.run(["git", "apply", str(here / patch)], cwd=tree,
                           check=True, capture_output=True)
        for name, destination in generate.DESTINATIONS.items():
            require((tree / destination).read_bytes() == (here / name).read_bytes(), "patch payload: " + name)
        require(set(str(path.relative_to(tree)) for path in tree.rglob("*") if path.is_file()) ==
                set(generate.DESTINATIONS.values()), "no activation/parent build hunks")
    if staged:
        for source, destination in plan["sources"].items():
            require((staged / destination).read_bytes() == (root / source).read_bytes(), "staged byte drift")
    if kernel:
        clocks = kernel / "drivers/clk/mediatek"
        top = (clocks / "clk-mt6878-topckgen.c").read_text()
        for parent in generate.PARENTS.values():
            require(re.search(r'MUX(?:_GATE)?_CLR_SET_UPD\(CLK_TOP_\w+[^,]*,\s*"' + parent + '"', top),
                    "native mux parent missing: " + parent)
        for operation in ("mtk_clk_gate_ops_setclr", "mtk_clk_gate_ops_no_setclr_inv"):
            require(operation in (clocks / "clk-gate.h").read_text(), "native gate API")
    print("CAMISP resources/source/patch/isolation PASS; no C/dtc compilation or hardware access")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-tree", type=Path)
    parser.add_argument("--kernel-tree", type=Path)
    args = parser.parse_args()
    check(staged=args.staged_tree, kernel=args.kernel_tree)


if __name__ == "__main__":
    main()
