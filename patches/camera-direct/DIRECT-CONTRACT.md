# Direct first-frame CAMSV owner

Kernel-only owned draft. No CCD daemon, private ioctl, RPMSG, remoteproc or
firmware service. Existing recipe/encoder filenames retain `ccd` for provenance;
they are pure memory functions and impose no transport dependency. Existing
draft and frozen files are untouched. Nothing is registered or enabled at boot.

## Executable path

1. Native platform capture consumer calls `mt6878_camsv_direct_init` with its
   actual platform device, bound CAMISP larb port supplier and real CAMSV
   hardware backend. Existing resource getter owns six named resource mappings,
   four IRQ numbers and eight clock handles; it does not enable power or IRQ.
   Recipe register starts come from `platform_get_resource_byname`, never a
   handset address. Coherent CQ uses the same port device/domain as vb2 WDMA.
   Device references preserve object identity; they do NOT prevent devres removal.
2. `direct_queue_init` configures native VIDEO_CAPTURE and META_CAPTURE vb2
   queues with one shared mutex, dma-contig memops and MMAP/DMABUF. Existing
   capture driver must provide real vb2_ops, lists, format negotiation and media
   graph/video registration; no placeholder ops or private userspace UAPI added.
3. Under the common queue mutex, both buffers must be ACTIVE with one plane,
   matching queue allocator, zero data_offset and a real dma-contig cookie.
   `direct_submit` obtains IOVAs/capacities from vb2, not caller job addresses.
   It calls existing `mt6878_camsv_recipe` directly into `dma_alloc_coherent`
   memory. Descriptor head and tail values share the retained allocation.
   `dma_wmb` orders the complete CQ before frozen capture submit/CQ START.
4. Composer verification uses actual encoder finish/head/tail/allocation state,
   exact output buffers and current IOMMU domain, not caller ready booleans.
   Real backend RESOURCES/IOMMU/ROUTE/IRQ verification remains mandatory before
   frozen submit can do any MMIO. Its COMPOSER gate is supplied by this direct
   owner because it actually generated/owns the coherent CQ.
5. Sole native DONE IRQ consumer calls `direct_done` in a threaded context under
   the shared mutex. After power/IRQ gates, it reads the exact pinned order:
   inner FIRST_TAG, outer FH_SPARE, inner FH_SPARE, central DONE_STATUS.
   Inner sequence and actual group bits accumulate via existing capture logic.
   Return 1 records complete tags; neither queue is returned or freed here.
   Full DONE is latched once: later calls return EALREADY without MMIO and
   cannot replace the original observed timestamp. No stop/reset/drain is
   called by this IRQ entry point.
   First causal ownership/read-gate error is cached before MMIO; subsequent
   calls return it without another status read. Foreign inner sequence or
   duplicate groups are returned as ESTALE/EALREADY, not fabricated completion.
6. Controller must stop actual sensor/SENINF/CAMMUX/TG/VF, disable/drain the
   owned IRQ lines OUTSIDE the common queue mutex/IRQ thread, then call
   `direct_stop` under lock. STOPPED verification is checked before consuming
   the frozen one-shot reset. Existing bounded reset/SMI sequence establishes
   quiescence. Only then buffers become DONE for a full error-free frame, or
   ERROR on aborted/error capture. References are cleared after buffer_done.
   Both DONE and ERROR preserve the observed full-DONE timestamp when present;
   aborted frames without a full DONE use the controller completion time.
   STOPPED is checked by the real hardware backend, not a caller-set quiesced
   bit. Calling this controller entry point from its own IRQ thread is invalid.
7. `direct_release` refuses ANY MMIO-attempted CQ without proven quiescence.
   Failed stop retains coherent CQ, queues, suppliers, clock/IRQ context and
   driver/devres. Never call vb2 queue release or unbind/free parent on that
   failure. No devm DMA allocation silently freed during an unsafe remove.

One zero-initialized owner supports one frame. No streaming loop, frame reuse,
subsampling, RAW/MRAW engine, compressed output, second SMI, additional group
or scenario. Modes remain 4000x3000 and 4096x2304; recipe accepts only its
source-supported linear RAW10 layouts/tags. PDAF wire remapping is distinct
from emitted DMA format: byte stride/sizeimage come from explicit negotiated
layout, not RAW bytes / 4. Full CQ allocation is range/overlap checked, not
only its descriptor head. DMA zero is legal. First causal errors are retained.

## Evidence and closure

Sources: modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835,
`mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c` and its register/reset interfaces;
device ee2be53cb75670b548948636a0db1d1ff112bf12 resource/IOMMU description;
matching B4.1 libccd recipe already frozen/reviewed. No ELF execution needed.
The existing 59-write native recipe and CQ encoder are reused, not rewritten.

STAGING.json is an eleven-file flat closure: new direct C/header/smoke plus
frozen vb2 C/header, capture/register headers, recipe/encoder, internal IPI
configuration types and IRQ offsets. Explicit objects: direct, vb2, smoke.
No CCD owner/session/pipeline/composer ACK parser/worker/private RPMSG header.
No new native daemon or transport build/config requirement. Config needs actual
DMA/IOMMU/media/vb2 selections; no local C compilation and no shipped linkage.
Main integration can reuse the existing camera-owner isolated destination:
its 20-file closure already supplies every dependency here. Add only direct
C/header/smoke (20 -> 23 sources), and direct/direct-smoke object targets
(main's 6 -> 8 objects). Do not duplicate the shared harness source dictionary
or overwrite the same basenames in two research destinations. This standalone
eleven-file manifest documents an independently daemon-free closure only.

## Exact remaining consumer

This does NOT claim a captured frame. A native MT6878 platform/media driver
still must own and implement:

- CAM_MAIN runtime power, its eight clocks, CAMSYS_TOP reset/golden settings,
  both CAMISP supplier lifetimes and the verified larb14 (SV-A)/larb13 (SV-B)
  CQI/WDMA domain. SMI common31 clamp must be owned, not a guessed register write.
- IMX882 power/stream ownership, enabled sensor->SENINF media links, calibrated
  CPHY receiver, CAMMUX tag/VC mapping and actual TG/VF start/stop. The coherent
  CQ is only the existing proven CAMSV first-frame register recipe.
- Four CAMSV IRQ consumers with chip/source-proven acknowledgment. DONE reads
  are reused exactly; this draft adds no assumed write-clear. IRQ disable and
  synchronization cannot occur while holding a mutex its threaded handler needs.
- Real vb2_ops/media graph/video nodes and deterministic stop/reset recovery.
  vb2 stop_streaming is void: registering a user-facing streaming node before
  guaranteed safe DMA stop can allow core queue destruction or deadlock. This
  draft therefore does not register a node or pretend that boundary is solved.

Next gates: isolated ARM64 objects, then provider-backed test-kernel lifetime
checks (unsupported owner before MMIO; failed stop keeps CQ/buffers; complete
tags alone cannot return buffers). Only after power/route/IRQ/reset owners are
validated may main activate DT and attempt one frame while preserving USB.
