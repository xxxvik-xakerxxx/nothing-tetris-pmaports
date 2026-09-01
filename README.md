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
| Kernel version | `6.18` (`pkgrel=127` in the active CI candidate) |
| Kernel source commit | `d84b264a54a37611f2f46bc19363cb9b41606205` |
| Device DTB | `mt6878-nothing-tetris` |

Patch grouping and cleanup debt are documented in [docs/PATCH_SERIES.md](docs/PATCH_SERIES.md).
Driver packaging and vendor-to-native migration are documented in
[docs/DRIVER_STRATEGY.md](docs/DRIVER_STRATEGY.md).
The current mainline promotion policy and remaining hardware order are tracked
in [docs/PORT_COMPLETION_PLAN.md](docs/PORT_COMPLETION_PLAN.md).
The concise installed-versus-candidate hardware matrix is maintained in
[docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md).
The fail-closed SCP and sensorhub ownership boundary is documented in
[docs/SCP_SENSOR_BRINGUP.md](docs/SCP_SENSOR_BRINGUP.md).
The measured charging path, source-classification blocker and idle-drain test
contract are documented in
[docs/POWER_CHARGING_BRINGUP.md](docs/POWER_CHARGING_BRINGUP.md).

The active `pkgrel=127` candidate is pmaports commit
`fdeeda042144e5ff1d2159f1590dbc5fb6b9392c`. CI run `33502390335` passed and
published images whose manifest pins U-Boot `b76e47e`. That exact U-Boot is
installed in both boot partitions and the CI image is installed as kernel
`6.18.0 #128`; clean boot, warm reboot and exact 32 MiB USB SSH transfers pass.
The installed device package remains `device-nothing-tetris-8-r3`. Source
candidate `8-r4` moves the PulseAudio speaker policy from every user manager to
the real graphical session and excludes the `greetd` account; it is not
installed or hardware-validated yet.

Per-device data remains outside the image. The live phone exposes separate
`nvcfg`, `nvdata`, `nvram`, `persist`, `proinfo`, `protect1`, `protect2` and
`md_sec` stores plus A/B subsystem firmware partitions. Wi-Fi/BT use bounded
records from `nvdata`; future modem, GNSS, sensor and camera work must identify
its exact calibration records without committing whole dumps or unique IDs.

## Feature Status

