# Nothing Tetris port completion plan

This file tracks the current working order for turning the CMF Phone 1
postmarketOS port into a stable daily-phone build.

## Current source of truth

| Track | Branch / path | State |
| --- | --- | --- |
| Stable hardware baseline | `xxxvik-xakerxxx/nothing-tetris-pmaports:main` | Current SHA `fa00144adde95333fab32e19d63caa32968909c1`. Keep as the published rollback until the active candidate completes all promotion gates. |
| Merged hardware baseline branch | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` | Already merged into `main`. Keep only as historical CI reference until branch cleanup. |
| Active candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/scp-thermal` | `9afc17e886bcef00d01ce7f63cf33f58b94ee582` was clean-flashed to `super` and `userdata`. Kernel `6.18.0 #117`, USB NCM/SSH, an exact 32 MiB raw transfer, charger gate, Wi-Fi AP enumeration, Bluetooth HCI and audio enumeration passed. LVTS and SCP failed as documented below. `18a962ace0f86da173875d06b0440b077cfe5f29` adds the thermal correction and is in CI run `33309950811`; it is not live-verified yet. |
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
| Sensors/SCP | `0032`, `0036`, `0037` plus `APKBUILD` | Exact-source clean compile passes for mailbox, RPMSG, IPI, SCP, HF manager and sensorhub. Build-only package integration is prepared; no autoload or DT enablement. |
| SIM / modem | `local/patch-drafts/modem-sim/` | Draft CCCI/CCMNI/ECCCI plan and live gates. Compile-only branch should be next; no `conn_md`/`mddp` first pass. |
| GPU | `local/patch-drafts/gpu/` | RFC Panthor path with MFG0 domain and disabled DT node drafts. Wait for thermal and regulator work. |
| Camera foundation | `local/patch-drafts/camera/` | Source inventory and config draft for sensor ID/cam_cal/VCM/flash only. No ISP/autoload yet. |

## Current blockers

- The `9afc17e` live thermal gate exposed only 6 of 24 LVTS values. The latched
  MSR correction at `18a962a` must pass CI, clean flash and the full thermal
  gate before promotion.
- Manual `scp.ko` loading hangs in `wait_scp_dvfs_init_done()` and floods WARN
  messages when the DVFS platform driver does not complete. Keep SCP and
  sensorhub manual-only; add a proven fail-closed timeout and then solve the
  real firmware, reserved-memory and boot handoff contract.
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
