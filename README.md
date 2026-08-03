# Nothing CMF Phone 1 postmarketOS overlay

postmarketOS overlay for the Nothing CMF Phone 1 (`nothing-tetris`, model
A015, MediaTek MT6878 / Dimensity 7300).

The repository is intentionally small: it tracks only the device package,
kernel package, patch series, validation scripts, and CI config needed to build
the postmarketOS port. Full upstream source trees, generated images, local
logs, and device backups are not committed.

## Device

| Field | Value |
| --- | --- |
| Manufacturer | Nothing |
| Name | CMF Phone 1 |
| Codename | `nothing-tetris` |
| Model | A015 |
| Released | 2024 |
| Type | Handset |
| Chipset | MediaTek Dimensity 7300 (`MT6878`) |
| CPU | 4x Cortex-A55 + 4x Cortex-A78 |
| Display | 1080x2400 AMOLED |
| Storage | 128/256 GB UFS |
| Memory | 6 GB in some markets, 8 GB common |
| Architecture | `aarch64` |
| Vendor source baseline | Nothing OS 4.1 (`Tetris-B4.1-260415-1709`) |
| NFC | Not present |

## postmarketOS

| Field | Value |
| --- | --- |
| Category | `testing` |
| UI | Phosh |
| Bootloader | U-Boot FIT image |
| FOSS boot path | Yes |
| Device package | `device/testing/device-nothing-tetris` |
| Kernel package | `device/testing/linux-postmarketos-mediatek-mt6878` |
| Kernel version | `6.18-r88` package (`#89` build) |
| Kernel source commit | `d84b264a54a37611f2f46bc19363cb9b41606205` |
| Device DTB | `mt6878-nothing-tetris` |

Patch grouping and cleanup debt are documented in [docs/PATCH_SERIES.md](docs/PATCH_SERIES.md).
Driver packaging and vendor-to-native migration are documented in
[docs/DRIVER_STRATEGY.md](docs/DRIVER_STRATEGY.md).

## Feature Status

