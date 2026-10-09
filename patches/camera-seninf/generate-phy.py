#!/usr/bin/env python3
"""Generate audited full-port, three-trio CPHY operations from pinned sources."""
import argparse
import ast
import difflib
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMIT = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
DEVICE = "ee2be53cb75670b548948636a0db1d1ff112bf12"
PREFIX = "mtkcam/camsys/isp7sp/cam/mtk_csi_phy_3_1/"
PATCH = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0116-media-platform-mediatek-mt6878-seninf-phy-backend.patch"


def show(repo, commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=repo, text=True)


def clean(text):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)


def integer(expr):
    tree = ast.parse(expr.strip(), mode="eval")
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.LShift):
                return a << b
            if isinstance(node.op, ast.BitOr):
                return a | b
        raise ValueError(f"unreviewed constant expression: {expr}")
    return visit(tree)


def calls(text):
    """Parse only the two audited write macros, including nested value expressions."""
    result = []
    text = clean(text)
    for match in re.finditer(r"\b(SENINF_BITS|SENINF_WRITE_REG)\s*\(", text):
        start = match.end()
        depth, args, mark = 1, [], start
        for pos in range(start, len(text)):
            char = text[pos]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if not depth:
                    args.append(text[mark:pos].strip())
                    break
            elif char == "," and depth == 1:
                args.append(text[mark:pos].strip())
                mark = pos + 1
        assert len(args) == (4 if match[1] == "SENINF_BITS" else 3)
        result.append((match[1], args))
    return result


def function(text, name):
    start = text.index("static int " + name + "(")
    end = text.find("\nstatic ", start + 1)
    return text[start:end if end != -1 else len(text)]


