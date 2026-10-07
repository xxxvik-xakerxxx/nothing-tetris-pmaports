# Port summary, 2026-10-07

## Canonical sources and installed device

- pmOS: `xxxvik-xakerxxx/nothing-tetris-pmaports`, branch `main`, integrated
  source `6576019` (before this documentation update).
- U-Boot: `xxxvik-xakerxxx/u-boot`, branch `master`, source
  `791756c966e2b40f3d190c77de00ed7710e2f1e5` (new remap transaction;
  CI `37639979367` passed; installed loader remains `1d4cb6496b`).
- Installed clean kernel: `7.2.1-r168`, Linux `6.18.0 #169`, CI
  `37614381947`, source `6576019bea1d31e7ff15e2c28870329a7bce6be4`.
- Installed loader: `1d4cb6496b02971dbdb537e92f921d036f29ec7a`, explicit
  SCP-profile CI `37609012691`, slot A only; stock slot B retained. The earlier
  `bf75c572e160` loader is backed up locally for rollback. Warm boot and image
  readback passed. One subsequent r167 cold sensor startup passed; greeter
  sensor behavior remains unresolved. Display/touch were confirmed on r168.
- The complete main CI image was clean-installed on 2026-10-07 to `super`
  and `userdata`; device package `8-r17` and SensorProxy `3.9-r1` came from
  the image, with no runtime implementation replacement. Root expanded to
  104.5 GiB. Display/touch were visually confirmed and a 32 MiB USB transfer
  passed. Sensor startup was disabled in the fresh image; its opt-in was
  restored without starting modules. One subsequent r168 cold start passed,
  including SensorProxy light readings and the 32 MiB USB transfer.
