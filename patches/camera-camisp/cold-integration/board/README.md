# Producer-Driven Board Root: Untested

`board-owner.patch` adds an actual built-in CAMSV0 platform resource driver and
producer-publication caller atop the frozen cold integration. Only this new
directory is edited. It is not packaged/installed; the selector defaults to n
and the DT fragment stays disabled. There is no capture or compile result.

## Actual Call Path

Probe resolves three explicit DT supplier phandles (logical CAMISP larb14,
existing CAM_MAIN, existing common31 reset owner), retaining real device and
receiver fwnode references. It rejects a self/wrong/disabled/dynamic supplier,
root IOMMU ownership and a receiver outside the main sensor's CSI port 1.
Probe **does not call the capture constructor** or pretend the root is bound.

The real producer calls `mt6878_cold_board_publish(pdev, layout, config)` after
driver-core binding, with a pdev reference and stable negotiated metadata.
The caller must hold neither root device_lock nor native capture locks. The
entry checks the actual driver identity and `device_is_bound()` before reading
drvdata, drops device_lock before the constructor's supplier pinning, validates
the native VMM attachment, copies the supplied metadata unchanged and calls
`mt6878_cold_capture_register`. This fixes the probe-time permanent deferral
without fake binding, a probe retry or a placeholder format.

`mt6878_cold_board_wait` observes the existing actual notifier completion.
`mt6878_cold_board_retire` invokes checked native unregister. A non-NULL failed
owner stays stored; retirement failure releases nothing. Successful retirement
ends this one-shot instance. Root/devm claims remain until reboot. The driver
is built-in, hides bind attributes, rejects dynamic DT and has no remove or
shutdown adapter. Forced platform removal remains unsupported, as in the
frozen constructor's persistent-supplier contract.

Binding is only resource ownership, not readiness. Runtime-PM bookkeeping in
probe is not physical OFF proof. In exact Linux d84, platform core calls
`dev_pm_domain_attach(... PD_FLAG_ATTACH_POWER_ON ...)` **before probe**;
single-domain genpd attach can power on. Do not enable this DT to exercise the
caller before the existing native supplier/VMM/MMUP admission is proven. No
generic platform/genpd behavior or legacy/secure owner is overridden here.

## Source And DT Evidence

- Linux `d84b264a54a37611f2f46bc19363cb9b41606205`: exact archive checksum,
  driver-core bound semantics, platform/domain attachment and native DT cells.
- Device NOS B4.1 `ee2be53cb75670b548948636a0db1d1ff112bf12`: `mt6878.dts`
  CAMSV id0 six banks, four IRQs, eight clocks, CAM_MAIN and larb14; matching
  `cust_mt6878_camera_v4l2.dtsi` connects sensor0 (IMX882/IMX882TXD) to CSI1.
- Camera NOS `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`:
  `mtk_cam-job_utils.c:handle_sv_tag` obtains metadata geometry from the actual
  request's SV sink; `mtk_cam-job.c:mtk_cam_job_fill_ipi_config_only_sv` copies
  actual per-tag inputs and uses INIT flags. Both sensor variants specify PDAF
  RAW10 remapping. `evidence.json` records exact blob IDs and file hashes.

The reviewed root DT references the tracked frozen supplier-resource fixture,
not new regulator/SMI/IOMMU owners. Native soc reg encoding is **one address +
one size cell**, translated from NOS 64-bit cells; native GIC retains **four
interrupt cells**, including the zero affinity field. It adds no display-IOMMU
membership, voltage, frame dimensions or producer metadata. The endpoint has
no fabricated remote phandle: a reviewed reciprocal SENINF endpoint is still
required. This is an incomplete disabled fragment, not a boot-ready board.

## Exact Missing Producer Prerequisite

No matching installed native producer currently calls the publication entry.
The next required implementation is a source-backed adapter that emits the
frozen native recipe's **actual output-DMA layout and per-tag input config**
from negotiated producer data. NOS's PDAF `REMAP_TO_RAW10` does not prove the
frozen native queue's Bayer8 output width/stride/packing. NOS's INIT config also
does not satisfy the frozen recipe's flags=0 restriction. This root rejects
nonzero flags; it does not erase them, invent Bayer8 geometry, or install a
fake worker. Missing metadata returns `-ENODATA` after a genuine bound point.

The real reciprocal receiver/efuse graph, common31 membership input, native
USID6 voltage/rate policy and observed MMUP/firmware voting handoff remain
required before activation. Available legacy voter admission remains unchanged.

## Source Checks And Parent Integration

```sh
python3 -B patches/camera-camisp/cold-integration/board/generate.py
python3 -B patches/camera-camisp/cold-integration/board/check.py
python3 -B patches/camera-camisp/cold-integration/board/test_board.py
```

Explicit archive/device/modules path options are supported. `stage.py` requires
those three paths plus `--cold-staged-kernel`: it checks the actual CI copy's
input hashes and patch applicability **without editing it**. Apply this delta
only to the parent's disposable, cold-staged `work/kernel-source`, never the
normal prepared source. No new compiler runner or parent workflow edit is made.
Parent CI must enable `VIDEO_MT6878_COLD_BOARD=y`, build
`drivers/media/platform/mediatek/tetris-cold/board/mt6878-cold-board.o` and link
vmlinux, preserving ThinLTO/CFI and the existing real object-identity check.
Inspect the three publish/wait/retire exports. Do not enable the DT afterward
solely because linkage passed; dt-schema/DTB and hardware gates remain unrun.
