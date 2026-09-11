# Native display first-frame audit, 2026-09-10

Status: **Broken**. No new kernel candidate or image was built in this cycle.
Installed baseline: CI `34470405429`, source `a03529f61a46`, kernel
`6.18.0 #152`, package `6.18-r151`. Integration remains `0b8c416`.

## Fresh active measurement

The user authorized reloading the diagnostic module. Reloading with no
experimental parameters after restarting greetd and verifying DSI-1 enabled
produced 20 samples at kernel uptime approximately 3269 seconds:

- DSC interrupt status: `0x8` in every sample (abnormal EOF).
- DSI input: `0x00010001` in every sample (1x1).
- DSC control: `0x00010081`.
- Mutex SOF/EOF: `0x41`; membership: `0x1280ffc7`.
- OVL0/1/2 flow: `0x08041020`, `0x080c1020`, `0x080c1020`.
- OVL0/1/2 positions: `0x401d`, `0x13`, `0x09`, unchanged across samples.
- USB remained UP at the control address; subsequent 32 MiB transfer passed.

Zero diagnostic IRQ counters with DSC INTEN zero do not independently prove
that no frames completed. Here the sampled abnormal EOF and static input
counters are the evidence for the stall. Visible pixels remain unverified in
this cycle and no support status is promoted.

USB evidence:
`local/live-logs/20260910T134858Z-172.16.42.1-regression-gate`.

## Measurement validity

An earlier capture at uptime 3180 sampled a disabled connector: most DSI
register reads returned `0x01000000`. Those values must not be compared with
an active LK reference. The local display gate now requires a fresh module,
checks DSI-1 enabled before and after sampling, rejects input stuck at 1x1,
and parses both versions of the OVL1/2 log format. It no longer sends
best-effort compositor D-Bus commands after the sampling window has started.

The amended gate rejected a further capture because DSI-1 stopped during
sampling. This is an invalid measurement, not a new first-frame diagnosis.
The gate remains a local diagnostic tool, not a production feature test.

## Source provenance and remaining comparison

The workspace checkout of
`upstream/android_kernel_device_modules_6.1_nothing_mt6878` is at `957dac1`
(Nothing OS 2.6). The required 4.1 commit
`ee2be53cb75670b548948636a0db1d1ff112bf12` exists in its object database;
read it with `git show <commit>:<path>` rather than trusting checked-out files.
The DSC implementation is identical between these two commits. Panel and
DSI files are not identical.

4.1 `mtk_dsi_tx_buf_rw()` explicitly uses buffer capacity 1554 for MT6878
when calculating FIFO thresholds. The current port programs fixed thresholds
matching the saved working LK state. This difference is a source-backed
hypothesis only: LK success with those thresholds prevents treating it as the
established cause. Compare the calculated thresholds and actual MM clock
before proposing any live change.

The saved working references remain in the sibling worktree:
`nothing-tetris-scp-thermal/local/display-reference-r132.txt` and
`display-reference-r132-full.txt`. They contain advancing DSI input samples
and DSC status 1. Continue the first-frame investigation from these references;
do not repeat already disproven reset/route/constant-frame experiments.

## Follow-up: clock and FIFO calculation

Read individual `clk_rate` files after confirming the actual clock names:
`top_disp0_sel`, `mm_disp_dsc_wrap0`, `mm_disp_dsi0` and
`mm_disp_ovl0_2l` all report 624000000 Hz; `mipi_tx0_pll` reports
1140000000 Hz. USB remained UP. These are clock-framework rates, not an
independent measurement of physical clock signals.

With four lanes, 32-byte units and DSC buffer bpp 3, the exact 4.1 integer
calculation gives fill rate 58, drain rate 17 and SODI high
`1554 - 12 * (58 - 17) / 10 = 1505`. Remaining thresholds are
498/463/445/409/267/249, matching the port. Only SODI high differs from the
fixed 1048575 inherited from working LK. No FIFO register was changed:
this evidence does not establish the first-frame cause.

A reboot interrupted an earlier full clock-summary read. The next boot ID
was `80a491b5-dd85-4229-9f1e-7ae15244f74d`, still r151, with USB and no
failed units. The previous boot's journal shows orderly systemd session
shutdown. The pstore archive is older (different filesystem UUIDs) and cannot
establish the cause of this reboot. Do not classify it as a clock-read crash
or a successful controlled lifecycle test.

