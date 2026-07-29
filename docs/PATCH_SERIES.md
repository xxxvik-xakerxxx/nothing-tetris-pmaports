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

The kernel package currently uses `pkgver=6.18` and `pkgrel=66`.

`pkgrel` is high because this port had many hardware-test rebuilds before being
cleaned up for publication. Do not reset it while devices may already have
r50-r66 packages installed; that would make future packages look like
downgrades. For public releases, tag the repository with `v0.x.y` and keep the
APK package version monotonic.

When the kernel source commit or `pkgver` changes, reset `pkgrel` according to
normal Alpine/postmarketOS practice.

## Active patch groups

### Base board support

| Patch | Purpose |
| --- | --- |
| `0001-arm64-dts-mt6878-nothing-tetris-add-FT3519-touch.patch` | Board DT for FT3519 touch and related pinctrl/regulator wiring. |
| `0002-input-touchscreen-add-focaltech-ft3519t.patch` | Vendor-derived FT3519 touchscreen driver with debug logging disabled by default. Large and not upstream-quality yet, but required for working touch. |
| `0003-mt6878-add-mt6369-spmi-pmic.patch` | MT6369 SPMI PMIC/regulator foundation required by touch and peripheral rails. |
| `0011-arm64-dts-mt6878-nothing-tetris-add-disabled-peripherals.patch` | Hardware inventory nodes kept disabled until drivers are ready, including MT6631 connsys/Wi-Fi/BT/GNSS. |
| `0025-pinctrl-mediatek-mt6878-fill-eint-table-holes.patch` | EINT table fix needed by board interrupts. |

### Stable framebuffer display path

| Patch | Purpose |
| --- | --- |
| `0012-drm-sysfb-add-full-frame-update-quirk.patch` | Marks the Tetris inherited framebuffer as requiring full-frame updates. |
| `0013-drm-sysfb-flush-inherited-framebuffer-cache.patch` | Flushes CPU cache for the inherited framebuffer. |
| `0014-drm-sysfb-limit-cache-clean-to-damage.patch` | Narrows the cache clean path where possible. |
| `0015-drm-sysfb-use-iomem-copy-for-tetris.patch` | Uses an MMIO-safe copy path for the Tetris framebuffer. |

### PMIC, keys and power telemetry

| Patch | Purpose |
| --- | --- |
| `0016-mt6878-add-mt6363-keys-and-mt6375-telemetry.patch` | MT6363 PMIC keys and MT6375 read-only telemetry foundation. |
| `0029-power-supply-mt6375-add-read-only-monitor.patch` | Read-only battery/USB monitor. |
| `0030-regulator-mt6363-add-connectivity-rails.patch` | Connectivity regulator rails only; consumers stay disabled. |
| `0032-power-supply-mt6375-register-monitor-on-platform-bus.patch` | Registers the read-only monitor from the platform bus. |

### Peripheral identification and staged bring-up

| Patch | Purpose |
| --- | --- |
| `0033-asoc-aw88261-identify-tetris-speaker-amp.patch` | Identifies the AW88261 speaker amplifier. Does not create an ALSA card. |
| `0034-clk-mediatek-mt6878-add-mfg-plls.patch` | Adds MFG PLL/top mux clock foundation for future GPU work. |
| `0035-input-rt6010-haptics.patch` | Adds a conservative RT6010 `FF_RUMBLE` driver using vendor init/trim and stream playback. |
| `0036-arm64-dts-mt6878-tetris-enable-rt6010-haptics.patch` | Enables the RT6010 node for the haptics driver. |
| `0037-clk-mediatek-mt6878-audiosys.patch` | Adds MT6878 audiosys clock foundation. Audio still needs AFE/machine-driver work. |
| `0038-arm64-dts-mt6878-tetris-add-rt1711h-typec-inventory.patch` | Adds disabled RT1711H Type-C inventory node. |
| `0039-usb-typec-mt6375-tcpc.patch` | Adds the MT6375 interrupt domain and a minimal Linux TCPM/TCPCI Type-C driver. |
| `0040-soc-mediatek-mt6878-add-consys-bringup-driver.patch` | Adds a minimal MT6878/MT6631 connsys regulator/MMIO bring-up driver with sysfs validation hooks. MT6878 scpsys power-domain support still needs a separate port. |

The r66 package also stages Android MT6878 connectivity modules from the Nothing
kernel module releases and installs the MT6631 Wi-Fi firmware blob into the
device package for on-device validation. This is a practical overlay bring-up
step, not an upstream-ready replacement for native Linux connectivity support.

The kernel config deliberately keeps `CONFIG_TYPEC_RT1711H` disabled. The
detected `5-004e` I2C client is the MT6375 TCPC bank exposed by the MT6375 MFD,
not a confirmed external RT1711H controller.

## Known cleanup debt

- `0002` is a large vendor touchscreen drop. It works, but should eventually be
  reduced or rewritten around existing Linux input patterns.
- Some historical patches are bare diffs rather than complete
  `git format-patch` output. They are accepted by `abuild`, but future work
  should use normal commit-style patches with subject, rationale and sign-off.
- Patch numbering has gaps from discarded native-display experiments. Keep the
  gaps for now to avoid noisy file renames; new patches should use the next
  free number and a clear subsystem prefix.
- Native DSI/display patches are intentionally not in this active series.

## Next clean patch targets

1. Validate MT6375 Type-C attach/orientation/role events on device, then remove
   the disabled RT1711H inventory node if hardware confirms it is not populated.
2. Validate r66 MT6631 vendor module loading on device: conninfra, WMT, Wi-Fi
   and Bluetooth.
3. Flashlight as LED-class/V4L2 flash.
4. GNSS/FM clients after Wi-Fi/BT connectivity is stable.
5. MT6878 AFE + MT6369 machine driver + AW88261 routing + UCM.
6. Sensorhub/IIO for rotation, proximity and ambient light.
7. Modem/SIM and cameras as later large projects.
