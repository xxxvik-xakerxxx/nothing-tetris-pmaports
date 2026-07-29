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

## postmarketOS

| Field | Value |
| --- | --- |
| Category | `testing` |
| UI | Phosh |
| Bootloader | U-Boot FIT image |
| FOSS boot path | Yes |
| Device package | `device/testing/device-nothing-tetris` |
| Kernel package | `device/testing/linux-postmarketos-mediatek-mt6878` |
| Kernel version | `6.18-r61` |
| Kernel source commit | `d84b264a54a37611f2f46bc19363cb9b41606205` |
| Device DTB | `mt6878-nothing-tetris` |

Patch grouping and cleanup debt are documented in [docs/PATCH_SERIES.md](docs/PATCH_SERIES.md).

## Feature Status

| Area | Feature | Status | Notes |
| --- | --- | --- | --- |
| Boot | U-Boot boot flow | Works | Uses `fastboot oem board:boot_pmos` and FIT image handoff. |
| Boot | Kernel boot | Works | Mainline MT6878 kernel reaches userspace. |
| Display | Simple framebuffer | Works | Stable inherited framebuffer through `simpledrm`. |
| Display | Native DSI/panel | Broken | Native display bring-up is intentionally not in the active baseline. |
| Input | Touchscreen | Works | FT3519 touchscreen is enabled. |
| Input | Hardware keys | Partial | Volume-down works; power/volume-up behavior still needs MT6363 IRQ/key validation. |
| Power | Battery/USB telemetry | Partial | Read-only MT6375 monitor is present. Charging control is not implemented. |
| USB-C | Type-C attach/orientation | Pending | r58 adds MT6375 IRQ domain and minimal TCPM/TCPCI driver; needs device validation. |
| Haptics | RT6010 rumble | Pending | Driver and DT node are present; runtime stability still needs validation on r58+. |
| Audio | Speaker amp identification | Partial | AW88261 is identified; no ALSA card/machine driver yet. |
| Audio | Playback/recording | Broken | Needs MT6878 AFE, MT6369 codec/machine routing, UCM. |
| GPU | 3D acceleration | Broken | MFG clock groundwork exists; GPU stack is not enabled. |
| Camera | Front/rear cameras | Broken | Not started. |
| Camera | Flash | Broken | Needs LED-class/V4L2 flash bring-up. |
| Connectivity | Connsys foundation | Pending | r61 adds an MT6878/MT6631 manual regulator/MMIO bring-up driver for on-device validation; MT6878 scpsys still needs porting. |
| Connectivity | Wi-Fi | Broken | MT6631 DT inventory is present but disabled; needs WMT/firmware/WLAN client bring-up after connsys validation. |
| Connectivity | Bluetooth | Broken | MT6631 BT inventory is present but disabled; depends on WMT and connectivity foundation. |
| Connectivity | GPS/GNSS | Broken | MT6631 GNSS inventory is present but disabled; depends on WMT and connectivity foundation. |
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
4. Bring up flashlight as LED-class or V4L2 flash.
5. Port the MT6631 connectivity foundation: conninfra power/reset/EMI first,
   then WMT, then Wi-Fi/BT/GNSS clients.
6. Add Bluetooth/GNSS after connectivity is stable.
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