| Area | Feature | Status | Notes |
| --- | --- | --- | --- |
| Boot | U-Boot boot flow | Works | Uses `fastboot oem board:boot_pmos` and FIT image handoff. |
| Boot | Kernel boot | Works | Mainline MT6878 kernel reaches userspace. |
| Display | Simple framebuffer | Works | Stable inherited framebuffer through `simpledrm`. |
| Display | Native DSI/panel | Broken | Native display bring-up is intentionally not in the active baseline. |
| Input | Touchscreen | Works | FT3519 touchscreen is enabled. |
| Input | Hardware keys | Works | Power, volume-up and GPIO volume-down are hardware-tested; MT6363 uses distinct press/release IRQ handlers. |
| Power | Battery/USB telemetry | Partial | Read-only MT6375 monitor is present. Charging control is not implemented. |
| Power | CPU idle | Pending validation | The next kernel enables only per-CPU PSCI power-off; cluster/system idle states remain disabled until USB/SSH survival is proven. |
| Power | Thermal management | Broken | The running kernel has no thermal class or zones. Nothing OS 4.1 provides MT6878 LVTS data for 24 sensors across MCU/AP/GPU domains, but it is not integrated yet. |
| USB | Device mode / NCM | Works | The pmOS USB gadget enumerates and carries stable SSH traffic without RX/TX errors. |
| USB-C | Type-C attach/orientation | Partial | MT6375 TCPC reports reverse orientation, sink power, device data role and charging. MTU3 dual-role support is disabled, `/sys/class/usb_role` is empty, and host mode/wake remain unvalidated. |
| USB-C | Analog audio switch | Pending validation | r86 wires the HL5280 to the MT6375 Type-C connector and uses its required audio-accessory sequence. |
| Haptics | RT6010 rumble | Works (live) | The native driver uses the official B4.1 RAM waveform through `FF_RUMBLE`; full-strength and repeated bounded effects work without kernel, USB or radio faults. |
| Haptics | Clean-install integration | Pending validation | The device package autoloads `rt6010` and identifies it to feedbackd. A clean CI-artifact flash, suspend/resume and cold-boot repetition remain. |
| Audio | Speaker amp identification | Partial | AW88261 probes, identifies chip `0x2113` and loads `aw88261_acf.bin`; physical output is not validated. |
| Audio | Playback/recording | Partial | MT6878 AFE, MT6369, AW88261 and the machine card register automatically. ALSA exposes playback and capture endpoints, but both speakers, every microphone, routing/UCM and lifecycle tests remain. |
| GPU | 3D acceleration | Broken | MFG clock groundwork and `panthor.ko` exist, but no Mali platform device or render node is present; `card0` is the inherited simple framebuffer. |
| Camera | Front/rear cameras | Broken | No V4L2/media nodes are present. Sensors, SENINF/ISP, clocks, power domains, IOMMU and userspace still need a staged port. |
| Camera | Torch | Works (live) | Both LM3644 rear LED channels accept bounded brightness effects, illuminate physically and return to off without USB or radio faults. |
| Camera | Flash strobe | Pending validation | The Linux flash class exposes both channels; timed strobe, fault reporting and the V4L2 camera-flash bridge remain unvalidated. |
| Connectivity | Connsys foundation | Partial | `connadp`, `conninfra` and `connfem` probe reliably at boot; vendor `conninfra` cannot be safely unloaded. |
| Connectivity | Wi-Fi | Partial | B4.1 WLAN firmware, factory NVRAM, scans and Wi-Fi/Bluetooth coexistence work live. Clean-install automatic startup is staged for CI validation. |
| Connectivity | Bluetooth | Partial | Native BlueZ HCI, factory address provisioning, discovery and Wi-Fi coexistence work live. Clean-install automatic startup still requires CI image validation. |
| Connectivity | GPS/GNSS | Partial | The B4.1 MT6878 v050 module probes seven IRQs and completes a real DSP open/close power cycle without disturbing Wi-Fi, Bluetooth or USB. Reserved-memory handoff, position data, suspend and a standard Linux GNSS userspace bridge remain unvalidated, so it is not autoloaded. |
| Connectivity | NFC | Not present | CMF Phone 1 / `nothing-tetris` has no NFC hardware; do not port shared Nothing NFC modules. |
| Modem | Calls/SMS/mobile data | Broken | ModemManager reports no modem and there are no CCCI/DPMAIF/WWAN devices. The generic Phosh SIM UI is not evidence of modem support. |
| Sensors | Rotation/accelerometer | Broken | Requires the MT6878 SCP remoteproc and vendor sensorhub transport before IIO clients can be exposed safely. |
| Sensors | Ambient light/proximity | Broken | Shares the unported SCP sensorhub path; no blind client probing. |
| Storage | microSD | Partial | Native MSDC1 probes as `mmc0`; no card was present for insertion and I/O validation. |
| Storage | Root filesystem | Works | Verified live: `/dev/sdc82` ext4, 104.6 GiB, about 97 GiB free. |
| Desktop UI | Storage panel | Partial | UDisks sees many Android GPT partitions; r8 device package hides non-pmOS partitions. |
| Desktop UI | CPU name | Partial | `lscpu` identifies Cortex-A55/A78 clusters. GNOME 50.3 ignores ARM `CPU implementer`/`CPU part` fields and therefore leaves the Settings processor row blank; this needs a portable GNOME/libgtop fix. |

## Current Live Findings

On the tested r53 userspace/kernel image:

- Power, volume-up and volume-down generate balanced press/release events without stuck keys.
- `/` is mounted from `/dev/sdc82` as ext4 and is not full.
- `/boot` is mounted from `/dev/sdc81` as ext2.
- `hostnamectl` reports `Hardware Vendor: Nothing` and `Hardware Model: CMF Phone 1`.
- `/proc/cpuinfo` exposes ARM CPU part IDs only; `lscpu` decodes them as
  Cortex-A55 and Cortex-A78 clusters.
- UDisks sees the whole Android GPT with many small firmware partitions. The
  device package now installs `80-nothing-tetris-udisks.rules` to hide
  non-postmarketOS partitions from desktop storage UIs.

Additional historical live checks on r63:

- RT6010 haptics probes on I2C, registers an input force-feedback device and
  executes the official B4.1 RAM waveform at the expected physical strength.
