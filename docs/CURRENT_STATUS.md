# Nothing Tetris current port status

Updated: 2026-09-11.

## Latest GPS reliability result

The unchanged supervised v2 protocol passed another clean boot on c931695,
then failed its next repetition waiting for the post-stop RESET_DONE record.
The late normal close does not turn that timeout into a pass. Recovery was
an orderly reboot, never a module reload. Three repeatable starts are not
established, and no position fix has been obtained.

An isolated six-function trace on the next clean boot passed the full cycle.
The stop handler completed in about 116 us; its FSM call took about 17 us.
The corresponding journal record appeared roughly 277 ms later. This run
does not reproduce the earlier multi-second delay or prove its cause.
Vendor FSM messages lack a trailing newline; log finalization is now being
checked before changing hardware timing or the eight-second test deadline.
USB 32 MiB hashes passed before/after, Wi-Fi remained connected, BT powered,
no GPS owners or failed units remained, and the isolated tracer was removed
with global tracing still nop. Raw evidence is retained locally under
gnss-supervised-c931-repeat-{1,2} and gnss-supervised-c931-stop-trace.

The display promotion candidate has advanced to
7e8503e8371cb0394425ca0698b9acf8602aaf7a (kernel r154/device 8-r11).
It preserves the installed audio and greeter configuration and creates the
greeter dconf directory with checked ownership. CI 34587197925 is building;
the image is not installed or merged. Its older unrelated GNSS package is
not the v051 research environment. Main has not moved.

## Latest bootloader observation

The subsequent bounded header-list candidate c931695bb963efaa0dfdf928ea475440581838b4
also passed CI 34584756418 and is now installed in lk_a. That observation was on
3bcabc1f-8d6e-4c0c-8d97-977eae5affc2, loader c931695bb963, unchanged r153.
tag-list-header-error=0, count=38, ID masks low=0x3b0c7fff,
high=0x0026ff3b. Their combined population is 38, so this observed list has
38 distinct IDs in the reported range. No tag payload was read or validated.
FDT errors remain unchanged. USB 32 MiB passed, Wi-Fi connected, BT powered,
DRM connected, no failed units or matching kernel/DRM critical errors.
Initial SSH timed out; subsequent read succeeded without reset/reflash.
Visual confirmation below applies to the preceding dd40 boot, not this one.

CI 34583094081 passed for dd40c7d6420d25ecc9cd75ae608cd5b9d1a155d9.
The manifest-checked LK artifact was installed only in lk_a, leaving lk_b,
rootfs and calibration unchanged. Boot 043e6e88-b832-423c-a58d-50fdf3438684
reports U-Boot 2026.07-rc1-gdd40c7d6420d and unchanged r153/kernel #154.
The new tag-header-error is zero: the bounded eight-byte MediaTek header
check passed. This does not validate the list or establish modem ownership.
FDT diagnostics remain source/preservation/x2=-61, x0=-74 and
no-fdt/invalid/not-checked. Next establish complete tag-list structure and
the actual modem producer, not a relaxed FDT check or guessed power call.

USB reattached with the Mac unlocked without a host reset. SSH initially
returned connection refused during startup, then connected successfully.
The 32 MiB transfer hash matches before/after; usb0 UP, Wi-Fi connected,
Bluetooth powered, DRM connected, no failed units. The user subsequently
confirmed visually good display output. Touch, audio, suspend and modem
functionality were not established by these checks.
The prior GNSS milestone below belongs to the preceding boot; no GNSS
download was performed on either new diagnostic boot.

## Latest GNSS milestone

One supervised primary GNSS download/start/stop cycle now passes on r153,
device8-r9, boot 3baa4f13-1c6d-4cf7-858a-6497d04f0de5. The real DSP reaches
RAM-code WORKING, then RESET_DONE after one FE05/4 stop, and normal OFF before
the device finishes closing. No forced A-die off or abnormal FSM occurred
in the bounded capture. USB 32 MiB hashes pass before/after, Wi-Fi remains
connected, Bluetooth powered, no failed units and no GPS owners. The module
was left loaded with its link closed until the next orderly diagnostic
reboot; no unload/reload was performed.

