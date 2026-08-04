# Nothing Tetris port completion plan

This file tracks the current working order for turning the CMF Phone 1
postmarketOS port into a stable daily-phone build.

## Current source of truth

| Track | Branch / path | State |
| --- | --- | --- |
| Stable hardware baseline | `xxxvik-xakerxxx/nothing-tetris-pmaports:main` | Fast-forwarded from verified `codex/next-hardware` on 2026-08-04. Current SHA `2eb79b72daefb3ac5435c80e6f9eb39412ab3449`, packages `linux-postmarketos-mediatek-mt6878 6.18-r105`, `device-nothing-tetris 8-r0`, `firmware-nothing-tetris 1-r3`. |
| Merged hardware baseline branch | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` | Already merged into `main`. Keep only as historical CI reference until branch cleanup. |
| Thermal candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/scp-thermal` | Adds safe polled MT6878 LVTS zones. Current SHA `06eb2d3066f59fef4ec7340f29a755db62843585`; CI run `30919258028` is still building. Must pass CI and live boot before promotion to `main`. |
| U-Boot candidate | `xxxvik-xakerxxx/u-boot:codex/scp-thermal-handoff` | Current handoff branch for preserving LK devinfo calibration data. |

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
| 1 | Thermal / devinfo | Boot MT6878 LVTS thermal zones in polling-only mode with LK devinfo calibration. | CI build, clean boot, `/sys/class/thermal` zones, plausible idle/load temps, USB/Wi-Fi/BT/audio regression pass. |
| 2 | Sensorhub | Build-only/manual-gated sensor transport after existing `hf_manager.ko`: `mtk-mbox.ko`, `mtk_rpmsg_mbox.ko`, `mtk_tinysys_ipi.ko`, `sensorhub.ko`. Do not autoload vendor SCP or nanohub. | SCP/mainline RPMSG state is understood, no legacy SCP conflict, at least one sensor path reaches standard Linux/IIO or documented bridge, USB debug remains stable. |
| 3 | SIM / modem | Stage CCCI/CCMNI/ECCCI modules without autoload. Keep `conn_md` and `mddp` disabled until basic modem boot is clean. | ModemManager sees modem, SIM state is readable, SMS/data smoke test, no radio regression with Wi-Fi/BT/GNSS. |
| 4 | GPU | Prefer native DRM Panthor over vendor Mali/GED/GPUEB. Solve thermal, MFG0 genpd, MT6319 GPU rail, firmware path and IOMMU mapping first. | `/dev/dri/renderD*`, short GL/offscreen smoke test, thermal zones active, suspend and USB debug regression pass. |
| 5 | Camera foundation | Build-only sensor inventory, cam_cal, `pd9302a` VCM and LM3644 V4L2 flash bridge before ISP. Do not autoload camsys/imgsys/hcp/aie/OIS. | Sensor IDs visible without hangs, media nodes documented, torch unchanged, no blanket camera stack autoload. |
| 6 | Native display | Separate DSI/DSC/panel branch while keeping simpledrm as fallback. | KMS framebuffer works, brightness works, suspend/resume works, fallback boot path documented. |

## Draft workspaces

Local draft workspaces are intentionally not committed to this repo. They are
the current staging notes for follow-up patch branches:

| Block | Draft path | Status |
| --- | --- | --- |
| Sensors/SCP | `local/patch-drafts/sensors-scp/` | Draft patch applies cleanly, stable overlay unchanged. Needs USB live baseline before any module load. |
| SIM / modem | `local/patch-drafts/modem-sim/` | Draft CCCI/CCMNI/ECCCI plan and live gates. Compile-only branch should be next; no `conn_md`/`mddp` first pass. |
| GPU | `local/patch-drafts/gpu/` | RFC Panthor path with MFG0 domain and disabled DT node drafts. Wait for thermal and regulator work. |
| Camera foundation | `local/patch-drafts/camera/` | Source inventory and config draft for sensor ID/cam_cal/VCM/flash only. No ISP/autoload yet. |

## Current blockers

- Wi-Fi SSH to `192.168.2.76` timed out from the workstation on 2026-08-04, so
  live audit still needs USB debug or a reachable LAN SSH path.
- `codex/scp-thermal` CI failed at `0888c289` because the LVTS patch added
  `mtk-boot-devinfo.c` but referenced `nvmem-mtk-boot-devinfo.o` in Makefile.
  Commit `06eb2d3066f59fef4ec7340f29a755db62843585` fixes this with the
  correct GitHub author/committer and awaits CI.