- Ten repeated bounded effects and feedbackd-triggered effects completed
  without atomic-context warnings, watchdog resets, USB loss or radio faults.
- AW88261 speaker amplifier probes on I2C, but the kernel still reports
  `No soundcards found`.
- MT6375 TCPC currently probes the wrong/empty register path and reports vendor
  ID `0x0000`.
- The phone exposes `connsys_wifi_a`, `connsys_bt_a` and `connsys_gnss_a`
  partitions, but `firmware-nothing-tetris` ships the required blobs so the
  rootfs does not depend on reading Android partitions at runtime.

Audio validation for the `pkgrel=100` candidate sources:

- The AFE maps the official `audio_sram@11059000`, parses the Tetris B4.1 ETDM
  contract and registers all 75 DAIs.
- `mtk_spmi_pmic_adc` and `nvmem_mt635x_efuse` provide MT6369 calibration data;
  the codec completes MTKAIF and headphone trim calibration.
- Preserving `-EPROBE_DEFER` in the machine driver allows the ALSA card to
  register automatically after AW88261 becomes ready, without a manual bind.
- The live cold boot retained USB networking, NetworkManager Wi-Fi and BlueZ.
  Playback and capture remain blocked from `Works` until the new topckgen
  clocks are present in a CI kernel and every physical route is tested.

Connectivity validation for the `pkgrel=99` package sources:

- U-Boot preloads the exact MT6631 payloads from the packaged Nothing OS 4.1
  firmware containers before Linux applies the conninfra memory protection.
- Wi-Fi factory calibration is read-only extracted from the `nvdata` GPT
  partition at boot and delivered to `/dev/wmtWifi` as one validated write.
- Three clean boots of the CI kernel/rootfs with the rebuilt package DTB
  completed automatic joint Wi-Fi/Bluetooth pre-calibration. NetworkManager
  scans found 77, 75 and 79 BSS while the Bluetooth controller remained
  powered, with no WFSYS assert, instruction abort, SCIF timeout or reset.
- The Bluetooth module uses the native kernel HCI interface. BlueZ powered the
  controller and discovered 23 nearby devices without an Android HAL. The
  driver exposes the standard `set_bdaddr` callback; a boot helper reads only
  the six address bytes from `nvdata` and provisions them through BlueZ MGMT
  before `bluetooth.service`. The factory address survived a controller power
  cycle and matched `nvdata` without exposing it in logs.
- `wmt_drv` is intentionally neither loaded nor installed because it exports
  symbols already owned by `conninfra` in this stack.
- The vendor `conninfra` module must never be unloaded; its platform cleanup
  is unsafe on this kernel. Connectivity recovery uses a normal reboot.
- MT6375 exposes battery/USB power supplies and a Type-C partner, RT6010
  exposes `FF_RUMBLE`, AW88261 identifies as chip `0x2113`, and MSDC1 exposes
  `mmc0`.
- The earlier r88 kernel had no cpuidle framework or thermal zones. The MT6375
  PMIC ADC reported about 40-41 C during connected Wi-Fi/Bluetooth use, while
  the WLAN driver emitted several INFO telemetry records every second. The next
  package enables only shallow per-CPU PSCI idle, enables NetworkManager Wi-Fi
  power saving and moves only the periodic WLAN telemetry records to TRACE.
- Type-C sysfs reports normal orientation, sink power role and device data role.
  `/sys/class/usb_role` is absent, so role swap and host mode are not claimed.

Additional live audit on the `6.18.0 #99` kernel:

- Opening `/dev/gpsdl0` transitioned the GNSS DSP from `OFF` to `ON`, reached
  `OPENED`, and returned cleanly through `CLOSING` to `OFF`. Wi-Fi and
  Bluetooth remained powered and USB SSH survived without an assert, abort,
  reset, oops or watchdog event.
- The GNSS probe still reports no usable LK `emi-addr` or `memory-region` and
  falls back to small DMA buffers. Do not autoload it until the memory owner
  and Linux userspace ABI are made explicit.
- MT6375 TCPC reports reverse cable orientation, sink power, device data role,
  5.1 V USB input and a configured MTU3 gadget. The Type-C state is valid, but
  the MTU3 data-role switch is not registered because dual-role mode is off.
