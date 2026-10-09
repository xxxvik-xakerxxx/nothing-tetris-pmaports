# Linear RAW10/PDAF first-frame recipe and native CCD caller

Candidate, separate from the frozen CQ encoder. No runtime DT, service install,
probe, production linkage or local native compilation. Actual hardware capture
is untested. This implements a complete restricted descriptor recipe, not a
claim that the whole camera pipeline is operational.

## Exact implementation boundary

Matching B4.1 `libccd.so` SHA256
`6d859690d1662b3bfedf058b874e6e46b264e3a202f7d7c69c2c65d4ae5f1f6a`.
Source modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`, device modules
`ee2be53cb75670b548948636a0db1d1ff112bf12`.

`mt6878-camera-camsv-recipe.h` composes 59 writes plus END for SV0 or SV1,
two independent outputs, first frame, single SMI, first-order tags, normal
hardware_scenario=0, no RAW/MRAW companion engine, no metadata-off, UFO or
compressed packing. Only image tags0..3 and pixel_mode_shift=0 are accepted;
other image-enable masks and pixel-mode recipes are not extrapolated.
Resource identity, central and DMA starts are supplied by
the owner; their 0x10000 delta and 0x1000 sizes match this chip's vendor program.
All buffer IOVAs/strides/sizeimage are supplied by the owner. No handset address,
calibration, voltage or invented polling is used.

| Matching code range | Commands implemented |
| --- | --- |
| 0x32eb0..0x33048, 0x333f4..0x33544 | Full crop, input format/config, FBC0=0x8000, stride/basic and linear LEN basic |
| 0x33070..0x33354, 0x3355c..0x33610 | Output format, primary DMA stride/address, disabled secondary-SMI fields, FBC0=0x8080 |
| 0x33648..0x33960 | Sensor mode, timestamp, error control, subsample period, DMA masks, DONE/ERR/SOF enables and channel control |
| 0x33a80..0x33ba0 | Normal scenario with no RAW-derived exposures: routing values zero |
| 0x34150..0x34940 | First-order group0, no normal/last groups, lowest first-order tag selection |
| 0x33d44..0x33e78 | Frame cookie to all eight FH_SPARE registers |
| 0x349b0 / tables 0xf83c, 0xf88d | Bayer8 hardware format0, Bayer10 format1, Bayer10_MIPI format8; pack flag zero |

The native recipe preflights formats, geometry, grouping, every register target,
59-descriptor value capacity, CQ/raw/PDAF mapping overlap and session cookie
before mutating CQ memory. Error paths retain the first error and never publish
a partial ACK. Linear stride is `(owner.bytesperline << 16) | 0x10`.
Secondary-SMI/UFO fields are cleared only in the matched single-SMI branch.
The entire work slice stays owned, not just the 720 descriptor bytes.

PDAF **wire** DT30 and its maximum packet length do not determine memory bytes.
This code encodes the actual negotiated owner DMA format/crop/stride and retains
the frozen layout validator. BAYER8 versus packed BAYER10 PDAF and row padding
must still be proven with the sensor/receiver's actual emitted data before live
COMPOSER ownership may pass. Fixture BAYER8 layouts are test inputs, not a claim
that the handset outputs that packing. No bytes are inferred as RAW size/4.

## Actual CCD session/caller

`ipi_cam_handler` 0x39350 is the matching dispatcher. CREATE calls
`create_session` (0x34ab0); CONFIG calls `camsys_config` (0x34c80); FRAME maps the
message offset via `camsys_frame_get_frame_param` (0x35270), calls
`camsys_frame_process` (0x352c0) and emits a 75-byte ACK via `ccd_ipi_send`.
The latter calls ioctl 0xc40c6305. Mapping operations table at 0x63e70 points to
0x39860 (mmap64), 0x39910 (munmap) and 0x39930 (close). mmap takes the actual
process-local `ccd_fd` at buffer byte8 and size at byte12, with RW/MAP_SHARED.
This is CPU composition, not sensor SCP camera firmware.

`mt6878-camera-ccd-composer-session.h` implements that actual envelope lifecycle
without libccd/HAL execution or an external CQ callback. Ordered CREATE/CONFIG
have no fabricated ACK. FRAME is matched against the entire canonical frozen
0118 frame, calls the real native recipe and sets only ACK camsv[0]. Stale
endpoint/cookie, repeated frame, foreign planes/engines, undersized message and
mapping aliases are rejected. FLUSH drains synchronous composition; DESTROY
requires FLUSH and closes the session. Neither means that hardware DMA stopped.
Work/message/scratch mappings must be disjoint and their producer serialized.

`mt6878-camera-ccd-worker.c` contains the concrete Linux worker READ -> native
composition -> worker WRITE caller, using the pinned CCD UAPI. No Android HAL,
interpreter or dynamic libraries are required for this replacement composer.
It uses actual dma-buf CPU-access START/END ioctls before ACK publication;
unsupported exporters or sync failure fail closed, never bypass cache ownership.
This caller is compile-only: no executable is installed or started here.

## Worker lifetime and quiescence review

Pinned `mtk_ccd_rpmsg_ipi.c::ccd_worker_read` first has a 200ms
TASK_UNINTERRUPTIBLE endpoint-ready wait, then an unbounded interruptible queue
wait. Its `err_ret` path returns zero, including after interrupted queue wait.
The caller therefore treats zero-length envelopes as ENOMSG, not ready/success,
and never retries automatically. A direct ioctl EINTR is also propagated; the
fault fixture does not imply the pinned kernel always propagates that error.

`ccd_worker_write` is void; missing/destroyed endpoint or absent callback can
silently discard a WRITE. `ccd_unlocked_ioctl` still returns zero. Caller return
zero means only local ioctl acceptance, never proof of ACK receipt or capture.
The kernel owner must validate the actual returned cookie/session event and
hardware completion independently.

The API borrows session, message/work mappings, scratch and fds. They must remain
owned until the synchronous call returns; dispatch and teardown must not run
concurrently. Closing an fd in another thread is not a READ cancellation gate.
FLUSH only drains synchronous composition; DESTROY only retires the protocol
session. Neither proves CQ DMA finished, IRQs drained or endpoint callbacks
quiescent. Signal delivery is not proof that a worker exited, and CPU cache-sync
ioctls have no timeout guarantee here either.

Runtime teardown must stop accepting new frames, resolve outstanding CPU work,
observe worker termination/join and endpoint callback quiescence, then prove
CAMSV/CQ stop plus IRQ drain before freeing any CQ/output mappings. If any stage
does not quiesce, retain the referenced buffers/resources and fail visibly;
never unmap on a guessed delay or because FLUSH/WRITE returned zero. This
candidate does not implement that complete kernel/worker supervisor lifetime.

## Exact remaining integration gates

1. Main CI: static ELF/source checker, ASan/UBSan recipe/session fixtures,
   ASan/UBSan ioctl fault fixtures in `worker-test.c`, compile-only
   `mt6878-camera-ccd-worker.c`, explicit kernel recipe smoke object.
2. Native service owner: port/register `/dev/mtk_ccd` master/endpoint lifecycle,
   export valid work/msg fds **into the registered CCD process** and map them;
   verify that these exporters implement DMA_BUF_IOCTL_SYNC. Integers from the
   kernel sender's fd table are not enough. The current pmOS candidate does not
   yet provide this complete service/remoteproc personality.
3. Pinned worker READ uses an interruptible wait with no full receive timeout.
   Run it in a cancellable owned worker process, never the bounded control path
   or IRQ thread. No timeout/ready behavior is invented here.
4. Freeze 0117/0118 integration must bind full workbuf lifetime/cache proof,
   actual RAW/PDAF packing, route/tag groups and source-validated power/IOMMU.
   Recipe DONE/ERR/SOF enable writes are not IRQ acknowledgment writes. Pinned
   DONE handler reads FIRST_TAG, two FH_SPARE values and DONE_STATUS without
   writing status. Read-clear/W1C semantics remain a separate unresolved gate.
5. Only after these gates, main may enable a single RAW10/PDAF capture, check
   exact buffer payload/cookie/guards, perform bounded stop with IRQ drain, and
   verify USB/SSH. No DT or hardware activation is authorized by this candidate.

No matching vendor ISP firmware asset is selected or required by this native
restricted CPU composer. Full stock HAL dependencies/tuning are not silently
needed here; JPEG/3A/ISP processing and other modes are intentionally unsupported.