Status remains Partial: no coordinates/fix, three clean repetitions,
suspend/resume or automatic GNSS service. GSM/SIM remains unverified. The
verified research sequence is preserved locally as GNSS worktree commit
f4db1b5; it is not merged into main or packaged as working GPS. Exact inputs,
timestamps and retained prior failure are in GNSS_USERSPACE_BRIDGE_AUDIT.md
and local/gnss-supervised-r153-v2/LIVE-PLAN.md. New boot recovery required
Mac unlock plus the guarded host USB reset; that reconnection defect remains.

## Publication and radio follow-up

The display-only promotion candidate is published as
`codex/display-main-promotion` at `8f61a02d2e0d12584a11a111998c1adf4e89b040`,
based on primary branch `main` at `ee994e4236d69c9f3eb18e81614dd0dff9e60266`.
It carries the display dependency series and fixes 0096/0097, with kernel
6.18-r154 and device 8-r10. It is not the installed full-integration r153
image and does not include the later unrelated hardware experiments.
All 72 kernel patches apply in package order; source/checksum and route
tests pass. CI 34575901650 completed successfully and produced image,
build-log and radio-live artifacts. They are not yet installed. Main has
not moved. Clean-install/regression and lifecycle
checks remain prerequisites; review the candidate's older unrelated
userspace packaging before replacing the working r153 installation.

U-Boot diagnostic 38192f202c8bc3009efbb1d357b97975768424af was explicitly
approved and published. CI 34575135682 passed; downloaded artifact hashes
match its manifest. A subsequent fastboot write installed it only in lk_a;
lk_b retains 60bcf22. After unlocking the Mac, one identity-checked host USB
reset restored en4 and SSH without rebooting the phone. Running loader is
2026.07-rc1-g38192f202c8b, boot 6fca0ea2-9c15-4a05-8a9e-ee07fa8a76c6.
The 32 MiB USB transfer hash passed; usb0 is UP, DRM is connected, no failed
system units or matching Oops/panic/DRM timeout were found. CCCI reports
source-error=-61, preservation-error=-61, x2-validation-error=-61 and
x0-validation-error=-74, with no-fdt/invalid/not-checked. The x0 rejection
is FDT header/full validation, not the range predicate; which of those two
checks failed is not yet distinguished. Neither modem boot nor SIM/network
functionality is established. This supersedes the installed-loader row in
historical tables; locked-host USB reconnection remains an unresolved defect.
See MODEM_SIM_EVIDENCE_PLAN.md for the bounded diagnostic and next gate.
The installed container replaces its first `lk` payload with U-Boot while
preserving a separate bl2_ext. Complete stock-LK modem preparation cannot
be assumed from that packaging. Trace the actual argument producer before
changing the FDT parser or attempting modem startup.

The r153 GNSS experiment received one checksum-valid FE31 acknowledgement
after BINFO, but closing this incomplete download failed the kernel off-done
poll and forced A-die off. A clean reboot restored the baseline; the last
verified boot is 3334a5ab-4658-4310-b07e-77b6fcaf0fa1, with USB/SSH available
and GNSS inactive before the later bootloader test above. A full-fragment
research probe passes 29 mocked-I/O
scenarios but has not run on the phone. DSP readiness and safe shutdown
remain unresolved; there is no position fix. See GNSS_BRINGUP.md.

## Latest display result

Installed now: CI `34492172863`, commit
`aecf4f44f4170952709a7dd514538f0d75b55e22`, kernel `6.18-r153` / `#154`,
device package `8-r9`. All image hashes matched the CI manifest. The paired
super/userdata clean flash completed (17 sparse userdata transfers); the
unchanged U-Boot is `60bcf22`. Although fastboot reboot lost its USB status
reply, Linux and USB NCM/SSH returned automatically. Native DRM exposes an
active 1080x2400 XR24 framebuffer without either diagnostic patch module.
The installed FIT hash is
`da5e33c9342b1a7d4ea4af7b278496021b3d222ca5756dd1d7338058282602a2`.

The 32 MiB USB transfer regression gate passed at
`local/live-logs/20260910T192547Z-172.16.42.1-regression-gate`.
A ten-cycle DPMS test stopped at cycle five: the first four cycles produced
the requested DRM sequence events, then QUEUE_SEQUENCE returned EINVAL.
The connector remained available afterward, USB/SSH survived, and no DRM
timeout or Oops was found. Phoc logged additional off/on transitions around
the failing cycle. That run's root cause was not isolated; do not count it
as ten passed cycles or erase the first failure with retries. This is not a
suspend/resume test. The user subsequently confirmed visible working output
on the installed image. Repeated cold boots, stable lifecycle and 120 Hz
remain pending. The earlier live experiments are recorded below.

