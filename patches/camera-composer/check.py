#!/usr/bin/env python3
"""Static inactive-owner/patch consistency checks; no C compilation."""
from pathlib import Path
import re
import subprocess
import tempfile
from generate import HERE, OUTPUT

patch = OUTPUT.read_text()
names = re.findall(r"^\+\+\+ b/drivers/media/platform/mediatek/seninf/(.+)$", patch, re.M)
with tempfile.TemporaryDirectory() as directory:
    subprocess.run(["patch", "-p1", "-i", str(OUTPUT)], cwd=directory, check=True, capture_output=True)
    for name in names:
        assert (Path(directory) / "drivers/media/platform/mediatek/seninf" / name).read_bytes() == (HERE / name).read_bytes()
owner = (HERE / "mt6878-camera-capture-owner.c").read_text()
assert "writel" not in owner
assert owner.count("readl_relaxed(") == 4
assert owner.index("owner->verify_irq_read(owner)") < owner.index("readl_relaxed(")
assert "mt6878_camsv_vb2_done(" in owner  # Single authoritative DMA payload contract.
assert "job.pdaf_layout.sizeimage" in owner
for forbidden in ("request_irq(", "module_platform_driver(", "clk_prepare_enable(", "rproc_boot("):
    assert forbidden not in owner
assert not re.search(r"^diff --git .*?(Makefile|Kconfig|\.dts)", patch, re.M)
print("PASS: patch application, exact new files, bounded IRQ reads, explicit payload, no activation")
