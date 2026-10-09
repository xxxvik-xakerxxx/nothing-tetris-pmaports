#!/usr/bin/env python3
"""Source/static checks only; kernel/native compilation belongs to main CI."""
import argparse
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("capture_generator", HERE / "generate.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def check(args):
    regs = generator.registers(args.modules_repo, args.device_repo)
    assert (HERE / "mt6878-camsv-registers.h").read_text() == regs
    assert generator.OUTPUT.read_text() == generator.patch_text(regs)
    core = (HERE / "mt6878-camsv-capture.h").read_text()
    vb2 = (HERE / "mt6878-camsv-vb2.c").read_text()
    submit = core.split("static inline int mt6878_camsv_submit", 1)[1].split("static inline int mt6878_camsv_done", 1)[0]
    assert submit.index("io->verify(") < submit.index("mt6878_camsv_update(")
    writes = re.findall(r"mt6878_camsv_write\(io, tx, MT6878_SV_CQ, (\w+)", submit)
    assert writes == ["SV_CQ_SIZE", "SV_CQ_MSB", "SV_CQ_LSB", "SV_CQ_START"]
    assert "count < 100000" in core and "if (value & 2)" in core
    assert "inner_sequence != tx->job.sequence" in core
    assert "job->group_tags[i] & seen" in core
    assert "iommu_get_domain_for_dev(dma_owner) != verified_domain" in vb2
    assert "vb->vb2_queue->mem_ops != &vb2_dma_contig_memops" in vb2
    assert "if (!pair->tx.quiesced)" in vb2
    assert "if (ret && !pair->tx.hw_attempted)" in vb2
    assert "V4L2_BUF_TYPE_META_CAPTURE" in vb2
    assert "of_parse_phandle_with_args" in vb2 and "larb != (sv_id ? 13 : 14)" in vb2
    assert "device_link_add(dev, port_owner, DL_FLAG_AUTOREMOVE_CONSUMER)" in vb2
    assert "DL_FLAG_PM_RUNTIME" not in vb2
    assert not re.search(r"\b(?:writel|readl|clk_prepare_enable|pm_runtime_resume_and_get|module_platform_driver|video_register_device)\s*\(", core + vb2)
    assert "raw_size / 4" not in core and "size / 4" not in vb2
    assert "pair->tx.job.pdaf_layout.sizeimage" in vb2
    assert "mt6878_camsv_layout_validate(&job->pdaf_layout" in core
    with tempfile.TemporaryDirectory(prefix="camsv-apply-") as temp:
        subprocess.run(["patch", "--batch", "-p1", "-i", str(generator.OUTPUT)], cwd=temp, check=True)
        for name in ("mt6878-camsv-capture.h", "mt6878-camsv-registers.h", "mt6878-camsv-vb2.h", "mt6878-camsv-vb2.c"):
            applied = Path(temp) / "drivers/media/platform/mediatek/seninf" / name
            assert applied.read_text() == (HERE / name).read_text()
    print("PASS: pinned CQ/reset/VC/resource provenance and patch application")
    print("PASS: pre-MMIO ownership, distinct video/meta DMA queues, IRQ grouping and timeout pinning guards")
    print("Native fault injection and vb2 kernel object remain CI-only, not run locally")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--device-repo", type=Path, required=True)
    check(parser.parse_args())
