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

The kernel package currently uses `pkgver=6.18` and `pkgrel=101`.

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
| `0004-arm64-dts-mt6878-tetris-disabled-peripherals.patch` | Board peripheral inventory plus the hardware-tested MT6631 conninfra reserved-memory/PMIC contract. Wi-Fi and Bluetooth are enabled; unvalidated clients remain disabled. |
| `0006-pinctrl-mediatek-mt6878-eint.patch` | EINT table fix needed by board interrupts. |

### Stable framebuffer display path

| Patch | Purpose |
| --- | --- |
| `0005-drm-sysfb-tetris-framebuffer.patch` | Stable inherited U-Boot framebuffer path for Tetris: full-frame updates, cache flushes, damage-limited cleaning and MMIO-safe copy. |

### PMIC, keys and power telemetry

| Patch | Purpose |
| --- | --- |
| `0003-mfd-mt6363-keys-mt6375-telemetry.patch` | MT6363 PMIC core, hardware-tested power/volume-up press and release IRQ handling, and MT6375 telemetry foundation. |
| `0007-power-supply-mt6375-monitor.patch` | Read-only battery/USB power monitor and platform registration. |

### Peripheral identification and staged bring-up

| Patch | Purpose |
| --- | --- |
| `0008-connectivity-mt6878-mt6631-connsys.patch` | MT6363 connectivity rails plus minimal MT6878/MT6631 connsys regulator/MMIO bring-up driver with sysfs validation hooks. MT6878 scpsys power-domain support still needs a separate port. |
| `0009-clk-mediatek-mt6878-mfg.patch` | MFG PLL/top mux clock foundation for future GPU work. |
| `0010-audio-mt6878-aw88261.patch` | MT6878 audiosys and topckgen audio clocks, audio SRAM/ETDM contract, AW88261 speaker amplifier identification, and Tetris sound-card DT wiring for the vendor MT6878/MT6369 ASoC stack. |
| `0011-input-rt6010-haptics-tetris.patch` | RT6010 `FF_RUMBLE` driver using the Tetris B4.1 gain, boost, RAM layout and full-scale waveform 1 playlist, with atomic-safe workqueue execution, threaded protection IRQ handling, system-sleep recovery and Tetris DT enablement. |
| `0012-usb-typec-mt6375-tcpc-tetris.patch` | Disabled RT1711H inventory node plus MT6375 interrupt domain and minimal Linux TCPM/TCPCI Type-C driver. |
| `0013-iio-nvmem-mt6369-calibration.patch` | MT6369 AUXADC and efuse DT providers required by codec calibration and PMIC telemetry. |
| `0014-mmc-mt6878-tetris-sdcard.patch` | Native MT6878 MSDC1 host support and the Tetris microSD slot wiring. |
| `0015-leds-flash-lm3644-tetris.patch` | Native dual-channel LM3644 Linux LED flash-class driver and Tetris I2C/GPIO wiring. Both torch channels work live; timed strobe and V4L2 integration remain gated. |
| `0016-usb-typec-hl5280-audio-switch.patch` | HL5280 support in the Linux Type-C analog mux driver, including the vendor-required audio accessory sequence and MT6375 connector graph. |
| `0017-mfd-mt6363-auxadc-registers.patch` | MT6363 AUXADC register definitions shared by the official PMIC ADC and audio calibration modules. |
| `0018-pmdomain-mediatek-mt6878-audio.patch` | MT6878 audio power-domain wiring required by the staged ASoC card. |
| `0019-arm64-dts-mt6878-shallow-cpuidle.patch` | Corrects CPU0-3 to Cortex-A55 and CPU4-7 to Cortex-A78 from live MIDR evidence, and limits the first PSCI cpuidle rollout to per-CPU power-off. Cluster, MCU and system states remain gated behind live USB/SSH validation. |
| `0020-arm64-dts-mt6878-gnss.patch` | Publishes the MT6878 GNSS transport after live DT boot, probe, IRQ and power-cycle validation; module loading remains manual. |
| `0021-usb-mtu3-native-role-switch.patch` | Connects the MT6375 Type-C graph to MTU3 while keeping peripheral mode as the safe default; it remains staged because kernel dual-role mode and OTG VBUS ownership are not complete. |
| `1002-vendor-gnss-linux-6.18-compat.patch.vendor` | Adapts the official Nothing OS 4.1 MT6878 GNSS v050 external module to Linux 6.18 without selecting unrelated v060/v061 profiles. |

The `pkgrel=101` package stages Nothing OS 4.1 MT6878 connectivity modules from the
official Nothing kernel module releases. Connectivity firmware is isolated in
`firmware-nothing-tetris`, and connectivity/audio modules are built and shipped
inside the matching kernel package. The official `connadp` bridge is built and
loaded before `conninfra`; it provides the WMT, CONAP/SCP diagnostic,
stack-dump, and connectivity power-throttling interfaces consumed by Wi-Fi and
Bluetooth and the staged GNSS v050 transport.
The boot service loads the bridge, WLAN and native-HCI Bluetooth modules in the
hardware-tested order. It extracts the 6146-byte per-device Wi-Fi calibration
from `nvdata`, performs one WMT NVRAM write, completes joint pre-calibration and
powers Wi-Fi before NetworkManager and BlueZ start. It also extracts only the
six-byte factory Bluetooth address and provisions it through the standard
kernel HCI/BlueZ MGMT path before `bluetooth.service`. On-device testing
confirmed automatic joint pre-calibration across three clean boots, Wi-Fi scans
of 77, 75 and 79 BSS, native BlueZ discovery, address persistence across a
controller power cycle and simultaneous radio operation without WFSYS/BGFSYS
reset. The standalone `wmt_drv` is not installed because
it duplicates symbols already provided by `conninfra` in this source
combination.
The vendor `conninfra` cleanup path also oopses if the module is unloaded, so
connectivity tests must use a clean boot instead of module remove/reload cycles.
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
2. Validate the clean CI U-Boot and postmarketOS images, Wi-Fi association/DHCP,
   native Bluetooth discovery and factory Bluetooth address provisioning.
3. Validate LM3644 timed strobe and add the V4L2 flash bridge with the camera
   stack; both torch channels already pass bounded live tests.
4. GNSS/FM clients after Wi-Fi/BT connectivity is stable.
5. Validate the `pkgrel=100` audio-clock image, then test every physical
   speaker/microphone path and add UCM profiles.
6. Sensorhub/IIO for rotation, proximity and ambient light.
7. Modem/SIM and cameras as later large projects.
