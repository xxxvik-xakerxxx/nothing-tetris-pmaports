#!/usr/bin/env python3
"""Pinned ownership/API source checks only; do not compile or activate a camera."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
DEVICE = "ee2be53cb75670b548948636a0db1d1ff112bf12"


def show(repo, pin, path):
    return subprocess.check_output(["git", "show", f"{pin}:{path}"], cwd=repo, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--device-repo", type=Path, required=True)
    parser.add_argument("--kernel-tree", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    staging = json.loads((here / "STAGING.json").read_text())
    sources = [root / name for name in staging["sources"]]
    by_name = {path.name: path for path in sources}
    assert len(by_name) == len(sources) and all(path.is_file() for path in sources)
    for path in sources:
        for header in re.findall(r'^#include "([^"]+)"', path.read_text(), re.MULTILINE):
            assert header in by_name, (path, header)
    for target in [*staging["objects"], staging["fault_object"]]:
        assert Path(target).with_suffix(".c").name in by_name, target
    subprocess.run([sys.executable, str(here.parent / "camera-ccd-cq/check-recipe.py"),
                    str(args.assets), "--modules-repo", str(args.modules_repo)], check=True)
    mem = show(args.modules_repo, MODULES, "mtkcam/camsys/remoteproc/mtk_ccd_mem.c")
    for operation in ("dma_buf_attach(buf->dbuf, dev)", "DMA_BIDIRECTIONAL",
                      "sg_dma_address(buf->dma_sgt->sgl)",
                      "dma_buf_fd(buf->dbuf,  O_RDWR | O_CLOEXEC)"):
        assert operation in mem, operation
    bus = show(args.modules_repo, MODULES, "mtkcam/camsys/rpmsg/mtk_ccd_rpmsg.c")
    direct = bus.split("void mtk_rpmsg_ipi_handler(", 1)[1].split("static struct rpmsg_endpoint", 1)[0]
    assert "(*ept->cb)" in direct and "cb_lock" not in direct
    assert "ept->addr = ipi_id" in bus and "mept->mchinfo.id = ipi_id" in bus
    ipi = show(args.modules_repo, MODULES, "mtkcam/camsys/rpmsg/mtk_ccd_rpmsg_ipi.c")
    assert "srcmdev->rpdev.ept" in ipi and "kref_get(&srcmdev->rpdev.ept->refcount)" in ipi
    assert "wait_event_interruptible" in ipi
    dt = show(args.device_repo, DEVICE, "arch/arm64/boot/dts/mediatek/mt6878.dts")
    for port in ("M4U_L14_P1_CAMSV_A0_WDMA", "M4U_L13_P1_CAMSV_B0_WDMA"):
        assert port in dt
    dma = (args.kernel_tree / "include/linux/dma-buf.h").read_text()
    for api in ("dma_buf_map_attachment_unlocked", "dma_buf_unmap_attachment_unlocked",
                "dma_buf_vmap_unlocked", "dma_buf_vunmap_unlocked",
                "dma_buf_begin_cpu_access", "dma_buf_end_cpu_access", "dma_buf_fd"):
        assert api in dma, api
    code = (here / "mt6878-camera-pipeline-owner.c").read_text()
    for forbidden in (r"\breadl\w*\s*\(", r"\bwritel\w*\s*\(",
                      r"\brpmsg_destroy_ept\s*\(", r"\brequest.*irq\s*\(",
                      r"\bclk_prepare_enable\s*\(", r"\bregulator_enable\s*\(",
                      r"\bmodule_(?:platform_driver|init)\s*\(",
                      r"\bmt6878_camera_capture_ack\s*\("):
        assert not re.search(forbidden, code), forbidden
    assert "value.sgt->nents != 1" in code and "sg_dma_len(value.sgt->sgl) < buffer->size" in code
    assert "owner->consumer != current" in code and "work != owner->work.buffer" in code
    export = code.split("int mt6878_pipeline_export(", 1)[1].split("int mt6878_pipeline_endpoint", 1)[0]
    assert export.index("get_dma_buf(buffer)") < export.index("dma_buf_fd(buffer")
    assert "if (ret < 0)\n\t\tdma_buf_put(buffer);" in export
    assert "owner->endpoint || owner->published || owner->work.cpu_active" in code
    assert "endpoint->cb = NULL" not in code and "endpoint->priv = NULL" not in code
    callback = code.split("int mt6878_pipeline_rx(", 1)[1].split("int mt6878_pipeline_close_callback_gate", 1)[0]
    assert callback.index("owner->callback_users++") < callback.index("mt6878_camera_ccd_rx(")
    assert callback.index("mt6878_camera_ccd_rx(") < callback.index("owner->callback_users--")
    assert "return owner ? -EOPNOTSUPP : -EINVAL;" in code
    tests = (here / "owner-kunit.c").read_text()
    for fault in ("ATTACH_FAULT", "MAP_FAULT", "MULTI_SG", "SHORT_SG", "VMAP_FAULT", "IOMEM_VMAP"):
        assert fault in tests
    assert "file_count(buffer->file)" in tests and "mt6878_pipeline_close_callback_gate(owner), -EBUSY" in tests
    print("PASS: pinned DMA/CCD ownership and exact upstream API names (static only)")
    print("PASS: contiguous full mappings, current-task fd transfer, callback gate, fail-closed activation")
    print("PASS: 20-file staging closure; 5 owner/API objects plus separate KUnit fault object")
    print("Native/kernel objects and KUnit execution remain CI-only and unverified")


if __name__ == "__main__":
    main()
