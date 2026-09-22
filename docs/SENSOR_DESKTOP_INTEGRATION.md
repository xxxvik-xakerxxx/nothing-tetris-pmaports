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
The next full rootfs workflow now builds and installs the backend as an
extra package and checks its executable, service drop-in and udev rule.
The already-running full image run `35738754109` contains only the earlier
startup helper, not this later backend. Do not flash that older image and
expect this later integration to be present.

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
