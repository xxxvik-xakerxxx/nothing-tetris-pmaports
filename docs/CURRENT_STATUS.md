# Nothing Tetris current port status

Updated: 2026-09-10.

## Exact software state

| Role | Revision | Device state |
| --- | --- | --- |
| Installed pmaports image | `3dd12a1c64e4c4ca73eef9bec13540fc7cf52838` | Kernel package `6.18-r147`, kernel `6.18.0 #148`. USB NCM/SSH, touch, Phoc, backlight and the native connector return; pixels remain corrupt and no complete DSC frame is produced. |
| Previous rollback image | `f607513` | Kernel `6.18.0 #123`; preserved stable artifacts and prior clean/warm regression evidence. |
| Stable pmaports source | `main` at `ee994e4236d69c9f3eb18e81614dd0dff9e60266` | Rollback source of truth. |
| Previous pmaports CI candidate | `codex/next-hardware` at `0600a13ceba889d294f6bc1be289e273a75eca00` | `pkgrel=126`; CI run `33495661863` applied the patch series and completed the main kernel build, then failed before the IMX882 object check because a disabled Kconfig symbol was absent rather than serialized as `# ... is not set`. No image was produced or installed. |
| Active pmaports source | `codex/next-hardware` at `d0451a64f816a9f6d7c86382b70e51c7daf48da4` plus the pending CI patch-position fix | Installed r147 carries the integrated panel/DSI/DSC/OVL parity set. It remains off `main` until clean pixels and lifecycle gates pass. |
| Prepared native-display integration | Pending fresh CI, kernel package `6.18-r149` | Patch `0087` fully normalizes the five vendor DSC handoff registers plus `C00/C0C` after DISP power/clock enable, then reapplies OVL force-relay after `OVL_EN`. Patch `0088` clears only `PQ_LOOP_CON[0]` at the B4.1 offset `0x2e0` after reset and before enable. CI run `34446306149` failed before compilation because one `0087` hunk had a stale source position; the corrected complete series now applies to a fresh pinned tree locally. Runtime success is not claimed before successful CI and a clean paired image test. |
| Prepared modem common boundary | Local validation passed, kernel package `6.18-r149` | Clang/LLVM 21.1.8 builds only `ccci_modem.o`, `ccci_hif.o` and `ap_md_mem.o` from exact Nothing OS 4.1 sources; representative symbol checks pass and the ECCCI tree contains zero `.ko`. The sole adaptation adds the explicit scheduler-clock header. No modem module, DT, autoload, SMC or DMA path is enabled or packaged. |
| Installed OVL-shadow candidate | CI `34179197562`, pmaports `263a398`, kernel package `6.18-r144`, kernel `6.18.0 #145` | OVL shadow bypass changes the physical corruption pattern, proving the lifecycle write reaches hardware, but does not complete a frame. Active tracing shows DSI cycling through video states while reporting buffer-underrun/input-unfinished, DSC produces repeated `ABN_EOF` with zero `FRAME_DONE`, and the pipeline stalls at OVL0/1/2 positions `15/5/2` with DSI input `1x1`. USB SSH remains stable. Continuous DSC reset, a constant-color OVL frame, delayed/resequenced DSI start, single-shot mutex, clearing generic OVL SMI-ID and clearing `HSTX_CKL_WC` all fail to advance the counters; none is a production fix. |
| Installed full-OVL candidate | CI `34152637999`, pmaports `705da68`, kernel package `6.18-r143`, kernel `6.18.0 #144` | USB NCM/SSH, touch, panel ID `40 41 02`, Phoc and backlight return automatically. The first native frame does not complete: OVL0/1/2 report downstream-blocked flow, DSC input remains `1x1`, and DRM repeatedly reports `flip_done`, commit and vblank timeouts. The display is not usable. Read-only and reversible live probes preserved USB while disproving DSC reset/chunk, route selectors and inherited mutex membership as independent fixes. |
| Installed native-display candidate | CI `34091038734`, pmaports `d8fa8ac`, kernel package `6.18-r139`, kernel `6.18.0 #140` | SHA-verified `super`/`userdata` clean-flashed. USB NCM/SSH and `fts_ts event0` returned automatically with no legacy framebuffer, Oops or failed units. Patch `0079` works: DSI reads the complete ID `40 41 02` and IRQ 360 advances. The early compile-only driver's unsupported `40 21 01` allowlist then rejects this valid revision, leaving the connector disabled and no backlight. |
| Installed native-display candidate | CI `34099691006`, pmaports `e641138`, kernel package `6.18-r140`, kernel `6.18.0 #141` | SHA-verified `super`/`userdata` clean-flashed. USB NCM/SSH, touch, native backlight, Phoc and connected 1080x2400 DRM returned automatically with no Oops or failed units. The complete panel ID is `40 41 02`. Brightness and blank/unblank lifecycle work, but the physical image is stripes/artifacts: the DSI host still frames the DSC payload as uncompressed RGB888. |
| Installed DSC-framing candidate | CI `34112462413`, pmaports `63c6039`, kernel package `6.18-r141`, kernel `6.18.0 #142` | SHA-verified `super` and all 17 `userdata` sparse chunks flashed successfully. USB NCM/SSH returned automatically. Native DRM is enabled at 1080x2400, Phoc runs, panel ID is `40 41 02`, OVL/DSI IRQs advance, touch remains `fts_ts event0`, and failed units are zero. The physical output changed from moving stripes to a stable pale frame with one blue vertical line, proving the DSI framing change took effect but not correct pixels. |
| Installed DSC-threshold candidate | CI `34119470557`, pmaports `dd10944`, kernel package `6.18-r142` | CI passed and the image was installed. Correcting DSC RC-threshold encoding did not change the physical output: it remains a stable pale frame with one blue vertical line. This disproves RC thresholds as the remaining cause. Read-only live probing then found persistent DSC abnormal EOF and the firmware-inherited full three-OVL route. |
| Installed U-Boot | `60bcf22fdc0a94526424db59fc7640298ea8f0dd` | Hash-verified CI `33954506650` LK image is flashed to both 16 MiB `lk_a` and `lk_b`; live Linux reports exact `2026.07-rc1-g60bcf22fdc0a`. The unchanged r132 image reached clean Phoc output on two consecutive boots and USB NCM/SSH returned. The expected `atag,devinfo` node is absent, so it cannot yet seed stable USB identity. |
| Previous U-Boot rollback | `b76e47e774304ab550a6354f3286860b7caffb3a` | Preserved rollback artifact; it passes boot, Linux-to-fastboot reboot and GPS EMI handoff but produced persistent physical artifacts with r132. Older `8aa048f` is also retained. |

