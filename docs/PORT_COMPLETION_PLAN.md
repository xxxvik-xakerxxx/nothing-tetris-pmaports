# Nothing Tetris port completion plan

This file tracks the current working order for turning the CMF Phone 1
postmarketOS port into a stable daily-phone build.

## Current source of truth

| Track | Branch / path | State |
| --- | --- | --- |
| Stable source baseline | `xxxvik-xakerxxx/nothing-tetris-pmaports:main` | Current SHA `ee994e4236d69c9f3eb18e81614dd0dff9e60266`. Keep as the published rollback until the active candidate completes all promotion gates. |
| Installed device candidate | CI image from `fdeeda0` | Kernel `6.18.0 #128` passed clean boot/root expansion, warm reboot, automatic USB NCM/SSH, routed Wi-Fi and BlueZ coexistence. Bounded speaker/haptics, measured microphone capture and manual GNSS transport/link0 open-close pass; system audio and GNSS position remain open. |
| Previous rollback image | CI image from `f607513` | Kernel `6.18.0 #123` retains the prior full physical regression evidence and preserved rollback artifacts. |
| Previous CI candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` at `0600a13ceba889d294f6bc1be289e273a75eca00` | `pkgrel=126`. CI run `33495661863` applied the series and completed the main kernel build, then failed on a brittle disabled-Kconfig text check before the IMX882 object gate. It produced no install image. |
| Installed image source | `xxxvik-xakerxxx/nothing-tetris-pmaports` at `fdeeda042144e5ff1d2159f1590dbc5fb6b9392c` | Kernel `pkgrel=127` and device package `8-r3`; CI run `33502390335` produced the installed artifacts. |
| Active source candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` | Device package `8-r4` binds the speaker policy to `graphical-session.target`, excludes `greetd`, and defers mono-remap creation until the ALSA master exists. Kernel, DT and bootloader inputs are unchanged. CI and clean-install lifecycle gates remain. |
| Flashed bootloader | `xxxvik-xakerxxx/u-boot:master` | Commit `b76e47e774304ab550a6354f3286860b7caffb3a` is installed in `boot_a` and `boot_b`. It passed CI `33492618726`, normal boot and Linux-to-fastboot reboot. It validates CCCI/GNSS handoff data but starts neither subsystem. |
| Previous bootloader rollback | `8aa048f93bb7569e4107ef85aa994c630f85de48` | Preserved rollback artifact. |

The verified image archive for run `33502390335` has SHA-256
`c47230ff07ebefe86faf54cf216bf7901279afbef482647389c91cd4a56bc996`.
Its three payload hashes match `SHA256SUMS`, and `BUILD-MANIFEST` pins the exact
pmaports head plus U-Boot `b76e47e`/`86930322...`. It publishes no separately
named `super` or `userdata` file, but the package's validated
`fastboot-bootpart` contract maps the 512 MiB boot image to `super` and the root
sparse image to `userdata`. The standalone FIT is evidence, not another
partition target.

## Branch policy

Use `main` for known-good phone builds only. Short-lived branches are allowed
for CI and hardware bring-up, but they must not be merged to `main` until:

1. The branch builds in GitHub CI.
2. A clean boot confirms USB debug/NCM SSH.
3. The existing working hardware does not regress.
4. The branch has a documented rollback point and no automatic loading of
   unvalidated high-risk modules.

`codex/next-hardware` is the current promotion candidate. It must remain
separate from `main` until the CI image boots and completes the hard regression
gates below. Sensors/SCP, Modem/SIM, GPU, Camera and native display remain
staged or compile-only until their own gates pass.

## Hard regression gates

Every hardware change must keep these working before it can move into the
stable baseline:

1. Cold boot reaches userspace without manual module surgery.
2. USB debug/NCM SSH comes up reliably at `172.16.42.1`.
3. USB debug/NCM survives at least a 32 MiB SSH transfer.
4. Wi-Fi, Bluetooth, audio playback/capture, touch, haptics and root I/O still
   work after the change.
5. No unload/reload testing of `conninfra` or radio modules; reboot between
   unsafe radio attempts.
6. Any new default module must be packaged, dependency-checked, and covered by
   `scripts/validate-pmaports-overlay.sh`.

