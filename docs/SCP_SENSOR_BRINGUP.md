# Nothing Tetris SCP and sensor bring-up

Status: `Broken`; runtime remains disabled.

## Tetris sensor hardware inventory

The saved stock `dumpsys sensorservice` observation identifies these SCP
endpoints.  The endpoint strings prove the stock firmware-facing identity;
they do not prove that Linux owns the underlying bus or that a similarly named
mainline driver is register-compatible.

| Function | Stock endpoint | Confidence | Linux ownership |
| --- | --- | --- | --- |
| Accelerometer | `icm4n607_acc` | Observed on Tetris | SCP firmware |
| Gyroscope | `icm4n607_gyro` | Observed on Tetris | SCP firmware |
| Ambient light | `ltr569_als` | Observed on Tetris | SCP firmware |
| Proximity | `ltr569_ps` | Observed on Tetris | SCP firmware |
| Magnetometer | Model not preserved in the available dump | Class advertised by stock product configuration only | SCP inventory must identify it |
| SAR | `SAR-hx9031as` | Observed on Tetris; outside the requested five basic classes | SCP firmware |

The exact Nothing OS 4.1 device-module source at
`ee2be53cb75670b548948636a0db1d1ff112bf12` contains no Tetris I2C/SPI child
nodes for these physical sensors.  Its AP-side sensor code is the generic
MediaTek 2.0 transport.  The stock DTBO likewise exposes no matching physical
motion, light, proximity or magnetic node.  Therefore adding guessed I2C
addresses for ICM-426xx or LTR-559-family drivers would create a second bus
owner beside SCP and is rejected.

## Exact AP-side chain

The source and package dependency chain is:

1. LK/preloader selects and authenticates the active `scp1`/`scp2` image and
   supplies TCM region-info plus loader/shared-memory handoff.
2. `mtk-mbox.ko` provides the vendor mailbox controller.
3. `mtk_rpmsg_mbox.ko` and `mtk_tinysys_ipi.ko` provide the vendor IPI path.
4. `scp.ko` consumes the firmware/handoff and exports `scp_ipidev`, ready
   notifiers and reserve-memory lookup helpers.
5. `sensorhub.ko` registers control/notify IPIs, configures SCP shared memory,
   requests the firmware sensor list and registers one HF device.
6. `hf_manager.ko` exposes `/dev/hf_manager`; a future native userspace bridge
   must translate that ABI to standard Linux sensor consumers.

All six modules are built and installed under
`extra/mediatek-sensors/` by the kernel package.  None is in `modules-initfs`,
a modules-load file, a device preset or an automatic service.  The normal
kernel also builds `inv-icm42600-i2c.ko` and `ltr501.ko`, but they have no
matching DT devices and are only historical candidates, not the active Tetris
chain.  No model-specific magnetometer driver has been selected.

The manual-only inventory patch exports `firmware_ready`, `sensor_count` and
`physical_sensor_mask`.  Mask bits 0..4 represent accelerometer,
magnetometer, gyroscope, light and proximity respectively.  The mask and the
firmware-provided model/vendor log become valid only after the SCP handshake,
shared-memory list transfer and HF manager registration all succeed.

## Compile and runtime boundaries

There is no known compile blocker in the currently packaged AP bridge: the
mailbox, RPMsg, IPI, SCP, HF manager and sensorhub modules were built together
in the prior CI artifact.  The inventory-mask revision still requires a fresh
targeted build before it can enter an image.

The first runtime blocker remains earlier than sensor enumeration:
`scp.ko` waits for the separate `mediatek,scp-dvfs` driver and returns
`-ETIMEDOUT` after three seconds because the target DT has no valid, proven
DVFS provider chain.  The clean installed image reproduced this boundary;
`sensorhub.ko` consequently cannot bind and no firmware inventory is
available.  The same boot also failed to reserve the LK-derived SCP loader
range, so enabling a guessed DVFS node would merely move execution into an
unvalidated firmware/TCM/shared-memory handoff.

## First causal blocker

