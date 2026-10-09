# Compile-only pipeline owner: concrete memory and CCD transport

Candidate, not a camera Works claim. No probe, ioctl registration, production
archive linkage, DT enable, clock/rail/IRQ/MMIO access, or local native build.
`mt6878_pipeline_start` refuses activation with EOPNOTSUPP.

## Source/API boundary

Modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835:
`mtkcam/camsys/remoteproc/mtk_ccd_mem.c`,
`mtkcam/camsys/rpmsg/mtk_ccd_rpmsg.c`, `mtk_ccd_rpmsg_ipi.c`.
Device ee2be53cb75670b548948636a0db1d1ff112bf12:
`arch/arm64/boot/dts/mediatek/mt6878.dts`, CAMSV A/B WDMA supplier ports.
Linux API target: the pinned 6.18 tree used by main; map/vmap unlocked wrappers
take the reservation lock internally. DMA direction is BIDIRECTIONAL for owned
attachments, as in matching vendor CCD. No Android heap name is required:
the consumer supplies actual dma-bufs whose exporter supports these operations.

## Concrete operations

1. Initialize in the registered CCD consumer's user task, holding its task and
   DMA device references. Confirm the actual IOMMU domain, not a physical address
   or a domain inferred from a phandle. Recheck that identity on each operation.
   This adapter does not register the consumer with `/dev/mtk_ccd` by itself.
2. Import two actual fds using dma_buf_get, attach to the DMA owner and map via
   dma_buf_map_attachment_unlocked. Require one mapped SG entry covering the
   entire allocation and the 34-bit aperture; reject overlap and shared objects.
   Vmap only ordinary memory; unwind vmap/map/attach/ref in reverse order.
3. Export an additional reference with dma_buf_fd in that same task. Failure
   drops the extra reference; success transfers it to the process-local fd.
   Returned fds belong to userspace and are not silently closed by this owner.
   Export does not install fds in an unrelated task or prove service readiness.
4. Bind the enabled sensor -> SENINF media link, actual RAW10 format, three
   CPHY trios and both RAW/PDAF frame descriptors. Bind queued active single-plane
   vb2 buffers from the same DMA owner; prove cookie IOVAs and full capacity
   before constructing any CCD frame. No wire-to-DMA packing inference is made.
5. Create the actual RPMSG endpoint for matching `mtk-camsysN`, src=N+1. Pinned
   worker READ/WRITE look up client->ept, so the bus must serialize that assignment
   with remove and all sends. The wrapper delegates to the existing CCD owner;
   it does not substitute a success provider or invent a transport response.
6. Build the full frozen frame ABI into the owned message vmap under actual
   dma_buf_begin/end_cpu_access. Failed END leaves cpu_active set and keeps
   resources pinned. Queue CREATE/CONFIG with the verified process-local fds.
   Compose waits for the actual CCD FRAME event, validates its cookie/result
   and exact 720-byte restricted recipe span. An ACK never starts hardware.

Mapping, exporter callbacks, CPU sync, fd operations and RPMSG creation can
sleep; none is claimed bounded by this adapter. The existing CCD FRAME reply
timeout bounds the reply wait only, not an arbitrary supplier's send routine.

## Callback drain and retirement

The matching vendor also defines `mtk_rpmsg_ipi_handler`, which dereferences
ept->cb without cb_lock. Clearing ept->cb/priv under that mutex would not cover
this path. The new endpoint therefore keeps its callback/priv immutable and
uses a spinlocked closed gate plus active-delegate count. Closing refuses new
delegate entries; existing entries must return before drain reports success.
No endpoint callback pointer is nulled and no endpoint is destroyed here.

Detach takes nonblocking owner/CCD control locks, closes the callback gate and
retires the old CCD send pointer only when no delegate is in flight. It must
not race a CCD exchange. Gate success proves only that delegates are drained;
rejected callbacks may still enter the immutable wrapper and touch this owner.
Therefore endpoint and owner remain pinned. Vendor READ waiters and the bus
endpoint table need a separate owned cancellation/removal protocol before the
wrapper or its containing owner can be freed. Never infer that from FLUSH,
DESTROY, a signal, fd close, empty READ or successful WRITE.

Release is implemented for pre-publication/no-endpoint failure unwind only.
Once an endpoint or session is published it returns EBUSY and retains all refs,
even after logical callback drain. This intentional limitation avoids calling
the vendor's unbounded/racy endpoint destruction behind a placeholder proof.
No destructor/owner reuse is permitted on EBUSY. A failed CPU END also pins the
mapping until a later audited cleanup path exists; this candidate never retries.

Caller must serialize media graph/subdevice unbind, vb2 queue/buffer lifetime,
CCD worker execution and RPMSG bus remove throughout these operations. Device
references alone do not pin a subdevice driver instance. Only the bound consumer
task may control this owner; the callback path uses its separate spinlock.

## CI integration and exact next activation ownership

Main owns packaging/CI. Stage the new header/C/smoke/KUnit files beside existing
camera headers in `drivers/media/platform/mediatek/seninf/`, compile explicit
objects, and run `check.py` against pinned modules/device sources and verified
B4.1 assets. No Kconfig/Makefile/archive changes are supplied here. Required
existing dependencies are CCD session/owner (draft 0119), frozen composer/
capture owner (0118), CAMSV vb2 (0117), sensor/SENINF graph and frozen CQ recipe.
KUnit executable linkage needs CCD owner + capture owner + CAMSV vb2 objects;
object smoke alone is not execution evidence. `owner-kunit.c` exercises real
dma-buf core with a synthetic fault exporter and callback gate state; it does
not touch a phone. Neither KUnit nor native C has been run locally.

`STAGING.json` is the exact flattened 20-file source/header closure, five
explicit owner/API object targets, separate KUnit fault target and required
non-stub config symbols. All targets go in a fresh research-only directory,
never overwrite the already-patched `seninf/` tree. Config dependencies must
survive olddefconfig; hidden IOMMU_API needs the platform IOMMU driver selector.
The existing main research smoke at 79b9b11 does not yet stage these camera
objects. Untracked CCD owner/session dependencies require their own main review
and source hashes; presence in this manifest is not permission to ship them.

Next concrete gate: implement the CCD character-device/RPMSG bus owner with an
owned consumer-registration ioctl and worker/endpoint removal handshake; this
must prove callback wrapper/READ lifetime retirement, not accept a boolean.
Then supply the SENINF calibrated PHY/MAC + TSREC + VC/CAMMUX resource owner,
four CAMSV IRQ lines with proven DONE acknowledgment and bounded DMA/CQ stop.
Frozen graph still refuses stream-on; no exported PHY/stream owner connects it
to the mux yet. Bind the CAMMUX tag route and full CQ content/cache proof into
the frozen CAMSV backend before enabling any sensor stream or CQ submit.
Only then run one RAW10/PDAF capture, verify payload/guards/cookie, drain stop,
check USB/SSH, and repeat lifecycle validation. Sensor-link validation or a CCD
ACK is not that hardware gate.
