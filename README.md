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
| Kernel version | `6.18` (`pkgrel=125` in the active candidate) |
| Kernel source commit | `d84b264a54a37611f2f46bc19363cb9b41606205` |
| Device DTB | `mt6878-nothing-tetris` |

Patch grouping and cleanup debt are documented in [docs/PATCH_SERIES.md](docs/PATCH_SERIES.md).
Driver packaging and vendor-to-native migration are documented in
[docs/DRIVER_STRATEGY.md](docs/DRIVER_STRATEGY.md).
The current mainline promotion policy and remaining hardware order are tracked
in [docs/PORT_COMPLETION_PLAN.md](docs/PORT_COMPLETION_PLAN.md).
The concise installed-versus-candidate hardware matrix is maintained in
[docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md).

## Feature Status

| Area | Feature | Status | Notes |
| --- | --- | --- | --- |
| Boot | U-Boot boot flow | Works | Uses `fastboot oem board:boot_pmos` and FIT image handoff. |
| Boot | Kernel boot | Works | Mainline MT6878 kernel reaches userspace. |
| Display | Simple framebuffer | Partial | Inherited U-Boot framebuffer provides basic scanout through `simpledrm`, but has no native brightness, vblank/page-flip or validated suspend/resume path and desktop rendering is CPU-bound. |
| Display | Native DSI/panel | Broken | MT6878 DSI/DSC and the AMOLED panel driver are not integrated. |
| Input | Touchscreen | Works | FT3519 touchscreen is enabled. |
| Input | Hardware keys | Works | Power, volume-up and GPIO volume-down are hardware-tested; MT6363 uses distinct press/release IRQ handlers. |
| Power | Battery/USB telemetry | Partial | MT6375 telemetry and a conservative charging policy work. The current USB 2.0 default-current source is correctly limited to 500 mA; BC1.2, Type-C Rp and PD current detection still need implementation and charger testing. |
| Power | CPU idle | Partial | Per-CPU PSCI power-off is enabled. Cluster/system idle states remain disabled until USB/SSH and radio suspend tests pass. |
| Power | Idle battery drain | Broken | An uncontrolled overnight observation lost roughly half the battery. CPU cluster-off works, but a repeatable unplugged screen-off/suspend measurement has not yet isolated the cause. |
| Power | Thermal management | Partial | The installed baseline exposes all 24 MT6878 LVTS zones with plausible polling-mode values. Hardware trips/IRQ routing and sustained-load lifecycle tests remain disabled. |
| USB | Device mode / NCM | Partial | The clean baseline automatically exposes `usb0`; exact 32 MiB SSH transfers passed across clean and warm boots. Repeated reconnect and suspend/resume remain. |
| USB-C | Type-C attach/orientation | Partial | MT6375 TCPM reports orientation, sink power and device data role. Peripheral/NCM is the safe default; host VBUS ownership, PD and wake remain unvalidated. |
| USB-C | Analog audio switch | Untested | HL5280 is described through the MT6375 Type-C connector, but physical accessory detection and audio routing are not validated. |
| Haptics | RT6010 rumble | Partial | The driver uses the official B4.1 RAM waveform through `FF_RUMBLE`; shell, UI and repeated bounded effects work physically. Suspend/resume and three cold boots remain. |
| Audio | Upper earpiece | Partial | Physical playback and the desktop speaker test work through MT6369. Lifecycle tests remain. |
| Audio | Lower main speaker | Partial | Direct ALSA playback works through AW88261. The current kernel exposes its MCK as a fixed gate, so 44.1/48 kHz streams fail `clk_set_rate()` and can truncate; the next kernel stages the native SI1 divider fix. |
| Audio | Built-in microphones | Partial | AIN0 and AIN2 capture physically through the packaged UCM profile. Per-input recordings, suspend/resume and cold-boot repetition remain. |
| Audio | Desktop integration | Partial | PulseAudio exposes earpiece, mono main-speaker and internal-microphone endpoints. The main-speaker stream lifecycle is not stable. |
| GPU | 3D acceleration | Broken | MFG clock groundwork and `panthor.ko` exist, but no Mali platform device or render node is present; `card0` is the inherited simple framebuffer. |
| Camera | Front/rear cameras | Broken | No V4L2/media pipeline is present. The candidate compile-checks a disabled, bounded IMX882 physical-ID probe, but it is not packaged or autoloaded and no sensor has been powered on Linux. SENINF/ISP, clocks, power domains, IOMMU and userspace remain. |
| Camera | Torch | Partial | Both LM3644 rear LED channels accept bounded brightness effects, illuminate physically and return to off. Clean-install and lifecycle tests remain. |
| Camera | Flash strobe | Untested | The Linux flash class exposes both channels; timed strobe, fault reporting and the V4L2 bridge are not validated. |
| Connectivity | Connsys foundation | Partial | `connadp`, `conninfra` and `connfem` probe reliably at boot; vendor `conninfra` cannot be safely unloaded. |
| Connectivity | Wi-Fi | Partial | The clean CI image automatically registers `wlan0`; NetworkManager scans, associates and routes traffic while Bluetooth remains active. Three cold boots, suspend/resume and a second unit remain. |
| Connectivity | Bluetooth | Partial | The clean CI image automatically registers native BlueZ `hci0` with the factory address and the UI works alongside connected Wi-Fi. RFCOMM/BNEP are staged for the next kernel; lifecycle/second-unit checks remain. |
| Connectivity | GPS/GNSS | Broken | A manual B4.1 v050 probe creates both `gpsdl` device nodes, but the installed boot chain lacks a valid GPS EMI handoff and exact LNA pinctrl. No position fix is confirmed and the module is not autoloaded. |
| Connectivity | NFC | Not present | CMF Phone 1 / `nothing-tetris` has no NFC hardware; do not port shared Nothing NFC modules. |
| Modem | Calls/SMS/mobile data | Broken | ModemManager reports no modem and there are no CCCI/DPMAIF/WWAN devices. The generic Phosh SIM UI is not evidence of modem support. |
| Sensors | Rotation/accelerometer | Broken | Requires the MT6878 SCP remoteproc and vendor sensorhub transport before IIO clients can be exposed safely. |
| Sensors | Ambient light/proximity | Broken | Shares the unported SCP sensorhub path; no blind client probing. |
| Storage | microSD | Partial | Native MSDC1 probes as `mmc0`; no card was present for insertion and I/O validation. |
| Storage | UFS/root I/O | Works | UFS is stable and `/dev/sdc82` mounts read-write as ext4. |
| Storage | Automatic root grow | Partial | The pmOS initramfs runs `e2fsck` and `resize2fs` before mounting root. The current filesystem is 104.6 GiB; a fresh sparse-image flash still needs the clean-install gate. |
| Desktop UI | Storage panel | Partial | UDisks sees many Android GPT partitions; r8 device package hides non-pmOS partitions. |
| Desktop UI | CPU name | Partial | `lscpu` identifies Cortex-A55/A78 clusters. GNOME 50.3 ignores ARM `CPU implementer`/`CPU part` fields and therefore leaves the Settings processor row blank; this needs a portable GNOME/libgtop fix. |