The installed CI `33954042399` candidate matches GitHub commit `c2b19a9`,
pinned pmaports `7ea600a`, pmbootstrap `ea17c14` and its manifest-pinned
U-Boot `b76e47e`. Runtime currently uses the separately verified `60bcf22`
bootloader from CI `33954506650`. SHA-256 verification passed for `boot_image.itb`
(`8b1bb8f30cf7db919f22583cc4a8f951fb4c28c45436106adb234cfd3277d1f2`),
the 512 MiB boot image
(`3f0a46a5a3cd312cf2fa869717bea836ab07bec70a181403eb2b367fa2e0ba3b`)
and the Android sparse root image
(`eecee1976a12e0a75a427fc78b627aca79a6fcfe6fe004a121ccc979f5626dda`).
The package contract maps the boot image to `super` and the sparse root image
to `userdata`; `boot_image.itb` is evidence, not a third fastboot partition.

The previous rollback `nothing-tetris-images` ZIP is SHA-256
`c47230ff07ebefe86faf54cf216bf7901279afbef482647389c91cd4a56bc996`.
Its manifest matches `fdeeda0` and requires U-Boot `b76e47e` with SHA-256
`869303227941e0f050d083c74eeffcfb9bf90bf80a59978780b915d22722b9c4`.
Streaming verification passed for `boot_image.itb` (`d4c97120...`), the 512 MiB
boot image (`edfb650a...`) and the root sparse image (`0fdcff2f...`). The CI
filenames are generic, but the package's `fastboot-bootpart` contract and the
validated installation path map `nothing-tetris-boot.img` to `super` and
`nothing-tetris-root.sparse.img` to `userdata`. `boot_image.itb` is retained as
the independently verifiable FIT payload; it is not a third fastboot partition.

The live partition inventory confirms separate per-device stores without
reading their contents: `nvcfg` 32 MiB, `nvdata` 80 MiB, `nvram` 64 MiB,
`persist` 48 MiB, `proinfo` 3 MiB and `protect1`/`protect2` 8 MiB each. A/B
firmware partitions also exist for modem, GNSS, Wi-Fi, Bluetooth, SCP, CCU and
GPUEB, plus `md_sec`. Wi-Fi/BT already use bounded records from `nvdata`; other
subsystems must validate their own calibration records rather than copying a
whole partition or one handset's data into the image.

`Works` means the end-user function was physically demonstrated. `Partial`
means useful behavior works but lifecycle, integration or portability gates are
still open. A compile-only patch does not improve the end-user status.

