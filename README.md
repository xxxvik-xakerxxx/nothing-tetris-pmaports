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
| Kernel version | `6.18-r86` package (`#87` build) |
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
| USB-C | Type-C attach/orientation | Partial | MT6375 TCPC probes with device ID `0x0241` and exposes `port0` plus an attached partner; orientation, role swap and wake still need testing. |
| USB-C | Analog audio switch | Pending validation | r86 wires the HL5280 to the MT6375 Type-C connector and uses its required audio-accessory sequence. |
| Haptics | RT6010 rumble | Partial | RT6010 probes and exposes `FF_RUMBLE`; longer runtime stability still needs validation. |
| Audio | Speaker amp identification | Partial | AW88261 probes on I2C. |
| Audio | Playback/recording | Broken | The official modules are packaged, but the MT6369 machine driver defers with `-EPROBE_DEFER`; no ALSA sound card exists yet. |
| GPU | 3D acceleration | Broken | MFG clock groundwork exists; GPU stack is not enabled. |
| Camera | Front/rear cameras | Broken | Not started. |
| Camera | Flash | Broken | r86 contains the LM3644 driver and board wiring, but no LED class device probes on the current image. |
| Connectivity | Connsys foundation | Partial | `connadp`, `conninfra` and `connfem` probe reliably at boot; vendor `conninfra` cannot be safely unloaded. |
| Connectivity | Wi-Fi | Broken | Module/AXI/reserved-memory/NVRAM setup works, but WMMCU power-on fails because the secure EMI remap is absent; no `wlan0`. |
| Connectivity | Bluetooth | Broken | Module and pre-cal callback register, but BGFSYS power-on fails under the same boot-time connsys contract; no HCI device. |
| Connectivity | GPS/GNSS | Broken | Generic GNSS core registers; MT6631 GNSS client is not packaged yet. |
| Connectivity | NFC | Not present | CMF Phone 1 / `nothing-tetris` has no NFC hardware; do not port shared Nothing NFC modules. |
| Modem | Calls/SMS/mobile data | Broken | Modem/SIM stack not started. |
| Sensors | Rotation/accelerometer | Broken | Sensorhub/IIO path not started. |
| Sensors | Ambient light/proximity | Broken | Sensorhub/IIO path not started. |
| Storage | microSD | Partial | Native MSDC1 probes as `mmc0` with card-detect GPIO; insertion and I/O are not yet hardware-tested. |
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

Additional live checks on the r86 package (`6.18.0 #87`):

- The device service loads only `connadp`, `conninfra` and `connfem`; this
  base-only boot remains stable and does not power either radio.
- The exact 6146-byte factory Wi-Fi NVRAM is accepted through `/dev/wmtWifi`.
  WLAN module probe, AXI mapping, the 20 MiB DMA pool and firmware loading all
  complete before WMMCU reports `0x18060b10=0` and `0x184c1604=0`.
- Loading both WLAN and BT modules triggers the official joint pre-cal flow.
  BT reaches BGFSYS but power-on fails; WLAN then reaches WMMCU and fails at
  the same missing secure connsys remap. Neither `wlan0` nor an HCI device is
  created.
- A failed radio pre-cal leaves userspace running, but unloading the vendor
  `conninfra` module oopses in its platform-driver cleanup. Do not use
  `modprobe -r conninfra`; reboot after connectivity experiments.
- MT6375 exposes battery/USB power supplies and a Type-C partner, RT6010
  exposes `FF_RUMBLE`, AW88261 identifies as chip `0x2113`, and MSDC1 exposes
  `mmc0`. ALSA still has no sound card and LM3644 exposes no LED device.

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
2. Reproduce the complete stock LK connsys secure-memory contract in U-Boot,
   then repeat the already-working MT6631 module/NVRAM/pre-cal sequence.
3. Stabilize RT6010 haptics and confirm repeated rumble no longer freezes or
   reboots the phone.
4. Resolve the MT6369 ASoC deferred probe, then add speaker/microphone routing
   and UCM.
5. Validate MSDC1 card insertion/removal and LM3644 torch/strobe operation.
6. Add GNSS/FM clients after Wi-Fi/BT connectivity is stable.
7. Add sensorhub/IIO support for rotation, proximity and ambient light.
8. Treat modem/SIM and cameras as later large projects.

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
