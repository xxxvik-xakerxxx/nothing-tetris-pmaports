# Nothing Tetris port completion plan

This file tracks the current working order for turning the CMF Phone 1
postmarketOS port into a stable daily-phone build.

## Current source of truth

| Track | Branch / path | State |
| --- | --- | --- |
| Stable source baseline | `xxxvik-xakerxxx/nothing-tetris-pmaports:main` | Current SHA `ee994e4236d69c9f3eb18e81614dd0dff9e60266`. Keep as the published rollback until the active candidate completes all promotion gates. |
| Installed device candidate | CI image from `c2b19a9` | Kernel package candidate `6.18-r132` and device `8-r6` were clean-flashed from CI `33954042399`. Linux exposes valid NCM descriptors, but a locked macOS host ignored the new random gadget MAC; physical display and exact userspace checks are therefore pending. The previous `980c566` result remains rejected because Phoc corrupts or blacks inherited scanout. |
| Previous rollback image | CI image from `f607513` | Kernel `6.18.0 #123` retains the prior full physical regression evidence and preserved rollback artifacts. |
| Previous CI candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` at `0600a13ceba889d294f6bc1be289e273a75eca00` | `pkgrel=126`. CI run `33495661863` applied the series and completed the main kernel build, then failed on a brittle disabled-Kconfig text check before the IMX882 object gate. It produced no install image. |
| Installed image source | `xxxvik-xakerxxx/nothing-tetris-pmaports` at `c2b19a92d44229c4335170ec8ae33d8a499aac3b` | Kernel `pkgrel=132` and device package `8-r6`; CI run `33954042399` produced the installed and hash-verified artifacts. It is an isolated display experiment, not a stable `main` candidate. |
| Audio CI candidate | `xxxvik-xakerxxx/nothing-tetris-pmaports:codex/next-hardware` at `384f155f88dfc601e5597d43b34471e1cae6a71e` | Device package `8-r4` binds the speaker policy to `graphical-session.target`, excludes `greetd`, and defers mono-remap creation until the ALSA master exists. CI `33522638794` built kernel and device packages; image verification failed only because its assertion still searched the old static config. The following candidate corrects that assertion. |
| Installed GNSS candidate | Current `codex/next-hardware` image | Device `8-r5` packages only stock-derived Tetris GNSS v051 as a manual service. GPS EMI handoff, transport, bounded link0 open, ATF boot-info and close pass without USB/Wi-Fi/BT regression; no position fix exists yet. |
| Flashed bootloader | `xxxvik-xakerxxx/u-boot:master` | Commit `b76e47e774304ab550a6354f3286860b7caffb3a` is installed in `lk_a` and `lk_b`; fastboot reports the exact revision. It passed CI `33492618726`, normal boot, Linux-to-fastboot reboot and GPS EMI handoff. It starts no subsystem itself. |
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
4. The gadget host/device MAC pair is stable across clean boot and reboot,
   derived per device without exposing or packaging the source identity, and a
   previously trusted locked host assigns the interface without user action.
5. Wi-Fi, Bluetooth, audio playback/capture, touch, haptics and root I/O still
   work after the change.
6. No unload/reload testing of `conninfra` or radio modules; reboot between
   unsafe radio attempts.
7. Any new default module must be packaged, dependency-checked, and covered by
   `scripts/validate-pmaports-overlay.sh`.

## Bring-up order

| Order | Block | Goal | Promotion gate |
| --- | --- | --- | --- |
| 1 | Thermal / devinfo | Boot MT6878 LVTS thermal zones in polling-only mode with per-device calibration read from MT6878 read-only devinfo registers. | CI build, clean boot, `/sys/class/thermal` zones, plausible idle/load temps, USB/Wi-Fi/BT/audio regression pass. |
| 2 | Power / suspend | Complete safe source classification and isolate the high unplugged drain before enabling more remote processors. The 500 mA fallback works, and a real 5 V / 2 A PD contract now drives the existing policy to 2 A, but the battery was full and native MT6375 BC1.2 classification is absent. Existing USB-connected logs still cannot measure unplugged idle. | Repeat fixed 5 V PD from a partially discharged battery with rate/thermal/taper/termination evidence; observe a USB 2.0 host, known Rp source and known 5 V BC1.2 DCP without losing USB; then run local unplugged screen-off Wi-Fi-on/off intervals with coulomb, suspend, wake and IRQ evidence. |
| 3 | Sensorhub | Build-only/manual-gated transport: `mtk-mbox.ko`, `mtk_rpmsg_mbox.ko`, `mtk_tinysys_ipi.ko`, `scp.ko`, `hf_manager.ko`, `sensorhub.ko`. The exact Nothing OS 4.1 source set compiles on Linux 6.18. The first runtime blocker is the absent `mediatek,scp-dvfs` platform device, but adding it alone is unsafe before SCP firmware/TCM/carveout handoff is proven. | U-Boot validation/publication of active `scp1`/`scp2`, TCM region-info and both carveouts; disabled DVFS provider compile gate; one observation-only boot; then one DVFS-only probe. Sensorhub and nanohub remain off until SCP lifecycle and idle-power gates pass. |
| 4 | GNSS | Correct `b76e47e` LK publishes GPS EMI `0x86a00000/0x100000`. Installed manual v051 completes transport, bounded link0 power lifecycle and ATF boot-info while preserving USB/Wi-Fi/BT. | Integrate MNL or a maintainable Linux GNSS bridge, obtain a standard timed/accurate fix, then pass three cold starts, restart, coexistence and suspend/resume. |
| 5 | SIM / modem | Validate the bootloader CCCI descriptor, then stage CCCI/CCIF/DPMAIF/CCMNI boundaries without autoload. Keep `conn_md` and `mddp` disabled until basic modem boot is clean. | ModemManager sees modem, SIM state is readable, calls, SMS and data pass, no radio regression with Wi-Fi/BT/GNSS. |
| 6 | GPU | Prefer native DRM Panthor over vendor Mali/GED/GPUEB. The MT6363 VSRAM descriptor, MT6319-compatible regulator config and disabled MFG RPC topology are compile/static-only; VGPU DT, full power sequencing, firmware and protected memory remain blockers. | `/dev/dri/renderD*`, short GL/offscreen smoke test, sustained load, thermal zones active, suspend and USB debug regression pass. |
| 7 | Camera foundation | Build-only `0051` inventory covers six Tetris sensor variants and four cam_cal layouts alongside corrected `pd9302a` VCM and LM3644 flash groundwork. Do not autoload camsys/imgsys/hcp/aie/OIS. | Sensor IDs visible without hangs, media nodes documented, preview/capture, torch unchanged, repeated start/stop and USB regression pass. |
| 8 | Native display | Current simpledrm is not a stable desktop path. The r132 fallback experiment tests damage-limited MMIO copies. Historical native r40 already bound OVL/COLOR/CCORR/AAL/GAMMA/DSI and created fb0; selecting OVL frame-start IRQ bit 14 removed vblank timeout logs. Reconstruct that exact opt-in DDP/DSC/DSI/panel path before changing the default DTB. | KMS framebuffer, 60/120 Hz modes, brightness, blank/unblank, sustained touch, suspend/resume and fallback boot path all work while USB SSH remains stable. |

## Prepared boundaries

These paths record source and compile boundaries only. They do not imply that a
driver is packaged, autoloaded or safe to probe on hardware:

| Block | Draft path | Status |
| --- | --- | --- |
| Sensors/SCP | `0032`, `0036`, `0037`, `0041` plus `APKBUILD` and `local/agent-results/scp-uboot-next/` | Exact-source clean compile passes for mailbox, RPMSG, IPI, SCP, HF manager and sensorhub. `ba02998` proves bounded SCP failure containment. A host-only U-Boot parser validates unique 64-bit shared/loader carveouts, DRAM containment, minimum size, non-overlap and FDT immutability. Active-slot firmware identity, TCM region-info and boot publication remain missing. |
| SIM / modem | `0039`, `0048`, `0053` and compile-only `APKBUILD` gates | `6bc2096` / CI `33356899792` proves clean `ccci_util_lib.ko` modpost; ECCCI core objects compile without a module. The isolated CCIF boundary now compiles `ccci_ringbuf.o` and `ccci_hif_ccif.o` with reviewed Linux 6.18 timer APIs and guarded exact B4.1 service ID `0x505`. No CCIF `.ko`, DT, packaging, autoload, firmware, power/reset, DMA, DPMAIF or CCMNI. |
| GPU | `0035`, `0052`, `docs/GPU_BRINGUP.md` and `APKBUILD` | MFG0 data and the B4.1 MFG RPC topology are present with both RPC provider levels disabled. Exact active-series apply and direct DT compilation pass; no GPU consumer, register access or runtime claim. |
| Camera foundation | `0046`, `0047`, `0049`, `0051`, `0055`, `docs/CAMERA_COMPILE_ONLY_AUDIT.md` and `APKBUILD` | Object-only gates cover PD9302A, IMX882 identity and the six-variant/four-layout Tetris inventory. The stock-derived main-IMX882 fixture keeps its client and all four rails disabled, does not alter shared I2C8, and adds no EEPROM, actuator or graph. CI rejects camera runtime modules; no sensor, SENINF/ISP or CCU is enabled. |
| Native panel | `0050` plus `APKBUILD` | S6E8FC3X02 binding/driver passed standalone patch application, arm64 translation-unit compilation and full pmaports CI run `33502390335`. `pkgrel=127` keeps it object-only with no shipped module or DT client; no runtime panel claim exists. |

The audio lifecycle candidate is tracked directly in the device package rather
than a kernel patch. Clean #128 evidence shows that pre-login SSH starts a user
manager, whose default-target audio policy autospawns PulseAudio before the
active seat grants ALSA/haptics access. Device r4 starts that policy only as
part of the graphical session and leaves mono-remap creation to the existing
idempotent policy after UCM publishes the master sink.
Clean #130 showed that r5 still allowed the standard XDG desktop entry and
libpulse clients to autospawn a separate `greetd` PulseAudio process. Device r6
adds overrides only under `/var/lib/greetd/.config`; the real user's PulseAudio
startup and policy are unchanged until clean-session testing proves one owner.
A reversible r6 overlay on installed #130 passed one normal reboot with zero
greeter PulseAudio owners, no new ALSA/BlueZ ownership errors, no failed units,
and automatic USB/Wi-Fi/Bluetooth recovery. Packaged clean-install and real-user
login/relogin gates remain open.

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
- The CCIF timer lifetime conversion and exact-source service ID are complete in
  an isolated object-only patch. The next boundary is link/modpost dependency
  inventory plus installed trusted-firmware command/return semantics. Do not
  issue the SMC or proceed to DPMAIF DMA ownership before that evidence exists.
- U-Boot reinjects `clk_ignore_unused` after the packaged DTB is checked. A
  one-shot boot without the token failed and reset, with no ramoops record.
  Capture the early failure before attempting kernel or U-Boot policy changes.
- The 500 mA fallback is measured, and a separate power bank published a valid
  5 V / 2 A PD limit that the existing policy consumed. Because that sample was
  at 100 percent battery, sustained rate and thermals remain open. Test known
  host, Rp and DCP sources before adding only the missing BC1.2 boundary; DP/DM
  ownership must not disrupt USB NCM. Keep PPS, higher voltages and OTG disabled.
- Current battery drain is too high for a stable-phone baseline. Existing
  USB-connected captures cannot prove the unplugged cause. Run local screen-off
  Wi-Fi-on/off intervals on separate boots before sensorhub, modem or GPU remote
  processors are enabled by default.
- Thermal IRQs and hardware trips remain disabled until routing and reboot
  behavior are validated independently of the polling-only temperature path.
- The USB suspend hook is installed, but this image exposes no RTC wake device.
  Full suspend/resume therefore needs a coordinated physical power-button wake
  while USB and Wi-Fi recovery are monitored.