## Hardware matrix

| Subsystem | Current status | Confirmed evidence | Candidate / next gate |
| --- | --- | --- | --- |
| Boot and root filesystem | Works | Clean flash boots pmOS; root is writable and expanded. | Recheck after every candidate installation. |
| USB debug / NCM SSH | Partial | Automatic `usb0`, SSH and an exact 32 MiB transfer passed after the clean #130 install. A normal Linux reboot produced a new boot ID and restored USB SSH automatically with no failed system units. Clean r132 presents a valid CDC-NCM control/data pair; after the macOS session was unlocked, a host-side reset created `en4`, assigned `172.16.42.2` and restored SSH without rebooting the phone. The random host MAC remains a locked-host reliability defect. | Package a stable per-device hashed gadget identity, then repeat clean install, locked-host reconnect, reboot, 32 MiB transfer and suspend/resume. |
| Wi-Fi | Partial | Clean #130 automatically reassociates with DHCP/default route/DNS/HTTPS and completed an exact 64 MiB SSH stream at `192.168.22.64` while USB and Bluetooth remained active. | Cold reconnect, suspend/resume, sustained bidirectional transfer and second-unit checks. |
| Bluetooth | Partial | Clean #130 registers powered BlueZ `hci0`; `bluetoothctl --timeout 8 scan on` found 23 devices and exited with `Discovering: no` while USB and Wi-Fi remained active. The earlier stuck-discovery result came from an unbounded client invocation rather than the bounded lifecycle. | Pair/reconnect and test audio/data profiles across suspend. |
| Touch and keys | Works | Installed r132 binds `fts_ts` at I2C `2-0038` and exposes `/dev/input/event0`; the reported graphical failure is not a missing touch device. The current fbcon intentionally has no touch interaction. Balanced power/volume events passed previously. | Recheck sustained touch after the graphical display path is restored. |
| Haptics | Partial | The user physically confirmed the bounded RT6010 effect on clean #128; USB remained healthy. | Cold-boot repetition and suspend/resume. |
| Audio | Partial | Speaker playback remains historical physical evidence. On clean #130 a quiet five-second capture produced 387856 samples, 386262 nonzero, zero clipping and 193359 stereo pairs with different channels. After a reversible r6 overlay and normal reboot (`246b8a99-05bc-4ae6-8017-623314471cf9`), `greetd` had zero PulseAudio processes, no fresh ALSA/BlueZ ownership errors appeared, failed units were zero and USB/Wi-Fi/BT returned normally. | Pass CI and clean install, require zero greeter PulseAudio owners and one real graphical-user owner, then retest login/relogin, speaker/system events, capture, Bluetooth profiles and suspend. |
| Thermal | Partial | All 24 MT6878 zones return plausible polling-mode values without USB loss. | IRQ/trip routing and sustained load remain disabled/unverified. |
| Charging | Partial | Clean #128 uses AICR/ICHG 500000 uA when TCPM publishes no current limit. A later real PD session published 5 V / 2 A and drove the policy to 2 A. On clean #130 the charger/gauge and TCPM source all register, survive a warm reboot and report charging at 99-100% and 4.488 V; this computer attachment still publishes 5 V with `CURRENT_MAX=0`, so the conservative fallback remains necessary. These are contract/taper snapshots, not a full charge-rate result. Native BC1.2 SDP/CDP/DCP classification is absent. | Repeat PD from a partially discharged battery while logging battery/connector temperatures, rate, taper, termination and detach. Separately observe a USB 2.0 host, known Rp source and known 5 V BC1.2 DCP. Preserve USB2 DP/DM ownership; explicit PPS setpoints, higher voltages and OTG remain disabled. |
| Idle battery drain | Broken | Roughly half the battery was reported lost during an uncontrolled overnight period. Existing captures retained `usb0`, kept MTU3 runtime-active with `power/control=on`, and sometimes charged, so they cannot identify an unplugged cause. Wi-Fi runtime PM is unsupported and its wake/IRQ counters make it the first A/B candidate, not a proven fault. | Run local, physically unplugged, screen-off intervals on separate clean boots with Wi-Fi associated and disabled. Record start/end coulomb counter, monotonic time, suspend result and wake/IRQ deltas; reconnect USB only after each interval. |
| GNSS | Partial | Fastboot proved the previous executable loader was `8aa048f`; after `b76e47e` was installed in `lk_a/b`, live DT exposed GPS EMI `0x86a00000/0x100000`. Clean #130 manual v051 then created both nodes and completed bounded link0 open, ATF boot-info ioctl 23 and close. No owner/modem module remained; Wi-Fi, Bluetooth and exact 32 MiB USB survived. | Integrate MediaTek MNL or a maintainable Linux GNSS bridge, obtain a timed/accurate fix, then test cold starts, restart and suspend/resume. |
| Modem / SIM | Broken | No ModemManager modem, CCCI/DPMAIF/WWAN device or SIM state. U-Boot validates the LK CCCI payload. CCCI core, CCIF ring-buffer/host-interface and the bounded modem common objects (`ccci_modem.o`, `ccci_hif.o`, `ap_md_mem.o`) are compile-only; no ECCCI module is linked, shipped or run. | Inventory the complete common/FSM/port undefined-symbol closure before any link/modpost gate. Handoff memory, trusted-firmware semantics, DPMAIF, DT and runtime remain later gates. |
| Sensors | Broken | SCP/mailbox/IPI/HF/sensorhub sources compile and fail closed; no accelerometer, gyro, proximity or light sensor is exposed. A host-only parser against U-Boot `b76e47e` now validates unique 64-bit shared/loader carveouts, DRAM containment, size and non-overlap without changing the FDT. It does not validate SCP firmware or TCM. | Establish authoritative active `scp1`/`scp2` authentication/selection and TCM region-info ABI. Only then integrate an observation-only U-Boot path; publication, disabled DVFS nodes and live probes remain separate later gates. |
| GPU | Broken | Panthor is configured, but no Mali platform device or render node exists. A disabled MFG RPC provider/domain topology is prepared as source inventory only. | Validate the RPC schema/DT and register map with all nodes disabled. MFG runtime sequencing, DT consumer, CSF firmware and protected memory are still required. |
| Rear/front cameras | Broken | No camera media pipeline or preview/capture. Torch channels work independently. | The source candidate records the main IMX882 I2C8/CAMTG2/reset/four-rail topology with the sensor and every provider disabled. Compile-only gates still ship no camera module or live client. Final-DTB CI, observation-only clean boots, sensor identity, SENINF/ISP, CCU and the media graph remain. |
| Display | Broken | Installed r147 boots without framebuffer fallback and retains USB SSH. On an active graph, OVL0/1/2 accept only `15/5/2` pixels before downstream backpressure; force-relay changes this to `29/19/9`, while DSC remains `ABN_EOF`, zero `FRAME_DONE`, input `1x1`. A complete `greetd` stop/start reliably re-enables the hardware domain after it is gated. | Build and clean-flash matched r149 `super` and `userdata`; require active DSC selector state, `FRAME_DONE`, advancing counters, clean pixels and stable USB before promotion, then test DPMS, brightness, warm reboot and suspend/resume. |
| microSD | Untested | Controller probes, but no physical card I/O test was recorded. | Insert/remove, read/write and remount test. |

