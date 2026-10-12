# CAMISP resource prerequisite (Untested)

This isolated candidate implements native MediaTek CCF gate providers for the
B4.1 MRAW and CAM_VCORE banks. It does not implement camera power ownership,
VMM, streaming, or a genpd. All devices in the reference description are disabled;
no shipping board includes it, and no shipping Kbuild, Kconfig or APKBUILD changes.

`evidence.json` records full input hashes from `git show` at device-module commit
`ee2be53cb75670b548948636a0db1d1ff112bf12` and camera-module commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. It retains the vendor power-domain
requirements rather than assigning them to an unproven native supplier.
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

Run static checks from the repository root:

```sh
python3 patches/camera-camisp/resources/generate.py --check --verify-vendor
python3 patches/camera-camisp/resources/check.py
python3 patches/camera-camisp/resources/test-source.py
python3 ci/test-kernel-object-smoke.py
```

Generation is deterministic from the frozen trace; `--verify-vendor` requires
the local pinned vendor repositories. CI checks the frozen trace and generated
bytes without network access to vendor sources. `clock-providers.patch` and
`disabled-description.patch` contain only new files, with no activation hunks.
The isolated object harness copies these exact source bytes into its own
directory and compiles the provider with KUnit enabled and disabled in CI only.
No parent Makefile is replaced, no module is linked/installed, and the DTS
fragment is copied but neither included nor compiled as a hardware DTB.

Next gates: isolated AArch64 object build, then a separately proven native
CAM_MAIN/CAM_VCORE power and VMM contract before any DT enablement or live test.
Compilation alone cannot establish cold-start safety or camera functionality.