A separate controlled test now passes all ten DPMS cycles on unchanged r153.
It holds a session idle inhibitor and observes GET_SEQUENCE readiness before
queuing frame events, reporting every pre-ready EINVAL. Enabling needs
288-298 ms after the D-Bus request. Every cycle then delivers 30 sequence
steps without a queue retry, timeout or discontinuity. The Phoc journal
contains exactly ten off/on pairs in the interval; no DRM fault was found,
USB/SSH remain UP and the idle inhibitor was released. Evidence:
`local/r153-dpms-ready-10cycles.txt`, `local/r153-dpms-ready-post.txt`,
`local/r153-dpms-ready-transitions.txt`. This supports a readiness race in
the older test, not a proof that every earlier artifact had that cause.
Physical pixel inspection after this new run is still pending.

One bounded exclusive-PQ-bypass experiment was rejected: retaining working
DSC selection while selecting only the bypass produced 16 abnormal EOF
events and zero frame completions. Automatic route restoration immediately
restored frame completions, the post-test DRM event completed, USB/SSH stayed
UP and the diagnostic was removed. No production source/timing/firmware
change follows that failed candidate. Native RSZ/PQ lifecycle ownership
remains the next source boundary; see the complete first-frame audit.

Read-only PQ capture now narrows that boundary: RSZ is disabled with zero
dimensions, while subsequent blocks retain their configuration. POSTMASK
is enabled with relay clear, DRAM mode set and local INTEN=0x917, without a
native owner. Actual DMA transactions were not measured. The next causal
test is its vendor-defined relay bit, not blindly enabling an RSZ scaler.
All ten PQ clocks were on; frame events and USB survived the read-only
capture and diagnostic removal.

The next bounded POSTMASK test changed only CFG bit 0 (0x146 -> 0x147), then
automatically restored it. Relay sustained 15 frame completions but produced
one abnormal EOF at transition; the restored phase had 15 completions and
no abnormal EOF. This is not a clean pass and does not justify a persistent
live toggle. Configure while the path is stopped before enabling OVL in
the native lifecycle; interrupt/DMA quiescence and pixel proof remain open.
USB/SSH survived and the temporary module was removed.

An unreferenced native POSTMASK helper candidate now exists under
`patches/native-display/`. Eight host configurations and a negative mutation
pass; its translation unit compiles for ARM64 against the prepared 6.18
diagnostic tree. It adds MT6878-specific interrupt masking, shadow bypass
and relay configuration, preserving generic behavior. It is not packaged
or enabled. CRTC currently interleaves config/start, so activation also
requires a reviewed configure-before-start order, DT/clock/mutex/routing
integration and stopped-path live evidence. See the candidate README.

Candidate 0002 now supplies the MT6878-only configure-all-before-start
callback order. Reconstructed APKBUILD-order source passes 24 host traces,
a negative interleaving mutation and ARM64 object compilation with local
patched headers. It remains unreferenced; inherited engine quiescence,
POSTMASK DT/routing/clock ownership and live lifecycle are not proven by
the callback order test. Installed r153 is unchanged.

Current performance observation: the running Phoc session uses Pixman after
EGL/Vulkan initialization failure, and only card0 exists (no render node).
The fixed panel DT selects 60 Hz; it does not expose a runtime 120 Hz mode.
A bounded 120-sequence measurement on an active CRTC took 2032465770 ns
(59.0416 sequence Hz). This is not compositor FPS or a long-term stability
result. An initial attempt on a disabled CRTC and an attempt immediately
after the wake request both failed with EINVAL; neither is silently retried.
See DISPLAY_FIRST_FRAME_AUDIT.md for the measurement boundary.

## Historical r151 live experiments

Update after the route-only test: changing OVL0 INTEN from frame-start bit 14
to frame-completion bit 1 eliminated redraw flicker according to the user.
The bounded trace retained the correct route and mask 2 throughout, with
DSC frame completions and no new abnormal EOF. A DRM sequence event completed
and USB/SSH stayed available. Prepared r153 patch `0097` makes this source
selection persistent in MT6878 driver data. The fully patched OVL translation
unit compiled with clang 21.1.8 against the prepared diagnostic kernel tree.
This is still a live result, not installed CI/lifecycle proof. Perceived slow
rendering remains; the session uses software rendering, but its precise
performance bottleneck has not been measured. The route-only history follows.