## Current installation test

The installed image is a regression candidate, not a claim that all new
hardware works. Current gate state:

1. Clean flash and automatic root expansion: passed on installed #130.
2. Automatic USB NCM/SSH and exact 32 MiB transfer: passed on the clean boot.
3. Warm reboot: passed with a new boot ID, automatic USB return, no failed units and charging telemetry retained.
4. Wi-Fi interface autostarted after reboot; association/routing and Bluetooth/audio/touch/haptics still need regression checks on #130.
5. Camera, GPU and CCCI additions are absent from the runtime module/device set as required.
6. Manual GNSS v051 transport, GPS EMI handoff, bounded link0 open, ATF boot-info ioctl 23 and close passed without connectivity regression. No position fix is claimed.
7. With U-Boot `60bcf22` installed in both slots, the unchanged r132 image produced clean Phoc output on the initial and warm boots; native brightness and suspend remain unavailable.

Modem, GPU, sensorhub and camera pipeline stay disabled in the installed boot.
Native display is installed without any framebuffer fallback. The HWCCF and
SPM DISP-domain, DSI publication and mutex readiness blockers are fixed.
Installed r144 registers native DRM without Oops, reads panel ID `40 41 02`,
starts Phoc and preserves automatic USB/touch, but its first atomic frame never
completes. OVL shadow bypass is active and changes the physical artifact, yet
OVL0/1/2 stop at `15/5/2`, DSC emits abnormal EOF without frame completion and
DSI input stays at `1x1` with underrun/input-unfinished flags. Constant-color,
continuous-reset, start-order, mutex, SMI-ID and HSTX live tests did not advance
the pipeline and were fully reverted. The retained r132 framebuffer image is
now the next reference source; it should only be booted while physical fastboot
recovery is available. The next GNSS gate is
userspace protocol integration and a real position fix, followed by cold-start
and lifecycle validation.