def generate(modules, device):
    source = show(modules, COMMIT, PREFIX + "mtk_cam-seninf-hw_phy_3_1.c")
    dts = show(device, DEVICE, "arch/arm64/boot/dts/mediatek/mt6878.dts")
    sensor = show(modules, COMMIT, "mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c")
    csi = function(sensor, "get_csi_param")
    preview = csi[csi.index("case SENSOR_SCENARIO_ID_NORMAL_PREVIEW:"):csi.index("case SENSOR_SCENARIO_ID_NORMAL_VIDEO:")]
    video = csi[csi.index("case SENSOR_SCENARIO_ID_NORMAL_VIDEO:"):csi.index("case SENSOR_SCENARIO_ID_SLIM_VIDEO:")]
    assert "csi_param->dphy_trail = 0x47" in preview
    assert "csi_param->dphy_trail = 0x31" in video
    assert "csi_param->legacy_phy = 0" in video
    assert "csi_param->not_fixed_trail_settle = 0" in video
    assert ".mipi_pixel_rate = 700800000" in sensor
    assert "u8 map_hdr_len[] = {0, 1, 2, 4, 5}" in source
    route = show(modules, COMMIT, "mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-route.c")
    assert "memset(csi_param, 0, sizeof(struct mtk_csi_param))" in route
    hw = clean(show(modules, COMMIT, "mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-hw.h"))
    assert not re.search(r"^\s*#define\s+CDPHY_ULPS_MODE_SUPPORT\b", hw, re.M)
    for step, clock in enumerate((312, 343, 416, 499)):
        assert re.search(r"cdphy-dvfs-step" + str(step) + r" = [^;]*<" + str(clock) + r">", dts)
    assert "(settle_ns * seninf_ck)" in source and "(_val / 1000000000) - 6" in source
    assert "#define CPHY_SETTLE_DEF 70" in source and "#define DPHY_TRAIL_SPEC 224" in source
    for offset in ("0x2000", "0xA000", "0x3000", "0xB000", "0x4000", "0xC000", "0x5000", "0xD000", "0x6000", "0xE000"):
        assert "ana_base + " + offset in source
    headers = {}
    for name in ("mipi-rx-ana-cdphy-csi0a", "csi0-dphy", "csi0-cphy", "csirx_mac_top", "csirx_mac_csi0", "seninf1", "top-ctrl"):
        text = show(modules, COMMIT, PREFIX + "mtk_cam-seninf-" + name + ".h")
        for key, expr in re.findall(r"^#define[ \t]+(\w+)[ \t]+([^\n]+)", clean(text), re.M):
            try:
                value = integer(expr)
            except (ValueError, SyntaxError):
                continue
            if key in headers:
                assert headers[key] == value, key
            headers[key] = value

    tables = {}
    tables["init"] = calls(function(source, "csirx_phyA_init"))
    tables["efuse"] = calls(function(source, "apply_efuse_data"))
    timing = function(source, "csirx_dphy_init")
    tables["timing"] = calls(timing[timing.index("SENINF_BITS(base, DPHY_RX_DATA_LANE0_HS_PARAMETER"):timing.index("if (!ctx->is_cphy)")])
    tables["timing"] += calls(timing[timing.rindex("} else {"):])
    tables["post"] = calls(function(source, "csirx_cphy_init"))
    top = function(source, "csirx_mac_top_setting")
    tables["mac_top"] = calls(top[:top.index("} else {")])
    tables["mac_fixed"] = calls(function(source, "csirx_mac_csi_fixed_setting"))
    mac = function(source, "csirx_mac_csi_setting")
    tables["mac"] = calls(mac[mac.index("/* select C / D phy */"):mac.index("switch (ctx->port)")])
    tables["mac"] += calls(mac[mac.index("case 3:"):mac.index("case 4:")])
    tables["mac"] += calls(mac[mac.index("/* Select CSI2 pixel mode */"):mac.index("if (!ctx->is_cphy)")])
    tables["mac"] += calls(mac[mac.index("} else { //Cphy"):])
    lrte = function(source, "csirx_mac_csi_lrte_setting")
    tables["lrte_off"] = calls(lrte[lrte.index("if(!ctx->csi_param.cphy_lrte_support)"):lrte.index("if (!ctx->is_cphy)")])
    analog = function(source, "csirx_phyA_setting")
    analog = analog[analog.index("/* CPHY Config */"):]
    analog = analog[analog.index("/* CPHY non-split mode */"):analog.index("/* CPHY split mode */")]
    # IMX882 audited wire rate gives 1.022Gsym/s, selecting the vendor <1.5G branch.
    analog = analog[:analog.index("} else {\n\t\t\t\tSENINF_WRITE_REG")] + analog[analog.index("SENINF_WRITE_REG(baseA, CDPHY_RX_ANA_SETTING_0"):]
    analog = analog[:analog.index("} else if (data_rate < 2500000000)")]
    tables["analog_setup"] = calls(analog)
    cphy = function(source, "csirx_cphy_setting")
    tables["trios"] = calls(cphy[cphy.index("case CSI_PORT_0:"):cphy.index("} else if (ctx->num_data_lanes == 2)")])
    tables["trios"] += calls(cphy[cphy.index("if (!ctx->csi_param.legacy_phy)"):].split("else", 1)[0])
    tables["trios"] += calls(cphy[cphy.index("/* CPHY_RX_IRQ_EN */"):])
    tables["seninf"] = calls(function(source, "seninf1_setting"))

    bases = {"baseA": 0, "baseB": 0x1000, "csirx_mac_top": 0x4000,
             "csirx_mac_csi_A": 0x5000, "csirx_mac_csi_B": 0x6000,
             "csirx_mac_csi": 0x5000, "cphy_base": 0x3000, "dphy_base": 0x2000}
    substitutions = {
        "(ctx->port >= CSI_PORT_MIN_SPLIT_PORT) ? 1 : 0": 0,
        "(ctx->port >= CSI_PORT_MIN_SPLIT_PORT) ? 2 : 0": 0,
        "(ctx->is_cphy) ? 1 : 0": 1,
        "(ctx->num_data_lanes > 1) ? 0x5 : 0x6": 5,
        "(ctx->num_data_lanes > 1) ? 0x4 : 0x6": 4,
        "(ctx->is_4d1c) ? ((ctx->num_data_lanes > 1) ? 0x4: 0x6) : 0x6": 4,
        "map_hdr_len[(unsigned int)ctx->num_data_lanes]": 4,
    }
    out = "/* SPDX-License-Identifier: GPL-2.0-only */\n"
    out += "/* Register definitions: Copyright (c) 2020 MediaTek Inc. */\n"
    out += "/* Generated from Nothing modules " + COMMIT + "; do not edit. */\n"
    counts = {}
    for name, operations in tables.items():
        out += f"static const struct mt6878_phy_op mt6878_phy_{name}[] = {{\n"
        for macro, args in operations:
            base, reg = args[:2]
            base_offset = bases.get(base, {"init": 0, "efuse": 0, "timing": 0x2000, "post": 0x3000, "seninf": 0x200}.get(name))
            assert base_offset is not None, (name, base)
            kind, shift = "MT6878_PHY_LITERAL", 0
            expr = args[-1]
            if expr in ("settle_delay_dt", "settle_delay_ck"):
                value, kind = 0, "MT6878_PHY_SETTLE"
            elif expr == "hs_trail":
                value, kind = 0, "MT6878_PHY_TRAIL"
            elif "m_csi_efuse" in expr:
                value = int(re.search(r">>\s*(\d+)", expr)[1])
                kind = "MT6878_PHY_EFUSE"
                if value < 17:
                    base_offset = 0x1000
            elif expr in substitutions:
                value = substitutions[expr]
            else:
                value = integer(expr)
            if macro == "SENINF_BITS":
                field = args[2]
                mask, shift = headers[field + "_MASK"], headers[field + "_SHIFT"]
                if kind == "MT6878_PHY_LITERAL":
                    assert not ((value << shift) & ~mask), (field, value)
            else:
                field, mask = "full write", 0xffffffff
                kind = "MT6878_PHY_WRITE"
            offset = base_offset + headers[reg]
            region = "MT6878_SENINF_BASE" if name == "seninf" else "MT6878_SENINF_ANALOG"
            out += f"\t/* {reg}: {field} */\n"
            out += f"\t{{ {region}, 0x{offset:x}, 0x{mask:08x}U, {shift}, {kind}, 0x{value:x} }},\n"
        out += "};\n\n"
        counts[name] = len(operations)
    out += f"#define MT6878_PHY_TOP_CTRL2 0x{headers['SENINF_TOP_CTRL2']:x}\n"
    assert counts == {"init": 31, "efuse": 12, "timing": 20, "post": 1,
                      "mac_top": 4, "mac_fixed": 36, "mac": 28,
                      "lrte_off": 2, "analog_setup": 33, "trios": 26, "seninf": 2}, counts
    return out