## Bring-up order

| Order | Block | Goal | Promotion gate |
| --- | --- | --- | --- |
| 1 | Thermal / devinfo | Boot MT6878 LVTS thermal zones in polling-only mode with per-device calibration read from MT6878 read-only devinfo registers. | CI build, clean boot, `/sys/class/thermal` zones, plausible idle/load temps, USB/Wi-Fi/BT/audio regression pass. |
| 2 | Power / suspend | Complete safe source classification and isolate the high unplugged drain before enabling more remote processors. The bounded 500 mA path works, but native MT6375 BC1.2 classification is absent and the existing USB-connected logs cannot measure unplugged idle. | Observe a USB 2.0 host, known Rp 1.5 A source and known 5 V BC1.2 DCP without losing USB; then run local unplugged screen-off Wi-Fi-on/off intervals with coulomb, suspend, wake and IRQ evidence. Pass charge-rate/thermal/termination and suspend/recovery lifecycle tests before promotion. |
| 3 | Sensorhub | Build-only/manual-gated transport: `mtk-mbox.ko`, `mtk_rpmsg_mbox.ko`, `mtk_tinysys_ipi.ko`, `scp.ko`, `hf_manager.ko`, `sensorhub.ko`. The exact Nothing OS 4.1 source set compiles on Linux 6.18. The first runtime blocker is the absent `mediatek,scp-dvfs` platform device, but adding it alone is unsafe before SCP firmware/TCM/carveout handoff is proven. | U-Boot validation/publication of active `scp1`/`scp2`, TCM region-info and both carveouts; disabled DVFS provider compile gate; one observation-only boot; then one DVFS-only probe. Sensorhub and nanohub remain off until SCP lifecycle and idle-power gates pass. |
| 4 | GNSS | Transport, EMI/LNA handoff and one bounded link0 open/close pass. Ioctl 23 proves v050 has a non-ATF boot-info stub; public Kleaf metadata builds all profiles but does not reveal the Tetris load selection. Recover that exact stock selection before MVCD/MNL work. | Standard position fix with time/accuracy, three cold starts, restart, coexistence with Wi-Fi/BT, suspend/resume and USB regression pass. |
| 5 | SIM / modem | Validate the bootloader CCCI descriptor, then stage CCCI/CCIF/DPMAIF/CCMNI boundaries without autoload. Keep `conn_md` and `mddp` disabled until basic modem boot is clean. | ModemManager sees modem, SIM state is readable, calls, SMS and data pass, no radio regression with Wi-Fi/BT/GNSS. |
| 6 | GPU | Prefer native DRM Panthor over vendor Mali/GED/GPUEB. The MT6363 VSRAM descriptor and MT6319-compatible regulator config are compile-only; MFG0 genpd, VGPU DT, firmware and protected memory remain blockers. | `/dev/dri/renderD*`, short GL/offscreen smoke test, sustained load, thermal zones active, suspend and USB debug regression pass. |
| 7 | Camera foundation | Build-only sensor inventory, cam_cal, corrected `pd9302a` VCM and LM3644 V4L2 flash bridge before ISP. Do not autoload camsys/imgsys/hcp/aie/OIS. | Sensor IDs visible without hangs, media nodes documented, preview/capture, torch unchanged, repeated start/stop and USB regression pass. |
| 8 | Native display | The bounded S6E8FC3X02 panel driver/binding applies to pinned Linux `d84b264a` and passes a targeted arm64 compile. Package it compile-only with no DT/autoload, then implement DDP/mutex/CMDQ/DSC/DSI/PHY and use a separate opt-in DTB while keeping simpledrm as fallback. | KMS framebuffer, 60/120 Hz modes, brightness, blank/unblank, suspend/resume and fallback boot path all work. |

## Draft workspaces

Local draft workspaces are intentionally not committed to this repo. They are
the current staging notes for follow-up patch branches:

