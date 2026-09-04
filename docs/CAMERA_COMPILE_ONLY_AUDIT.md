# Nothing Tetris camera compile-only audit

Status: static/package gate only. Nothing in this change can probe a camera,
enable a rail or clock, register a media device, start SENINF, or boot CCU.

## Source boundary

The audit is pinned through the kernel package to the Nothing OS 4.1 Tetris
source pair:

- camera modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`;
- device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`.

`0051-vendor-camera-tetris-compile-only-audit.patch.vendor` adds one object-only
build target. It has no `module_init`, platform/I2C driver, module metadata,
firmware request, CCU call, or hardware access. The package build requires the
object to compile and rejects a generated `.ko`.

## Assertions

The object compiles against the matching `kd_imgsensor.h` and rejects source
drift in the exact Tetris variant IDs:

| Role | Variants | IDs | Bus/address | CSI |
| --- | --- | --- | --- | --- |
| Main | IMX882 / IMX882TXD | `0x8202` / `0x8203` | I2C8 / `0x1a` | 1 |
| Front | GC16B3C / GC16B3CTXD | `0x16b3` / `0x16b4` | I2C4 / `0x10` | 0 |
| Auxiliary | SC202CS / SC202CSSJ | `0xeb52` / `0xeb53` | I2C7 / `0x36` | 2A |

The IDs are compile-asserted against the pinned headers. Bus, address and CSI
columns are manually reviewed B4.1 Tetris DTS evidence; the object records them
but does not independently derive or validate those wiring assignments.

The package gate also requires all six sensor source directories and the four
Tetris cam-cal layouts for IMX882/IMX882TXD and GC16B3C/GC16B3CTXD. Those
layouts use vendor 8-bit write ID `0xA0` (7-bit EEPROM address `0x50`), maximum
size `0x4000`, and preload size `0x1500` in the B4.1 source.

SC202CS/SC202CSSJ are deliberately rejected if a same-name cam-cal layout
appears without review. The current Tetris DTS has no auxiliary EEPROM client;
the vendor sensor drivers instead contain their own module-ID path. This audit
does not read either path and never copies calibration data.

The SENINF check is source-only: MT6878 must remain selected under the `isp7sp`
implementation and provide `mt6878_data`. SENINF is not compiled or linked by
this gate because its clock, power-domain, SMI, DMA/IOMMU and CCU ownership is
not yet validated for mainline Linux.

## Packaging boundary

The audit object is built after the main kernel, inspected, and discarded. It
is absent from `modules_install`, initramfs, rootfs module directories,
`modules-load.d`, udev rules, and service presets. The shipped kernel config and
DT remain unchanged, so a clean install has the same camera runtime behavior as
the preceding image.

This boundary is integrated into the active candidate. Its package revision is
raised only after the preceding `r128` CI result is known, so two concurrent
candidate definitions never share one published package identity.

## First safe live gate

The first device gate is observation-only on a clean CI image:

1. Record artifact hashes, bootloader, slot, kernel/DTB and package versions.
2. Confirm USB NCM/SSH and Wi-Fi before collecting camera state.
3. Record existing I2C adapters, `/dev/media*`, `/dev/video*`, loaded modules,
   failed services, and the first camera/CCU/SENINF/IOMMU errors.
4. Confirm no camera I2C client, audit module, CCU firmware request, camera
   power-domain transition, or new kernel fault appears.
5. Repeat across three cold boots and run the existing USB/Wi-Fi regression
   gate after each boot.

Do not run `i2cdetect`, raw EEPROM reads, load a camera module, toggle a camera
GPIO/regulator/clock, or start CCU during this gate. Any USB/SSH or Wi-Fi
regression rejects the image and returns testing to the previous artifact.
