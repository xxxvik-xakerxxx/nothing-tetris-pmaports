#!/usr/bin/env python3
"""Build a source-only patch from the reviewed SENINF graph templates."""
import argparse
import difflib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0114-media-platform-mediatek-mt6878-seninf-graph.patch"


def new_files():
    return {"drivers/media/platform/mediatek/seninf/" + name:
            (HERE / name).read_text() for name in
            ("mt6878-seninf-graph.c", "mt6878-seninf-contract.h")}


def patch_text(kernel):
    result = "From: Codex <codex@openai.com>\n"
    result += "Subject: [PATCH] media: mediatek: prepare MT6878 SENINF resources and graph\n\n"
    result += "No board activation, PHY writes, clock enable, IRQ handler or DMA.\n"
    result += "Graph validation is not camera capture. Stream and runtime resume\n"
    result += "fail explicitly until PHY/DVFS/mux/downstream ownership is implemented.\n\n"
    files = new_files()
    files["drivers/media/platform/mediatek/seninf/Makefile"] = (
        "# SPDX-License-Identifier: GPL-2.0-only\n"
        "obj-$(CONFIG_VIDEO_MT6878_SENINF_GRAPH) += mt6878-seninf-graph.o\n")
    files["drivers/media/platform/mediatek/seninf/Kconfig"] = """# SPDX-License-Identifier: GPL-2.0-only
config VIDEO_MT6878_SENINF_GRAPH
	tristate "MT6878 SENINF resource and graph candidate"
	depends on OF && COMMON_CLK && PM && PM_GENERIC_DOMAINS && NVMEM && REGULATOR
	depends on VIDEO_DEV && MEDIA_CONTROLLER
	select V4L2_FWNODE
	help
	  Resource-only C-PHY receiver subdevice for an explicitly described
	  MT6878 camera graph. Checks the audited binned IMX882 packet contract.
	  Does not enable receiver hardware, clocks, supplies, IRQs or DMA.
	  Stream-on fails until the full PHY and capture path is implemented.
"""
    for path, text in files.items():
        result += f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
        result += "".join(difflib.unified_diff([], text.splitlines(keepends=True),
                        fromfile="/dev/null", tofile="b/" + path))
    for name, suffix in (("Kconfig", '\nsource "drivers/media/platform/mediatek/seninf/Kconfig"\n'),
                         ("Makefile", "obj-y += seninf/\n")):
        path = "drivers/media/platform/mediatek/" + name
        before = (kernel / path).read_text()
        result += f"diff --git a/{path} b/{path}\n"
        result += "".join(difflib.unified_diff(before.splitlines(keepends=True),
                          (before + suffix).splitlines(keepends=True),
                          fromfile="a/" + path, tofile="b/" + path))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-tree", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = patch_text(args.kernel_tree)
    if args.check:
        assert OUTPUT.read_text() == text, "SENINF generated patch is stale"
        print("SENINF patch matches reviewed templates")
    else:
        OUTPUT.write_text(text)
