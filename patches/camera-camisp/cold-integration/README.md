# Integrated Cold Capture Candidate: Untested

This directory owns a generated implementation patch and a CI-only native
built-in link gate. It changes no frozen input, APKBUILD, workflow, shipping
configuration or DTS. The patch is **not packaged or installed**. The new
`VIDEO_MT6878_COLD_CAPTURE` bool defaults to n. No hardware capture is claimed.

## Exact Inputs

- Linux `d84b264a54a37611f2f46bc19363cb9b41606205`: archive SHA512 verified
  against APKBUILD before extracting any framework/provider input.
- NOS B4.1 device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`:
  GPIO/clock topology, SCPSYS parents and rail, VMM/MMDVFS firmware voters.
- NOS B4.1 camera modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`:
  sensor resources/sequence and existing CAM/larb consumer PM contracts.
- Frozen stream-owner and rail-owner patch/evidence hashes are enforced.
  All other reused sources are tracked files with recorded SHA256. No
  pre-existing untracked CCD source is adopted. Vendor inputs use exact Git
  objects, never checkout HEAD. `evidence.json` records the full file census.

The input profile is the **normal packaged source preparation**, including
0121 identity MCLK, not an already-staged stream/rail/native-VMM tree. All
selected packaged inputs have tracked provenance and APKBUILD SHA512 checks.
Legacy package preparation follows `ci/check-kernel-patch-stack.py` rules;
0098 currently needs the same context fuzz as normal preparation after 0092
inserts a clock Makefile line. This adjustment is recorded, not hidden. The
**new patch** has strict `git apply --check` and application/byte comparison.
Actual prepared input files must match those reconstructed hashes before
staging. This includes pristine archive GPIO/pinctrl implementations and the
packaged 0006 EINT table delta. Other native/provider profiles fail explicitly.

## Installed Call Sites In The Candidate

The new real Kbuild composite contains 16 production units: CAMSV vb2/CQ,
platform/hardware, SMI backend, SENINF route/controller/PM/graph, native
capture/video, cold probe/reset/joint reset, CAMISP logical DMA, and the
registration entry. It excludes standalone smoke, emulation, CCD bus and
worker objects. Kbuild suppresses the original resource-only graph object
only when this composite is selected, preventing a duplicate graph owner.
The original clock, SMI, IOMMU and pmdomain drivers remain the suppliers.

- Sensor `.enable_streams`/`.disable_streams` use the existing active-state
  mutex and frozen checked stream lifecycle; `.s_stream` uses the pinned
  V4L2 helper. Core `.s_power(0)` rejects active native streaming and calls
  the same checked stop. It does not infer OFF from a software stream mask.
  Existing 24 MHz CAMTG2_SEL/UVPLL192M_D8 source locking, reset, regulator
  references and uncertain-removal retention are unchanged.
- The real SENINF route now queries active sensor format through the pinned
  state helper, rather than passing NULL to `v4l2_subdev_get_fmt`.
- SENINF PM checks the actual attached CAM_MAIN genpd supplier after domain
  resume and before programming clocks/vote. Failure latches and retains
  acquired references; suspend does not release them after the first error.
- Both CAMSV power acquisition and SENINF resume validate the actual installed
  domain owner **before** requesting PM resume. This read-only admission permits
  initial OFF, proves no voltage/readiness, and prevents an unknown genpd from
  receiving a camera activation request before the powered check rejects it.
- CAMSV's actual powered-resource gate checks that same supplier before
  hardware accesses. The new public accessor first identifies the installed
  native runtime-resume and ON/OFF callbacks, then accesses the original
  SCPSYS storage. It checks the actual domain ID and current PM lease before
  calling the existing mutex-protected VMM checker. It creates no rail owner.
- `mt6878_cold_capture_register` enters the existing video constructor. That
  constructor checks bound, non-self CAMSV/DMA/CAM_MAIN/SMI suppliers,
  SV0/larb14 or SV1/larb13, common31, matching receiver graph endpoint and
  actual runtime-PM links. Existing constructor checks still require static
  suppliers with retained device/module lifetime. Video queues call the real
  joint cold probe/frame path, not the old standalone CAM_MAIN reset helper.

The registration entry is exported but **has no installed board-root caller**.
The caller must provide the actual supported RAW10/PDAF layout, configuration
and receiver fwnode, and retain a non-NULL failed owner until checked retirement.
No default producer metadata or ready cookie is provided. Successful native
linkage will not make that missing caller or a CCD service exist.