The CI FIT was inspected in the existing `mt6878-probe-build` container:
kernel 13929843 bytes, native DTB 47750 bytes, initramfs 12598538 bytes.
The installed boot directory only contains the native DTB. A legacy diagnostic
image therefore still needs preparation and validation; none was flashed.
The untouched FIT and extracted native DTB are at `/tmp/r151-native.itb` and
`/tmp/r151-native.dtb` inside that container. The kernel/initramfs and UUID
contract must remain identical when preparing the reference capture.

## Diagnostic boot prepared and started

The local `display-probe/r151-reference-overlay.dts` disables native display
devices, its SMI/IOMMU nodes and MM_INFRA domain 7, and restores the legacy
chosen framebuffer node from the base DTS. The DT diff contains only those
changes plus the framebuffer panel symbol. Audio domain 2 and USB nodes are
unchanged. Both framebuffer drivers are disabled in the running r151 config,
so the purpose is to observe retained LK scanout, not run a fallback desktop.

The local diagnostic FIT was packed with extracted CI components; extracted
kernel and initramfs from the resulting FIT compare byte-for-byte equal to
the originals. SHA256:

- FIT: `94ea75ab1e72157808465504278f2c190167d1cae123e266da27e38a46c17666`
- DTB: `be1325f8981016cd9d9a59f1c660611c287bc7254cc62269ea13a86fa6f5583c`
- Kernel: `8af5e4417326ada7792ffe680cc7667b392afe2c8462f36c1dc8964fc94e4110`
- Initramfs: `07fe81d8b17c2d54a08c25da4136e02e9a54d8ed2385ca159a26eb420938dc8a`

On the handset, `/boot/boot_image.native-r151.itb` is the hash-verified native
backup. `tetris-display-reference-restore.service` was installed, enabled and
successfully executed before the test; it restores that backup atomically to
`/boot/boot_image.itb` on the next boot. Its script is
`/usr/local/sbin/restore-r151-native.sh`. The active FIT was then replaced by
the diagnostic FIT and a reboot requested. This diagnostic boot was explicitly
authorized in the original user request, line 85; approval review accepted
the action after checking that authorization.

After reboot, the host enumerates Nothing/postmarketOS NCM with both
AppleUSBNCMControl and AppleUSBNCMData attached and an IOEthernetInterface,
but no BSD network-interface name or USB route. Fastboot is absent.
`networksetup -detectnewhardware` did not produce an interface. The user was
asked to unlock the Mac and reconnect USB once. No inference of successful
rootfs boot or completed FIT restoration is justified yet.

Next mandatory recovery checks: regain SSH, verify native FIT SHA256 and the
restore unit, capture retained LK registers if the diagnostic DT is running,
reboot into native r151 and pass USB transfer. Remove the temporary restore
unit only after native boot is verified; retain image backups and evidence.

## Reference captured; native restored

USB returned as host interface en4. SSH confirmed the diagnostic DT was
running and the restore service had already put the original native FIT back.
The complete capture is in the sibling worktree at
`nothing-tetris-scp-thermal/local/display-reference-r151-full.txt`.
All 32 DSC status samples are 1; DSI input samples advance through the frame.
This proves an active retained LK stream on the same r151 kernel. It is not
proof of native DRM or a Linux graphical session.

A reboot returned to native DTB with the original FIT hash. The captured
working PHY words at DSI offsets 0x110..0x11c are
`0x0f0f0a0c 0x133c1230 0x10260100 0x0011100a`, unlike the old probe's
`reference_phy_timing` constants. A separate local probe parameter
`lk_reference_phy_timing` now selects the actual captured words and uses
the existing save/restore path. It was built with clang 21.1.8; the kernel
reports 21.1.2. The diagnostic build lacks Module.symvers and emits unresolved
symbol warnings at modpost; runtime loading succeeded. This is not a
production module build or a CI validation claim.

After one controlled activation and load, all 32 native samples still had
DSI input 0x00010001 and DSC status 9 (done latched plus abnormal EOF).
The full result is `local/display-native-r151-lk-phy.txt` in the sibling
worktree. Therefore matching the captured PHY timing alone is not the fix.
Some earlier attempts never loaded the module because SSH authentication
failed or the connector was already disabled; they are not experiments.
Explicit password-only SSH succeeded where keyboard-interactive failed.