The Nothing OS 4.1 SCP initialization registers a separate
`mediatek,scp-dvfs` platform driver and then waits for its probe to complete.
The target DT intentionally contains no matching device, so
`wait_scp_dvfs_init_done()` reaches the bounded failure path. The existing
timeout patch prevents a warning loop and leaves USB intact; it does not make
SCP or any sensor functional.

Adding only a vendor `scp-dvfs` node is not a valid fix. Its probe immediately
touches ULPOSC, frequency measurement and clock providers before the port has
proved the active SCP firmware, TCM region-info, secure reset contract or
shared-memory ownership.

## Required ownership chain

| Boundary | Required evidence | Current state |
| --- | --- | --- |
| Image selection | Active `scp1`/`scp2` slot, authenticated identity and bounded size | Unknown |
| Firmware state | Valid LK/preloader launch state and TCM region-info ABI | Unknown |
| LK FDT input | Structurally valid preserved FDT with portable carveout data | Host parser validates shape/ranges without mutation; live payload unobserved |
| Linux publication | Sanitized ranges and firmware state from U-Boot | Missing |
| Shared memory | Non-overlapping region below `0x90000000`, at least `0x11a9b00` bytes | One captured unit has `0x11c8000`; portability unproven |
| Loader memory | Separate `mediatek,SCP-reserved` region | Captured only; ownership unproven |
| DVFS providers | MT6878 VLP clocks, fmeter and ULPOSC with a disabled consumer | Missing |
| Sensor interface | Standard IIO devices or a documented bounded bridge | Missing |

The shared-memory and loader carveouts are distinct and must never be
substituted for one another. Physical addresses captured from this phone are
evidence for validation fixtures, not constants for production DT or U-Boot.

The live partition table contains 16 MiB `scp_a` and `scp_b` images. Their
container format, active-slot selection, authentication state and relationship
to the TCM `scp_region_info` ABI remain unknown. They are firmware inputs, not
generic sensor calibration blobs, and must not be copied into rootfs. Sensor
calibration ownership is still unlocated; it may be supplied by SCP firmware
rather than directly from `nvdata`, `nvcfg` or `persist`.

## Completed host-only boundary

A standalone libfdt test against U-Boot
`b76e47e774304ab550a6354f3286860b7caffb3a` now validates exactly one shared
and one loader carveout, two-cell 64-bit encoding, overflow, DRAM containment,
minimum shared size, non-overlap and byte-for-byte FDT immutability. Its positive
and malformed fixtures pass on the host. It is not called from the board boot
path and publishes nothing to Linux.

## Next patch boundary

The next runtime-facing work belongs in U-Boot and must remain observation-only:

1. Establish an authoritative active-slot metadata ABI.
2. Validate `scp1`/`scp2` payload identity and TCM region-info against an
   authoritative loader ABI.
3. Integrate the already host-tested carveout parser only after those inputs
   can be validated from the live preserved LK data.
4. Publish only sanitized status/ranges to Linux; do not start, stop or reset
   SCP.
5. Fail closed with no SCP/Sensorhub DT activation on any mismatch.

After host tests and bootloader CI, perform one observation-only boot while USB
NCM/SSH remains available. A later, separate candidate may compile the missing
DVFS providers and add a disabled DT node. Enabling only DVFS is its own
single-variable live test after three clean handoff repeats.

## Evidence and limits

The contract was checked against Nothing OS 4.1 Tetris branch head
`7493a2ab6b2e91ab9f7dd6a171defaafb1855b75` from 2026-08-28 and U-Boot
`b76e47e774304ab550a6354f3286860b7caffb3a`. Positive source/DT checks,
reserved-memory accounting, negative activation tests and undersized-memory
tests pass offline.

This proves the fail-closed staging contract only. It does not prove firmware
execution, remoteproc readiness, sensor enumeration, calibration, idle power,
warm reboot or suspend/resume.

The clean `fdeeda0` / kernel #128 boot still logs failure to reserve the captured
`mblock-27-SCP-reserved` range at `0xb8000000` (35 MiB). This is live evidence
that the current LK-derived loader-memory contract is not usable by Linux; it
reinforces the fail-closed gate and must not be bypassed by hard-coding that
physical address.