| Block | Draft path | Status |
| --- | --- | --- |
| Sensors/SCP | `0032`, `0036`, `0037`, `0041` plus `APKBUILD` and `local/agent-results/scp-uboot-next/` | Exact-source clean compile passes for mailbox, RPMSG, IPI, SCP, HF manager and sensorhub. `ba02998` proves bounded SCP failure containment. A host-only U-Boot parser validates unique 64-bit shared/loader carveouts, DRAM containment, minimum size, non-overlap and FDT immutability. Active-slot firmware identity, TCM region-info and boot publication remain missing. |
| SIM / modem | `0039`, `0048`, compile-only `APKBUILD` gates and `local/agent-results/modem-timer-next/` | `6bc2096` / CI `33356899792` proves clean `ccci_util_lib.ko` modpost; ECCCI core objects also compile without a module. The isolated CCIF boundary compiles `ccci_ringbuf.o`, replaces the removed timer APIs with reviewed Linux 6.18 equivalents, and now fails first at unproven `MTK_SIP_KERNEL_CCCI_CONTROL`. No DT, packaging, autoload, firmware, power/reset, DMA, DPMAIF or CCMNI. |
| GPU | `local/patch-drafts/gpu/` | RFC Panthor path with MFG0 domain and disabled DT node drafts. Wait for thermal and regulator work. |
| Camera foundation | `local/patch-drafts/camera/` | Source inventory and config draft for sensor ID/cam_cal/VCM/flash only. No ISP/autoload yet. |
| Native panel | `0050` plus `APKBUILD` | S6E8FC3X02 binding/driver passed standalone patch application, arm64 translation-unit compilation and full pmaports CI run `33502390335`. `pkgrel=127` keeps it object-only with no shipped module or DT client; no runtime panel claim exists. |

The audio lifecycle candidate is tracked directly in the device package rather
than a kernel patch. Clean #128 evidence shows that pre-login SSH starts a user
manager, whose default-target audio policy autospawns PulseAudio before the
active seat grants ALSA/haptics access. Device r4 starts that policy only as
part of the graphical session and leaves mono-remap creation to the existing
idempotent policy after UCM publishes the master sink.

## Current blockers

- `ba02998` fixes the incomplete LVTS reads: both clean-boot thermal gates
  exposed all 24 plausible MT6878 zones plus the battery temperature while USB
  remained healthy. Thermal IRQs and hardware trips are still disabled pending
  an independent routing and reboot-safety audit.
- `ba02998` also contains the failure-containment-only SCP fix. A manual probe
  returned `-ETIMEDOUT` after 3.09 seconds with one diagnostic, no loaded `scp`
  module, no WARN/Oops and no USB loss. Keep SCP and sensorhub manual-only while
  the real firmware, reserved-memory and boot handoff contract is solved.
- The SCP host validator proves parser behavior for two portable carveout
  ranges without modifying the FDT. It does not prove active-slot firmware
  identity or TCM region-info. Establish those authoritative ABIs before any
  U-Boot publication or Linux `scp-dvfs` node.
- The CCIF timer lifetime conversion is complete in an isolated compile-only
  patch. The next first blocker is the exact `MTK_SIP_KERNEL_CCCI_CONTROL`
  secure ABI. Do not copy a SiP number or proceed to DPMAIF DMA ownership before
  trusted-firmware ownership and return semantics are proven.
- U-Boot reinjects `clk_ignore_unused` after the packaged DTB is checked. A
  one-shot boot without the token failed and reset, with no ramoops record.
  Capture the early failure before attempting kernel or U-Boot policy changes.
- The 500 mA charging path is measured, but TCPM reports `CURRENT_MAX=0` and
  the native MT6375 driver lacks BC1.2 SDP/CDP/DCP detection/publication. Test
  known host, Rp and DCP sources before adding only that boundary; DP/DM
  ownership must not disrupt USB NCM, and PD/PPS/OTG remain disabled.
- Current battery drain is too high for a stable-phone baseline. Existing
  USB-connected captures cannot prove the unplugged cause. Run local screen-off
  Wi-Fi-on/off intervals on separate boots before sensorhub, modem or GPU remote
  processors are enabled by default.
- Thermal IRQs and hardware trips remain disabled until routing and reboot
  behavior are validated independently of the polling-only temperature path.
- The USB suspend hook is installed, but this image exposes no RTC wake device.
  Full suspend/resume therefore needs a coordinated physical power-button wake
  while USB and Wi-Fi recovery are monitored.