Clean reboot rolled back the experiment. Native DT, absence of the probe,
the original FIT hash, USB UP and zero failed units were verified. The restore
service is now disabled; its files and native backup remain for recovery.

Full reference versus PHY-experiment comparison shows identical mutex arrays.
Most DSC configuration, including the full PPS, also matches; mode and checksum
enable differ, as do dynamic status registers. MMSYS route-array differences
(array base 0xc00) are:

| Register | Working LK | Native |
| --- | --- | --- |
| 0xd00 | 0x00010001 | 0x00050005 |
| 0xd30 | 0 | 0x00020002 |
| 0xd60 | 0x00020000 | 0x00020002 |

Audit these against the exact 4.1 crossbar definitions and the old experiment
parameters before another route test. The old exclusive-PQ probe clears bit 0
and bit 16 of 0xd00, which is not the captured LK value. This observation is
not yet proof that routing is the cause.

## First user-confirmed native image: captured LK route

The next controlled live experiment selected exactly the three recorded
crossbar values via local probe parameter `lk_reference_route=1`, keeping
PHY and DSC configuration unchanged. No boot or production driver changed.
DSI input advanced across many frame positions instead of remaining at 1x1.
The user confirmed a visible interface, initially flickering and then
apparently stable. This is the first functional native-image evidence in this
cycle. It is **Partial (manual live experiment)**, not completed support.

Evidence: sibling worktree
`local/display-native-r151-lk-route.txt`. DSC INTSTA remains 9 throughout the
32 samples; that register is sticky and was not acknowledged, so these samples
cannot distinguish an old abnormal EOF from newly generated errors. Do not
claim the error is gone. The probe's existing IRQ handler resets DSC on frame
events and must not be used as a passive counter for this check.

The 4.1 source defines 0xd00 bit 0 as RSZ0 and bit 2 as PQ_OUT_CB4. Thus the
working LK route selects RSZ0, while native enables both RSZ0 and bypass CB4.
The old `exclusive_pq_bypass` probe cleared RSZ0; it never selected this exact
working graph. The three-register experiment is new causal evidence, but it
does not yet isolate which selector is necessary or prove initialization of
the inherited PQ processing blocks. Before packaging, isolate the minimum
route correction, observe freshly acknowledged DSC status, repeat from clean
boots, and express all required graph ownership/configuration in the driver.

The phone was left on the successful live route for observation. The setting
is temporary: unloading the module restores the saved route, and reboot or
a new modeset can reintroduce the old driver route. No new CI artifact exists.

User follow-up: moving/interacting with the interface makes the image flicker
again. The apparent stability was limited to a static image. Correct dynamic
scanout remains unproven and flicker must be fixed before promotion.

## Acknowledged sampling: route overwritten, blue stripes, rollback

Added optional `ack_dsc_samples` to the ignored local diagnostic module.
It acknowledges each sampled INTSTA through INTACK only when INTEN is zero;
it does not reset DSC. Targeted clang-21 build passed with the same missing
Module.symvers warnings noted above. No production patch or image changed.

On the existing native boot, restarted greetd, waited for connector enabled,
unloaded the previous reversible route probe and loaded the new probe with
`lk_reference_route=1 ack_dsc_samples=1 status_samples=32 status_interval_ms=100`.
Loading succeeded. Samples were `9,9` then thirty `8` values; all DSI input
samples were 65537. Reset count was zero, INTEN zero. However DSI START sampled
`1,0,1,...` and the final MMSYS route dump contained native values again:
0xd00=0x00050005, 0xd30=0x00020002, 0xd60=0x00020002. A display lifecycle
transition therefore overwrote the one-shot route during this observation.
Fresh abnormal EOF is demonstrated on that resulting configuration, not on
the previously user-confirmed working route. Do not infer that acknowledging
status itself caused the visual regression or that the good route is stable.
The initial capture command exited 1 because an optional parameter filename
was wrong; subsequent readback verified samples and USB connectivity.

The user reported blue stripes everywhere. Stopped the experiment by clean
reboot rather than further live register changes. After USB re-enumeration,
SSH confirmed uptime 41 seconds, absence of the probe, connector enabled,
USB UP, no failed systemd units and unchanged native FIT SHA256
`2867364adabe2d9bd7a8026279803618bc4892e7f0620962267131ed9f3dd7cb`.
This is recovery to the original native r151 baseline, not recovery to a
verified good picture. The first SSH timeout during enumeration was followed
by host en4 state 3 and successful SSH; no kernel crash is established.

