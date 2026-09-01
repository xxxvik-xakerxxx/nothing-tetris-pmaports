# Nothing Tetris power and charging bring-up

Updated: 2026-09-01.

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

The next gate is observation with exactly three known sources: a USB 2.0 data
host, a Type-C Rp 1.5 A source and a 5 V BC1.2 DCP. Do not test PD yet. If the
Rp source publishes a valid limit, test the existing policy unchanged. If the
DCP remains unclassified, implement only a disabled MT6375 BC1.2
detection/publication boundary. Validate USB2 PHY ownership and attach/detach
ordering before enabling it because incorrect DP/DM routing can break USB
debugging.

Charging remains `Partial` until multiple real chargers pass rate, battery and
connector temperature, termination, detach, reboot and suspend/resume tests.
BC1.2 and PD/PPS remain `Broken`; Type-C Rp selection remains `Untested`.

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
