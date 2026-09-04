# Nothing Tetris postmarketOS patch series

This repository carries a postmarketOS overlay for the Nothing CMF Phone 1
(`nothing-tetris`) on top of the MT6878 mainline kernel fork.

Official NothingOSS source selection and the module-first bring-up policy are
tracked in `docs/NOTHINGOSS_SOURCES.md`.

The current baseline is intentionally conservative:

- display uses the inherited framebuffer through `simpledrm`;
- native MediaTek DSI/DSC/panel support is not part of the active baseline;
- charger and PMIC telemetry uses a conservative 500 mA USB-debug policy until
  the source current is classified through BC1.2, Type-C Rp or PD;
- risky Android vendor stacks stay disabled until they are split into small,
  reviewable Linux-facing patches;
- NFC is not tracked because CMF Phone 1 / `nothing-tetris` has no NFC
  hardware.

## Kernel package versioning

The installed CI image uses `pkgver=6.18` and `pkgrel=127` at pmaports commit
`fdeeda042144e5ff1d2159f1590dbc5fb6b9392c`. CI run `33502390335` passed overlay
validation, the full kernel and device packages, install-image construction and
artifact upload. The downloaded image ZIP has SHA-256 `c47230ff07ebefe86faf54cf216bf7901279afbef482647389c91cd4a56bc996`, and all
three payload hashes match its manifest. The previous
`pkgrel=126` CI run `33495661863` completed the main kernel build but stopped on
a brittle disabled-Kconfig text check before compile-only IMX882 validation;
it produced no image.

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
| `0027-power-supply-nothing-tetris-charging-policy.patch` | Conservative board charging policy: 500 mA USB-debug limit, Nothing OS 4.1 battery CV, temperature cutoffs with hysteresis, fail-closed sensor handling and suspend inhibition. |
| `0054-power-supply-mt6375-bc12-compile-only.patch` | Compile-only MT6375 BC1.2 status decoder with fail-closed USB type/current mapping. It has no Kconfig, Makefile, hardware access, module or runtime path. |
| `0028-dt-bindings-watchdog-mediatek-mt6878-reboot-mode.patch` | Describes the MT6878 watchdog syscon and named reboot-mode child. |
| `0029-arm64-dts-mediatek-mt6878-enable-reboot-mode.patch` | Populates the reboot-mode child so `reboot bootloader` can reach U-Boot fastboot without physical buttons. |
| `0038-arm64-dts-mediatek-tetris-stop-ignoring-unused-clocks.patch` | Removes the stale argument from the packaged DTB. The verified U-Boot revision currently injects it again at `bootm`, so this patch alone does not change runtime clock policy. A one-shot boot without the argument failed and reset; keep unused-clock cleanup gated until the missing clock ownership is identified. |
| `0040-thermal-mediatek-mt6878-read-latched-msr.patch` | Uses the MT6878 vendor-style latched MSR read path. The `9afc17e` baseline returned only 6 of 24 LVTS values because mainline waited for a transient valid bit. Clean-flashed `ba02998` passed two gates with all 24 plausible LVTS temperatures while USB remained healthy. |

### Peripheral identification and staged bring-up

