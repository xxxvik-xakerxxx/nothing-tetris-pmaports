#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the shipping consumer patch to stdout; never edit package files."""
from difflib import unified_diff
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

# Preserve the existing package integration; the C file is authoritative.
INTEGRATION = """From: xxxvik-xakerxxx <19531907+xxxvik-xakerxxx@users.noreply.github.com>
Subject: [PATCH] misc: expose authenticated GPUEB RAM through a read-only consumer

Require the matching optional bootloader reservation. No GPU startup.

Signed-off-by: xxxvik-xakerxxx <19531907+xxxvik-xakerxxx@users.noreply.github.com>
---
diff --git a/drivers/misc/Kconfig b/drivers/misc/Kconfig
--- a/drivers/misc/Kconfig
+++ b/drivers/misc/Kconfig
@@ -662,3 +662,13 @@
 source "drivers/misc/amd-sbi/Kconfig"
 source "drivers/misc/rp1/Kconfig"
+config TETRIS_GPUEB_FLAT_ANALYSIS
+\ttristate "Tetris authenticated GPUEB RAM analysis"
+\tdepends on ARM64 && OF && OF_RESERVED_MEM
+\tselect CRYPTO_SHA256
+\thelp
+\t  Read-only root diagnostic for authenticated ordinary reserved DRAM
+\t  supplied by the opt-in U-Boot flat-retention path. Checks the complete
+\t  snapshot digest; no MMIO, upload, reset or GPU power operations.
+\t  The module remains pinned after probe until reboot.
+
 endmenu
diff --git a/drivers/misc/Makefile b/drivers/misc/Makefile
--- a/drivers/misc/Makefile
+++ b/drivers/misc/Makefile
@@ -77,1 +77,2 @@
 obj-$(CONFIG_MISC_RP1)\t\t+= rp1/
+obj-$(CONFIG_TETRIS_GPUEB_FLAT_ANALYSIS) += gpueb-flat-analysis.o
"""


def render(source):
    if not source or not source.endswith("\n"):
        raise ValueError("consumer source must be nonempty and newline terminated")
    target = "drivers/misc/gpueb-flat-analysis.c"
    addition = "".join(unified_diff([], source.splitlines(keepends=True),
                                    fromfile="/dev/null", tofile="b/" + target))
    return (INTEGRATION + f"diff --git a/{target} b/{target}\n"
            + "new file mode 100644\n" + addition)


if __name__ == "__main__":
    sys.stdout.write(render((HERE / "gpueb-flat-analysis.c").read_text()))
