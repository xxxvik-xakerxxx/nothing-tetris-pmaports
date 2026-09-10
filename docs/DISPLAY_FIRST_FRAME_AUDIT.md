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
