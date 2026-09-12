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
| Kernel version | `6.18` (clean-installed CI `34692383850`, `pkgrel=156`, kernel `6.18.0 #157`; display route/frame-end updates and next SCP prerequisites, lifecycle testing incomplete) |
| Kernel source commit | `3a016d36153d504f6b1002d29120bd84a8183533` |
| Device DTB | `mt6878-nothing-tetris-native` |

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

The installed image is the `codex/hardware-integration-next-scp` CI artifact
from pmaports commit `3a016d36153d504f6b1002d29120bd84a8183533`. CI run
`34692383850` passed and its downloaded `nothing-tetris-images` artifact
`10297439743` was verified locally before flashing. The ZIP SHA256 is
`a97f7dd37950e92279a27168fcdf667b607baec91cc00c34194865fccb86bf71`; the
manifest maps `nothing-tetris-boot.img` to `super` and
`nothing-tetris-root.sparse.img` to `userdata`, requires U-Boot
`60bcf22fdc0a94526424db59fc7640298ea8f0dd`, and reports kernel `6.18.0`.
The clean flash on 2026-09-12 booted kernel `6.18.0 #157` with
`device-nothing-tetris-8-r10` and `linux-postmarketos-mediatek-mt6878-6.18-r156`;
USB NCM/SSH returned automatically, zero systemd units were failed, and the
transfer regression gate passed at
`local/live-logs/20260912T170559Z-172.16.42.1-regression-gate`. The user
confirmed visually good native display output after the clean boot.

Native DRM still exposes only `/dev/dri/card0`; there is no render node. Touch
is bound as `fts_ts` on `/dev/input/event0`. Wi-Fi and Bluetooth initialize
automatically (`wlan0` and powered BlueZ `hci0`), but Wi-Fi is not associated
on this clean audit. GNSS v051 remains manual/transport-only and no `/dev/gps*`
node is present on the clean next-SCP baseline. No position fix, NMEA bridge,
autostart, coexistence or suspend/resume is claimed. Camera, GPU and CCCI
additions remain compile/static-only; ModemManager reports no modem; sensor
IIO contains only PMIC ADC devices, not accelerometer, gyro, proximity or light.

Per-device data remains outside the image. The live phone exposes separate
`nvcfg`, `nvdata`, `nvram`, `persist`, `proinfo`, `protect1`, `protect2` and
`md_sec` stores plus A/B subsystem firmware partitions. Wi-Fi/BT use bounded
records from `nvdata`; future modem, GNSS, sensor and camera work must identify
its exact calibration records without committing whole dumps or unique IDs.

## Feature Status

