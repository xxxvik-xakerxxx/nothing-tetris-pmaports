# Sensor transport to the standard desktop stack

Status: **Partial**, with live end-user behavior verified on 2026-09-22.
This is not a claim of calibrated sensors, working GSM calls or lifecycle
completion. Kernel r167 and the prepared cold SCP handoff remain prerequisites.

## Implementation

`integrations/sensor-proxy/` adds a native MediaTek HF backend to pinned
iio-sensor-proxy 3.9. It uses upstream D-Bus, authorization, subscriber
tracking, orientation hysteresis and mount-matrix handling. Phosh and
gnome-settings-daemon remain responsible for screen behavior. No alternate
D-Bus service implementation or brightness-control script is introduced.

The backend probes only the HF class/device with explicit opt-in and ready
firmware. It checks the version-pinned HF inventory and gains. Each active
sensor has its own client, enabled only while claimed. Release closes the
client, so a subsequent claim cannot replay its old FIFO. Invalid data,
control errors, transport loss or missing initial samples fail the service
visibly; there are no module resets/reloads or automatic restart loops.
Gyroscope and magnetometer data are not falsely advertised as a calibrated
compass or an IIO interface.

The optional `iio-sensor-proxy-tetris` APK installs a separate binary, a
drop-in for the existing `iio-sensor-proxy.service`, and a Tetris udev mount
matrix. It depends on device package `8-r17` for the handoff/startup guards.
The opted-in sensor startup service Wants the proxy; the proxy waits for
successful startup and checks fresh readiness. No second owner of the same
systemd D-Bus service name is installed. The underlying startup service
remains disabled by default pending lifecycle validation.

## Live evidence

### Standard activation packaging fix

The r179 clean install contains the service/drop-in but lacks a system-bus
activation descriptor. A standard D-Bus request reports "not activatable";
after a verified cold handoff, one systemd start brings up the real HF
inventory (24 entries, physical mask 31) and accelerometer/light properties.
Package `3.9-r2` installs `net.hadess.SensorProxy.service` with the existing
`iio-sensor-proxy.service` as its systemd owner. This retains upstream D-Bus
and subscriber behavior, without a boot polling script or duplicate service.
It does not solve inherited warm SCP state or establish calibration.
The descriptor was installed live on r179 and the bus configuration reloaded.
The proxy deactivated cleanly and was immediately reactivated while a client
was present; accelerometer/light properties remained true, the HF inventory
was unchanged and USB stayed up. Only the userspace proxy was restarted.
CI [37970239648](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37970239648)
passed and built package `3.9-r2` from `d941aa6`. Its APK SHA256 is
`ba8ce7185648dcc7d745c516a158fd4de9ff02a9722ace8e483c842f5b0d792c`.
The hash-verified APK was installed offline through APK on the same r179 boot;
the activation descriptor is package-owned, both services remain active and
standard accelerometer/light properties are true. No failed system units or
USB regression were observed. APK triggers regenerated initramfs/FIT using
the unchanged kernel. Automatic activation on a new cold boot and lifecycle
validation remain pending; live replacement is not a clean-image pass.

### Scalar callback optimization candidate

Package `3.9-r1` suppresses repeated equal light values and repeated equal
near/far states in our HF adapter. It preserves timestamp/error validation,
the first sample deadline, all transitions and the first value after every
new claim. Accelerometer delivery, sampling periods and upstream desktop
code are unchanged. ABI tests include zero light, negative-value rejection
handoff, proximity transitions and claim reset. CI `37589615272` passed for
source `c82813f02d0662beac0865d5b99da2976a27107c`. The verified `3.9-r1` APK
was installed on boot `6266d1ef-9e48-4959-8d33-27e14a74f2e1`; only the
userspace proxy was restarted, with no vendor-module reload. Standard APK
triggers regenerated initramfs/FIT from the unchanged installed kernel.
The user confirmed rotation and automatic brightness. The bounded D-Bus
capture also observed normal/right-up/left-up orientation, light/backlight
changes and proximity transitions. There were zero failed system units.
Post-update 32 MiB USB transfer gate `20261007T075248Z` passed.
No battery or frame-rate improvement has been measured, and this is a live
package update rather than clean-image validation of r1.

