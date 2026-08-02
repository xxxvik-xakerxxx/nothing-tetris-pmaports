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
| Power | Thermal management | Broken | No thermal zones or MT6878 LVTS driver exist in the current kernel. |
| USB | Device mode / NCM | Works | The pmOS USB gadget enumerates and carries stable SSH traffic without RX/TX errors. |
| USB-C | Type-C attach/orientation | Partial | MT6375 TCPC exposes `port0`, partner, sink/device roles and orientation. Kernel USB role switching, host mode and wake remain unvalidated. |
| USB-C | Analog audio switch | Pending validation | r86 wires the HL5280 to the MT6375 Type-C connector and uses its required audio-accessory sequence. |
| Haptics | RT6010 rumble | Partial | RT6010 probes and exposes `FF_RUMBLE`; longer runtime stability still needs validation. |
| Audio | Speaker amp identification | Partial | AW88261 probes on I2C. |
| Audio | Playback/recording | Broken | The official modules are packaged, but the MT6369 machine driver defers with `-EPROBE_DEFER`; no ALSA sound card exists yet. |
| GPU | 3D acceleration | Broken | MFG clock groundwork exists; GPU stack is not enabled. |
| Camera | Front/rear cameras | Broken | Not started. |
| Camera | Flash | Broken | r86 contains the LM3644 driver and board wiring, but no LED class device probes on the current image. |
| Connectivity | Connsys foundation | Partial | `connadp`, `conninfra` and `connfem` probe reliably at boot; vendor `conninfra` cannot be safely unloaded. |
| Connectivity | Wi-Fi | Partial | B4.1 WLAN firmware, factory NVRAM, scans and Wi-Fi/Bluetooth coexistence work live. Clean-install automatic startup is staged for CI validation. |
| Connectivity | Bluetooth | Partial | Native BlueZ HCI, factory address provisioning, discovery and Wi-Fi coexistence work live. Clean-install automatic startup still requires CI image validation. |
| Connectivity | GPS/GNSS | Partial | The B4.1 MT6878 v050 module boots, probes seven IRQs and completes a live power cycle without disturbing Wi-Fi, Bluetooth or USB. Position data, suspend and a standard Linux GNSS userspace bridge remain unvalidated, so it is not autoloaded. |
| Connectivity | NFC | Not present | CMF Phone 1 / `nothing-tetris` has no NFC hardware; do not port shared Nothing NFC modules. |
| Modem | Calls/SMS/mobile data | Broken | Modem/SIM stack not started. |
| Sensors | Rotation/accelerometer | Broken | Requires the MT6878 SCP remoteproc and vendor sensorhub transport before IIO clients can be exposed safely. |
| Sensors | Ambient light/proximity | Broken | Shares the unported SCP sensorhub path; no blind client probing. |
| Storage | microSD | Partial | Native MSDC1 probes as `mmc0`; no card was present for insertion and I/O validation. |
| Storage | Root filesystem | Works | Verified live: `/dev/sdc82` ext4, 104.6 GiB, about 97 GiB free. |
| Desktop UI | Storage panel | Partial | UDisks sees many Android GPT partitions; r8 device package hides non-pmOS partitions. |
| Desktop UI | CPU name | Partial | `lscpu` identifies Cortex-A55/A78 clusters; Settings may still show a generic/blank processor string. |

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

Additional live checks on r63:

- RT6010 haptics probes on I2C and registers an input force-feedback device.
- AW88261 speaker amplifier probes on I2C, but the kernel still reports
  `No soundcards found`.
- MT6375 TCPC currently probes the wrong/empty register path and reports vendor
  ID `0x0000`.
- The phone exposes `connsys_wifi_a`, `connsys_bt_a` and `connsys_gnss_a`
  partitions, but `firmware-nothing-tetris` ships the required blobs so the
  rootfs does not depend on reading Android partitions at runtime.

Connectivity validation for the r88 package sources:

- U-Boot preloads the exact MT6631 payloads from the packaged Nothing OS 4.1
  firmware containers before Linux applies the conninfra memory protection.
- Wi-Fi factory calibration is read-only extracted from the `nvdata` GPT
  partition at boot and delivered to `/dev/wmtWifi` as one validated write.
- Four consecutive NetworkManager scans completed with `Status:NORMAL`; the
  final coexistence scan found 28 BSS while the Bluetooth controller remained
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
  `mmc0`. ALSA still has no sound card and LM3644 exposes no LED device.
- The current r88 kernel has no cpuidle framework or thermal zones. The MT6375
  PMIC ADC reported about 40-41 C during connected Wi-Fi/Bluetooth use, while
  the WLAN driver emitted several INFO telemetry records every second. The next
  package enables only shallow per-CPU PSCI idle, enables NetworkManager Wi-Fi
  power saving and moves only the periodic WLAN telemetry records to TRACE.
- Type-C sysfs reports normal orientation, sink power role and device data role.
  `/sys/class/usb_role` is absent, so role swap and host mode are not claimed.

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
4. Stabilize RT6010 haptics and confirm repeated rumble no longer freezes or
   reboots the phone.
5. Resolve the MT6369 ASoC registration with dynamic ALSA minors, then add speaker/microphone routing
   and UCM.
6. Validate MSDC1 card insertion/removal and LM3644 torch/strobe operation.
7. Add the MT6878/MT6631 GNSS client after Wi-Fi/BT connectivity is stable.
8. Port SCP handoff, then sensorhub/IIO for rotation, proximity and ambient light.
9. Treat modem/SIM, cameras and native GPU support as separate large projects.

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