## Installed Baseline Findings

On the clean CI image from pmaports commit `f607513` with kernel
`6.18.0 #123`:

- Power, volume-up and volume-down generate balanced press/release events without stuck keys.
- `/` is mounted from `/dev/sdc82` as ext4 and currently exposes 104.6 GiB.
  Root growth remains owned by the standard pmOS initramfs path; the device
  package does not install a second systemd resize service.
- `/boot` is mounted from `/dev/sdc81` as ext2.
- `hostnamectl` reports `Hardware Vendor: Nothing` and `Hardware Model: CMF Phone 1`.
- `/proc/cpuinfo` exposes ARM CPU part IDs only; `lscpu` decodes them as
  Cortex-A55 and Cortex-A78 clusters.
- UDisks sees the whole Android GPT with many small firmware partitions. The
  device package now installs `80-nothing-tetris-udisks.rules` to hide
  non-postmarketOS partitions from desktop storage UIs.
- Wi-Fi association and routed traffic, native BlueZ Bluetooth, feedbackd
  haptics, earpiece playback and both microphone inputs survive the clean boot.
  The lower speaker stream lifecycle remains the known audio regression. Live
  clock-tree evidence identified its first error as a non-programmable
  `apll12_div_si1`; the next kernel models the official B4.1 divider fields in
  CCF instead of retrying playback in userspace.
- ECM USB networking is active as `usb0`/`en4` and transferred 32 MiB without
  RX/TX errors while Wi-Fi and Bluetooth remained active.
- All 24 MT6878 LVTS thermal zones report plausible polling-mode values.
  Standard GNSS position, modem/WWAN, camera/media, user-sensor IIO and DRM
  render nodes are absent. The existing IIO devices are PMIC ADCs.
- Both LM3644 torch class devices are present. Earlier bounded physical tests
  illuminated each channel independently and returned it to off.

`Works` means the feature is usable on the current CI installation. `Partial`
means a useful path is physically demonstrated but at least one clean-install,
lifecycle, userspace or portability gate remains. No live-only result is
promoted to `Works` until CI artifacts reproduce it without manual commands.

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
5. Validate packaged UCM audio from a clean CI artifact, then repeat both
   speaker, both microphone, suspend/resume and cold-boot lifecycle tests.
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