def patch_text(data):
    text = "From: Codex <codex@openai.com>\nSubject: [PATCH] media: mediatek: prepare calibrated full-port CPHY/MAC transactions\n\n"
    text += "Exact audited IMX882 three-trio setup; caller retains power, IRQ,\nVC/TSREC and DMA ownership. No runtime adapter or DT activation.\n\n"
    for name, source in (("mt6878-seninf-phy.h", (HERE / "mt6878-seninf-phy.h").read_text()),
                         ("mt6878-seninf-phy-data.h", data),
                         ("mt6878-seninf-phy-smoke.c", (HERE / "mt6878-seninf-phy-smoke.c").read_text())):
        path = "drivers/media/platform/mediatek/seninf/" + name
        text += f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
        text += "".join(difflib.unified_diff([], source.splitlines(keepends=True), fromfile="/dev/null", tofile="b/" + path))
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--device-repo", type=Path, required=True)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    data = generate(args.modules_repo, args.device_repo)
    patch = patch_text(data)
    if args.generate:
        (HERE / "mt6878-seninf-phy-data.h").write_text(data)
        PATCH.write_text(patch)
    else:
        assert (HERE / "mt6878-seninf-phy-data.h").read_text() == data
        assert PATCH.read_text() == patch
    print("PASS: exact pinned CPHY field masks, values, offsets, order and regeneration")