| Area | Feature | Status | Notes |
| --- | --- | --- | --- |
| Boot | U-Boot boot flow | Partial | The clean next-SCP image manifest requires U-Boot `60bcf22fdc0a94526424db59fc7640298ea8f0dd` and the handset entered `tetris-uboot` fastboot on slot `a` before flashing. Cross-slot recovery, exact runtime loader reporting and second-unit portability remain open. |
| Boot | Kernel boot | Works | Clean CI image `3a016d3` from run `34692383850` reaches userspace with `linux-postmarketos-mediatek-mt6878-6.18-r156`, `device-nothing-tetris-8-r10`, zero failed units and working USB NCM/SSH. |
| Display | Legacy framebuffer | Retired | U-Boot `60bcf22` proved that the r132 artifacts were a bootloader framebuffer-handoff fault, not Phoc or touch corruption. Native builds no longer select the simplefb DTB. The clean r132 CI image is retained only as an external fastboot rollback. |
| Display | Native DDP/DSC/DSI | Partial | Clean next-SCP CI `3a016d3` is installed; USB transfer passes and the user confirms visually good output. The frame-end update removed the redraw flicker during live testing. Fixed 60 Hz mode and software rendering remain; 120 Hz, brightness/blank lifecycle, suspend/resume, repeated cold boots, native PQ ownership and render acceleration remain open. See `docs/DISPLAY_FIRST_FRAME_AUDIT.md`. |
| Input | Touchscreen | Works | FT3519 remains bound as `fts_ts` on I2C `2-0038` and exposes `/dev/input/event0` on the clean next-SCP image. |
| Input | Hardware keys | Works | Power, volume-up and GPIO volume-down are hardware-tested; MT6363 uses distinct press/release IRQ handlers. |
| Power | Battery/USB telemetry | Partial | MT6375 charger, gauge and TCPM telemetry work. The r151 source-aware power gate passed on a PD-capable computer attachment that reports 5 V with `CURRENT_MAX=0`, so the safe 500 mA fallback remains; an earlier real PD contract drove AICR/ICHG to 2 A. Charge rate, taper and thermals from a partially discharged battery remain unproven, and native BC1.2 SDP/CDP/DCP classification is absent. |
| Power | CPU idle | Partial | Per-CPU PSCI power-off is enabled. Cluster/system idle states remain disabled until USB/SSH and radio suspend tests pass. |
| Power | Idle battery drain | Broken | A live r147 capture identified a greeter dconf retry loop consuming 5.1 GiB RSS, swap and CPU because its writable directory was absent. Device package r10 now installs `/var/lib/greetd/.config/dconf` and repairs ownership from target `/etc/passwd`; the live audio audit passes after the same directory is created on r151/r8. USB and Wi-Fi suspend costs still require unplugged screen-off A/B measurements. |
| Power | Thermal management | Partial | The installed baseline exposes all 24 MT6878 LVTS zones with plausible polling-mode values. Hardware trips/IRQ routing and sustained-load lifecycle tests remain disabled. |
| USB | Device mode / NCM | Partial | Kernel #130 automatically exposes `usb0`; USB SSH and an exact 32 MiB transfer pass after clean install, and USB returns automatically after a normal reboot. On clean r132 the gadget exposes a valid two-interface CDC-NCM descriptor. A locked macOS session initially ignored its newly randomized host MAC; after unlock and a host-side USB reset, `en4`, DHCP and SSH recovered without rebooting the phone. A per-device stable address derived from hashed bootloader devinfo remains the next packaging fix; repeated physical reconnect and suspend/resume remain. |
| USB-C | Type-C attach/orientation | Partial | MT6375 TCPM reports orientation, sink power and device data role. A 5 V / 2 A PD contract was observed without changing the installed image; PPS, alternate voltages, detach/reconnect and suspend remain unvalidated. Peripheral/NCM stays the safe data role and host VBUS ownership remains disabled. |
| USB-C | Analog audio switch | Untested | HL5280 is described through the MT6375 Type-C connector, but physical accessory detection and audio routing are not validated. |
| Haptics | RT6010 rumble | Partial | A bounded `feedbackd` effect works physically on clean kernel #128 and stops without affecting USB. Suspend/resume and three cold boots remain. |
| Audio | Upper earpiece | Partial | Physical playback and the desktop speaker test work through MT6369. Lifecycle tests remain. |
| Audio | Lower main speaker | Partial | A bounded PulseAudio 440 Hz test plays physically through AW88261 on clean kernel #128 and the sink returns to `SUSPENDED`. System sounds remain inconsistent; measured microphone capture passes separately. |
| Audio | Built-in microphones | Partial | A clean #130 five-second stereo capture contains 387856 samples, 386262 nonzero, zero clipping and 193359 pairs with distinct channels. Physical per-input mapping, suspend/resume and cold-boot repetition remain. |
| Audio | Desktop integration | Partial | PulseAudio exposes speaker and internal-microphone endpoints, but clean #130 proves device r5 only fixes the policy layer. A reversible r6 live overlay followed by a normal reboot produced zero `greetd` PulseAudio owners and no fresh ALSA/BlueZ ownership errors while USB/Wi-Fi/BT returned normally. The new audio audit gate passed on r151 after the r9 dconf-directory fix was applied live. Clean install, one real-user owner, login/relogin and physical audio regression remain. |
| GPU | 3D acceleration | Broken | The clean next-SCP audit exposes `/dev/dri/card0` only and no `/dev/dri/renderD*`. MFG clock groundwork and `panthor.ko` exist, but no Mali platform device, rail consumer, firmware path or render acceleration is enabled. |
| Camera | Front/rear cameras | Broken | The clean next-SCP audit exposes no `/dev/video*` or `/dev/media*` nodes. The source candidate adds a fully disabled main-IMX882 DT fixture matching the reviewed stock I2C8, CAMTG2, reset and four-rail topology. Compile-only gates inventory six sensor variants, four EEPROM layouts and the disabled identity probe; no camera component is enabled, packaged or autoloaded and no sensor has been powered on Linux. SENINF/ISP, power domains, IOMMU, CCU and userspace remain. |
| Camera | Torch | Partial | Both LM3644 rear LED channels accept bounded brightness effects, illuminate physically and return to off. Clean-install and lifecycle tests remain. |
| Camera | Flash strobe | Untested | The Linux flash class exposes both channels; timed strobe, fault reporting and the V4L2 bridge are not validated. |
| Connectivity | Connsys foundation | Partial | `connadp`, `conninfra` and `connfem` probe reliably at boot; vendor `conninfra` cannot be safely unloaded. |
| Connectivity | Wi-Fi | Partial | The clean next-SCP audit starts the bounded connectivity service successfully and exposes `wlan0`; NetworkManager sees it as disconnected. Earlier clean images proved association/DHCP/DNS/traffic, but the current clean image still needs association, route and stress validation. |
| Connectivity | Bluetooth | Partial | The clean next-SCP audit powers BlueZ `hci0` with the factory Bluetooth address configured. Earlier discovery testing passed; pair/reconnect, audio/data profiles and suspend lifecycle remain. |
| Connectivity | GPS/GNSS | Partial | Earlier clean r155 from CI `34589225716` passed three fresh supervised v051 BINFO/download/stop cycles. On the clean next-SCP baseline no `/dev/gps*` node is present because GNSS remains manual/transport-only and was not opened. MNL/MVCD navigation, NMEA/GeoClue, satellite acquisition, timed position fix, autostart, coexistence and suspend/resume remain absent. |
| Connectivity | NFC | Not present | CMF Phone 1 / `nothing-tetris` has no NFC hardware; do not port shared Nothing NFC modules. |
| Modem | Calls/SMS/mobile data | Broken | The clean next-SCP audit still reports no ModemManager modem and no CCCI/DPMAIF/WWAN devices. Object-only LLVM 21 gates cover CCCI core, CCIF, modem common and the vendor FSM/port/non-page-pool-DPMAIF groups; CI forbids ECCCI/DPMAIF modules and autoload. Integrated B4.1 offline gates validate modem member lookup, stock48 descriptor bounds and bounded LK bootchain feasibility. Trusted-firmware semantics, handoff memory, DT, link/modpost and runtime remain unproven. |
| Sensors | Rotation/accelerometer | Broken | The clean next-SCP audit exposes only PMIC ADC IIO devices, not accel/gyro. Stock identifies SCP-owned ICM4N607 accel/gyro, LTR569 light/proximity and HX9031AS SAR endpoints. The vendor SCP probe remains gated before DVFS/sensorhub publication; no user sensor device is enabled. |
| Sensors | Ambient light/proximity | Broken | The clean next-SCP audit exposes no light/proximity IIO device. This shares the blocked SCP sensorhub path. Adding only the vendor DVFS node is rejected because it would touch ULPOSC, fmeter and clocks before firmware handoff is proven. |
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
- The installed manual GNSS v051 transport creates `/dev/gpsdl0` and `/dev/gpsdl1`; a
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
