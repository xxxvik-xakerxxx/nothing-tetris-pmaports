# Disabled CAMISP board fixture (Untested)

The separate supplier board and explicit blocked observer-to-owner delta are
documented in [SUPPLIER-WIRING.md](SUPPLIER-WIRING.md). They have a distinct
`SUPPLIER-STAGING.json` check plan. The original fixture below remains
nonbootable even though it compiled in CI38317130122; it is not the new
baseline-preserving candidate. No parent CI or shipping integration is changed.

This isolated candidate implements native MediaTek CCF gate providers for the
B4.1 MRAW and CAM_VCORE banks. It does not implement camera power ownership,
VMM, streaming, or a genpd driver. All new devices in the reference description are disabled;
no shipping board includes it, and no shipping Kbuild, Kconfig or APKBUILD changes.

`evidence.json` records full input hashes from `git show` at device-module commit
`ee2be53cb75670b548948636a0db1d1ff112bf12` and camera-module commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`, plus native binding bytes from Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`. It now translates source-proven
CAM_MAIN/CAM_VCORE resource dependencies to the real native onecell SPM owner.
MRAW has nine set/clear gates (status/set/clear 0/4/8). CAM_VCORE has two
inverted read/modify/write gates at 0x2c. The parent names map the vendor
`top_cam_ck`/`top_camtm_ck` to the pinned native `cam_sel`/`camtm_sel` muxes.
The clock indices retain the B4.1 ABI in a separate header; CAM_MAIN IDs stay
in the existing native header.

The disabled fragment describes the actual chain: logical CAMISP 13/14 with
two IOMMU ports each; physical larbs 13/14; subcommons 16/19; CAM_VCORE common31;
the existing display common. It uses native one-cell-address `reg` entries,
`mediatek,smi` PM links, and the common31 `mediatek,smi-supply` reset-owner link.
IOMMU membership retains display larb0. It defines a disabled CAM_MAIN clock
node because the packaged provider has no board node. No physical resources
are assigned to a logical DMA node.

## Native Power Board

`mt6878-nothing-tetris-camisp-disabled.dts` includes the existing native board,
then the resource and native-power fragments. It is a **compile-only board**,
not an overlay intended to be applied at runtime or a boot/install artifact.
It explicitly disables the existing SPM controller and MM_INFRA, so booting it
would interfere with native display PM. Shipping sources are unchanged.

`mt6878-camisp-native-power-disabled.dtsi` extends `&mm_infra` with disabled
CAM_VCORE -> CAM_MAIN and sibling ISP_VCORE. It does not redefine SPM,
MM_INFRA, HWV, a synthetic shared-VMM domain, or any MMIO controller. The native
integration's internal shared-VMM graph remains that driver's responsibility.
CAM_MAIN has the real TOPCKGEN `cam` clock followed by the eight B4.1 protection
clocks, with names `cam_main-0` through `cam_main-7`. Native clock IDs are traced
separately from vendor IDs; CAM_MAIN IDs are not assumed numerically identical.
VCORE nodes have no clocks or per-domain supplies, matching the parent contract.

The fragment extends the already described `&mt6319_gpu` direct SPMI USID6
provider, with no second PMIC at address 6. The existing compatible, USID,
explicit buck1 phase mask 1, regulators container and disabled VBUCK2 are
retained unchanged, including `mediatek,observe-vgpu-only`. That observer route
does not register regulators: switching to actual registration needs a separate
reviewed ownership migration, not just enabling these nodes or silently deleting
the observer property. Disabled VBUCK1 supplies both controller VCORE properties;
the real controller itself is disabled in this isolated fixture. Disabled
VBUCK4 retains the stock `regulator-always-on` constraint. Source voltage bounds
and ramp delay are copied as constraints, **not an operating point**; no initial
voltage, mode, clock rate, OPP or boot-on request is introduced. Disabled nodes
are not registered, so this description makes no PMIC writes.

Activation is blocked on firmware/MMUP ownership migration, including the two
source-proven VBUCK1 users (vmmspm and MMDVFS debug), an actual voltage/rate
policy, safe cold OFF/ON and lifecycle evidence. Linux-exclusive acquisition
alone does not establish firmware ownership. Wider CAM/ISP descendants remain
outside the native provider slice. This fixture proves no image capture.

Run static checks from the repository root:

```sh
python3 patches/camera-camisp/resources/generate.py --check --verify-vendor
python3 patches/camera-camisp/resources/check.py
python3 patches/camera-camisp/resources/test-source.py
python3 patches/camera-camisp/resources/test-dt.py
```

Generation is deterministic from the frozen trace; `--verify-vendor` requires
the local pinned vendor repositories. CI checks the frozen trace and generated
bytes without network access to vendor sources. Read-only parent input hashes
freeze the actual display/MM_INFRA, GPU-supply, regulator and native integration
contracts; changed parent bytes require review, not blind regeneration.
`clock-providers.patch` and
`disabled-description.patch` contain only new files, with no activation hunks.
The isolated object harness copies these exact source bytes into its own
directory and compiles the provider with KUnit enabled and disabled in CI only.
No parent Makefile is replaced, no module is linked/installed, and the DTS
fixtures are staged. The existing harness does not automatically build the new
board target; the parent must opt into the explicit target in `STAGING.json`.

## Parent CI Handoff

Apply the additive description patch, or stage the exact manifest sources,
after preparing the pinned package tree. No DTS Makefile change is necessary
for an explicit single-board Kbuild target. In CI only, compile the unchanged
native base and `mediatek/mt6878-nothing-tetris-camisp-disabled.dtb` with normal
board Kbuild flags (no overlay `-@` symbol export), then run:

```sh
python3 -B patches/camera-camisp/resources/check-dt.py \
  --base path/to/mt6878-nothing-tetris-native.dtb \
  --fixture path/to/mt6878-nothing-tetris-camisp-disabled.dtb
```

The checker uses the repository's existing read-only `fdtget` tree reader and
typed phandle comparison. It checks the exact additive node inventory, disabled
owners/children, native hierarchy, paired real rail, ordered clock phandles,
physical/SMI/IOMMU resources and preservation of every unrelated baseline
property, including existing USID6 rails and MM_INFRA HWV. `test-dt.py` exercises
those guards on synthetic tree dictionaries, without a compiler or hardware.
DTB compilation and dt-schema checks have **not** been run for this fixture.

Next gates: parent CI board compilation/schema validation and combined native
provider link, then physical ownership/policy closure before any DT enablement.
Compilation alone cannot establish cold-start safety or camera functionality.