Installed software remains CI `34470405429`, kernel package `6.18-r151`.
A reversible live change to MMSYS 0xd00/0xd30/0xd60 produces a user-confirmed
native interface. With that route stable, acknowledged DSC samples are one
initial stale 9 followed by 31 FRAME_DONE-only samples. USB/SSH remain available.
The image still flickers on interaction. Subsequent modesets overwrite the
temporary route even though the probe remains loaded, restoring grey/striped
output and abnormal EOF. This is **Partial (live probe only)**.

At the user's request, prepared r152 patch `0096` puts those exact selections
in the driver connect path. It does not add an autoloaded diagnostic module
or a register-writing background service. Patch application and a host-side
connect/disconnect model are checked; CI and installation are still pending.
Inherited LK PQ initialization, flicker, cold repeat and lifecycle validation
remain open. The older rows below describe baseline images, not this live
experiment. Full evidence is in `DISPLAY_FIRST_FRAME_AUDIT.md`.

## Historical software state before r153

| Role | Revision | Device state |
| --- | --- | --- |
| Installed pmaports image | `a03529f` / CI `34470405429` | Kernel package `6.18-r151`, kernel `6.18.0 #152`. A paired clean flash boots automatically; USB NCM/SSH, touch, Phoc, backlight and the native connector return. After restarting Phoc, DRM exposes an active 1080x2400 XR24 framebuffer, but pixels remain corrupt: `DSC_MODE=0x00000001` is now confirmed and DSC still reports abnormal EOF without `FRAME_DONE`. |
| Previous rollback image | `f607513` | Kernel `6.18.0 #123`; preserved stable artifacts and prior clean/warm regression evidence. |
| Stable pmaports source | `main` at `ee994e4236d69c9f3eb18e81614dd0dff9e60266` | Rollback source of truth. |
| Previous pmaports CI candidate | `codex/next-hardware` at `0600a13ceba889d294f6bc1be289e273a75eca00` | `pkgrel=126`; CI run `33495661863` applied the patch series and completed the main kernel build, then failed before the IMX882 object check because a disabled Kconfig symbol was absent rather than serialized as `# ... is not set`. No image was produced or installed. |
| Active pmaports source | `codex/hardware-integration`, local validation passed after r151 install | Consolidates the installed r151 display baseline with fail-open USB identity, source-aware charging validation, a stricter Wi-Fi functional gate, the packaged greetd dconf directory fix, an audio lifecycle gate, read-only GNSS diagnostics and compile-only charging, GPU, camera, sensor and modem boundaries. It remains off `main` until the native display and regression gates pass. |
| Native-display integration | Installed CI `34470405429`, kernel package `6.18-r151` | Patch `0088` correctly restores the vendor default `DSC_MODE=0x00000001`, disproving the forced parameter-load bit as the complete fix. Active KMS probing still reports `DSC_INTSTA=0x00000008`, `FRAME_DONE=0` and DSI input stuck at `0x00010001`; native display remains broken. |
| Prepared modem boundary | Local validation passed, kernel package `6.18-r151` | Clang/LLVM 21 gates now cover CCCI util/core/CCIF, modem common and 39 FSM/port/non-page-pool-DPMAIF objects. No ECCCI/DPMAIF module, DT node, autoload, SMC or DMA runtime path is enabled or packaged. |
| Prepared BC1.2 lifecycle boundary | Pending CI, kernel package `6.18-r150` | Patch `0090` is compile-only and models bounded timeout recovery, retryable cleanup, role-granted DP/DM ownership and initial/current attach-state reconciliation. Host tests exercise each lifecycle path. CI rejects production DT, IRQ, PHY, regmap, module, packaging or autoload wiring, so USB and charging runtime behavior remain unchanged. |
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
| Wi-Fi | Partial | Clean #130 automatically reassociates with DHCP/default route/DNS/HTTPS and completed an exact 64 MiB SSH stream at `192.168.22.64` while USB and Bluetooth remained active. The r151 regression gate now distinguishes `wlan0` presence from usable Wi-Fi; the current boot fails the new Wi-Fi mode because `wlan0` is present but not associated. | Cold reconnect, suspend/resume, sustained bidirectional transfer and second-unit checks. |
| Bluetooth | Partial | Clean #130 registers powered BlueZ `hci0`; `bluetoothctl --timeout 8 scan on` found 23 devices and exited with `Discovering: no` while USB and Wi-Fi remained active. The earlier stuck-discovery result came from an unbounded client invocation rather than the bounded lifecycle. | Pair/reconnect and test audio/data profiles across suspend. |
| Touch and keys | Works | Installed r132 binds `fts_ts` at I2C `2-0038` and exposes `/dev/input/event0`; the reported graphical failure is not a missing touch device. The current fbcon intentionally has no touch interaction. Balanced power/volume events passed previously. | Recheck sustained touch after the graphical display path is restored. |
| Haptics | Partial | The user physically confirmed the bounded RT6010 effect on clean #128; USB remained healthy. | Cold-boot repetition and suspend/resume. |
| Audio | Partial | Speaker playback remains historical physical evidence. On clean #130 a quiet five-second capture produced 387856 samples, 386262 nonzero, zero clipping and 193359 stereo pairs with different channels. After a reversible r6 overlay and normal reboot (`246b8a99-05bc-4ae6-8017-623314471cf9`), `greetd` had zero PulseAudio processes, no fresh ALSA/BlueZ ownership errors appeared, failed units were zero and USB/Wi-Fi/BT returned normally. On installed r151/r8 the new audio audit initially failed because `/var/lib/greetd/.config/dconf` was absent; after creating it live with `greetd:greetd 0700`, the audit passed with USB, ALSA card and zero greeter PulseAudio owner regressions. Device package r9 now installs that directory. | Build and clean-install r9, require zero greeter PulseAudio owners and one real graphical-user owner, then retest login/relogin, speaker/system events, capture, Bluetooth profiles and suspend. |
| Thermal | Partial | All 24 MT6878 zones return plausible polling-mode values without USB loss. | IRQ/trip routing and sustained load remain disabled/unverified. |
| Charging | Partial | Clean #128 uses AICR/ICHG 500000 uA when TCPM publishes no current limit. A later real PD session published 5 V / 2 A and drove the policy to 2 A. On installed r151, the source-aware power gate passed: this PD-capable computer attachment reports 5 V but `CURRENT_MAX=0`, so the conservative 500 mA fallback remains correct. These are contract/taper snapshots, not a full charge-rate result. Native BC1.2 SDP/CDP/DCP classification is absent. | Repeat PD from a partially discharged battery while logging battery/connector temperatures, rate, taper, termination and detach. Separately observe a USB 2.0 host, known Rp source and known 5 V BC1.2 DCP. Preserve USB2 DP/DM ownership; explicit PPS setpoints, higher voltages and OTG remain disabled. |
| Idle battery drain | Broken | Roughly half the battery was reported lost overnight. A live r147 capture found `dconf-service` at 5.1 GiB RSS plus 596 MiB swap and persistent CPU use because `/var/lib/greetd/.config/dconf` did not exist; Calls and Chatty retried failed writes continuously. A soft restart reclaimed the memory, but growth resumed until the directory was created. Device package r9 now ships the private dconf directory directly and the overlay validator rejects regressions. Wi-Fi and USB suspend costs remain unisolated. | Build and clean-install r9, validate flat dconf RSS/CPU across reboot, then run physically unplugged screen-off A/B intervals with Wi-Fi associated and disabled. Record coulomb, suspend and wake/IRQ deltas. |
| GNSS | Partial | Fastboot proved the previous executable loader was `8aa048f`; after `b76e47e` was installed in `lk_a/b`, live DT exposed GPS EMI `0x86a00000/0x100000`. Clean #130 manual v051 then created both nodes and completed bounded link0 open, ATF boot-info ioctl 23 and close. No owner/modem module remained; Wi-Fi, Bluetooth and exact 32 MiB USB survived. The `pkgrel=150` candidate now extracts the three proven read-only ioctls and packages an explicit, deadline-bounded link0 diagnostic with no autostart. | Run the manual diagnostic regression gate. A position bridge remains blocked on locally absent MNL/MVCD/navigation protocol evidence; after that is obtained, prove a timed/accurate fix, cold starts, restart and suspend/resume. |
| Modem / SIM | Broken | No ModemManager modem, CCCI/DPMAIF/WWAN device or SIM state. U-Boot validates the LK CCCI payload. The combined 64-object CCCI/util/CCMNI/RPS/ADC/UDC/non-page-pool-DPMAIF inventory classifies 242 remaining references; optional MRDUMP dependency is guarded and checked in both configurations. No ECCCI/DPMAIF module is linked, shipped, autoloaded or run. | Validate actual configured-kernel exports, module ownership and final LTO/modpost; then cover page-pool and UDC provider lifecycle. Handoff memory, trusted-firmware semantics, power, IRQ/DMA isolation, DT and runtime remain later gates. |
| Sensors | Broken | SCP/mailbox/IPI/HF/sensorhub remain manual-only; no accelerometer, gyro, proximity or light sensor is exposed. Patch `0093` structurally rejects malformed TCM region-info before SCP recovery. U-Boot candidate `5e450af73a` passes host-only slot/identity/carveout/region-info agreement tests but deliberately returns `-EOPNOTSUPP` on the board because its live adapters are absent. | Establish authoritative active `scp1`/`scp2` authentication/selection and decode the live LK TCM region-info ABI. Only then integrate an observation-only U-Boot path; publication, disabled DVFS nodes and live probes remain separate later gates. |
| GPU | Broken | Panthor is configured and has a pinned LLVM 21 compile/source-trace gate, but no Mali platform device or render node exists. The shipped DT has no GPU node; MFG RPC remains disabled inventory, with no GPU regulator consumer or autoload. | Complete MFG runtime sequencing, clock/reset ownership, coupled rails, DT consumer, CSF firmware and protected memory before any recovery-image probe. |
| Rear/front cameras | Broken | No camera media pipeline or preview/capture. Torch channels work independently. | The source candidate records the main IMX882 I2C8/CAMTG2/reset/four-rail topology with the sensor and every provider disabled. Compile-only gates still ship no camera module or live client. Final-DTB CI, observation-only clean boots, sensor identity, SENINF/ISP, CCU and the media graph remain. |
| Display | Broken | Installed r151 boots without framebuffer fallback and retains USB SSH, touch, Phoc and backlight. MMSYS routing matches Nothing OS and `DSC_MODE=0x00000001` now matches the Tetris vendor configuration, but OVL/DSC still do not complete the first native frame: `DSC_INTSTA=0x00000008`, `FRAME_DONE=0` and DSI input remains `0x00010001`. | Continue from the remaining first-frame stall; require `FRAME_DONE`, advancing counters, clean pixels and stable USB before promotion, then test DPMS, brightness, warm reboot and suspend/resume. |
| microSD | Untested | Controller probes, but no physical card I/O test was recorded. | Insert/remove, read/write and remount test. |

