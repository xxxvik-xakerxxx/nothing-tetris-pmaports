#!/usr/bin/env python3
"""Generate exact pinned camera ABI and inactive capture-owner patch."""
import argparse
import difflib
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMIT = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
PREFIX = "mtkcam/camsys/isp7sp/cam/"
OUTPUT = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0118-media-platform-mediatek-mt6878-camera-composer-owner.patch"
CCD_OUTPUT = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0119-media-platform-mediatek-mt6878-camera-ccd-owner.patch"


def show(repo, path):
    return subprocess.check_output(["git", "show", f"{COMMIT}:{path}"], cwd=repo, text=True)


def generated(repo):
    ipi = show(repo, PREFIX + "mtk_cam-ipi.h")
    defs = show(repo, PREFIX + "mtk_cam-defs.h")
    fmt = show(repo, "mtkcam/camsys/common/mtk_cam-fmt.h")
    # All wire structs, including the entire large frame, retained verbatim.
    # defs.h provides no wire-layout types; import only the used enums.
    enums = "\n".join(re.search(r"enum " + name + r" \{.*?\n\};", text, re.S)[0]
                      for text, name in ((defs, "mtkcam_pipe_subdev"),
                                         (defs, "mtkcam_ipi_video_id"),
                                         (fmt, "mtkcam_ipi_fmt")))
    assert ipi.count('#include "mtk_cam-defs.h"') == 1
    ipi = ipi.replace('#include "mtk_cam-defs.h"', enums)
    regs = show(repo, PREFIX + "mtk_cam-sv-regs.h")
    sv = show(repo, PREFIX + "mtk_cam-sv.c")
    handler = sv.split("static irqreturn_t mtk_irq_camsv_done(", 1)[1].split("\nbool is_all_tag", 1)[0]
    assert "writel" not in handler and "CAMSV_WRITE" not in handler
    for access in ("base_inner + REG_CAMSVCENTRAL_FIRST_TAG", "base + addr_frm_seq_no",
                   "base_inner + addr_frm_seq_no", "base + REG_CAMSVCENTRAL_DONE_STATUS"):
        assert access in handler
    out = "/* SPDX-License-Identifier: GPL-2.0-only */\n/* Generated pinned vendor DONE-handler offsets. */\n"
    for local, vendor in (("CAMERA_FIRST_TAG", "REG_CAMSVCENTRAL_FIRST_TAG"),
                          ("CAMERA_FH_SPARE_TAG1", "REG_CAMSVCENTRAL_FH_SPARE_TAG_1"),
                          ("CAMERA_FH_SPARE_SHIFT", "CAMSVCENTRAL_FH_SPARE_SHIFT"),
                          ("CAMERA_DONE_STATUS", "REG_CAMSVCENTRAL_DONE_STATUS")):
        value = re.search(r"^#define\s+" + vendor + r"\s+(0x[0-9a-fA-F]+)", regs, re.M)[1]
        out += f"#define {local} {value}\n"
    utils = show(repo, PREFIX + "mtk_cam-fmt_utils.c")
    assert "ALIGN(bpp, 16) << pixel_mode_shift" in utils
    assert "return bus_size / 8" in utils and "return ALIGN(bytes, bus_size)" in utils
    job = show(repo, PREFIX + "mtk_cam-job.c")
    assert "cq_rst->camsv[0].size" in job and "cq_rst->camsv[0].offset" in job
    assert "fp->camsv_param[0][tag_idx].hardware_scenario = 0" in job
    job_h = show(repo, PREFIX + "mtk_cam-job.h")
    assert re.search(r"#define BITS_FRAME_SEQ\s+24\b", job_h)
    assert "return ctx << BITS_FRAME_SEQ | seq_no" in job_h
    ccd = show(repo, "mtkcam/camsys/remoteproc/mtk_ccd.c")
    load = ccd.split("static int ccd_load(", 1)[1].split("static int ccd_start", 1)[0]
    assert "request_firmware" not in load and "IOCTL_CCD_WORKER_WRITE" in ccd
    return {"mt6878-camera-ipi-abi.h": ipi, "mt6878-camera-irq-registers.h": out}


def ccd_files(repo):
    uapi = show(repo, "mtkcam/include/uapi/linux/mtk_ccd_controls.h")
    ipi = show(repo, "mtkcam/camsys/rpmsg/mtk_ccd_rpmsg_ipi.c")
    rpmsg = show(repo, "mtkcam/camsys/rpmsg/mtk_ccd_rpmsg.c")
    assert "write_obj->sbuf, write_obj->len" in ipi
    assert "memcpy(read_obj, &ccd_params->worker_obj, sizeof(*read_obj))" in ipi
    assert "mtk_subdev->ops->ccd_send(mtk_subdev, mept, data, len, 0)" in rpmsg
    assert "#define BUF_MAX_SIZE" in uapi and "(1024)" in uapi
    files = {"mt6878-camera-ccd-uapi.h": uapi}
    for name in ("mt6878-camera-ccd-owner.h", "mt6878-camera-ccd-owner.c", "mt6878-camera-ccd-test.c"):
        files[name] = (HERE / name).read_text()
    out = "From: Codex <codex@openai.com>\nSubject: [PATCH] media: mediatek: own bounded CCD frame transport\n\n"
    out += "Actual CCD ABI and rpmsg lifecycle, no fabricated composer or activation.\n"
    out += "One-frame bounded transport with fault fixtures; CQ generation still needs\n"
    out += "the matching userspace CCD composition implementation.\n\n"
    for name, source in files.items():
        target = "drivers/media/platform/mediatek/seninf/" + name
        out += f"diff --git a/{target} b/{target}\nnew file mode 100644\n"
        out += "".join(difflib.unified_diff([], source.splitlines(keepends=True), fromfile="/dev/null", tofile="b/" + target))
    return files, out


def patch_text(files):
    out = "From: Codex <codex@openai.com>\nSubject: [PATCH] media: mediatek: validate CCD CQ replies and capture completion\n\n"
    out += "Pinned ISP7SP ABI, explicit output layout, bounded vendor DONE snapshot.\nNo production registration, firmware surrogate or DT activation.\n\n"
    for name in (*files, "mt6878-camera-composer.h", "mt6878-camera-capture-owner.h", "mt6878-camera-capture-owner.c"):
        source = files[name] if name in files else (HERE / name).read_text()
        target = "drivers/media/platform/mediatek/seninf/" + name
        out += f"diff --git a/{target} b/{target}\nnew file mode 100644\n"
        out += "".join(difflib.unified_diff([], source.splitlines(keepends=True), fromfile="/dev/null", tofile="b/" + target))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    files = generated(args.modules_repo)
    patch = patch_text(files)
    ccd, ccd_patch = ccd_files(args.modules_repo)
    if args.generate:
        for name, source in files.items():
            (HERE / name).write_text(source)
        OUTPUT.write_text(patch)
        (HERE / "mt6878-camera-ccd-uapi.h").write_text(ccd["mt6878-camera-ccd-uapi.h"])
        CCD_OUTPUT.write_text(ccd_patch)
    else:
        for name, source in files.items():
            assert (HERE / name).read_text() == source
        assert OUTPUT.read_text() == patch
        assert (HERE / "mt6878-camera-ccd-uapi.h").read_text() == ccd["mt6878-camera-ccd-uapi.h"]
        assert CCD_OUTPUT.read_text() == ccd_patch
    print("PASS: complete pinned frame ABI, CCD transport, CQ slot, IRQ offsets, stride source")
