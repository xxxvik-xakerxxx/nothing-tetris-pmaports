# Nothing Tetris port completion plan

This file tracks the current working order for turning the CMF Phone 1
postmarketOS port into a stable daily-phone build.

## Current source of truth

| Track | Branch / path | State |
| --- | --- | --- |
| Stable hardware baseline | `xxxvik-xakerxxx/nothing-tetris-pmaports:main` | Current SHA `fa00144adde95333fab32e19d63caa32968909c1`. Keep as the published rollback until the active candidate completes all promotion gates. |
| Merged hardware baseline branch | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` | Already merged into `main`. Keep only as historical CI reference until branch cleanup. |
| Active candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/scp-thermal` | `ba0299888c5151b79d134c61cfcd57fc35f70f75` passed CI run `33312303262` and was clean-flashed to `super` and `userdata`. Kernel package `6.18-r118` (`6.18.0 #119`) passed two boots, two exact 32 MiB USB NCM/SSH transfers, two complete thermal gates, charger telemetry, Wi-Fi AP enumeration, Bluetooth HCI and audio enumeration. The manual SCP probe failed closed after 3.09 seconds without WARN/Oops or USB loss. |
| Bootloader baseline | `xxxvik-xakerxxx/u-boot:master` | Keep verified commit `6ab33f59df8b5116c1d63bd637cda4efbbaeb6ef`. Its built-in environment injects `clk_ignore_unused` while constructing dynamic pmOS UUID arguments. A temporary boot without that token produced a launch error/reset, so do not update U-Boot or force unused-clock cleanup until the dependency is identified. |

## Branch policy

Use `main` for known-good phone builds only. Short-lived branches are allowed
for CI and hardware bring-up, but they must not be merged to `main` until:

1. The branch builds in GitHub CI.
2. A clean boot confirms USB debug/NCM SSH.
3. The existing working hardware does not regress.
4. The branch has a documented rollback point and no automatic loading of
   unvalidated high-risk modules.

`codex/next-hardware` meets this bar and was merged into `main`. Thermal,
Sensors/SCP, Modem/SIM, GPU and Camera remain staged or draft work until their
own gates pass.

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
| 4 | SIM / modem | Stage CCCI/CCMNI/ECCCI modules without autoload. Keep `conn_md` and `mddp` disabled until basic modem boot is clean. | ModemManager sees modem, SIM state is readable, SMS/data smoke test, no radio regression with Wi-Fi/BT/GNSS. |
| 5 | GPU | Prefer native DRM Panthor over vendor Mali/GED/GPUEB. Solve thermal, MFG0 genpd, MT6319 GPU rail, firmware path and IOMMU mapping first. | `/dev/dri/renderD*`, short GL/offscreen smoke test, thermal zones active, suspend and USB debug regression pass. |
| 6 | Camera foundation | Build-only sensor inventory, cam_cal, `pd9302a` VCM and LM3644 V4L2 flash bridge before ISP. Do not autoload camsys/imgsys/hcp/aie/OIS. | Sensor IDs visible without hangs, media nodes documented, torch unchanged, no blanket camera stack autoload. |
| 7 | Native display | Separate DSI/DSC/panel branch while keeping simpledrm as fallback. | KMS framebuffer works, brightness works, suspend/resume works, fallback boot path documented. |

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
