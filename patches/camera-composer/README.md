# Camera composer / capture-owner candidate (0118)

Partial / untested on hardware. No driver registration, DT activation or
production linkage. 0117/0118 now share an explicit DMA layout contract;
0119 adds the actual kernel CCD transport owner. No claim of capture support.

## Source boundary

All ABI and register evidence is pinned to modules
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`:

- `mtkcam/camsys/isp7sp/cam/mtk_cam-ipi.h`: complete packed frame and ACK ABI,
  version 0.1. Generated unchanged wire structs, no partial invented frame.
- `mtk_cam-job.c`: logical `camsv_param[0][tag]`, hardware_scenario=0,
  physical pipe id, `cq_rst->camsv[0]` even for physical engine SV1.
- `mtk_cam-fmt_utils.c`: `mtk_cam_dmao_xsize`, bus size from aligned pixel
  bits and pixel-mode shift. `mtk_cam-job_utils.c:fill_img_fmt` copies actual
  negotiated output stride. Sensor packet bytes are not DMA output bytes.
- `mtk_cam-sv.c:mtk_irq_camsv_done`: four status/sequence reads, lowest FIRST_TAG
  bit, outer DONE status. No acknowledgment write in this handler. The adapter
  reproduces those reads only after a real owner proves the acknowledgment
  protocol. Read-to-clear hardware semantics have NOT been independently
  established; IRQ registration/activation remains blocked on that gate.
- `mtk_cam.c:isp_composer_init/isp_composer_handler` uses CCD rpmsg clients.
- `mtkcam/camsys/remoteproc/mtk_ccd.c`: `ccd_load/start` do not upload executable
  firmware; `/dev/mtk_ccd` master/worker ioctls deliver work to userspace. A
  successful CCD rproc start is NOT evidence of an available ISP composer.

This path needs the matching AP CCD composition service and shared-buffer fd
export/transport, not an assumed ISP service in the sensor SCP image. The sensor
SCP image is neither inspected nor demonstrated to contain this service. CCU,
AOV or other camera coprocessors are not substitutes for CCD's CAM_CMD_FRAME
composer. No guessed firmware is loaded here.

## Implemented

The full frame assembler validates explicit source-verified output descriptions
and mapped DMA addresses; it does not choose PDAF memory format. ACK validation
checks command, session, exact frame cookie, signed composer error, unused engines,
CQ size and workbuf subrange without overflow or unaligned dereferences. Stale
replies do not poison the active frame; causal errors latch; one acceptance only.

The kernel owner connects ACK to 0117 submission, preserving its real
COMPOSER/IOMMU/ROUTE/IRQ checks. It rejects buffers whose mapped addresses differ
from the sent frame. DONE dispatch accumulates exact groups and uses immutable
explicit sizeimage for each queue, not a `/4` payload shortcut. The job's two
DMA layouts are copied into the transaction before writes and remain authoritative
through completion. Sensor wire length and metadata bus code do not choose a
DMA output format.

The layouts must be proven against the actual emitted CQ and negotiated queues
by COMPOSER, including output packing, stride/padding, tag groups, FH_SPARE and
cache synchronization. A positive ACK alone does not prove any of those.
The previous 0117 minimum PDAF and completion `/4` assumptions are removed.
Both standalone and integrated completion now validate/use explicit padded
DMA lengths. Selecting the actual PDAF output format still requires the
matching emitted CQ, not a synthetic fixture.

0119 sends CREATE/CONFIG/FRAME over a real CCD rpmsg endpoint, validates replies,
limits frame/flush/destroy waits, tolerates delayed unrelated ACKs, and refuses
reuse of the one-frame session. Failed drain leaves the session owned; successful
drain does not prove camera DMA quiescence. The first error is preserved even
after successful cleanup. There is no endpoint creation, bus registration,
counterfeit firmware-ready state, or automatic hardware operation.

See [CCD-CONTRACT.md](CCD-CONTRACT.md) for the exact counterpart and missing assets.

## Tests / next gate

Generate/check with `generate.py --modules-repo <pinned modules repo>` then
`check.py`. Native CI: `sh patches/camera-composer/run-tests.sh`.
Object CI target (after 0117/0118, vb2 config enabled):
`drivers/media/platform/mediatek/seninf/mt6878-camera-capture-owner.o`.
Also compile `drivers/media/platform/mediatek/seninf/mt6878-camera-ccd-owner.o`
with RPMSG enabled. Optional isolated KUnit fixture:
`mt6878-camera-ccd-test.o` (KUNIT enabled; no production linkage).

Tests cover exact full frame ABI offsets, unaligned/truncated/foreign ACKs,
negative composer errors, first-error preservation, unsupported engines,
overflow/aperture/CQ bounds, both IMX882 mode row alignment and independent
8/10-bit metadata output contracts. These are synthetic contracts, not proof
of the firmware's chosen PDAF format.

Next runtime gate: establish a real matching CCD composer session/transport and
validate one frame's emitted CQ against mapped RAW and PDAF outputs and exact
strides. Independently prove DONE acknowledgment and capture ownership under
masked/synchronized IRQs. Only then test one bounded capture/start-stop with
USB/SSH intact; cold repeat/lifecycle gates still apply. No phone operations here.