Next observation must distinguish a settled modeset from connector readiness
and record the three route registers alongside every DSC sample. Do not
continually force routes against the DRM driver or promote these temporary
inherited-LK settings into a production fix without lifecycle ownership.

## Stable-route observation and requested persistent candidate

Used the running greetd session's introspected DisplayConfig PowerSaveMode
property to wake the panel, avoiding a greetd restart. After a two-second
settling interval, loaded the route probe with 32 acknowledged 100 ms samples.
All route samples matched the intended three words and DSI START remained 1.
DSI input advanced; DSC status was 9 initially, then 31 samples of 1. No resets
occurred. Full raw capture: sibling worktree
`local/display-native-r151-lk-route-ack-stable.txt`.
The user confirmed a real picture but persistent flicker during movement.

An OVL IRQ delta was 123 over 5.01 seconds with a nominal 60 Hz mode, but this
is not established hardware refresh frequency: DRM can gate vblank IRQs.
A separate bounded frame meter was built to acknowledge DSC status every
1.5-2 ms without modifying the route or resetting any engine. Its first
256-sample capture spans 526134 us, but the driver had already restored the
native route: zero fresh DONE and 31 ABN_EOF samples. Capture:
`local/display-native-r151-frame-meter.txt`. The user then reported grey
output. Both diagnostic modules were still loaded, disproving module unload
as the explanation. A subsequent restore attempt stopped at the disabled
connector check, and a wake attempt failed because the greetd session bus
was no longer present. Neither attempt changed the route or supplies.

The user explicitly requested a persistent driver change even with flicker
to remove the temporary-route obstacle to debugging. Prepared r152 patch
0096 therefore installs the exact live-tested words in the existing MMSYS
connect path. This is deliberately still partial and retains the LK PQ
handoff dependency; do not mark Works or merge to the stable branch.
The source-order route header applies and compiles in the host model test,
including repeated disconnect/reconnect and unrelated clock-register
preservation. This does not prove hardware lifecycle, full kernel build or
clean-install behavior. CI and installation are next.

## Frame-end update eliminates user-observed redraw flicker

The user authorized GitHub push explicitly; r152 commit `3a490d3` was pushed
and CI `34490904598` started, with overlay validation passing. While it built,
the user requested continued live debugging. The active session had changed
from greetd to user Phosh (runtime UID 10000), explaining the missing old bus.
After waking the correct session and restoring the route, a bounded DSC meter
captured 30 fresh DONE events in 523854 us, with approximately 16-18 ms sampled
intervals. Abnormal EOF appeared only at samples 0 and 2 during the route
transition. The route was constant. This rules out the earlier idle IRQ delta
as evidence of a 25 Hz scanout. Capture:
`local/display-native-r151-frame-meter-route.txt` in the sibling worktree.

The user localized artifacts to redraw. Source inspection found CPU plane
updates in mtk_crtc_ddp_irq(), OVL shadow bypass and MT6878 frame-start vblank.
The old claim that completion never arrives was based on a blocked route.
A read-only OVL trace on the working route observed completion bit 1. The
kernel has no KPROBES; no code hooks or instruction patches were attempted.

For one controlled source-selection test, a five-minute gnome-session idle
inhibitor prevented automatic blanking without saving power settings. A
DRM_IOCTL_CRTC_QUEUE_SEQUENCE event 3600 frames ahead held vblank enabled;
its helper had a 75-second timeout. A separate small diagnostic module
required active OVL with INTEN exactly BIT(14), then changed only INTEN to
BIT(1), with conditional restoration on unload. It did not reset any engine.
All 256 samples showed INTEN=2 and the intended route, with fresh DSC DONE and
no abnormal EOF. No flip/vblank timeout, BUG or Oops was found; USB was UP.
The future DRM event arrived with 32 bytes and the helper exited normally.
Raw capture: `local/display-native-r151-frame-end-irq.txt`.

The user confirmed no flicker after the change, while noting slow response.
That supports the update-phase hypothesis; it does not prove accelerated
rendering, cold repeat, long stress or physical output on other units.
Prepared r153 patch 0097 changes the MT6878 vblank_irq_mask to frame completion.
The earlier patch 0086 has context accepted by the packaging patch tool but
rejected by git apply. Reconstructed the OVL source with the packaging-style
patch tool in APKBUILD order, including 0097, then compiled the resulting
translation unit successfully with clang21. No production build was run
locally. The diagnostic source selection remains temporary until CI install;
driver re-enabling vblank or modesetting can still restore the old setting.

