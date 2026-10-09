# Stock B4.1 LNA Provenance: GPIO Control Gate Required

**Result: 0020's claim that GPIO143/144 LNA controls match the Tetris vendor DT
is not supported by the inspected stock B4.1 artifacts. The r178 candidate
removes the six added GPIO/DSP LNA states and their GPS pinctrl references.
Do not substitute ioctl16 success for wiring proof. Existing installations
with those states must not run another GNSS control experiment before update.**

## Verified Local Chain

Cached archive: `Tetris_B4.1-260415-1709-image-boot.7z`, 38537291 bytes.
SHA256: `dc9a5e91460c8e1cdd91f143a63c00074b2471b208a46c636d09102595c4ff14`.

The existing extracted vendor_boot.img SHA256 matches the vendor_boot.img
entry extracted directly from this archive:
`69381599b4c96d23135d845f510e578c14151badb2ee4e01594e91dbc2d2776e`.
Its header places the DT payload at byte42004480. That payload exactly matches
the existing vendor_boot-unpacked/dtb file:
`dd6cc7dc56fc3e8a941ec12e7fb422ebeea4f23471b455b3a6e914e7993298f2`.

The payload is an Android DT table, not raw FDT (initial dtc invocation failed
on its table magic). It has one base FDT at payload offset64, SHA256:
`c819c38dd8b9702390e4bc3ce2d9cb804162babe61ef762c7770d116fa23dc16`.

Stock dtbo.img was read from the same cached archive without downloading or
flashing anything. SHA256:
`452c3754cbd0ab0522d9a89739786aadac4e6a64f7cf2735fd64aa0be306fb63`.
Its three entries have IDs0/1/2, revision0, and these hashes:

| Entry | Overlay SHA256 | Independently merged DT SHA256 |
| --- | --- | --- |
| 0 | b173f4be2a7095edd6ee958be4029341200bd4ea0e6e71a59537b21d28431e5e | 964e62c6670a6c4ea0c91821fdb92ab68e58987603d398bc3ba38698e597fe79 |
| 1 | ca60141b3b664e566aa96ffa05e6189e42c4b1fdbc4298ab17a171eb035de1c6 | cc3ec0fab996f949e1386ffc33a1c0e2e1d112ce5b58e082d374373496c54740 |
| 2 | e99ee44e1c558e7d0b95fe0034e815446752913f83c230277202e11516670379 | 4f64c976c4f73b47e477282c989a4ba6c4c8407a5d8bee3d1ceb9daf0bf80df9 |

Each overlay was applied separately with fdtoverlay to the extracted base.
Every application succeeded. All four resulting trees have
`/soc/gps@18c00000`, compatible `mediatek,mt6878-gps`, no explicit status,
no GPS pinctrl/LNA properties, and no L1/L5 LNA state markers. Absent status
is not equivalent to disabled; the missing GPIO-control records are the issue.
Wi-Fi/BT connfem epa-elna records are unrelated and were not treated as GPS LNA.

## Matching Source And Actual Risk

At device-modules pin `ee2be53cb75670b548948636a0db1d1ff112bf12`, the
k6878v1_64.dts GPS LNA reference block is under #if0; Tetris's include adds
no LNA override. The cached stock binary DT and all three DTBO choices agree
with that absence. No authoritative active override was found.

Modules pin `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` contains actual
gps_dl_lna_pin_ctrl calls in data_link/hal/gps_dl_power_ctrl.c (including the
power-on and wake paths). The helper selects pinctrl states. These calls are
not guarded by GPS_DRV_CONTROL_LNA; its Kbuild value n alone is not a reliable
runtime safety gate. Injecting 0020's enabled named states can therefore change
hardware behavior even though stock provides none. No damage or physical
miswiring is asserted; the unsupported GPIO-control behavior is enough to gate.

Metadata candidate0002 may remain as fail-closed infrastructure: after removing
unsupported 0020 records it should return ENODATA/ENODEV, not fabricated143.
That truthful failure cannot be fixed by adding guessed DT data. Required next
evidence is authoritative board/SKU wiring/control ownership, or independently
validated bootloader DT fixups with provenance and lifecycle checks.

## Reproduction And Limits

`audit_stock_lna_dt.py` reads local inputs only, verifies vendor-header/cache
and archive-entry equality, checks DT-table bounds, applies each DTBO in a
temporary directory, and queries GPS properties using fdtget. It never modifies
the cached stock files, shared patches, phone or network. Finding candidate
metadata in a future input does not automatically clear the GPIO-control gate.

Use --archive, --vendor-boot and --cached-dtb with the three local paths.
Requires existing 7zz, dtc, fdtget, fdtoverlay. bsdtar listed this solid archive
but failed its selected dtbo extraction; 7zz completed successfully.
Four synthetic container/header fault tests passed without native builds.

This is evidence from the locally named stock B4.1 archive, not cryptographic
OEM authentication, physical schematic proof, or a captured final stock-kernel
runtime DT. Overlay selection/bootloader fixups were not observed live.
Since every available stock overlay lacks the records, none can currently
support 0020's precise wiring claim. Further archive downloads are unnecessary
for establishing this immediate gate.