| Patch | Purpose |
| --- | --- |
| `0008-connectivity-mt6878-mt6631-connsys.patch` | MT6363 connectivity rails plus minimal MT6878/MT6631 connsys regulator/MMIO bring-up driver with sysfs validation hooks. MT6878 scpsys power-domain support still needs a separate port. |
| `0009-clk-mediatek-mt6878-mfg.patch` | MFG PLL/top mux clock foundation for future GPU work. |
| `0010-audio-mt6878-aw88261.patch` | MT6878 audiosys and topckgen audio clocks, including the programmable B4.1 SI1 MCK divider required by AW88261, audio SRAM/ETDM contract, speaker amplifier identification, and Tetris sound-card DT wiring for the vendor MT6878/MT6369 ASoC stack. |
| `0011-input-rt6010-haptics-tetris.patch` | RT6010 `FF_RUMBLE` driver using the Tetris B4.1 gain, boost, RAM layout and full-scale waveform 1 playlist, with atomic-safe workqueue execution, threaded protection IRQ handling, system-sleep recovery and Tetris DT enablement. |
| `0012-usb-typec-mt6375-tcpc-tetris.patch` | Disabled RT1711H inventory node plus MT6375 interrupt domain and minimal Linux TCPM/TCPCI Type-C driver. |
| `0013-iio-nvmem-mt6369-calibration.patch` | MT6369 AUXADC and efuse DT providers required by codec calibration and PMIC telemetry. |
| `0014-mmc-mt6878-tetris-sdcard.patch` | Native MT6878 MSDC1 host support and the Tetris microSD slot wiring. |
| `0015-leds-flash-lm3644-tetris.patch` | Native dual-channel LM3644 Linux LED flash-class driver and Tetris I2C/GPIO wiring. Both torch channels work live; timed strobe and V4L2 integration remain gated. |
| `0016-usb-typec-hl5280-audio-switch.patch` | HL5280 support in the Linux Type-C analog mux driver, including the vendor-required audio accessory sequence and MT6375 connector graph. |
| `0017-mfd-mt6363-auxadc-registers.patch` | MT6363 AUXADC register definitions shared by the official PMIC ADC and audio calibration modules. |
| `0018-pmdomain-mediatek-mt6878-audio.patch` | MT6878 audio power-domain wiring required by the staged ASoC card. |
| `0019-arm64-dts-mt6878-shallow-cpuidle.patch` | Corrects CPU0-3 to Cortex-A55 and CPU4-7 to Cortex-A78 from live MIDR evidence, and limits the first PSCI cpuidle rollout to per-CPU power-off. Cluster, MCU and system states remain gated behind live USB/SSH validation. |
| `0020-arm64-dts-mt6878-gnss.patch` | Publishes the manual MT6878 GNSS transport and exact Tetris LNA pinctrl states. The service verifies both vendor devnodes without opening the links. A position fix is not yet proven. |
| `0021-usb-mtu3-native-role-switch.patch` | Connects the MT6375 Type-C graph to MTU3 and selects kernel dual-role support while keeping peripheral mode as the safe default. Host mode remains unsupported until OTG VBUS ownership is implemented and validated. |
| `0030-regulator-mediatek-mt6878-gpu-rails.patch` | Adds compile-only MT6363 VSRAM_CPUM inventory and enables the existing MT6319-compatible regulator provider config. No GPU rail DT consumer or Mali node is enabled. |
| `0047-media-i2c-pd9302a-vcm.patch` | Stages the PD9302A VCM driver with the corrected revision-specific initialization and a bounded suspend park path. It remains compile-only and is not autoloaded. |
| `0049-media-i2c-imx882-identity.patch` | Adds a compile-only IMX882 physical-ID probe using the exact B4.1 `0x0016/0x0017` ID registers and bounded board power sequence. The shipped config remains off, the build produces no module, and no camera DT client is added. `pkgrel=127` also removes stale DTS text that patch tooling previously ignored outside any valid hunk. |
| `0050-drm-panel-samsung-s6e8fc3x02.patch` | Adds the native S6E8FC3X02 binding and panel source behind a disabled Kconfig symbol. The package builds only its object for compatibility evidence and rejects any shipped module; no DSI graph, autoload or framebuffer change is included. |
| `0055-arm64-dts-mediatek-tetris-imx882-disabled-fixture.patch` | Records the reviewed stock main-camera I2C8 address, CAMTG2/CMMCLK1, reset and four switched rails. The sensor and every new regulator are disabled; shared I2C8 status/frequency, EEPROM, actuator, media graph and runtime behavior remain unchanged. |

### NothingOSS module adaptations

| Patch | Purpose |
| --- | --- |
| `1000-vendor-connectivity-adapter-linux-6.18.patch.vendor` | Adapts the official MediaTek connectivity adapter from Nothing OS 4.1 to the Linux 6.18 kernel ABI used by this package. |
| `1001-vendor-connectivity-linux-6.18-compat.patch.vendor` | Adapts the official MT6878/MT6631 conninfra, Wi-Fi and Bluetooth modules to Linux 6.18 and exposes Bluetooth through native Linux HCI. |
| `1002-vendor-gnss-linux-6.18-compat.patch.vendor` | Adapts the official Nothing OS 4.1 MT6878 GNSS v051 external module selected by stock-derived Tetris product configuration to Linux 6.18. |
| `1101-vendor-audio-optional-calibration.patch.vendor` | Keeps optional PMIC calibration failures explicit while allowing the MT6369 codec to probe when a provider is unavailable. |
| `1102-vendor-audio-linux-6.18-api.patch.vendor` | Adapts the official MT6878/MT6369 ASoC stack to Linux 6.18 APIs and the Tetris composite I2S4 pinctrl state. |
| `1103-vendor-audio-mt6685-clock.patch.vendor` | Adds the official MT6685 BBCK5 supplier and selects the MT6878 MTKAIF clock pin. Live tests prove this clock is required by the earpiece and both built-in microphones. |
| `1200-vendor-sensor-framework-linux-6.18.patch.vendor` | Adapts the official MediaTek sensor framework core to Linux 6.18; only the framework module is staged and no sensor is advertised as working yet. |
| `0032-vendor-sensorhub-fail-closed-handoff-linux-6.18.patch.vendor` | Adapts the sensorhub transport to Linux 6.18, removes automatic SCP reset recovery and fails closed when shared memory or IPI setup is unavailable. |
| `0036-vendor-scp-linux-6.18-api.patch.vendor` | Adapts the official SCP provider to Linux 6.18 timer, platform remove, bin-attribute and MT6397 APIs. |
| `0037-vendor-tinysys-transport-linux-6.18-api.patch.vendor` | Adapts the MediaTek mailbox, RPMSG and IPI transport to Linux 6.18 headers, tracepoints and string APIs. |
| `0041-vendor-scp-fail-closed-dvfs-timeout.patch.vendor` | Bounds the vendor SCP DVFS probe wait at three seconds, unregisters the DVFS driver and returns `-ETIMEDOUT` instead of flooding WARN forever. A `ba02998` manual probe returned after 3.09 seconds with one diagnostic, no retained `scp` module, no WARN/Oops and no USB loss. Contract validation confirms the immediate cause is no matching `mediatek,scp-dvfs` platform device; adding that node alone is rejected until firmware, TCM and carveout handoff is proven. This patch fixes failure containment only. |