## CI r153 clean installation and first lifecycle test

CI `34492172863` succeeded for `aecf4f44f4170952709a7dd514538f0d75b55e22`.
Downloaded image directory: `local/ci-run-34492172863-images-r153` in the
integration worktree. SHA256SUMS verification passed for all three payloads:

- FIT: `da5e33c9342b1a7d4ea4af7b278496021b3d222ca5756dd1d7338058282602a2`
- boot filesystem: `45c6d41c795197a3c9cff74e7dec54edb4baec4c4ee7f2204ef1ea1e82a2dfd5`
- root sparse: `bba6faf07c3e395645be6343586bbaa5f277fe9a0d51ab9c94b4b46f9ff26ac3`

User placed the phone in fastboot. Confirmed product nothing-tetris,
platform mt6878, U-Boot 60bcf22, slot a, 128 MiB download limit and sufficient
partition sizes. Wrote boot to super and all 17 sparse root pieces to
userdata; every write succeeded. No bootloader or calibration partition was
written. Fastboot reboot lost the USB status reply, but after 20 seconds
Linux #154 and USB NCM/SSH were available. Verified package versions r153 and
device 8-r9, native FIT hash, active DRM XR24 1080x2400 mode, no diagnostic
route/IRQ modules and no failed units. Capture: `local/r153-first-boot.txt`.
An initial package info command unnecessarily attempted repository access;
the later `apk --no-network info -vv` verified installed versions directly.

USB 32 MiB transfer and existing device-presence gate passed:
`local/live-logs/20260910T192547Z-172.16.42.1-regression-gate`.
This is not proof of all Wi-Fi/BT/audio end-user functions.

The local DPMS test toggled DisplayConfig PowerSaveMode 3/0 and waited for
connector disabled/enabled. After each wake it queued 30 frame events with a
3-second timeout, without any diagnostic kernel module. Cycles 1-4 passed.
Cycle 5 failed at QUEUE_SEQUENCE with EINVAL; preserved the failure rather
than retrying. Captures: `local/r153-dpms-10cycles.txt` and
`local/r153-dpms-first-failure.txt`. The latter shows active DRM and USB UP.
No DRM flip/vblank timeout, BUG or Oops was found. Phoc reports additional
off/on transitions around the failed cycle and input processing delays of
23-86 ms. Pinned drm_vblank.c permits EINVAL when vblank is disabled during
the sequence request; a modeset race is a hypothesis, not an established
root cause. A controlled session/idle condition is needed before another
test; no ten-cycle pass or suspend/resume claim is justified yet.

## Installed-image visual confirmation and cadence

The user subsequently confirmed that r153 displays the interface. This does
not prove flawless redraw under load, 120 Hz or lifecycle stability.
Read-only runtime inspection confirms Pixman rendering after failed EGL and
Vulkan initialization, no renderD node and input processing delays of
23-86 ms. GPU acceleration is a separate missing dependency; those messages
alone do not identify every performance bottleneck.

Patch 0050 exposes only the mode selected by samsung,refresh-rate; patch
0072 fixes that property at 60. The existing 120 Hz timing table is not proof
of a working runtime switch. Both tables use 377349 kHz / htotal 1293;
vtotal changes from 4864 to 2432 and the panel command changes from 0x21 to
0x01. Do not simply advertise both modes without synchronizing panel/host
configuration and testing the complete inherited RSZ/PQ route.

`scripts/measure-drm-sequence.py` queues two bounded sequence events without
changing registers or mode. It checks event type/size/cookie and rejects
timestamp or sequence discontinuities. Pending events hold a temporary
vblank reference. It measures DRM sequence cadence, not newly rendered
frames, pixels or per-frame jitter. Host tests cover 60/120 Hz arithmetic,
malformed events, discontinuities, timeout and close-on-first-error.

Three distinct observations on r153 (in order):

1. Initial measurement: EINVAL, subsequent state confirmed connector
   disabled and CRTC active=0. USB remained UP.
