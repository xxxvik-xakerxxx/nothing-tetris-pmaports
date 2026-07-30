# Nothing Tetris postmarketOS patch series

This repository carries a postmarketOS overlay for the Nothing CMF Phone 1
(`nothing-tetris`) on top of the MT6878 mainline kernel fork.

The current baseline is intentionally conservative:

- display uses the inherited framebuffer through `simpledrm`;
- native MediaTek DSI/DSC/panel support is not part of the active baseline;
- charger and PMIC telemetry is read-only where possible;
- risky Android vendor stacks stay disabled until they are split into small,
  reviewable Linux-facing patches;
- NFC is not tracked because CMF Phone 1 / `nothing-tetris` has no NFC
  hardware.

## Kernel package versioning

The kernel package currently uses `pkgver=6.18` and `pkgrel=76`.

`pkgrel` is high because this port had many hardware-test rebuilds before being
cleaned up for publication. Do not reset it while devices may already have
r50-r76 packages installed; that would make future packages look like
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
| `0010-audio-mt6878-aw88261.patch` | MT6878 audiosys clock foundation plus AW88261 speaker amplifier identification. Audio still needs AFE/machine-driver work. |
| `0011-input-rt6010-haptics-tetris.patch` | Conservative RT6010 `FF_RUMBLE` driver using vendor init/trim and stream playback, plus Tetris DT enablement. |
| `0012-usb-typec-mt6375-tcpc-tetris.patch` | Disabled RT1711H inventory node plus MT6375 interrupt domain and minimal Linux TCPM/TCPCI Type-C driver. |

The r76 package also stages Android MT6878 connectivity modules from the Nothing
kernel module releases and installs the MT6631 Wi-Fi firmware blob into the
device package for on-device validation. This is a practical overlay bring-up
step, not an upstream-ready replacement for native Linux connectivity support.

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

1. Validate MT6375 Type-C attach/orientation/role events on device, then remove
   the disabled RT1711H inventory node if hardware confirms it is not populated.
2. Validate r76 MT6631 vendor module loading on device: conninfra, WMT, Wi-Fi
   and Bluetooth.
3. Flashlight as LED-class/V4L2 flash.
4. GNSS/FM clients after Wi-Fi/BT connectivity is stable.
5. MT6878 AFE + MT6369 machine driver + AW88261 routing + UCM.
6. Sensorhub/IIO for rotation, proximity and ambient light.
7. Modem/SIM and cameras as later large projects.
