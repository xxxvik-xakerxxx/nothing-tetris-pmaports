# B4.1 CPU CCD CQ implementation candidate

Status: memory-only CQ encoder implemented; no native compilation or hardware
execution locally. This directory is separate from frozen 0117/0118/0119 inputs.
No DT enable, MMIO, IRQ registration, ELF loading, or production linkage.

## Exact evidence

CI 37941089972 assets, `Tetris_B4.1-260415-1709`, mirror extraction manifest
commit `8225c29a5d9154a956d4f4bad5c8bd09ffafd869`.
`vendor/lib64/mt6878/libccd.so`, 409888 bytes, SHA256
`6d859690d1662b3bfedf058b874e6e46b264e3a202f7d7c69c2c65d4ae5f1f6a`.
Static AArch64 disassembly, not execution:

| Symbol/address | Proven behavior |
| --- | --- |
| `cq_composer_init` 0x37bf0 | VA, IOVA, capacity; descriptors grow from start, value chunks from end |
| `cq_append_desc` 0x37ca0 | 12-byte descriptors; chunks capped at 511 words |
| `cq_append_with_values` 0x37d30 | Copy values to tail, translate VA into workbuf IOVA, emit descriptors |
| 0x37db0..0x37dcc | word0 = low16(register) plus bits16..20(register) in bits27..31 plus (count-1) in bits16..24; u64 IOVA at byte4 |
| `cq_append_desc_end` 0x380b0 | word0 = 0x06000000, u64 value address zero |
| `cq_desc_regaddr` 0x38240 | decoded address ORs 0x1a000000 with encoded 21-bit offset |
| `camsys_sv_compose` 0x32cc0 | Calls values builder, END, descriptor length and alignment helpers |
| `ccd_init` 0x181b0 | Opens `/dev/mtk_ccd` read/write and uses ioctl 0xc0046301 |
| `ccd_ipi_send` 0x18100 | Worker object with src/id, 1024-byte message, length; ioctl 0xc40c6305 |

Register aperture is format evidence, **not** permission to access a physical
address or a replacement for DT resource lookup. The caller supplies a restricted
owned CAMSV register bank. This encoder does not prove that arbitrary registers
inside that bank form a safe or complete capture program.

The encoder adds stricter transactional preflight: invalid ranges, insufficient
space, CQ length overflow and input/output aliasing fail before buffer mutation;
the first failure remains latched. No partial frame is published. One final END
and its value space are reserved on every append. Descriptor length excludes the
value tail; the entire workbuf must stay mapped and cache-synchronized until
capture-owner quiescence. Initial IOVA is 16-byte aligned and bounded by the
frozen 0117 34-bit DMA contract. A single CQ is finalized; the multi-CQ alignment
helper is intentionally not implemented or assumed safe.

The concrete `mt6878_ccd_cq_frame_cookie` recipe encodes eight FH_SPARE writes
from `camsys_sv_compose` 0x33d44..0x33e78, using the owned central resource base,
exact 0x57c offset and 0x40 step checked against the pinned vendor register header.
It validates the context cookie [31:24], all tag destinations and total space
before any write. This closes the cookie-command composition part, not the
DMA/packing/enable remainder of the frame program. It must never be submitted as
a complete capture CQ by itself.

## Real service boundary and missing assets

Pinned kernel modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` CCD
rpmsg/remoteproc implementation has matching INIT/worker WRITE ABI. Device
modules `ee2be53cb75670b548948636a0db1d1ff112bf12` declare CCD separately
from sensor SCP. Matching ELF now proves a CPU-side CCD composer exists; it does
not establish a standalone pmOS executable or a camera ISP firmware upload.

`libccd.so` direct dependencies: libcutils, liblog, libutils,
libmtkcam_perfctrl_wrapper, libc++, libc, libm, libdl. These Android ABI libraries
are not supplied by the current camera artifact. Porting a native executable
requires proving and replacing the CCD worker/master session lifecycle and
CAMSV frame-to-register composition, not merely calling an exported symbol with
an inferred prototype. Exported names alone are not a callable C ABI contract.

Actual executable extracted: `vendor/bin/hw/mt6878/camerahalserver`, SHA256
`f315202e7436e42600e610caa886d8bb3b1842724278004418bee4247d048ee4`.
Stock init points to `/vendor/bin/hw/camerahalserver`; that top-level file or
symlink resolution was not extracted. It links Android Binder/HIDL/AIDL camera
provider, ISP HAL, IPC and tuning libraries; it does **not** directly link
libccd. The current extraction lacks these dependency closures, including
`libmtkcam_hal_aidl_provider.so`,
`vendor.mediatek.hardware.camera.isphal_aidl@1.0-impl.so`,
`libmtkcam_ipc_core.so`, and `libmtkcam_ca.so`. A verified caller of `ccd_init`
and full session-to-`camsys_sv_compose` adapter still need tracing. The extracted
`libispinterpreter_mtkcam.so` also has no direct libccd dependency.

Do not advertise stock HAL/service activation, camera firmware readiness, IRQ
ack semantics or image capture from this evidence. The pinned CAMSV DONE handler
reads status without a documented ack write; CQ encoding does not resolve that
ownership gate. No guessed W1C/read-clear behavior is added here.

## Next gates

Main may run `python3 check.py <verified-assets-root> --modules-repo <pinned-modules>`
(pyelftools required), then
CI-only `sh run-tests.sh` under ASan/UBSan. Native fixtures cover high IOVA,
511/512-word split, byte-exact END, exact-capacity finalization, out-of-bank and
unaligned register ranges, IOVA overflow, overlap and immutable first failure.
This candidate is not yet packaged as a kernel patch.
`mt6878-camera-ccd-cq-smoke.c` is a kernel-only compile-smoke input for an explicit
CI object target. Do not add it to production archives or register runtime code.

Before runtime: prove CAMSV frame-to-register list and DMA output packing against
matching composer; verify all descriptor targets and embedded RAW/PDAF addresses
against frozen 0117/0118 layouts; own CCD session/mappings, PHY/mux/VC, CAMSV
resources and documented IRQ clear semantics. Only then, under main's live gates,
permit one RAW10 plus PDAF capture with bounded stop and USB/SSH preservation.
