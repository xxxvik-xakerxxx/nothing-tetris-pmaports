# Nothing Tetris port completion plan

This file tracks the current working order for turning the CMF Phone 1
postmarketOS port into a stable daily-phone build.

## Current source of truth

| Track | Branch / path | State |
| --- | --- | --- |
| Stable source baseline | `xxxvik-xakerxxx/nothing-tetris-pmaports:main` | Current SHA `ee994e4236d69c9f3eb18e81614dd0dff9e60266`. Keep as the published rollback until the active candidate completes all promotion gates. |
| Installed device baseline | CI image from `f607513` | Kernel `6.18.0 #123` passed clean installation, USB NCM/SSH, an exact 32 MiB transfer, Wi-Fi, Bluetooth, audio, touch, haptics, root I/O, thermal and warm-reboot regression gates. |
| Active candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` | `pkgrel=126`. It adds a PD9302A revision fix, exact GNSS LNA pinctrl, compile-only GPU regulator inventory and a compile-only IMX882 identity object with no DT client. The integrated CI pin is U-Boot `b76e47e`; no experimental module is newly autoloaded and native GPU/display remain disabled. |
| Flashed bootloader baseline | `xxxvik-xakerxxx/u-boot:master` | Commit `8aa048f93bb7569e4107ef85aa994c630f85de48` remains installed and passed the Linux reboot-mode fix. |
| Bootloader candidate | `xxxvik-xakerxxx/u-boot:master` | Commit `b76e47e774304ab550a6354f3286860b7caffb3a` passed CI run `33492618726`. It validates the LK CCCI payload and writes the exact GNSS EMI address only after the existing layout and secure mappings validate; it does not start either subsystem. |

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
| 2 | Power / suspend | Measure and fix the currently high battery drain before enabling more remote processors. Audit suspend residency, wakeup sources, IRQ rate, clocks, regulators and runtime PM for USB, Wi-Fi, audio, thermal and remoteproc. | Repeatable idle/screen-on/Wi-Fi power baselines, no IRQ or wakelock storm, one-hour idle discharge gate, suspend/resume and automatic USB/Wi-Fi recovery pass. |
| 3 | Sensorhub | Build-only/manual-gated transport: `mtk-mbox.ko`, `mtk_rpmsg_mbox.ko`, `mtk_tinysys_ipi.ko`, `scp.ko`, `hf_manager.ko`, `sensorhub.ko`. The exact Nothing OS 4.1 source set now compiles on Linux 6.18; do not autoload SCP, sensorhub or nanohub. | Full CI modpost, firmware/reserved-memory audit, manual fail-closed probe, at least one standard Linux/IIO or documented bridge path, idle-power and USB debug regression pass. |
| 4 | GNSS | Complete the bootloader EMI handoff and LNA pinctrl first, then test one cold manual link start without unloading conninfra. | `/dev/gpsdl*`, firmware/DSP open, position fix with accuracy, restart, coexistence with Wi-Fi/BT, suspend/resume and USB regression pass. |
| 5 | SIM / modem | Validate the bootloader CCCI descriptor, then stage CCCI/CCIF/DPMAIF/CCMNI boundaries without autoload. Keep `conn_md` and `mddp` disabled until basic modem boot is clean. | ModemManager sees modem, SIM state is readable, calls, SMS and data pass, no radio regression with Wi-Fi/BT/GNSS. |
| 6 | GPU | Prefer native DRM Panthor over vendor Mali/GED/GPUEB. The MT6363 VSRAM descriptor and MT6319-compatible regulator config are compile-only; MFG0 genpd, VGPU DT, firmware and protected memory remain blockers. | `/dev/dri/renderD*`, short GL/offscreen smoke test, sustained load, thermal zones active, suspend and USB debug regression pass. |
| 7 | Camera foundation | Build-only sensor inventory, cam_cal, corrected `pd9302a` VCM and LM3644 V4L2 flash bridge before ISP. Do not autoload camsys/imgsys/hcp/aie/OIS. | Sensor IDs visible without hangs, media nodes documented, preview/capture, torch unchanged, repeated start/stop and USB regression pass. |
| 8 | Native display | Compile the S6E8FC3X02 panel independently, then use a separate opt-in DSI/DSC DTB while keeping simpledrm as fallback. | KMS framebuffer, 60/120 Hz modes, brightness, blank/unblank, suspend/resume and fallback boot path all work. |

## Draft workspaces

Local draft workspaces are intentionally not committed to this repo. They are
the current staging notes for follow-up patch branches:

| Block | Draft path | Status |
| --- | --- | --- |
| Sensors/SCP | `0032`, `0036`, `0037`, `0041` plus `APKBUILD` | Exact-source clean compile passes for mailbox, RPMSG, IPI, SCP, HF manager and sensorhub. `ba02998` proves bounded SCP failure containment on the device; no sensor module autoload or DT enablement. The actual SCP firmware/handoff remains missing. |
| SIM / modem | `0039`, compile-only `APKBUILD` gate and `local/patch-drafts/modem-sim/` | `6bc2096` / CI `33356899792` proves clean `ccci_util_lib.ko` modpost and matching `6.18.0` vermagic while explicitly rejecting the module from rootfs. No DT, packaging, autoload, firmware, modem power/reset, `mddriver`, DPMAIF or CCMNI yet. |
| GPU | `local/patch-drafts/gpu/` | RFC Panthor path with MFG0 domain and disabled DT node drafts. Wait for thermal and regulator work. |
| Camera foundation | `local/patch-drafts/camera/` | Source inventory and config draft for sensor ID/cam_cal/VCM/flash only. No ISP/autoload yet. |

## Current blockers

- `ba02998` fixes the incomplete LVTS reads: both clean-boot thermal gates
  exposed all 24 plausible MT6878 zones plus the battery temperature while USB
  remained healthy. Thermal IRQs and hardware trips are still disabled pending
  an independent routing and reboot-safety audit.
- `ba02998` also contains the failure-containment-only SCP fix. A manual probe
  returned `-ETIMEDOUT` after 3.09 seconds with one diagnostic, no loaded `scp`
  module, no WARN/Oops and no USB loss. Keep SCP and sensorhub manual-only while
  the real firmware, reserved-memory and boot handoff contract is solved.
- U-Boot reinjects `clk_ignore_unused` after the packaged DTB is checked. A
  one-shot boot without the token failed and reset, with no ramoops record.
  Capture the early failure before attempting kernel or U-Boot policy changes.
- Current battery drain is too high for a stable-phone baseline. Capture idle,
  screen-on and Wi-Fi power data and fix suspend blockers before sensorhub,
  modem or GPU remote processors are enabled by default.
- Thermal IRQs and hardware trips remain disabled until routing and reboot
  behavior are validated independently of the polling-only temperature path.
- The USB suspend hook is installed, but this image exposes no RTC wake device.
  Full suspend/resume therefore needs a coordinated physical power-button wake
  while USB and Wi-Fi recovery are monitored.