## Current installation test

The installed image is a regression candidate, not a claim that all new
hardware works. Current gate state:

1. Clean flash and automatic root expansion: passed on installed #130.
2. Automatic USB NCM/SSH and exact 32 MiB transfer: passed on the clean boot.
3. Warm reboot: passed with a new boot ID, automatic USB return, no failed units and charging telemetry retained.
4. Wi-Fi interface presence is no longer treated as success. On the current r151 boot, the stricter Wi-Fi mode fails because `wlan0` is present but not associated.
5. Camera, GPU and CCCI additions are absent from the runtime module/device set as required.
6. Manual GNSS v051 transport, GPS EMI handoff, bounded link0 open, ATF boot-info ioctl 23 and close passed without connectivity regression. No position fix is claimed.
7. With U-Boot `60bcf22` installed in both slots, the unchanged r132 image produced clean Phoc output on the initial and warm boots; native brightness and suspend remain unavailable.

Modem, GPU, sensorhub and camera pipeline stay disabled in the installed boot.
Native display is installed without any framebuffer fallback. The HWCCF and
SPM DISP-domain, DSI publication, mutex readiness, full route, OVL shadow and
DSC parameter-flow blockers are fixed or disproven. Installed r151 registers
native DRM without Oops, reads panel ID `40 41 02`, starts Phoc and preserves
automatic USB/touch, but its first atomic frame still does not complete.
After a Phoc restart, KMS exposes an active 1080x2400 XR24 framebuffer; the
read-only probe confirms `DSC_MODE=0x00000001`, persistent `ABN_EOF`, zero
`FRAME_DONE` and DSI input stuck at `0x00010001`. Constant-color,
continuous-reset, start-order, mutex, SMI-ID, HSTX and parameter-load tests did
not advance the pipeline and were fully reverted or disproven. The retained
r132 framebuffer image remains the reference source and fastboot rollback.
The next GNSS gate is userspace protocol integration and a real position fix,
followed by cold-start and lifecycle validation.
