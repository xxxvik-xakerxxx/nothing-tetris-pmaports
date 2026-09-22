# Remaining port work

Current evidence: [PORT_SUMMARY.md](PORT_SUMMARY.md).
Source lives in pmOS main and U-Boot master; archived experiments must be
reviewed before reuse, not merged merely because they exist.

## Next gates

| Area | Next result needed |
| --- | --- |
| Packaged sensors | Clean-install the complete CI image, verify opt-in automatic startup and standard desktop consumers without host-side file fixes. |
| Sensor lifecycle | Three controlled cold starts; establish safe warm-start ownership; calibration, client stress, suspend/resume, clock-vote lifetime and idle power. |
| Display | Preserve stable redraw; prove PQ/POSTMASK ownership before activation; panel/host 120 Hz timing, repeated blank/unblank and suspend. |
| GPU | Prove rail readback, power domains, firmware and memory ownership before Panthor probe; then render node and accelerated compositor. |
| Modem | Complete authenticated handoff, secure ABI and DMA isolation before runtime; then SIM registration, calls, SMS and data. |
| GNSS | Resolve navigation protocol and userspace bridge; demonstrate timed fix/accuracy, restart and radio coexistence. |
| Cameras | Variant-aware bounded identity read with correct clocks/reset/rails; then CSI/SENINF/ISP/IOMMU/CCU pipeline and capture. |
| Power | BC1.2 source classification without disrupting USB; partially discharged charging/thermal tests; unplugged idle measurements. |
| Audio/radio | Clean packaged playback/capture and endpoint mapping; Bluetooth pairing/profiles, Wi-Fi reconnect, coexistence and suspend. |
| Remaining I/O | microSD real card I/O, torch lifecycle, flash strobe, USB identity/reconnect and physical wake. |

The unsolicited keyboard issue is deferred. It is not evidence of a sensor
or display-driver fault.

## Test contract

1. Record artifact hashes, boot ID, kernel/modules/DT, slot and firmware profile.
2. Establish recovery and baseline USB/SSH, display/touch and system logs.
3. Change one hardware variable per experiment; stop at the first causal error.
4. Require fresh data or physical behavior, not just a successful probe.
5. After an unsafe failure, collect evidence and power-cycle. Never repeatedly
   unload/reload vendor remote-processor or connectivity modules.
6. Check a 32 MiB USB transfer and relevant display/radio/audio regressions.
7. For a Works claim, reproduce from CI packages on a clean install and complete
   the relevant cold/warm/suspend/stress and second-unit/variant gates.

Do not bypass zero-TCM or firmware-authentication guards, disable watchdogs
to conceal faults, hard-code measured dynamic addresses, or automatically
enable unvalidated consumers. SCP remains opt-in.

## Known constraints

- Keep `clk_ignore_unused` until the early failure without it is understood;
  the previous one-shot removal reset the phone without a useful ramoops record.
- Thermal polling exists; thermal IRQ/hardware-trip behavior is not validated.
- USB-connected captures do not measure unplugged idle drain.
- Suspend testing needs coordinated physical wake; do not assume RTC wake exists.
- The CI manifest's generic U-Boot minimum does not describe SCP prerequisites.
  Keep the sensor startup guide's exact tested loader/profile requirements.
