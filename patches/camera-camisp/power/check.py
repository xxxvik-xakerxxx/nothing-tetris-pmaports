#!/usr/bin/env python3
"""Static negative gates only; does not execute or emulate C or hardware."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
trace_spec = importlib.util.spec_from_file_location("camera_power_trace", HERE / "trace.py")
source_trace = importlib.util.module_from_spec(trace_spec)
trace_spec.loader.exec_module(source_trace)
DEST = "drivers/pmdomain/mediatek/tetris-cam-power-smoke/"
PAYLOAD = ("mt6878-cam-power.c", "mt6878-cam-power.h")
EVIDENCE_SHA256 = "e2c40343be5981710459f3c55b5e996663fbc95d841be66af2b7ffcf869504c7"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def clean(text):
    return re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S))


def evidence_contract(data):
    expected = {
        "CAM_VCORE": (10, 0xe5c, [], [], [(0xc14, 0xc18, 0xc1c, [31]),
                                        (0xc24, 0xc28, 0xc2c, [9, 10])]),
        "CAM_MAIN": (13, 0xe48, [8], [12], [(0xc14, 0xc18, 0xc1c, [29]),
                                          (0xc14, 0xc18, 0xc1c, [30])]),
    }
    require(set(data["domains"]) == set(expected), "leaf domain scope")
    for name, (id_, control, pdn, ack, steps) in expected.items():
        domain = data["domains"][name]
        require((domain["id"], domain["control"], domain["sram_pdn_bits"],
                 domain["sram_ack_bits"]) == (id_, control, pdn, ack), "B4.1 domain data")
        require([(s["set"], s["clear"], s["status"], s["bits"])
                 for s in domain["protection"]] == steps, "ordered bus protection")
        require(all(s["ignore_clear_ack"] and s["enable"] == s["set"] - 4
                    for s in domain["protection"]), "B4.1 clear-ack policy")
    require(data["parent_edges"] == [["CAM_VCORE", "CAM_MAIN"], ["MM_INFRA", "CAM_VCORE"]],
            "real supplier chain")
    require(data["vmm_isolation"] == dict(iso_con_status=0xf28, iso_con_set=0xf2c,
            iso_con_clr=0xf30, ext_iso_bit=24, iso_din_bit=25, latch_en_bit=26), "MT6878 VMM variant")
    require(data["vmm_supply"] == "mt6319_6_vbuck1", "shared VMM PMIC supplier")
    require(data["generic_vmm_genpd_notifier_in_soc_dts"] is False, "no foreign notifier evidence")
    require(len(data["cam_main_subsys_clocks"]) == 8, "all CAM_MAIN protection clocks")
    require(data["runtime_activation"] == "disabled", "evidence activation")
    identities = [(source_trace.VENDOR_REPO, source_trace.VENDOR, p)
                  for p in source_trace.VENDOR_PATHS]
    identities += [("MT6878-mainline/linux", source_trace.KERNEL, p)
                   for p in source_trace.KERNEL_PATHS]
    identities += [("nothing-tetris-pmaports", "packaged-input", p) for p in source_trace.PATCHES]
    require([(p["repository"], p["commit"], p["path"]) for p in data["provenance"]] == identities,
            "pinned supplier provenance")
    require(all(re.fullmatch(r"[0-9a-f]{64}", p["sha256"]) for p in data["provenance"]),
            "source hashes")
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(digest == EVIDENCE_SHA256, "frozen pinned trace identity")


def source_contract(code, header, data):
    evidence_contract(data)
    c = clean(code)
    for token in ("#defineMTK_SCPD_", "KEEP_DEFAULT_OFF", "ALWAYS_ON", "BYPASS",
                  "pm_genpd_", "genpd->", "platform_driver", "module_init", "arm_smccc",
                  "notifier", "semaphore", "ioremap", "panic(", "BUG_ON(", "while(", "for(",
                  "power_ready", "secure_ready", "powered", "GENPD_FLAG"):
        require(token not in c, "no activation, invented flags or foreign flow: " + token)
    require('"mtk-pm-domains.h"' in header, "actual Linux descriptor API")
    require(set(re.findall(r"\[MT6878_POWER_DOMAIN_(\w+)\]", code)) == {"NR", "CAM_MAIN", "CAM_VCORE"},
            "only camera leaf descriptors")
    for name, domain in data["domains"].items():
        body = source_trace.body_after(code, "[MT6878_POWER_DOMAIN_" + name + "]")
        compact = clean(body)
        for field in ("ctl_offs", "pwr_sta_offs", "pwr_sta2nd_offs"):
            value = source_trace.one(r"\." + field + r"\s*=\s*(0x\w+)", body)
            require(int(value, 16) == domain["control"], "control-local status, not global F50/F54")
        require(".sta_mask=GENMASK(31,30)" in compact, "both control ACK bits")
        caps = "MTK_SCPD_STATUS_IN_CTL" + ("|MTK_SCPD_DOMAIN_SUPPLY" if name == "CAM_VCORE" else "")
        require(source_trace.one(r"\.caps=(.*?),", compact) == caps, "native descriptor caps/supply")
        actual = re.findall(r"BUS_PROT_WR_IGN\(INFRA,\s*(.*?),\s*(0x\w+),\s*(0x\w+),\s*(0x\w+)\)", body)
        actual = [(int(s, 16), int(cl, 16), int(st, 16),
                   [int(b) for b in re.findall(r"BIT\((\d+)\)", mask)]) for mask, s, cl, st in actual]
        require(actual == [(s["set"], s["clear"], s["status"], s["bits"])
                           for s in domain["protection"]], "descriptor bus protection order")
        require((".sram_pdn_bits=BIT(8),.sram_pdn_ack_bits=BIT(12)," in compact) ==
                bool(domain["sram_pdn_bits"]), "CAM_MAIN SRAM only")
    defines = {
        "CAM_PWR_RST_B": "BIT(0)", "CAM_PWR_ISO": "BIT(1)", "CAM_PWR_ON": "BIT(2)",
        "CAM_PWR_ON_2ND": "BIT(3)", "CAM_PWR_CLK_DIS": "BIT(4)",
        "CAM_PWR_ACK": "BIT(30)", "CAM_PWR_ACK_2ND": "BIT(31)",
        "CAM_POLL_DELAY_US": "10", "CAM_POLL_TIMEOUT_US": "1000000",
        "VMM_ISO_STA": "0x0f28", "VMM_ISO_SET": "0x0f2c", "VMM_ISO_CLR": "0x0f30",
        "VMM_EXT_BUCK_ISO": "BIT(24)", "VMM_SRAM_ISO_DIN": "BIT(25)",
        "VMM_SRAM_LATCH_ENB": "BIT(26)", "VMM_ISO_MASK": "GENMASK(26,24)",
    }
    for symbol, value in defines.items():
        require(clean(source_trace.one(r"^#define " + symbol + r"\s+([^\n]+)", code)) == value,
                "hardware bit/offset/timeout: " + symbol)
    ack = clean(source_trace.body_after(code, "static int mt6878_cam_ack("))
    require("returnregmap_read_poll_timeout(spm,offset,val,(val&mask)==(on?mask:0),"
            "CAM_POLL_DELAY_US,CAM_POLL_TIMEOUT_US);" in ack, "bounded, checked independent ACK")
    # Every fallible assignment must return its first errno before the next operation.
    operations = list(re.finditer(r"ret=(?:regmap_\w+|mt6878_cam_switch)\([^;]+\);", c))
    require(len(operations) == 13, "local transaction operation count")
    for match in operations:
        require(c[match.end():].startswith("if(ret)returnret;"), "first error must stop transaction")
    require(c.count("return0;") == 1, "only checked VMM readback may return zero directly")
    switch = clean(source_trace.body_after(code, "static int mt6878_cam_switch("))
    require("on?control:0" in switch and "returnmt6878_cam_ack(spm,offset,ack,on);" in switch,
            "checked switch cannot swallow ACK failure")
    ctl = clean(source_trace.body_after(code, "int mt6878_cam_ctl_set("))
    require("if(!spm)return-EINVAL;" in ctl and
            "if(domain!=MT6878_POWER_DOMAIN_CAM_MAIN&&domain!=MT6878_POWER_DOMAIN_CAM_VCORE)"
            "return-EINVAL;offset=mt6878_cam_domain_data[domain].ctl_offs;" in ctl,
            "invalid domain rejected before sparse-table indexing")
    calls = re.findall(r"(?:mt6878_cam_switch|regmap_(?:clear|set)_bits|udelay)\([^;]+\)", ctl)
    require(calls == [
        "mt6878_cam_switch(spm,offset,CAM_PWR_ON,CAM_PWR_ACK,true)", "udelay(50)",
        "mt6878_cam_switch(spm,offset,CAM_PWR_ON_2ND,CAM_PWR_ACK_2ND,true)",
        "regmap_clear_bits(spm,offset,CAM_PWR_CLK_DIS)", "regmap_clear_bits(spm,offset,CAM_PWR_ISO)",
        "regmap_set_bits(spm,offset,CAM_PWR_RST_B)", "regmap_set_bits(spm,offset,CAM_PWR_ISO)",
        "regmap_clear_bits(spm,offset,CAM_PWR_RST_B)", "regmap_set_bits(spm,offset,CAM_PWR_CLK_DIS)",
        "mt6878_cam_switch(spm,offset,CAM_PWR_ON,CAM_PWR_ACK,false)",
        "mt6878_cam_switch(spm,offset,CAM_PWR_ON_2ND,CAM_PWR_ACK_2ND,false)"], "B4.1 sequential ACK order")
    require(ctl.endswith("returnmt6878_cam_switch(spm,offset,CAM_PWR_ON_2ND,CAM_PWR_ACK_2ND,false);"),
            "off must confirm second ACK is zero")
    vmm = clean(source_trace.body_after(code, "int mt6878_vmm_iso_set("))
    require("offset=isolate?VMM_ISO_SET:VMM_ISO_CLR;" in vmm and "if(!spm)return-EINVAL;" in vmm,
            "VMM valid map and W1S/W1C aliases")
    require(re.findall(r"regmap_write\(([^;]+)\)", vmm) == [
        "spm,offset,isolate?VMM_SRAM_LATCH_ENB:VMM_EXT_BUCK_ISO", "spm,offset,VMM_SRAM_ISO_DIN",
        "spm,offset,isolate?VMM_EXT_BUCK_ISO:VMM_SRAM_LATCH_ENB"], "VMM reverse isolation order")
    require("ret=regmap_read(spm,VMM_ISO_STA,&status);if(ret)returnret;"
            "if((status&VMM_ISO_MASK)!=(isolate?VMM_ISO_MASK:0))return-EIO;return0;" in vmm,
            "readback error/mismatch cannot report successful isolation")


def staging_contract(plan):
    require(set(plan) == {"scope", "kernel_commit", "vendor_commit", "sources", "research_objects",
                         "include_directory", "required_enabled", "required_reachable",
                         "config_variants", "runtime_activation", "unresolved"}, "staging schema")
    require(plan["sources"] == {"patches/camera-camisp/power/" + n: DEST + n for n in PAYLOAD},
            "isolated staging closure")
    require(plan["research_objects"] == [DEST + "mt6878-cam-power.o"] and
            plan["include_directory"] == "drivers/pmdomain/mediatek", "native isolated object")
    require(plan["kernel_commit"] == source_trace.KERNEL and plan["vendor_commit"] == source_trace.VENDOR,
            "staging source pins")
    require(plan["runtime_activation"] == "disabled" and
            plan["config_variants"] == [{"KUNIT": "y"}, {"KUNIT": "n"}], "no runtime activation")
    require(plan["required_enabled"] == ["OF", "PM", "REGMAP"] and
            plan["required_reachable"] == ["MTK_SCPSYS_PM_DOMAINS"], "native config dependencies")


def patch_text():
    return "".join("".join(difflib.unified_diff([], (HERE / name).read_text().splitlines(True),
                     fromfile="/dev/null", tofile="b/" + DEST + name)) for name in PAYLOAD)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-sources", action="store_true")
    parser.add_argument("--write-patch", action="store_true")
    args = parser.parse_args()
    data = json.loads((HERE / "evidence.json").read_text())
    source_contract(*((HERE / n).read_text() for n in PAYLOAD), data)
    staging_contract(json.loads((HERE / "STAGING.json").read_text()))
    if args.verify_sources:
        require(source_trace.trace(source_trace.ROOT.parent) == data, "source/provenance drift")
    patch = HERE / "leaf-transactions.patch"
    if args.write_patch:
        patch.write_text(patch_text())
    require(patch.read_text() == patch_text(), "additive patch payload drift")
    with tempfile.TemporaryDirectory(dir=HERE, prefix=".apply-") as directory:
        tree = Path(directory)
        subprocess.run(["git", "apply", str(patch)], cwd=tree, check=True, capture_output=True)
        require({str(p.relative_to(tree)) for p in tree.rglob("*") if p.is_file()} ==
                {DEST + n for n in PAYLOAD}, "no supplier or board activation hunks")
        for name in PAYLOAD:
            require((tree / DEST / name).read_bytes() == (HERE / name).read_bytes(), "applied bytes")
    print("Camera power static source, staging and additive patch checks passed")


if __name__ == "__main__":
    main()
