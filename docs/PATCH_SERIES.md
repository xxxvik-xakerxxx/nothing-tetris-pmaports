# Nothing Tetris postmarketOS patch series

This repository carries a postmarketOS overlay for the Nothing CMF Phone 1
(`nothing-tetris`) on top of the MT6878 mainline kernel fork.

Official NothingOSS source selection and the module-first bring-up policy are
tracked in `docs/NOTHINGOSS_SOURCES.md`.

The current baseline is intentionally conservative:

- display uses the inherited framebuffer through `simpledrm`;
- native MediaTek DSI/DSC/panel support is not part of the active baseline;
- charger and PMIC telemetry is read-only where possible;
- risky Android vendor stacks stay disabled until they are split into small,
  reviewable Linux-facing patches;
- NFC is not tracked because CMF Phone 1 / `nothing-tetris` has no NFC
  hardware.

## Kernel package versioning

The kernel package currently uses `pkgver=6.18` and `pkgrel=85`.

`pkgrel` is high because this port had many hardware-test rebuilds before being
cleaned up for publication. Do not reset it while devices may already have
r50-r77 packages installed; that would make future packages look like
downgrades. For public releases, tag the repository with `v0.x.y` and keep the
APK package version monotonic.

When the kernel source commit or `pkgver` changes, reset `pkgrel` according to
normal Alpine/postmarketOS practice.

## Active patch groups

### Base board support

| Patch | Purpose |
| --- | --- |
| `0001-input-touchscreen-ft3519t-tetris.patch` | Board DT plus vendor-derived FT3519 touchscreen driver. Large and not upstream-quality yet, but required for working touch. |
| `0002-mfd-mt6369-spmi-pmic.patch` | MT6369 SPMI PMIC/regulator foundation required by touch and peripheral rails. |
| `0004-arm64-dts-mt6878-tetris-disabled-peripherals.patch` | Hardware inventory nodes kept disabled until drivers are ready, including MT6631 connsys/Wi-Fi/BT/GNSS. |
| `0006-pinctrl-mediatek-mt6878-eint.patch` | EINT table fix needed by board interrupts. |

### Stable framebuffer display path

| Patch | Purpose |
| --- | --- |
| `0005-drm-sysfb-tetris-framebuffer.patch` | Stable inherited U-Boot framebuffer path for Tetris: full-frame updates, cache flushes, damage-limited cleaning and MMIO-safe copy. |

### PMIC, keys and power telemetry

| Patch | Purpose |
| --- | --- |
| `0003-mfd-mt6363-keys-mt6375-telemetry.patch` | MT6363 PMIC core, PMIC key support with state resync on IRQ, and MT6375 telemetry foundation. |
| `0007-power-supply-mt6375-monitor.patch` | Read-only battery/USB power monitor and platform registration. |

### Peripheral identification and staged bring-up

| Patch | Purpose |
| --- | --- |
| `0008-connectivity-mt6878-mt6631-connsys.patch` | MT6363 connectivity rails plus minimal MT6878/MT6631 connsys regulator/MMIO bring-up driver with sysfs validation hooks. MT6878 scpsys power-domain support still needs a separate port. |
| `0009-clk-mediatek-mt6878-mfg.patch` | MFG PLL/top mux clock foundation for future GPU work. |
| `0010-audio-mt6878-aw88261.patch` | MT6878 audiosys clock foundation, AW88261 speaker amplifier identification, and Tetris sound-card DT wiring for the vendor MT6878/MT6369 ASoC stack. |
| `0011-input-rt6010-haptics-tetris.patch` | Conservative RT6010 `FF_RUMBLE` driver using vendor init/trim and stream playback, plus Tetris DT enablement. |
| `0012-usb-typec-mt6375-tcpc-tetris.patch` | Disabled RT1711H inventory node plus MT6375 interrupt domain and minimal Linux TCPM/TCPCI Type-C driver. |
| `0013-iio-nvmem-mt6369-calibration.patch` | MT6369 AUXADC and efuse DT providers required by codec calibration and PMIC telemetry. |
| `0014-mmc-mt6878-tetris-sdcard.patch` | Native MT6878 MSDC1 host support and the Tetris microSD slot wiring. |
| `0015-leds-flash-lm3644-tetris.patch` | Native dual-channel LM3644 Linux LED flash-class driver and Tetris I2C/GPIO wiring. |
| `0016-usb-typec-hl5280-audio-switch.patch` | HL5280 support in the Linux Type-C analog mux driver, including the vendor-required audio accessory sequence and MT6375 connector graph. |
| `0017-mfd-mt6363-auxadc-registers.patch` | MT6363 AUXADC register definitions shared by the official PMIC ADC and audio calibration modules. |

The r86 package stages Tetris 16b Android MT6878 connectivity modules from the
Nothing kernel module releases. Connectivity firmware is isolated in
`firmware-nothing-tetris`, and connectivity/audio modules are ABI-locked kernel
subpackages. The official `connadp` bridge is built and loaded before
`conninfra`; it provides the WMT, CONAP/SCP diagnostic, stack-dump, and
connectivity power-throttling interfaces consumed by Wi-Fi and Bluetooth.
It also stages the official
Nothing Tetris 16b MT6878 audio module stack (`snd-soc-mtk-common`,
`snd-soc-mt6369`, `snd-soc-mt6878-afe`, `mt6878-mt6369`) and wires the MT6369
PMIC codec plus AW88261 speaker amplifier into the board DT. This is a
practical overlay bring-up step, not an upstream-ready replacement for native
Linux connectivity/audio support. Linux 6.18 compatibility changes are normal
source patches instead of build-time source transformations. Patch `1000`
adapts the vendor connectivity bridge to Linux 6.18, while `1001` adapts the
MT6878 connectivity modules themselves. The audio bridge
uses `1101` for optional calibration handling and `1102` for Linux 6.18 ASoC
helper and namespace API changes.

The kernel config deliberately keeps `CONFIG_TYPEC_RT1711H` disabled. The
detected `5-004e` I2C client is the MT6375 TCPC bank exposed by the MT6375 MFD,
not a confirmed external RT1711H controller.

## Known cleanup debt

- `0001` contains a large vendor touchscreen drop. It works, but should eventually be
  reduced or rewritten around existing Linux input patterns.
- Some historical patches are bare diffs rather than complete
  `git format-patch` output. They are accepted by `abuild`, but future work
  should use normal commit-style patches with subject, rationale and sign-off.
- Patch numbering is contiguous and grouped by hardware/function. Keep future
  additions in that style: one patch file per maintained hardware block.
- Native DSI/display patches are intentionally not in this active series.

## Next clean patch targets

1. Validate MT6375 attach/orientation/role handling after correcting the TCPCI
   register window. The r63 live regmap confirms vendor ID `0x29cf` and product
   ID `0x6375` in the main bank; the old `0xf200` mapping read only zeros.
2. Validate r76 MT6631 vendor module loading on device: conninfra, WMT, Wi-Fi
   and Bluetooth.
3. Validate LM3644 torch/strobe channels and add the V4L2 flash bridge with
   the camera stack.
4. GNSS/FM clients after Wi-Fi/BT connectivity is stable.
5. Validate Tetris 16b vendor audio modules on device, then add UCM profiles
   for speaker and microphones.
6. Sensorhub/IIO for rotation, proximity and ambient light.
7. Modem/SIM and cameras as later large projects.
