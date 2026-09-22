# Native display: current implementation and open research

Status: **Partial**. Native output and touch are usable on clean r167, with
repeated user confirmation of no stripes or redraw flicker. Current mode is
1080x2400 at 60 Hz, with software rendering. 120 Hz, GPU acceleration and
complete power lifecycle are not established.

## Implemented in main

- Native panel/DSI/DSC/OVL dependency series, including panel patch 0050.
- Route correction 0096: retain the verified MT6878 graph.
- Plane-update correction 0097: use frame completion rather than frame-start
  vblank for MT6878 CPU plane updates.
- Packaged greeter idle/unblank handling; no temporary register-writing
  diagnostic module is required for normal display output.

The kernel APKBUILD is the authoritative patch order.
[PATCH_SERIES.md](PATCH_SERIES.md) maps the active groups.

## Causal evidence

The broken graph left DSI input at 1x1. Matching the recorded LK route
restored visible output, but movement still caused flicker. B4.1 identifies
0xd00 bit 0 as RSZ0 and bit 2 as PQ_OUT_CB4; enabling both does not reproduce
the working graph.

On the working route, 30 fresh DSC DONE events in 523854 us disproved the
earlier inference of 25 Hz scanout. Rendering FPS and scanout cadence are
different measurements. Sticky, unacknowledged DSC status is not an error rate.

A bounded live change selected OVL completion BIT(1) instead of frame-start
BIT(14), without engine resets. All 256 samples retained the intended route,
with fresh DSC DONE and no abnormal EOF. No flip timeout, BUG or Oops was
observed; USB remained up. The user confirmed the redraw flicker disappeared.
Patch 0097 packages that correction. Clean r153 and later r167 installations
confirmed visible output without the diagnostic module.

A readiness-synchronized, idle-inhibited ten-cycle DPMS test passed on r153
after an earlier unsynchronized failure. This is not system suspend/resume
or comprehensive lifecycle validation.

Evidence filenames in the original local display worktree:
`display-native-r151-lk-route.txt`,
`display-native-r151-frame-meter-route.txt`,
`display-native-r151-frame-end-irq.txt`. These are local captures, not
downloadable repository artifacts.

## PQ and POSTMASK: still experimental

Inherited PQ ownership is unresolved. A bounded B4.1 POSTMASK relay change
CFG 0x146 -> 0x147 preserved other registers and restored the original value.
Before/during/after samples had 16/15/15 FRAME_DONE events, but the relay
transition produced one abnormal EOF. Do not ship this live register toggle.

`patches/native-display/0003-mt6878-postmask-topology.patch` is not in
APKBUILD. It models the B4.1 resource 0x14010000/0x1000, SPI 317, clock,
component path and mutex bit 14. Host checks covered 768 register-array
comparisons and rejected the d00=0x50005 mutant. This is source-level
evidence, not a complete DT/schema, hardware or lifecycle pass.

Before activation, prove inherited engine/DMA quiescence, validate the full
DT, and configure the path while stopped before OVL fetch starts. Existing
configure-before-start callbacks alone do not prove quiescence: the CRTC
enables its mutex before configuration and does not stop all inherited
engines. Other PQ blocks also remain inherited.

Next: safe ownership, controlled blank/brightness/suspend, sustained redraw,
three cold starts, 60/120 Hz transitions and second-panel/handset validation.