The next `pkgrel=128` source package stages Nothing OS 4.1 MT6878 connectivity modules from the
official Nothing kernel module releases. Connectivity firmware is isolated in
`firmware-nothing-tetris`, and connectivity/audio modules are built and shipped
inside the matching kernel package. The official `connadp` bridge is built and
loaded before `conninfra`; it provides the WMT, CONAP/SCP diagnostic,
stack-dump, and connectivity power-throttling interfaces consumed by Wi-Fi and
Bluetooth and the manual GNSS v051 transport. Installed `pkgrel=127` still
uses the previously validated v050 transport.
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
Nothing Tetris 16b MT6878 audio module stack (`mt6685-core`, `mt6685-audclk`,
`snd-soc-mtk-common`, `snd-soc-mt6369`, `snd-soc-mt6878-afe`,
`mt6878-mt6369`) and wires the MT6369 PMIC codec plus AW88261 speaker amplifier
into the board DT. The device package installs UCM routes for the main speaker,
earpiece and AIN0/AIN2 built-in microphones. UCM opens DL6 directly as the
two-channel transport required by the AW88261. A PulseAudio drop-in hides that
transport and exposes the single physical main speaker as a one-channel mono
sink, so application stereo is downmixed before it reaches ALSA. This replaces
the discarded ALSA `route` and `dshare` experiments, which produced silent or
corrupted system event streams despite clean direct hardware playback. This is a
practical overlay bring-up step, not an upstream-ready replacement for native
Linux connectivity/audio support. Linux 6.18 compatibility changes are normal
source patches instead of build-time source transformations. Patch `1000`
adapts the vendor connectivity bridge to Linux 6.18, while `1001` adapts the
MT6878 connectivity modules themselves. The audio bridge
uses `1101` for optional calibration handling and `1102` for Linux 6.18 ASoC
helper and namespace API changes. Patch `1103` supplies MT6685 BBCK5 and the
MTKAIF clock pin required by the codec.

The package also builds and ships `mtk-mbox`, `mtk_rpmsg_mbox`,
`mtk_tinysys_ipi`, `scp`, `hf_manager` and `sensorhub` as a dependency-checked
set. None of these new SCP/sensor modules is autoloaded. Live module loading is
gated on the reboot-to-fastboot rollback path, firmware/reserved-memory audit,
idle-power baseline and USB NCM/SSH regression checks. A manual `9afc17e` probe
loaded the mailbox, RPMSG, IPI and HF framework modules, but `scp.ko` then hung
in `wait_scp_dvfs_init_done()` and flooded WARN messages because the DVFS
platform contract never completed. Clean-flashed `ba02998` proved that this
same missing contract now fails closed after 3.09 seconds without retaining
`scp`, producing WARN/Oops, or losing USB. `sensorhub.ko` was not loaded. SCP
remains manual-only until the missing handoff is supplied.

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
- The native panel source is compile-only. Native MT6878 DSI/DSC/PHY and an
  active display graph are intentionally not in this series.

## Next clean patch targets

1. Observe MT6375 source classification with a USB 2.0 host, a known Type-C Rp
   1.5 A source and a known 5 V BC1.2 DCP. The bounded 500 mA path works, but
   TCPM reported `CURRENT_MAX=0` and native BC1.2 SDP/CDP/DCP publication is
   missing. Preserve USB NCM while validating DP/DM ownership; leave PD/OTG off.
2. Validate the clean CI U-Boot and postmarketOS images, Wi-Fi association/DHCP,
   native Bluetooth discovery and factory Bluetooth address provisioning.
3. Validate LM3644 timed strobe and add the V4L2 flash bridge with the camera
   stack; both torch channels already pass bounded live tests.
4. Validate the GNSS EMI handoff and LNA states, then obtain a position fix
   while Wi-Fi, Bluetooth and USB remain stable.
5. Validate the packaged audio stack from a clean CI image, then repeat both
   speaker/microphone paths and suspend/resume lifecycle tests.
6. Sensorhub/IIO for rotation, proximity and ambient light.
7. Continue compile-only modem/CCIF/DPMAIF and camera sensor boundaries in
   parallel; activate each only after its power, memory and firmware contract
   is complete.
