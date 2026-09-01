# Nothing Tetris SCP and sensor bring-up

Status: `Broken`; runtime remains disabled.

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