2. Single ordinary DisplayConfig wake followed immediately by measurement:
   EINVAL although connector enabled was already visible. Subsequent DRM
   state showed active=1, the 60 Hz mode and framebuffer 63; no vblank/flip
   fault was logged. D-Bus return/connector enabled are not sufficient
   completion barriers. This does not resolve the earlier fifth-cycle fault.
3. Separate measurement after active state inspection: 120 sequence steps
   in 2032465770 ns, or 59.0415847 Hz. USB remained UP. No driver or timing
   change was made between these observations.

Next lifecycle test must synchronize with completed modesetting and control
idle/session activity, without retrying failed sequence ioctls. Retain these
failures alongside any later successful test.

## Controlled r153 DPMS repeat

The earlier test's connector state was an insufficient completion barrier.
New `scripts/check-live-display-dpms.py` retains one session D-Bus connection
and an idle inhibitor (flag 8), requiring an initially active CRTC. Each
ordinary PowerSaveMode change is followed by a bounded readiness observation
using connector state plus GET_SEQUENCE. Every pre-ready EINVAL is counted
in the log. Non-EINVAL errors and readiness timeouts stop the test. Once
ready, QUEUE_SEQUENCE is issued exactly once for each measurement event;
any queue error, timeout or sequence discontinuity fails immediately.
No diagnostic module, timing change, register override or kernel rebuild.

This distinction is deliberate: polling the documented inactive transition
is not retrying a failed frame measurement or claiming every ioctl succeeds.
On this target, successful GET_SEQUENCE acquires a vblank reference whereas
connector-enabled alone can precede that readiness by nearly 300 ms.

On the installed r153 / #154 / aecf4f4 image, all ten cycles passed:

- On readiness: 288-298 ms, ten observations with nine pre-ready EINVALs in
  each cycle. Off readiness: 345-353 ms, two observations with one EINVAL.
- Each subsequent 30-step event measurement completed in 508.03-508.27 ms,
  59.024-59.052 sequence Hz. No frame-queue errors, retries or discontinuities.
- Phoc's monotonic journal contains exactly ten off/on pairs between
  1187.399810 and 1198.568721 seconds. No extra transitions in that interval.
- Final CRTC active, XR24 1080x2400 at nominal 60 Hz; no matching DRM
  timeout/Oops/BUG. USB UP before and after; SSH intact.
- IsInhibited(8) returned false afterward. Normal idle blanking occurred
  at 1259.403588 seconds, after the test and inhibitor release.

Raw captures: `local/r153-dpms-ready-10cycles.txt`,
`local/r153-dpms-ready-post.txt`, `local/r153-dpms-ready-transitions.txt`.
The host suite `ci/test-drm-sequence.py` now has nine passing tests including
readiness/error separation, connector-only rejection and bounded timeout.

This passes the controlled DPMS/event gate only. The first failed test is
retained, and its additional transitions were not reproduced here. Do not
infer correct pixels after every transition, compositor FPS, cold startup,
120 Hz, suspend/resume or complete native PQ ownership from this result.

## Exclusive PQ bypass experiment on r153

Hypothesis: the earlier bypass failure could have been caused by the changed
DSC input selector or simultaneous fan-out rather than the bypass itself.
Test only the exclusive PQ_IN_CB0 -> PQ_OUT_CB4 -> SPLIT_OUT_CB2 route,
keeping the working DSC selector 0xd60=0x00020000 and all clocks, power,
timing, OVL and DSC configuration unchanged.

Authoritative route definitions are in B4.1 `mtk_drm_ddp.c` at ee2be53:
PQ0_IN_CB_TO_PQ_OUT_CB4 is BIT(2) at 0xd00; PQ0_OUT_CB_TO_SPLIT_OUT_CB2 is
BIT(1) at 0xd30. The bounded local `mt6878_bypass_probe` uses DT resources
for MMSYS0/DSC/DSI. It requires active engines, disabled DSC IRQ and the exact
working route before writes. It samples 128 times before, during and after
the change, acknowledges sampled DSC flags without resetting engines, and
restores its two owned route words before returning. No firmware/partition,
regulator, IRQ registration or background worker changes.

Single live test on unchanged r153 (about 0.8 seconds in total):

| Phase | d00 / d30 / d60 | 128-sample result |
| --- | --- | --- |
| Baseline | 00010001 / 00000000 / 00020000 | 16 FRAME_DONE, 112 zero, no abnormal EOF; 262045 us |
| Exclusive bypass | 00040004 / 00020002 / 00020000 | 16 abnormal EOF, 112 zero, no FRAME_DONE; 262637 us |
| Restored | 00010001 / 00000000 / 00020000 | 15 FRAME_DONE, 113 zero, no abnormal EOF; 261794 us |

