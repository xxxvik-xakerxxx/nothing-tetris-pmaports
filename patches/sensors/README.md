# Sensor enumeration reply prerequisite

Status: packaged offline prerequisite; sensors remain Broken. No SCP startup
or calibrated sample has been demonstrated by this work.

The integration owner independently reran the pinned-source predicate suite
after packaging the patch as
`pmaports/device/testing/linux-postmarketos-mediatek-mt6878/1201-vendor-sensorhub-reject-mismatched-list-reply.patch.vendor`:
all cases passed, with the same offline-only limits. Publication preserves the
candidate for CI and review; it must not be advertised as working sensors
before startup is proven.

## Scope and existing progress

This independent `codex/sensor-startup-contract` worktree starts at committed
integration `844a670`. Display candidate `7e8503e` and its running CI are not
changed. No existing dirty files are included. In particular, the SCP-region
tree has an uncommitted 0094 DRAM-recovery-span patch and host tests; those are
read for context but not copied, edited or rerun. The SCP-thermal tree's report
and the newer integration `docs/SCP_SENSOR_BRINGUP.md` establish the earlier
DVFS timeout and loader-memory reservation failure. The U-Boot inventory gate
is still missing authoritative live adapters. Cicero's modem/stock-audit work
and all other shared patches are outside this change.

All AP-side facts below use local git objects at the pinned Nothing OS 4.1
device-module revision `ee2be53cb75670b548948636a0db1d1ff112bf12`, not the older
checked-out vendor files. The package pin is checked by the test. This does
not establish the identity/authentication of firmware currently in SCP.

## Concrete defect

In `drivers/misc/mediatek/sensor/2.0/sensorhub/sensor_list.c`,
`sensor_list_seq_get_list()` rejects a response only if sequence, sensor type
AND command differ simultaneously. `sensor_comm.c` dispatches notifications
by command, so a delayed LIST reply with the wrong sequence and matching
command passes the original guard. Its write position is then passed to the
shared-memory reader, whose entries supply sensor identity and gain to
`transceiver_create_manager()` and ultimately HF manager registration.

The candidate changes only the two Boolean operators to OR. All three fields
must match before the write-position access. The existing unlock,
`-EREMOTEIO`, 100 ms wait and retry limit remain unchanged. This closes one
enumeration correctness prerequisite downstream of SCP readiness; it does
not fix or bypass the first observed DVFS/loader startup blocker.

The patch is packaged in APKBUILD as a compile/static prerequisite only. It
adds no autoload rule, service, DT node, power/reset call or SCP startup. None
of the other kernel patches changes sensor_list.c; the host check verifies
that assumption before applying this candidate to the pinned source.

## Offline check

```sh
python3 scripts/check-sensor-list-reply.py /path/to/device-modules-git
```

No compiler, kernel build, CI, network, device node, SSH or phone access is
used. Patch check/application runs in disposable storage. The test extracts
the actual guarded error path and evaluates its restricted Boolean syntax:

- Eight match/mismatch combinations: baseline six false accepts; candidate
  zero errors.
- All 65536 pairs of 8-bit sequence values, including 255/0: unequal sequence
  values are rejected even when type and command match.
- Either single-operator regression back to AND is detected.

This is a predicate test, not execution of the C driver, interrupt concurrency
or firmware. Eight-bit sequence reuse after 256 requests can still alias an
old reply. Firmware reply lengths, shared-ring bounds and lifetime, calibration
ownership, startup failure recovery and safe teardown remain separate gates.
No target compilation has been attempted under the no-build instruction.

## What can be live-tested next

On the currently recorded pmOS state, there is no justified direct experiment
that produces calibrated sensor samples. Loading SCP again, adding a DVFS
node, issuing SMC/reset calls or probing guessed physical I2C sensors does not
follow from this patch. ICM4N607 and LTR569 stock endpoints belong to SCP;
their names do not establish AP bus ownership.

The next permitted observation, in a separately authorized live task, is to
record boot/kernel/DTB/rootfs identities, USB/SSH baseline, existing module
state and existing sensorhub read-only inventory parameters. Do not load
missing modules or read unowned TCM/physical memory to manufacture readiness.
The known missing firmware/loader handoff still needs an authenticated active
slot, preserved LK carveouts and decoded region-info from a reviewed
observation-only bootloader path, without starting/stopping/resetting SCP.

Only after that handoff and the DVFS/provider ownership gates pass can a
separate controlled SCP/sensorhub startup be considered. After a successful
handshake, first inspect `firmware_ready`, `sensor_count`, physical sensor
mask, model/vendor and gain. The pinned HF ABI has REGISTER_STATUS,
READY_STATUS and SENSOR_INFO queries; these are useful inventory checks, not
sample or calibration commands. Opening the device allocates a client, so
even this is a later bounded userspace gate, not a raw-memory shortcut.

For subsequent sampling, preserve the sensor-info gain, event sensor type,
timestamp, action and vendor-spelled `accurancy` field. The pinned
`hf_sensor_io.h` distinguishes DATA, BIAS, CALI and RAW actions and calibrated
versus uncalibrated sensor types are separate identities. Neither nonzero gain
nor a DATA event proves calibration provenance or physical accuracy. Locate
the matching firmware/stock per-device calibration contract before claiming
calibrated samples; do not trigger ENABLE_CALI, CONFIG_CALI, self-test or write
generic calibration data. A later explicitly enabled single-sensor acquisition
needs bounded rate/duration, validated disable, monotonic events, stationary
gravity/gyro and light/proximity response checks, plus unchanged USB/SSH.
Stop on the first timeout, reset warning or USB regression; unsafe teardown
requires a clean reboot rather than reload/retry loops.
