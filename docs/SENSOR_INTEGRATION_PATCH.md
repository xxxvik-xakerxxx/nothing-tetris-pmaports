# Sensor integration patch on the verified r167 baseline

This integrates the working manual SCP/sensorhub path into one bounded
startup command and an opt-in systemd unit. It is **Partial** support, not
a declaration that every phone function, calibration or suspend works.

## Reproducible baseline

- pmOS source: `ff4433f1515a4f29529d7f14684b5aea9c62858a`, CI
  `35729169169`, kernel `7.2.1-r167` / Linux #168.
- Evidence/tools checkpoint: `a5193ef`, same kernel and image as above.
- Installed U-Boot: `bf75c572e16079a36ab43a032be3360c3e93250c`;
  CI `35718518185`, LK SHA256
  `7fd5bb218af3d3371dca59930f320ba98d38ddba6cbf7229851c33ba746d62fe`.
- Vendor modules: Nothing OS 4.1
  `ee2be53cb75670b548948636a0db1d1ff112bf12`.
- The U-Boot diagnostic remains restricted to its authenticated ATF/SCP
  profile and slot provenance. This patch does not broaden firmware/SKU
  support or copy calibration from the test phone.

The r167 baseline already contains the memory bounds, logger receive-buffer,
shared infracfg regmap and DT fixes. Do not apply just the new userspace
service to an older kernel and assume the prerequisites are present.
Do not downgrade the installed diagnostic U-Boot to the older generic
minimum recorded in the pmOS CI manifest.

## Included changes

Device package `8-r17` adds Python 3, `/usr/libexec/nothing-tetris-sensors`
and `nothing-tetris-sensors.service`. Kernel/display/USB code is unchanged.
The helper verifies the board, completed secure handoff, zero error codes,
enabled SCP node and unique shared infrastructure phandle before loading
anything. It performs the proven sequence once: SCP with `bootstrap_26m=1`,
then sensorhub, then bounded polling of the real firmware inventory.

Success requires a character HF device, all three modules, nonempty inventory
and all five physical class bits. Merely returning from modprobe is not
success. Already-ready state is idempotent. Partial state, timeout or failed
modprobe must not trigger another load, automatic reset or unload. The
attempt marker remains under `/run` until reboot. The service has no restart
policy and no hardware teardown command.

The preset explicitly disables this experimental unit. Opt-in cold-boot
tests must precede any future default enablement. Enabling the unit on the
test handset is an experiment, not clean-install verification of this new
device package. On warm boot, the current U-Boot guard still refuses stale
TCM; the service must fail visibly without disturbing USB/SSH. Removing that
guard is not part of this patch.

## Commands after installing the CI package

```sh
sudo /usr/libexec/nothing-tetris-sensors preflight
sudo /usr/libexec/nothing-tetris-sensors start
sudo /usr/libexec/nothing-tetris-sensors status
```

For an explicitly supervised cold-boot experiment:

```sh
sudo systemctl enable nothing-tetris-sensors.service
sudo systemctl poweroff
```

After full poweroff, power on without volume keys. Inspect both
`journalctl -b -u nothing-tetris-sensors.service` and the helper's `status`.
An active oneshot service does not replace a fresh hardware-status check.
Use the existing `scripts/check-live-sensor-samples.py` from the checkout
for bounded samples of each sensor class; it is not an IIO daemon.

To remove the opt-in on the next boot:

```sh
sudo systemctl disable nothing-tetris-sensors.service
sudo systemctl poweroff
```

Do not unload/reload the vendor modules. Disabling or stopping the service
does not release the diagnostic clock vote or tear down a running SCP;
full poweroff is the current cleanup boundary. A start failure likewise
requires inspection and a clean power cycle, not automatic retry.

## Validation and remaining gates

Ten offline startup tests cover wrong/malformed/missing handoff, ambiguous
nodes, missing/incorrect infrastructure owner, partial module state,
idempotent ready state, exact load order, failed modprobe, bounded timeout,
attempt retention, inventory completeness and missing device. Six sample
ABI tests remain enabled in CI. Package checks parse the Python source;
overlay validation verifies explicit disablement and bounded/no-restart unit.

On r167 cold boot `e60a958f-55af-4b19-a2ae-59e294ef10a6`, the new helper's
preflight/status and two consecutive start calls passed with the already
working 24-entry inventory, without creating a load-attempt marker or
reloading modules. Systemd unit verification and start passed. This only
proves adoption of already-ready state, not boot-time initialization.

Following a requested full poweroff, the next observed boot
`126ad547-de18-4874-bd8d-959aaeadd4f4` initialized SCP and sensorhub through
the enabled unit alone. Preflight passed and the service completed at
16.95 seconds with 24 entries and physical mask 31. No manual modprobe was
issued on this boot. Five-second captures returned:

| Class | Samples | Observed rate |
| --- | --- | --- |
| Accelerometer | 124 | 25.011 Hz |
| Gyroscope | 123 | 25.067 Hz |
| Magnetometer | 124 | 24.997 Hz |
| Light | 41 | 8.333 Hz |
| Proximity | 1 | On-change; raw value 5 |

System state remained running and USB/SSH survived. No BUG/Oops/panic,
SCP ready timeout or awake-handshake failure was found before or after capture.
The subsequent 32 MiB USB transfer gate passed; logs:
`local/live-logs/20260922T141854Z-172.16.42.1-regression-gate`.
The exact manual power-off interval has not been confirmed by the user;
do not count this as three controlled cold repeats or clean-package testing.
Evidence is saved at `/private/tmp/tetris-sensors-autostart-126ad547/`.
SHA256 of `kernel-after`:
`856880205c5b7d0ab6f4908eb9044f4b63d2adaa5d9b6badbefd076dfd5f9ab1`;
of `service-journal`:
`ed7e129dbfd482f95d1f46df5784ae20e0c9f06f871b6fe97d92cfa5fd944efc`.

Integration commit `fd61e7b` has been pushed. CI `35738754109` passed
the overlay and source/ABI checks; image building is still in progress.

Still required: repeated automatic cold starts, CI package clean installation,
safe warm-start ownership, controlled motion/light tests, calibration
provisioning, native IIO/sensor-consumer integration, suspend/resume,
clock/resource lifetime and idle power, and another supported handset.
Default enablement and production merge remain gated on these results.