- On the previous r167 installation, all five physical sensor classes and SensorProxy light updates passed
  after one supervised service start and a subsequent automatic cold start
  after user-confirmed 10-second poweroff. Startup remains opt-in. See the exact
  [clean-install evidence](SENSOR_INTEGRATION_PATCH.md#clean-ci-installation-2026-10-07).
- CI at the previous r167 checkpoint: pmOS sensor package `35746976387` passed; full image
  `35746976417` passed (rechecked and installed 2026-10-07).
  U-Boot ordinary `35747798350` and explicit SCP
  profile `35747862279` both passed. At that clean-install checkpoint the
  existing loader was retained. The later slot-A update is recorded below;
  factory/calibration partitions remain unchanged.

## Hardware summary

Before the r168 clean install, SensorProxy `3.9-r1` from CI `37589615272`
was live-installed, with rotation and automatic brightness confirmed again.
It skips duplicate scalar callbacks, not hardware sampling or validation.
No measured battery/FPS gain is claimed. Kernel r168 is now installed from
successful CI `37614381947`. Run `37600980145`, source `fdf549c`, built the kernel package
but failed before image creation: abuild removed the build tree before the
evidence collector ran. CI now appends a package-local `CLEANUP=""` override
to the mirrored kernel APKBUILD, retaining results for the collector without
changing the shipped kernel. Twelve collector tests pass, including cleanup
reproduction and retention. The full rerun passed, including kernel evidence
upload and install-image creation. The preceding run
`37592121416` built the kernel package, then failed in our evidence collector
while recursively entering a chroot's mounted `/proc`. Discovery now visits
only `chroot_*/home/pmos/build/src/*/Module.symvers`, with mounted-tree exclusion
and ambiguous-kernel rejection tested. The candidate includes fixes for active GPU-rail
voltage readback and GNSS clock-read error propagation, not GPU acceleration
or navigation enablement. The first r168 validation run failed on an obsolete
literal blocker-string assertion; the assertion was updated without removing
the runtime activation boundary.
The new separate kernel-export artifact is for dependency analysis, not
runtime enablement. Current live modem handoff remains `no-fdt`; there is
no modem, render node or camera node. GNSS transport is inactive.

### r168 clean installation

Both `super` and `userdata` writes completed successfully. The complete
download matched GitHub's archive digest; all three image checksums passed.
Boot `0c1ef926-a8c5-4b90-9340-8e43981ecbcf` reports r168, active USB/SSH,
`wlan0`, `hci0`, connected/enabled DSI and the touchscreen input device.
The user confirmed normal display and touch. No system units were failed.
The installed `/boot/boot_image.itb` hash matches the CI artifact. The 32 MiB
USB transfer passed. These checks do not establish Wi-Fi association,
Bluetooth pairing, GPU acceleration, modem operation, GNSS fixes or cameras.

SHA256:

- Boot partition image: `a102a9ace52760ebbae866012ad642e061a7711eed54a69aea14ac422637ae4b`.
- Sparse root image: `cf61bd6adca5f086a032d2339a354ad4c99283bc1020f7ad34798b51582abc16`.
- FIT: `73a565bd4bd16b3c59afd5d45e591611679f5313e5a8b48b6dd82a02ec9e0a28`.

The packaged sensor service was disabled on the fresh rootfs. It was enabled
for the next boot, without a module load/reload on this warm boot, then the
phone was powered off. After the user's full poweroff/on, cold boot
`9cb06d3b-0b5c-4b65-ba95-e0763d448647` automatically reported firmware ready,
24 inventory entries and physical mask 31 at 16.760 seconds. SensorProxy
started at 17.128 seconds. Its standard D-Bus interface advertised accelerometer,
ambient light and proximity; a bounded 20-second capture received real light
updates (52-55 lux). Rotation and proximity transitions were not observed in
that capture. The user subsequently confirmed both desktop autorotation and
automatic brightness. No system units
were failed, no critical kernel fault was found in the captured journal, and
a fresh 32 MiB USB transfer passed after sensor startup. This is one cold-start
pass after explicit opt-in, not zero-configuration or lifecycle completion.
Local logs and SensorProxy observations are in
`local/ci-run-37614381947/` in the parent workspace. The LK slots and factory
partitions were not flashed; both loader hashes matched before installation.

### Loader prerequisites

The next modem candidate, `0006-dpmaif-use-standard-allocation.patch.vendor`,
removes automatic selection of the incompatible vendor CMA pool while leaving
generic kernel page-pool support unchanged. CI `37641267429`, source `a88f8de`,
passed all overlay/candidate tests, including twelve actual Makefile selection
cases and rejection of a mutant restoring the unsafe default. The full image
job was deliberately skipped via `validation_only=true`; no new kernel/module
link or device installation is claimed. The candidate is outside APKBUILD.

The hash-verified r168 native DTB declares separate `mediatek,md_mem_usage`
fragments, not exclusive ownership of the complete 512 MiB remap window.
These inherited fragments cannot authorize the new loader's full-window
mapping. Contiguous reservation before firmware copy/remap and kernel memory
discovery remains necessary; no SMC was attempted on the running phone.

U-Boot `791756c966` adds a checked two-stage remap executor with injectable
transport, explicit consumed/failed state and verification of every owned
register field. Native tests and full ARM64 CI `37639979367` passed.
No production SMC adapter or boot caller was enabled, and this code
was not flashed. Exclusive reservation, authenticated platform selection,
reset ownership, complete EMI policy and Linux handoff remain prerequisites.

U-Boot modem prerequisites now on `master`: `f7ed9f7f6b` accepts bounded
zero-tail 48-byte stock v3 descriptors; `b2917cce8f` verifies signed modem
headers/payloads (full CI `37597316422` passed). `bbbc3b06c5` adds a bounded
relative ROM/DSP layout planner for the observed v6/DRDI-mode-3 profile; native
full CI `37601037773` passed. `b510cbb875` adds the initial physical block-map
planner: region/DSP/padding flags, overflow-safe base arithmetic, full reservation
coverage and an atomic 32-block limit; full CI `37603138572` passed.
`b9d96e38da` adds full-window remap bounds and masked register expectations:
the audited ATF maps 512 MiB in 32 MiB pages, not only the ROM's 480 MiB
declaration. Full CI `37604538052` passed, including native bounds tests.
`1167c6c1d9` additionally encodes EMI range arguments and raw readbacks without
silent ATF address truncation; full CI `37608301896` passed. Offline execution
of the pinned ATF handler passes 64 emulated scenarios, including one-shot
slot rejection and permission-preset writes. This does not test physical
protection or activate a modem boot path.
No memory is allocated/freed and no
protection SMC is executed. The exact stock LK skips separate DRDI loading in mode 3,
but still marks DRDI memory windows. These are unactivated loader
prerequisites, not modem boot: device-root/rollback policy, physical reservations,
remapping, secure reset/protection and CCCI publication remain unresolved.
See the [U-Boot implementation notes](https://github.com/xxxvik-xakerxxx/u-boot/blob/1167c6c1d9/doc/board/mediatek/mt6878-tetris.rst)
and the [exact ATF/LK memory-contract trace](MODEM_SIM_EVIDENCE_PLAN.md#2026-10-07-remap-and-protection-contract).
The explicit SCP-profile build `37609012691` of `1d4cb6496b` was flashed to
`lk_a` on 2026-10-07 and retained for the r168 installation. Ordinary push builds have
SCP preparation disabled and were not substituted for the sensor-ready profile.
The 3,275,616-byte LK artifact passed manifest, checksum, aligned-payload and
partition-size checks. Readback from the phone matches SHA256
`b8baaba76c131c6a47ccfd8ed63a5cdda55337c4b76e5bc6c9e665748324f983`.
Stock `lk_b` retained SHA256
`812873696e06a972eb5d67f5035687b91b1b48e4df0d25efc15d52fbf09b2518`.

Warm boot `a4478ecb-7af2-41d2-bba7-553c739e7d17` reports the new U-Boot
version, unchanged r167 kernel and USB/SSH recovery. The native display
connector appeared after normal deferred initialization, not at the first
early probe. SCP stopped at the documented warm-reboot `preflight -16` gate;
the sensor service refused startup rather than reusing unprepared state.
After full poweroff, cold boot `88190cd5-a538-4a6c-9afc-ec73b95d5059`
reports SCP secure state 3 and error 0. The transport automatically reports
firmware ready, 24 entries and physical mask 31 at 17.005 seconds; SensorProxy
starts at 17.432 seconds. User login occurs only at 1245.907 seconds. The user
reports sensor-driven behavior working after login but not before it. Thus
hardware/service startup is not login-triggered; the greeter's sensor use is
an unresolved desktop integration issue, not a demonstrated loader failure.
USB/SSH recovered and both services remain active. This is one cold-start
pass, not completed regression/lifecycle coverage or visual display/touch
confirmation. No modem execution was enabled.

A 60-second USB-attached idle capture passed on the same boot
(`local/live-logs/20261007T074856Z-172.16.42.1-idle-delta`). CPU idle counters
advance, but the phone is charging: this is not a battery-discharge test.
Our display-unblank service took 11.034 seconds and connectivity 6.311
seconds on that boot. These durations alone do not identify CPU cost or
justify removing initialization waits.

Works below refers to the demonstrated basic function, not every lifecycle
or hardware variant. Partial does not mean production-ready.

| Subsystem | Status | Demonstrated / remaining |
| --- | --- | --- |
| Boot, UFS/root expansion | Works for tested setup | r167 clean flash reaches userspace; writable expanded root. Other firmware/SKUs remain unverified. |
| Native display | Partial | Route/startup and frame-end plane updates are in main (`aecf4f4`, packaged `0097-drm-mediatek-update-MT6878-planes-at-frame-end.patch`). User repeatedly confirmed no stripes/flicker, including r167. Fixed 60 Hz/software rendering; 120 Hz, acceleration and full power lifecycle remain. |
| Touch and keys | Works for basic input | Touch and power/volume keys tested; not a claim of completed suspend/wake coverage. |
| Sensors | Partial | All five physical classes emit real data; 24 firmware entries. Correct rotation, automatic brightness and proximity screen blank/restore confirmed. Brightness is stepped; calibration, warm boot, suspend, repeated cold starts and another unit remain. |
| USB/NCM/SSH | Partial | Repeated clean boots and 32 MiB transfer gates pass; full reconnect/suspend lifecycle remains. |
| Wi-Fi / Bluetooth | Partial | Initialization and earlier Wi-Fi association/traffic and Bluetooth discovery demonstrated; pairing/profiles/coexistence/suspend are not complete. |
| Audio | Partial | Both speaker paths and microphone capture demonstrated in earlier tests; full route/call/lifecycle coverage remains. |
| Haptics / torch | Partial | Bounded physical effects tested; full lifecycle and camera strobe remain. |
| Battery, charging, thermal | Partial | Telemetry, charging observations and thermal polling exist; charger classification, sustained charging/thermal safety validation and idle power remain. |
| GNSS | Partial, transport only | Supervised firmware/transport work exists; no verified position fix or complete GeoClue navigation stack. |
| SIM, calls, SMS, mobile data | Broken | No operational modem demonstrated. Sensor proximity used a local dummy call, not GSM. |
| GPU acceleration | Broken | No render node or accelerated compositor demonstrated; compile-only groundwork is not runtime support. |
| Cameras | Broken | No working preview/capture; clocks/topology/identity groundwork only. |
| microSD | Partial | Controller probes; card insertion and real I/O remain untested. |
| NFC | Not present | No NFC hardware on this device. |

SCP startup is opt-in. The exact slot-A ATF/SCP profile, authenticated firmware,
dynamic reserved memory, and zero-TCM preflight remain mandatory. Warm reboot
can leave SCP disabled deliberately. No secure-boot bypass or universal NOS
4.0 support is claimed. See [sensor evidence](SENSOR_DESKTOP_INTEGRATION.md),
[display audit](DISPLAY_FIRST_FRAME_AUDIT.md) and [status history](CURRENT_STATUS.md).
The unsolicited on-screen keyboard issue was observed but deferred, not fixed.

## Branch consolidation

Only `main` (pmOS) and `master` (U-Boot) are active remote branches after
cleanup. Former remote tips are retained as immutable-by-convention tags:
`archive/2026-09-22/<former-branch-name>` in the corresponding repository.
This preserves unique work without enabling unvalidated experiments in the
default image. Archived does NOT mean merged or hardware-verified. Local
worktrees and uncommitted research files are intentionally untouched.

See `git tag -l 'archive/2026-09-22/*'` or GitHub tags for exact retired
tips. Unmerged research remains recoverable there, including NOS 4.0
early-boot diagnostics; it is not declared compatible or enabled.

Next: [remaining work and test gates](PORT_COMPLETION_PLAN.md).
Research: [documentation index](README.md).