## Native Link Closure

The media composite and sensor/rail selectors are built-in only; SMI, IOMMU,
CAM clock and SCPSYS must resolve to y. Native VMM helper objects are linked
only through their existing provider Kbuild. MRAW/CAM_VCORE gate providers are
connected to clock Kbuild, without adding another voltage policy.

The runner inspects these real export definitions before and after vmlinux:
`mt6878_cold_capture_register`, `mt6878_native_video_unregister`,
`mt6878_native_video_wait_ready`, `mt6878_camera_vmm_check`,
`mt6878_camera_vmm_validate_domain`,
`mt6878_cam_main_prepare/regmap/retire`, `mtk_smi_camera_reset_clamp`, and
`mt6878_camisp_dma_idle`. Missing config dependencies, compile errors, lost
exports or unresolved native linkage fail with the actual current target.
No compile/link result has been obtained locally.

## Remaining Activation Inputs

1. Native USID-6 VBUCK1 registration/constraints, validated camera voltage/rate
   policy and observable MMUP/firmware VMM voting handoff remain missing.
   Available legacy notifier/MMDVFS nodes retain the admission `-EBUSY` veto;
   removing/disabling them proves no handoff. Unsupported CAM/ISP descendants
   remain `-EOPNOTSUPP`. Cached-ON genpd cannot bypass the native resume guard.
2. The disabled common31 fixture lacks the reset owner's `mediatek,comm-port-id`
   membership input: enabling it as-is fails the real provider admission path.
   Physical common0/31/16/19, larb13/14, IOMMU and their PM links still need
   reviewed DT integration. No generic pinctrl or supplier rewrite is added.
3. Sensor rail DT must select the frozen GPIO owner before activation. That
   owner observes MODE/DIR/DI/DO through the actual pinctrl owner before ASIS,
   rejects alternate mux/high/unknown state, and permits checked input-low cold
   startup. Snapshot and exclusive request are not an atomic firmware/mux
   handoff; Linux GPIO exclusivity alone does not exclude firmware or a
   non-strict pinmux claimant. No inherited-ON takeover is permitted.
4. CSI_RX/CAM_MAIN resources, named clocks, calibrated rg_csi nvmem, SAT
   mapping and source-backed IRQ retirement require actual DT/runtime proof.
   SENINF G1 nonzero status still fails `-EOPNOTSUPP` without an ACK contract.
5. The existing mapped CCD worker only owns process mappings/composition and
   retirement tickets. Its kernel bus/controller counterpart, installation,
   negotiated producer data and checked DMA retirement remain unresolved.
   This direct native CQ path uses the tracked memory recipe, not libccd or a
   fabricated CCD session. Wider ISP/RAW ownership is outside this slice.

## Checks And Parent CI Call

From repository root, source-only commands (explicit path options supported):

```sh
python3 -B patches/camera-camisp/cold-integration/generate.py
python3 -B patches/camera-camisp/cold-integration/check.py
python3 -B patches/camera-camisp/cold-integration/test_cold_integration.py
```

`stage.py` accepts the same three **required** source path arguments as the
runner plus `--prepared-kernel`; it only checks actual input hashes and patch
application without changing that prepared tree. The CI call requires a fresh
normal prepared source tree, isolated output/report directories and both CI
markers. It accepts no sibling-archive default:

```sh
python3 -B patches/camera-camisp/cold-integration/run_ci.py \
  --kernel-archive "$LINUX_ARCHIVE" \
  --device-repo "$NOS_DEVICE_REPO" --modules-repo "$NOS_CAMERA_REPO" \
  --prepared-kernel "$PREPARED_KERNEL" \
  --output "$COLD_LINK_OUTPUT" --report "$COLD_LINK_REPORT"
```

CI copies the normal prepared tree into its own output directory and stages
only that independent source copy. The original input is rechecked on exit;
reports do not include the copied source, build directory or vmlinux.
CI uses the repository's LLVM toolchain. It preserves shipping ThinLTO, CFI and
related security settings across olddefconfig, inspects **actual AArch64 LLVM
bitcode or ELF** using `kernel-object-smoke.object_identity`, builds actual
production/provider units, and links real vmlinux. It builds no DTB, boots
nothing and installs/loads nothing. The manifest distinguishes started,
failed (including current leaf target), and passed-native-link; none is a
camera readiness or capture status. Parent owns workflow/package wiring.
