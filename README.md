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
| Vendor OS | Android 14 / Nothing OS |
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
| Kernel version | `6.18-r85` candidate |
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
| Input | Hardware keys | Pending validation | r85 uses the official MT6363 debounce and interrupt-select masks for power and volume-up. |
| Power | Battery/USB telemetry | Partial | Read-only MT6375 monitor is present. Charging control is not implemented. |
| USB-C | Type-C attach/orientation | Pending validation | r85 maps the hardware-confirmed TCPCI register bank directly; r63 used the wrong empty window. |
| USB-C | Analog audio switch | Pending validation | r85 wires the HL5280 to the MT6375 Type-C connector and uses its required audio-accessory sequence. |
| Haptics | RT6010 rumble | Partial | RT6010 probes and exposes `FF_RUMBLE`; longer runtime stability still needs validation. |
| Audio | Speaker amp identification | Partial | AW88261 probes on I2C. |
| Audio | Playback/recording | Pending validation | r85 packages the official MT6878 AFE, MT6369 codec and machine modules; routing/UCM still needs hardware validation. |
| GPU | 3D acceleration | Broken | MFG clock groundwork exists; GPU stack is not enabled. |
| Camera | Front/rear cameras | Broken | Not started. |
| Camera | Flash | Pending validation | r85 adds a native dual-channel LM3644 LED flash-class driver and the confirmed GPIO wiring. |
| Connectivity | Connsys foundation | Pending | MT6878/MT6631 manual regulator/MMIO bring-up driver is present; live r63 registers the device and can trigger power-on. |
| Connectivity | Wi-Fi | Pending validation | r85 packages ABI-locked MT6631 modules and dedicated firmware. |
| Connectivity | Bluetooth | Pending validation | r85 packages the MT6878 BEIF Bluetooth module after conninfra/WMT. |
| Connectivity | GPS/GNSS | Broken | Generic GNSS core registers; MT6631 GNSS client is not packaged yet. |
| Connectivity | NFC | Not present | CMF Phone 1 / `nothing-tetris` has no NFC hardware; do not port shared Nothing NFC modules. |
| Modem | Calls/SMS/mobile data | Broken | Modem/SIM stack not started. |
| Sensors | Rotation/accelerometer | Broken | Sensorhub/IIO path not started. |
| Sensors | Ambient light/proximity | Broken | Sensorhub/IIO path not started. |
| Storage | Root filesystem | Works | Verified live: `/dev/sdc82` ext4, 104.6 GiB, about 97 GiB free. |
| Desktop UI | Storage panel | Partial | UDisks sees many Android GPT partitions; r8 device package hides non-pmOS partitions. |
| Desktop UI | CPU name | Partial | `lscpu` identifies Cortex-A55/A78 clusters; Settings may still show a generic/blank processor string. |

## Current Live Findings

On the tested r53 userspace/kernel image:

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

1. Validate MT6375 Type-C on-device: attach/detach IRQs, orientation, sink role,
   USB data role, wake behavior.
2. Stabilize RT6010 haptics on r58+ and confirm it no longer freezes/reboots.
3. Fix MT6363 key handling for power and volume-up.
4. Validate r85 MT6631 connectivity modules on-device: conninfra, WMT, Wi-Fi,
   then Bluetooth.
5. Bring up flashlight as LED-class or V4L2 flash.
6. Add GNSS/FM clients after Wi-Fi/BT connectivity is stable.
7. Bring up MT6878 AFE, MT6369 audio routing, AW88261 speaker path and UCM.
8. Add sensorhub/IIO support for rotation, proximity and ambient light.
9. Treat modem/SIM and cameras as later large projects.

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