| Area | Feature | Status | Notes |
| --- | --- | --- | --- |
| Boot | U-Boot boot flow | Works | U-Boot `b76e47e` is installed in `boot_a` and `boot_b`; normal boot and Linux `reboot bootloader` both pass. The U-Boot fastboot implementation reports slot A but does not support `set_active`. |
| Boot | Kernel boot | Works | CI image `fdeeda0` boots mainline `6.18.0 #128` to userspace on clean and warm boots. |
| Display | Simple framebuffer | Partial | Inherited U-Boot framebuffer provides basic scanout through `simpledrm`, but has no native brightness, vblank/page-flip or validated suspend/resume path and desktop rendering is CPU-bound. |
| Display | Native DSI/panel | Broken | `pkgrel=127` stages a bounded S6E8FC3X02 driver and binding for a compile-only object. The shipped config remains off and no module or DT client is packaged. MT6878 DDP/mutex/CMDQ/DSC/DSI/PHY, lane-rate validation and an opt-in DT graph remain. |
| Input | Touchscreen | Works | FT3519 touchscreen is enabled. |
| Input | Hardware keys | Works | Power, volume-up and GPIO volume-down are hardware-tested; MT6363 uses distinct press/release IRQ handlers. |
| Power | Battery/USB telemetry | Partial | MT6375 telemetry and the bounded 500 mA path work; clean kernel #128 measured +195312 uA net battery current at 87%. TCPM still reports Type-C default mode and `CURRENT_MAX=0`. The native MT6375 driver lacks BC1.2 SDP/CDP/DCP classification; Type-C Rp needs a known-source test and PD/PPS remains disabled. |
| Power | CPU idle | Partial | Per-CPU PSCI power-off is enabled. Cluster/system idle states remain disabled until USB/SSH and radio suspend tests pass. |
| Power | Idle battery drain | Broken | An uncontrolled overnight observation lost roughly half the battery. Existing captures kept USB connected and the controller runtime-active, so they cannot identify the unplugged cause. The next valid test is local, physically unplugged and screen-off, comparing separate Wi-Fi-on/off boots with coulomb, wake and IRQ deltas. |
| Power | Thermal management | Partial | The installed baseline exposes all 24 MT6878 LVTS zones with plausible polling-mode values. Hardware trips/IRQ routing and sustained-load lifecycle tests remain disabled. |
| USB | Device mode / NCM | Partial | Kernel #128 automatically exposes `usb0`; exact 32 MiB SSH transfers passed after its clean boot and warm reboot. Repeated physical reconnect and suspend/resume remain. |
| USB-C | Type-C attach/orientation | Partial | MT6375 TCPM reports orientation, sink power and device data role. Peripheral/NCM is the safe default; host VBUS ownership, PD and wake remain unvalidated. |
| USB-C | Analog audio switch | Untested | HL5280 is described through the MT6375 Type-C connector, but physical accessory detection and audio routing are not validated. |
| Haptics | RT6010 rumble | Partial | A bounded `feedbackd` effect works physically on clean kernel #128 and stops without affecting USB. Suspend/resume and three cold boots remain. |
| Audio | Upper earpiece | Partial | Physical playback and the desktop speaker test work through MT6369. Lifecycle tests remain. |
| Audio | Lower main speaker | Partial | A bounded PulseAudio 440 Hz test plays physically through AW88261 on clean kernel #128 and the sink returns to `SUSPENDED`. System sounds remain inconsistent; measured microphone capture passes separately. |
| Audio | Built-in microphones | Partial | A clean #128 five-second stereo capture contains two distinct active channels with near-zero DC and less than 0.002% clipped samples. Physical per-input mapping, suspend/resume and cold-boot repetition remain. |
| Audio | Desktop integration | Partial | PulseAudio exposes earpiece, mono main-speaker and internal-microphone endpoints. Clean-boot logs prove pre-login SSH user managers repeatedly autostart PulseAudio without seat ACLs, causing ALSA/BlueZ/feedbackd conflicts. Candidate device package r4 gates the policy on `graphical-session.target`; CI and clean-session lifecycle tests remain. |
| GPU | 3D acceleration | Broken | MFG clock groundwork and `panthor.ko` exist, but no Mali platform device or render node is present; `card0` is the inherited simple framebuffer. |
| Camera | Front/rear cameras | Broken | No V4L2/media pipeline is present. The candidate compile-checks a disabled, bounded IMX882 physical-ID probe, but it is not packaged or autoloaded and no sensor has been powered on Linux. SENINF/ISP, clocks, power domains, IOMMU and userspace remain. |
| Camera | Torch | Partial | Both LM3644 rear LED channels accept bounded brightness effects, illuminate physically and return to off. Clean-install and lifecycle tests remain. |
| Camera | Flash strobe | Untested | The Linux flash class exposes both channels; timed strobe, fault reporting and the V4L2 bridge are not validated. |
| Connectivity | Connsys foundation | Partial | `connadp`, `conninfra` and `connfem` probe reliably at boot; vendor `conninfra` cannot be safely unloaded. |
| Connectivity | Wi-Fi | Partial | Clean kernel #128 registers `wlan0`; association to `DistributedLabDev`, DHCP, the default route, DNS and HTTPS pass while USB and Bluetooth remain active. Cold reconnect, suspend/resume and stress remain. |
| Connectivity | Bluetooth | Partial | Native BlueZ `hci0` performs discovery and found more than 40 nearby devices while USB/Wi-Fi survived. One bounded scan left `Discovering` stuck until only `bluetooth.service` was restarted, so pair/reconnect, profile and teardown lifecycle work remains. |
| Connectivity | GPS/GNSS | Partial | With U-Boot `b76e47e`, v050 creates both `gpsdl` nodes and a bounded link0 open/close preserves USB, Wi-Fi and Bluetooth. Boot-info ioctl 23 returns `EFAULT` because v050 links a non-ATF stub; stock-derived Tetris property and module trees select v051, now the next isolated compile/clean-boot candidate. |
| Connectivity | NFC | Not present | CMF Phone 1 / `nothing-tetris` has no NFC hardware; do not port shared Nothing NFC modules. |
| Modem | Calls/SMS/mobile data | Broken | ModemManager reports no modem and there are no CCCI/DPMAIF/WWAN devices. An isolated CCIF patch replaces `from_timer()`/`del_timer()` with Linux 6.18 lifetime-equivalent APIs and advances `ccci_hif_ccif.o` to the next first blocker: unowned `MTK_SIP_KERNEL_CCCI_CONTROL`. No modem module, DT or runtime path is enabled. |
| Sensors | Rotation/accelerometer | Broken | The vendor SCP probe currently stops at `wait_scp_dvfs_init_done()` because the target DT intentionally has no `mediatek,scp-dvfs` device. A host-only U-Boot parser now validates two bounded, non-overlapping SCP carveouts without modifying the FDT, but active-slot firmware identity and TCM region-info remain unknown; no publication, DVFS or sensorhub is enabled. |
| Sensors | Ambient light/proximity | Broken | Shares the blocked SCP sensorhub path. Adding only the vendor DVFS node is rejected because it would touch ULPOSC, fmeter and clocks before firmware handoff is proven. |
| Storage | microSD | Partial | Native MSDC1 probes as `mmc0`; no card was present for insertion and I/O validation. |
| Storage | UFS/root I/O | Works | UFS is stable and `/dev/sdc82` mounts read-write as ext4. |
| Storage | Automatic root grow | Works | The clean sparse-image flash ran the standard pmOS initramfs path and mounted a writable 104.6 GiB root filesystem without a device-specific resize service. |
| Desktop UI | Storage panel | Partial | UDisks sees many Android GPT partitions; r8 device package hides non-pmOS partitions. |
| Desktop UI | CPU name | Partial | `lscpu` identifies Cortex-A55/A78 clusters. GNOME 50.3 ignores ARM `CPU implementer`/`CPU part` fields and therefore leaves the Settings processor row blank; this needs a portable GNOME/libgtop fix. |

