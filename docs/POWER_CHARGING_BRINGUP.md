# Nothing Tetris power and charging bring-up

Updated: 2026-09-04.

This document records the measured power state and the next safe experiments.
It does not authorize charger-register writes, forced current limits, PD/PPS,
OTG, suspend beyond the existing s2idle boundary, or any change that can remove
USB NCM/SSH recovery.

## Current evidence

The installed pmaports image is `f607513` with kernel `6.18.0 #123`. Its saved
power capture showed all of the following at the same time:

- MT6375 charger state `Charging`;
- AICR and ICHG both at 500000 uA;
- +284424 uA net battery current at 62 percent;
- TCPM online at 5 V, USB Type-C default mode and `CURRENT_MAX=0`;
- USB gadget/device role and NCM retained as the debug path.

This proves useful telemetry and a bounded 500 mA path. It does not prove fast
or production charging. The policy must not infer a higher safe current from
voltage, cable presence, charger state or raw ADC values.

The clean `fdeeda0` image with kernel `6.18.0 #128` reproduces the same boundary:
AICR/ICHG 500000 uA, +195312 uA net battery current at 87%, 31.9 C battery
temperature and TCPM `CURRENT_MAX=0`. This is a clean-install confirmation of
the fallback, not a source-classification improvement.

The same installed image later observed a USB PD power bank contract without
any manual runtime writes or package changes. TCPM published 5 V, 2000000 uA,
`USB_TYPE_C PD [PD_PPS]`, sink power role and device data role. The existing
source-current policy set both AICR and ICHG to 2000000 uA, while Wi-Fi and SSH
remained available. The battery was already at 100 percent, 4.493 V and 32.7 C;
its +61645 uA net current therefore demonstrated near-full taper. A later
snapshot kept the same source contract and limits while the gauge changed to
`Not charging` at +20141 uA and 33.5 C. This supports full-battery termination,
but does not prove a complete charge cycle, sustained 2 A charging, programmable
PPS operation or production-safe thermal behavior.

On 2026-09-04 the same installed kernel was connected to the development host
and USB SSH succeeded at `172.16.42.1`. Type-C reported sink power role, device
data role and `default` power operation mode. The sysfs list `[C] PD PD_PPS`
therefore selected plain Type-C (`C`); PD and PD_PPS were supported alternatives,
not the active contract. `CURRENT_MAX=0` correctly retained AICR/ICHG at 500000
uA. At 100 percent and 4.492 V the gauge reported +103759 uA and 32.2 C. This is
a second valid USB-host fallback/taper snapshot, not evidence of failed PD or a
charge-rate measurement.

A later 2026-09-04 snapshot used a fast-charge-capable power bank while SSH ran
over Wi-Fi. This attachment still selected plain Type-C at 5 V with
`CURRENT_MAX=0`; the policy held AICR/ICHG at 500000 uA. The gauge was at 100
percent, 4.493 V and 33.6 C. The source being capable of fast charging does not
prove that this cable/attach negotiated PD, so this run is recorded as another
fallback case and not counted as a PD regression or fast-charge result.

## First charging blocker

The native path has MT6375 TCPC attach state and a conservative policy consumer.
It does not yet implement the Nothing OS 4.1 MT6375 charger ownership for BC1.2:

1. enable and completion state for BC1.2 detection;
2. controlled USB2 PHY DP/DM routing;
3. the `fl_bc12_dn` completion interrupt;
4. `PORT_STAT` decoding;
5. SDP/CDP/DCP publication through the power-supply API.

Patch `0043-power-supply-nothing-tetris-source-current.patch` can consume a
classified Type-C Rp or PD current, but correctly falls back to 500 mA when
`CURRENT_MAX` is zero. It cannot classify the saved source by itself.

The next source-classification gate still needs a USB 2.0 data host, a known
Type-C Rp source and a 5 V BC1.2 DCP. If the Rp source publishes a valid limit,
test the existing policy unchanged. If the DCP remains unclassified, implement
only a disabled MT6375 BC1.2 detection/publication boundary. Independently
repeat the now-observed 5 V / 2 A PD path from a partially discharged battery
with rate, battery/connector temperature, taper, termination and detach logs.
Keep PPS and higher-voltage requests disabled. Validate USB2 PHY ownership and
attach/detach ordering because incorrect DP/DM routing can break USB debugging.

Charging remains `Partial` until multiple real chargers pass rate, battery and
connector temperature, termination, detach, reboot and suspend/resume tests.
Fixed 5 V PD current selection is `Partial`; BC1.2 and PPS remain `Broken`, and
Type-C Rp selection remains `Untested`.

## Idle drain blocker

The reported loss of roughly half a battery overnight is a valid symptom, but
the existing captures cannot identify its cause. They deliberately preserved
`usb0`, kept the MTU3 device controller runtime-active with
`power/control=on`, and included charging or near-full intervals.

The first subsystem candidate for an A/B test is Wi-Fi, not a confirmed cause:

- `18400000.wifi` reports runtime PM unsupported;
- WLAN IRQ and worker wake counters rise during connected idle captures;
- the saved wakeup-source data does not prove a wakelock blocking s2idle;
- cluster-off residency already exists on kernel #123.

Run the next measurement locally while physically unplugged. Use separate clean
boots with Wi-Fi associated and Wi-Fi disabled, leaving all other variables
unchanged. Each interval must record start/end coulomb counter, elapsed
monotonic time, screen state, suspend result and wake/IRQ deltas. Reconnect USB
only after the interval to retrieve logs.

Idle drain remains `Broken` until repeatable unplugged measurements identify a
causal owner and the fix passes one-hour idle, overnight idle, reboot and
suspend/resume gates without degrading USB or Wi-Fi recovery.
