#!/usr/bin/env python3
"""Static inactive-owner/patch consistency checks; no C compilation."""
from pathlib import Path
import re
import subprocess
import tempfile
from generate import HERE, OUTPUT, CCD_OUTPUT

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
ccd_patch = CCD_OUTPUT.read_text()
with tempfile.TemporaryDirectory() as directory:
    subprocess.run(["patch", "-p1", "-i", str(CCD_OUTPUT)], cwd=directory, check=True, capture_output=True)
    for name in re.findall(r"^\+\+\+ b/drivers/media/platform/mediatek/seninf/(.+)$", ccd_patch, re.M):
        assert (Path(directory) / "drivers/media/platform/mediatek/seninf" / name).read_bytes() == (HERE / name).read_bytes()
ccd = (HERE / "mt6878-camera-ccd-owner.c").read_text()
assert "rpmsg_trysend(owner->endpoint" in ccd
assert "wait_for_completion_timeout" in ccd and "timeout_ms > 5000" in ccd
assert "ret == -ESTALE" in ccd and "owner->pending = 0" in ccd
assert "mt6878_camera_capture_ack(" in ccd
assert "rproc_boot(" not in ccd and "writel" not in ccd
print("PASS: patch application, exact new files, bounded IRQ reads, explicit payload, no activation")