## Installed Baseline Findings

On the clean CI image from pmaports commit `fdeeda0` with kernel
`6.18.0 #128` and U-Boot `b76e47e`:

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
- Wi-Fi association, DHCP, the default route, DNS and HTTPS work while USB and
  powered native BlueZ Bluetooth remain active.
- ALSA playback/capture devices plus PulseAudio stereo speaker, mono remap and
  microphone endpoints register after the desktop session settles. Bounded
  speaker playback and haptics are physically confirmed on #128. A five-second
  stereo microphone capture has two distinct valid channels; normal system
  sounds remain inconsistent because pre-login user-manager churn races audio
  ownership.
- NCM USB networking is active as `usb0`/`en4` and transferred exact 32 MiB
  zero streams with matching SHA after clean boot, warm reboot and the manual
  GNSS transport test.
- The manual GNSS v050 transport creates `/dev/gpsdl0` and `/dev/gpsdl1`; a
  bounded link0 open/close passes without a consumer leak or radio/USB loss.
  This is not a satellite position fix.
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
3. Observe a USB 2.0 host, known Type-C Rp 1.5 A source and known 5 V BC1.2
   DCP. Add only the missing MT6375 BC1.2 detection/publication boundary if the
   DCP stays unclassified; preserve USB gadget recovery and leave PD/OTG off.
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
