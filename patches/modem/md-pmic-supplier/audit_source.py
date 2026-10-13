#!/usr/bin/env python3
"""Pinned Nothing MT6363 descriptors, control semantics and unsupported DA scope."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import stage


def function(text, name):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    match = re.search(r"\b" + re.escape(name) + r"\([^;{}]*\)\s*\{", text)
    if not match:
        raise ValueError("missing function " + name)
    depth, pos = 1, match.end()
    start = pos
    while depth:
        depth += (text[pos] == "{") - (text[pos] == "}")
        pos += 1
    return text[start:pos - 1]


def evidence():
    sources, edges = {}, []
    vendor = Path(os.environ.get("TETRIS_VENDOR_TREE", str(stage.ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878")))

    def read(label, path):
        data = subprocess.run(["git", "-C", str(vendor), "show", stage.VENDOR + ":" + path],
                              capture_output=True, check=True).stdout
        sources[label] = {"path": path, "revision": stage.VENDOR, "sha256": hashlib.sha256(data).hexdigest()}
        return data.decode()

    def anchor(label, text, needle, meaning):
        if text.count(needle) != 1:
            raise ValueError("ambiguous or missing source anchor " + needle)
        edges.append({"source": label, "line": text[:text.index(needle)].count("\n") + 1,
                      "anchor": needle, "meaning": meaning})

    driver = read("vendor-driver", "drivers/regulator/mt6363-regulator.c")
    header = read("vendor-fields", "include/linux/regulator/mt6363-regulator.h")
    dt = read("vendor-pmic-dt", "arch/arm64/boot/dts/mediatek/mt6363.dtsi")
    board = read("vendor-board", "arch/arm64/boot/dts/mediatek/mt6878.dts")
    fields = {name: int(value, 0) for name, value in re.findall(r"^#define\s+(MT6363_\w+)\s+\((0x[0-9a-fA-F]+|\d+)\)", header, re.M)}
    rails = {}
    for name, kind in (("VBUCK1", "BUCK"), ("VBUCK2", "BUCK"), ("VSRAM_MODEM", "LDO")):
        prefix = "MT6363_RG_" + kind + "_" + name
        rails[name] = {key: fields[prefix + "_" + key] for key in ("EN_ADDR", "EN_SHIFT", "VOSEL_ADDR", "VOSEL_MASK", "LP_ADDR", "LP_SHIFT")}
        rails[name]["HW_LP"] = fields["MT6363_" + kind + "_" + name + "_HW_LP_MODE"]
        rails[name]["OP_EN"] = fields["MT6363_" + kind + "_" + name + ("_OP_EN_0" if kind == "BUCK" else "_OP_EN0")]
        if kind == "BUCK":
            rails[name]["SSHUB_EN"] = fields[prefix + "_SSHUB_EN_ADDR"]
            rails[name]["FCCM"] = fields["MT6363_RG_" + name + "_FCCM_ADDR"]
            rails[name]["FCCM_SHIFT"] = fields["MT6363_RG_" + name + "_FCCM_SHIFT"]
        anchor("vendor-driver", driver, ("MT6363_BUCK(" if kind == "BUCK" else "MT6363_LDO_LINEAR1(") + name + ",",
               "exact rail descriptor; VSRAM_MODEM also selects buck_ops and SET/CLR enables")
    anchor("vendor-driver", driver, "REGULATOR_LINEAR_RANGE(0, 0, 191, 6250)", "buck selectors 0..191, step 6250uV")
    anchor("vendor-driver", driver, "REGULATOR_LINEAR_RANGE(400000, 0, 127, 6250)", "VSRAM selectors 0..127, base 400000uV")
    anchor("vendor-driver", driver, "static int mt6363_buck_enable(struct regulator_dev *rdev)", "write enable_reg+1 with only rail mask")
    anchor("vendor-driver", driver, "static int mt6363_buck_disable(struct regulator_dev *rdev)", "write enable_reg+2 with only rail mask")
    anchor("vendor-driver", driver, "#define NORMAL_OP_EN\t0x800000", "normal AP control pattern; native code observes rather than rewriting hardware voters")
    anchor("vendor-driver", driver, "#define NORMAL_OP_CFG\t0x10", "source-defined OP_CFG profile at OP_EN+5")
    anchor("vendor-driver", driver, "\t\t\tudelay(100);", "source NORMAL transition out of IDLE delay")
    anchor("vendor-driver", driver, "#define MT6363_BUCK_TOP_UNLOCK_VALUE\t0x5543", "FAST/FCCM changes share the BUCK key; denied without a whole-key owner")
    anchor("vendor-driver", driver, "static int mt6363_regulator_set_load(struct regulator_dev *rdev, int load_uA)", "vendor DRMS rewrites OP banks; native implementation explicitly rejects it")
    anchor("vendor-fields", header, "#define MT6363_BUCK_VBUCK1_WDTDBG_VOSEL_ADDR", "WDT debug is not defined as a live DA selector")
    if re.search(r"\bMT6363_DA_\w*(?:VBUCK1|VBUCK2|VSRAM_MODEM)", header):
        raise ValueError("DA definitions changed: reassess scope")
    for supply, voltage in (("md-vmodem", 800000), ("md-vsram", 800000), ("md-vdigrf", 700000)):
        anchor("vendor-board", board, supply + " = <" + str(voltage) + " " + str(voltage) + ">;", "exact modem consumer target pair")
    for name in ("mt6363_vbuck1", "mt6363_vbuck2", "mt6363_vsram_modem"):
        anchor("vendor-pmic-dt", dt, 'regulator-name = "' + name + '";', "correct MT6363 supplier identity and source DT constraints")

    linux = Path(os.environ.get("TETRIS_KERNEL_TREE", str(stage.ROOT.parent / ("linux-" + stage.LINUX))))
    for label, path in (("linux-core", "drivers/regulator/core.c"), ("linux-of", "drivers/regulator/of_regulator.c")):
        data = (linux / path).read_bytes()
        sources[label] = {"path": path, "revision": stage.LINUX, "sha256": hashlib.sha256(data).hexdigest()}
        text = data.decode()
        if label == "linux-core":
            anchor(label, text, "\t\tinit_data = config->init_data;",
                   "core DT parsing can fall back; native registration explicitly parses and binds the exact node")
            anchor(label, text, "if (rdev->constraints->apply_uV &&",
                   "DT min/max may clamp an inherited selector at probe; registering flag denies this mutation")
    parent_path = "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0003-mfd-mt6363-keys-mt6375-telemetry.patch"
    parent = (stage.ROOT / parent_path).read_bytes()
    sources["packaged-spmi-parent"] = {"path": parent_path, "revision": None,
                                      "sha256": hashlib.sha256(parent).hexdigest()}
    if b".reg_bits = 16," not in parent or b".val_bits = 8," not in parent:
        raise ValueError("SPMI parent width changed")
    parent_config = parent.decode().split("+\tstatic const struct regmap_config regmap_config = {", 1)[1].split("+\t};", 1)[0]
    if "cache_type" in parent_config:
        raise ValueError("SPMI cache changed; reassess current register readback")
    return {"schema": 1, "pins": {"vendor": stage.VENDOR, "linux": stage.LINUX},
            "sources": sources, "causal_edges": edges, "rail_fields": rails,
            "active_selector_limit": "main RG selectors only under checked normal AP OP_EN/OP_CFG and inactive SSHUB; no DA voltage or power-good proof; no guaranteed exclusion of secure actors",
            "vsram_limit": "LDO_LINEAR1 lacks modeset/LP-load metadata; skip zero FCCM address and deny DRMS instead of reading register0 or returning fake success",
            "control_profile_basis": "NORMAL_OP_EN/CFG taken from vendor normal-control writer; VSRAM_MODEM OP address from its named field declaration. Readback admission only, not a hardware ownership attestation or a claimed stock register value.",
            "status": "source-derived-native-supplier-implemented; native/hardware-untested"}


if __name__ == "__main__":
    print(json.dumps(evidence(), indent=2))
