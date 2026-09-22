# Port summary, 2026-09-22

## Canonical sources and installed device

- pmOS: `xxxvik-xakerxxx/nothing-tetris-pmaports`, branch `main`, integrated
  source `7c0ce0389c03d2820155bde72192aca95281de8f` (before this documentation update).
- U-Boot: `xxxvik-xakerxxx/u-boot`, branch `master`, source
  `a55dc63befc0ec97bd946e412d6c14d3a82b9cc9`.
- Installed clean kernel: `7.2.1-r167`, Linux `6.18.0 #168`, CI
  `35729169169`, source `ff4433f1515a4f29529d7f14684b5aea9c62858a`.
- Installed loader: `bf75c572e16079a36ab43a032be3360c3e93250c`, CI
  `35718518185`, slot A only; stock slot B retained. Master has the same
  runtime code, plus documentation and reservation-order CI coverage.
- The r17 startup helper and desktop sensor backend were installed separately
  for live validation. They are now packaged in main, but that complete new
  image has not yet been clean-installed and tested.
- CI at this checkpoint: pmOS sensor package `35746976387` passed; full image
  `35746976417` in progress. U-Boot ordinary `35747798350` and explicit SCP
  profile `35747862279` both passed. No local build or new flash was performed
  for source consolidation.

## Hardware summary

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