- `/sys/class/thermal` is absent, ModemManager reports no modem, `/dev/dri` has
  no render node, and there are no camera media/video nodes. The two IIO
  devices are PMIC ADCs, not motion, light or proximity sensors.
- GNOME Settings 50.3 searches only `model name`, `cpu`, `Processor` and
  `Model Name`; arm64 exposes the heterogeneous clusters as MIDR implementer
  and part fields. Kernel CPU topology is correct, so the display bug belongs
  in GNOME/libgtop rather than a Tetris-specific kernel string.
- LM3644 registers `white:flash-rear-main` and `white:flash-rear-wide`. Both
  channels illuminated independently during bounded torch tests and returned
  to `brightness=0`; UDC stayed configured and no LED fault was logged.
- ALSA card `mt6878-mt6369` registers with 13 normal playback PCM devices,
  18 normal capture PCM devices and the expected hostless paths. Enumeration
  proves the AFE/card graph, not physical speaker or microphone routing.

Useful storage checks on a booted phone:

```sh
df -h
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,FSAVAIL,FSUSE%,MOUNTPOINTS
findmnt -R / -o TARGET,SOURCE,FSTYPE,SIZE,USED,AVAIL,USE%
udevadm info -q property -n /dev/sdc82
```

Useful CPU checks:

```sh
cat /proc/cpuinfo
lscpu
hostnamectl
```

## Next Porting Targets

The next useful hardware targets, in roughly pragmatic order:

1. Validate the shallow CPU-idle image first: USB/SSH survival, Wi-Fi/Bluetooth
   coexistence, cpuidle residency and temperature.
2. Validate a clean CI image boot, automatic Wi-Fi startup, association/DHCP,
   native Bluetooth discovery and the factory Bluetooth address.
3. Validate MT6375 Type-C attach/detach, orientation, sink/device roles and wake;
   preserve USB gadget recovery before adding host role switching.
4. Validate packaged RT6010 haptics from a clean CI installation, including
   cold boots, cancellation and suspend/resume.
5. Validate the `pkgrel=100` audio-clock image, then test each speaker and
   microphone route and add UCM profiles.
6. Validate MSDC1 card insertion/removal plus LM3644 timed strobe and V4L2
   flash integration; bounded torch on both channels already works live.
7. Complete the GNSS reserved-memory/userspace contract, then validate a real
   fix, restart and suspend/resume while Wi-Fi and Bluetooth remain active.
8. Port the MT6878 LVTS calibration/controller data and expose conservative SoC
   thermal zones before GPU, modem or camera stress testing.
9. Fix heterogeneous ARM CPU naming in GNOME/libgtop without hard-coding this
   handset's marketing SoC name.
10. Port SCP handoff, then sensorhub/IIO for rotation, proximity and ambient light.
11. Treat modem/SIM, cameras and native GPU support as separate large projects.

## Layout

- `pmaports/` - overlay files copied on top of upstream postmarketOS pmaports.
- `ci/pmbootstrap-aarch64.cfg` - pmbootstrap config used by CI and local Docker
  helpers.
- `docs/PATCH_SERIES.md` - active kernel patch series map.
- `scripts/validate-pmaports-overlay.sh` - checks APKBUILD local source and
  checksum references.
- `scripts/build-arm64-kernel.sh` - local Docker helper for the kernel package.
- `scripts/build-arm64-image.sh` - local Docker helper for the device image.

## Validate

```sh
./scripts/validate-pmaports-overlay.sh
```

The validator checks tracked local patch/config files against APKBUILD
`sha512sums`. Remote source archives are fetched by pmbootstrap during package
builds.

## Build

Kernel package:

```sh
./scripts/build-arm64-kernel.sh
```

Device image/rootfs:

```sh
./scripts/build-arm64-image.sh
```

Both helpers clone/update upstream `pmbootstrap` and `pmaports` under
`upstream/`, then copy this overlay on top before building.

## CI

GitHub Actions validates the overlay on pushes and pull requests. On pushes it
also builds the device and kernel packages against a fresh upstream pmaports
checkout and uploads flashable install images.