Kernel journal confirms exact changed route and `count=384 restored=1
capture_result=0`; zero means the diagnostic finished, not that bypass works.
Thirty-step DRM event measurements before/after returned 59.0322/59.0470 Hz.
USB/SSH remained UP, and the completed diagnostic module was removed once
without reload. The normal session idle inhibitor was released. Physical
pixel correctness during the quarter-second bypass was not asserted.

Evidence: `local/r153-exclusive-bypass-probe.txt`,
`local/r153-exclusive-bypass-kernel.txt`,
`local/r153-exclusive-bypass-cleanup.txt`. The diagnostic and runner remain
ignored local artifacts, not package inputs. Build used clang 21.1.8 against
the prepared kernel with missing Module.symvers warnings; successful runtime
load does not replace a production ABI/package check.

Conclusion: this exact bypass candidate is disproven even with exclusive
fan-out and the retained working DSC selector. Do not merge it or trigger
CI for it. This does not rule out all possible alternative routes. The next
boundary is explicit lifecycle ownership of the known-working RSZ/PQ chain,
starting with read-only state and B4.1 reset/config/clock ordering. Vendor
RSZ0 is at 0x14008000; its prepare sets shadow bypass, and its start/config
behavior depends on scaling ownership. Blindly enabling a generic resizer
with copied dimensions would not reproduce that contract. Its address must
be represented by a real DT resource in any production driver.

## Read-only PQ state on r153

One bounded `mt6878_pq_snapshot` load captured selected configuration words
from the known-working path. It checks nothing,tetris and the MT6878 MMSYS0
resource, requires the known route and DSC/DSI/APB clock gates, and skips any
PQ block whose gate is off. No MMIO writes, IRQ acknowledgement, clock
changes, reset, firmware access or background tasks. Addresses are pinned
B4.1 diagnostic data, not proposed production hard-coded resources.

All ten blocks were clocked (`captured=0x3ff`, MMSYS gate word 0x003f0000).
Before/after 30-step DRM measurements were 59.0281/59.0257 Hz. USB/SSH stayed
UP and the snapshot module was removed after evidence collection.

| Block | Selected captured configuration |
| --- | --- |
| RSZ0 | EN=0, CONTROL1=80000000, CONTROL2=0, input/output/steps=0, SHADOW=f0:3 |
| TDSHP0 | CTRL=5, CFG=1, input/output=04380960, shadow724=0, INTEN=0 |
| C3D0 | EN=1, CFG=11, SIZE=04380960, SHADOW=7, INTEN=0 |
| COLOR0 | CFG_MAIN=80, START=1, INTEN=0, width=438, height=960, shadow=7 |
| CCORR0/1 | EN=1, CFG=301, SIZE=04380960, SHADOW=7, INTEN=0 |
| AAL0 | EN=1, CFG=00400127, SIZE/output=04380960, SHADOW_f0=7, INTEN=0 |
| GAMMA0 | EN=1, CFG=101, SIZE=04380960 |
| POSTMASK0 | EN=1, INTEN=917, CFG=146, SHADOW=3, SIZE=04380960, SRAM_CFG=0 |
| DITHER0 | EN=1, CFG=80000183, SIZE=04380960, INTEN=0 |

Values are hexadecimal. These are configuration readbacks, not proof that
every processing operation is active; shadow semantics differ by block.
In particular, RSZ EN=0 with zero dimensions disproves the assumption that
the native path must initialize an active scaler to reproduce this state.
Do not set RSZ EN=1 merely because the crossbar route is named RSZ0.

POSTMASK requires special attention: CFG=0x146 has DRAM_MODE set and
RELAY_MODE clear, and its local interrupt enable is nonzero even though
native Linux has no POSTMASK node/owner. This does not prove a current DMA
transaction, an unmasked GIC interrupt or corruption; memory address/length
and transactions were not captured. The B4.1 no-round-corner config uses
0x147, and `mtk_postmask_bypass()` changes only CFG bit 0. Upstream already
has generic POSTMASK config/start/stop in `mtk_ddp_comp.c`, but that config
writes CFG=1 and does not initialize MT6878 shadow/INTEN state. Reusing it
without MT6878 handoff handling is insufficient.