APK SHA256:
`bb4bb92549552f0d82166f37f93fcbf7ead835c6c561da3ab0b8ffb5ce472152`.
Evidence `local/live-logs/20261007-proxy-r1.jsonl`, SHA256:
`eec72abefc8cdb32ebdef6f5401424417c9c0d0e68c9010a684ff36227c9995f`.

### Original behavior verification

Boot: `126ad547-de18-4874-bd8d-959aaeadd4f4`, kernel `7.2.1-r167`.
Installed U-Boot: `bf75c572e16079a36ab43a032be3360c3e93250c`.
The binary is from CI `35742898933`, source `37b2bc9`, SHA256:
`eafd756b3472d03849dbc852b5d40f69d5124c145ce99d0dcf872d1c51bc559e`.
Only userspace files/services were changed; SCP modules were not reloaded.

- Standard `monitor-sensor` discovers accelerometer, light and proximity,
  receives live light readings and orientation transitions.
- Initial identity matrix inverted the UI. With the phone held normally,
  USB down, raw Y was +8413..8643 (gain 1000), reported as `bottom-up`.
  Matrix `-1,0,0;0,-1,0;0,0,1` corrects display axes. User confirmed
  upright portrait and both landscape directions. Flat face-up Z is preserved.
- User confirmed automatic brightness. Recorded light ranged 1..124 lux
  and actual backlight changed 510 -> 64 -> 510 (maximum 4095).
  User reports visibly stepped transitions: smoothness is **not** verified.
  Idle dimming was enabled and separate 510/160 jumps occurred without
  light changes. This is a candidate contributor, not proof of the cause.
- Real proximity changed false -> true -> false while covering/uncovering.
- In GNOME Calls' local dummy provider, the user confirmed that covering
  the sensor blackens the call UI and uncovering restores it. MM, ofono
  and SIP were unloaded before the dummy call; no call was sent to a network.
  The test call disappeared and the previous providers were restored afterward.
  This verifies proximity UI behavior, not cellular calls or modem readiness.

The bounded observation client is `scripts/check-live-sensor-proxy.py`.
Raw trace: `/private/tmp/tetris-hf-behavior.jsonl`, SHA256:
`f26e84057af5cb42a22cd809f907a2c797bb9deb1131eb84d9e277ea9b1487b7`.
Sample timestamps and backlight readings are observations, not generated data.

## CI and installation boundary

CI `35744753594` (source `d6da684`) built the optional ARM64 APK and passed
the upstream orientation/matrix/policy tests and HF ABI tests. APK SHA256:
`1930baf2a276389bff9dc380049869c18adf6af9bda5f82208321847ca4de403`.
The APK was downloaded and verified, but has not yet been installed as a
package on the phone. Live tests used its equivalent sources/configuration.
The main rootfs workflow builds and installs the backend as an extra package
and checks its executable, service drop-in and udev rule. Current CI state is
tracked in [PORT_SUMMARY.md](PORT_SUMMARY.md). Older startup-only images do
not contain this backend.

Post-integration 32 MiB USB regression gate passed:
`local/live-logs/20260922T151139Z-172.16.42.1-regression-gate`.

Remaining gates: clean packaged installation, repeated startup, warm-handoff
ownership, suspend/resume, client lifetime/stress, calibration and units
against reference measurements, brightness smoothness, and a second handset.
The user requested source consolidation into main. This preserves the tested
implementation and its prerequisites as guarded experimental support; it
does not enable the startup preset, certify lifecycle behavior or assign a
blanket sensor Works status. Future clean installs must use the new image
containing the backend, not the earlier startup-only image.