Next isolated live boundary: prove the documented POSTMASK relay bit while
preserving other configuration, checking frame completion and pixels, then
separately validate interrupt/DMA quiescence and native start/stop ownership.
Do not infer those gates from this read-only capture or blindly copy all
captured words into a startup script.

Raw evidence: `local/r153-pq-snapshot.txt` and
`local/r153-pq-snapshot-kernel.txt`. Source diagnostic is in the sibling
display-probe directory; it is not packaged. Targeted module build has the
same clang-version/missing-Module.symvers limitations recorded above.

## POSTMASK relay-bit live boundary

One local bounded experiment applied exactly the B4.1
`mtk_postmask_bypass()` bit change, CFG 0x146 -> 0x147, on unchanged r153.
It preserved addresses, lengths, interrupt enable, shadow, clocks, routing
and engine enable. Preconditions required the known route, active engines,
clocked POSTMASK, EN=1, CFG=146 and shadow bypass. The module captured 128
DSC samples before/during/after, then restored CFG=146 before returning.
Only sampled DSC flags were acknowledged with DSC IRQ disabled; no resets.

| Phase | Result | Sample span |
| --- | --- | --- |
| Before | 16 FRAME_DONE, 112 zero, no abnormal EOF | 261455 us |
| Relay 0x147 | 15 FRAME_DONE, 112 zero, **one abnormal EOF** | 262057 us |
| Restored 0x146 | 15 FRAME_DONE, 113 zero, no abnormal EOF | 261885 us |

All 384 samples completed and restoration was confirmed. The kernel journal
reports relay CFG=147, capture=0 and restored=1. Baseline/post-test DRM
sequence cadence was 59.0296/59.0388 Hz; USB/SSH remained UP. The module was
removed after collection, with no reload or persisted register override.
No pixel-correctness claim was made for the quarter-second relay interval.

This is **partial**, not a clean pass: relay sustains subsequent frames, but
changing it mid-stream causes a transition error in this observation. Do
not ship a live register toggle or erase that error by averaging samples.
Native configuration must occur while the path is stopped and before OVL
fetch starts; that transition, POSTMASK interrupt/DMA quiescence and repeated
lifecycle still need separate validation. Upstream's existing POSTMASK
config/start/stop helpers are the integration point, with MT6878-specific
shadow and interrupt handoff rather than a register-writing service.

Evidence: `local/r153-postmask-relay-probe.txt` and
`local/r153-postmask-relay-kernel.txt`. The module and runner remain local
diagnostic artifacts, not production package inputs.

## Offline POSTMASK topology validation (2026-09-11)

Candidate `patches/native-display/0003-mt6878-postmask-topology.patch` now
connects the proposed native POSTMASK lifecycle helpers to a DT node,
component match, static DRM path and split routing. It is not in APKBUILD
and has not changed the installed r153 image. Matching B4.1 source confirms
register resource 0x14010000/0x1000, SPI 317 and POSTMASK clock identity;
the native node uses its parent bus's one-cell address/size encoding.

`check-topology.sh` reconstructed relevant packaged files, applied the
candidate and passed 768 host register-array comparisons, component order,
nonempty path-edge and mutex bit 14 checks. The incorrect d00=0x50005 mutant
was rejected. The changed mtk_drm_drv.o compiled for ARM64 with clang 21.1.8
against the prepared diagnostic tree and reconstructed local headers,
with the expected original-compiler-version warning (21.1.2). Nine DRM
sequence/readiness tests also passed. None of this is hardware or DT/schema
validation, complete linking, or a CI-image result.

A read-only phone check returned Linux 6.18.0, usb0 UP and /dev/dri/card0,
with no diagnostic modules or render node. The old SSH control session had
expired and the first fresh connection rejected the pre-install known-host
key; the established disposable USB connection options restored access.
This was an SSH identity-cache issue, not observed USB loss or kernel crash.

Remaining activation gates are concrete: prove inherited POSTMASK engine
and DMA quiescence, compile/validate the complete DT, and exercise native
startup/stop with frame and pixel checks. Configure-before-start callbacks
alone do not establish quiescence: the current CRTC enables its mutex before
configuration and does not stop bootloader-owned engines at entry. Other PQ
blocks remain inherited. No 120 Hz, accelerated compositor, cold-repeat or
suspend/resume claim follows from these checks.
