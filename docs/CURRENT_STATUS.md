# Nothing Tetris current port status

Updated: 2026-09-22.

## r167 candidate: share the existing infracfg syscon

Replaced the unmatched vendor auxiliary `scpsys` driver with a required
`mediatek,infracfg` phandle to the existing MT6878 syscon. Validate the
enabled node, exact compatible, syscon identity and register span before
DVFS setup or firmware start. Wake SET/CLEAR and exception dump accesses
now use that shared regmap, including explicit error handling. No second
MMIO owner, fake READY, or unconditional readiness wait is used.

Exact Nothing OS 4.1 source patch application and host UBSan checks pass:
16 dependency/ownership cases, wake lock/unlock and failure paths, plus
the existing memory, bootstrap and logger checks. Full kernel/image build
is CI-only. Overlay validation and native DT preprocessing/compilation pass
(pre-existing unit-address warnings); the compiled SCP phandle resolves
to the existing 0x10001000/0x1000 syscon. This candidate is not yet
device-validated; SCP stays manual
and sensors remain **Broken** until real data and lifecycle tests pass.

Initial CI `35728863556` passed host validation but failed package prepare:
0104 was listed before prerequisite 0099. Reordered the source list and
added an explicit order/application host gate; no failed artifact was flashed.

## r166 installed: logger panic absent; readiness blocked on infracfg

Cold boot `e14bf361-3811-44fd-8776-0467b865f8da` passed secure handoff
with error 0. One `modprobe scp bootstrap_26m=1` returned 0. The r165
LOGGER_CTRL null-buffer panic did not recur and USB/SSH survived. No sensorhub
or HF module was loaded. The first three-second collection had no SCP dump.

The new blocker is host readiness completion: at 104.199164 the log reports
`[SCP] scpreg.scpsys error`. Source tracing places this in `scp_A_set_ready()`
after the READY IPI, while `scp_A_notify_ws()` waits indefinitely for that
mapping before setting `scp_ready[]`. The vendor auxiliary driver matches
`mediatek,infracfg_ao`; this resource has not been connected in the current
port. Logger IPI 17 consequently fails its readiness precondition; the
uncancelled ready timer logs timeout 1 at 114.141321 and timeout 2 at
124.637063. This is not a complete ready transition or sensor support.
The resource is also used by wake/ack register accesses, so bypassing the
wait or fabricating readiness is not a valid fix.

Evidence is `/private/tmp/tetris-r166-scp-evidence/kernel-journal`, SHA256
`3e85b7edfed0845fd77e4e7afe4b6607c11dcdd4377751877c615e9ec8987694`.
Stopped without module reload and performed a clean reboot. Recovery boot
`bf25f907-0541-44df-94e4-9a323653250b` has systemd running, zero failed
units, USB/SSH up and no SCP/sensorhub/HF modules loaded. Sensors remain
**Broken**; next gate is proper infracfg ownership/mapping, then ready and
real samples. No production merge is justified by this single test.
Post-recovery 32 MiB transfer passed at
`local/live-logs/20260922T122940Z-172.16.42.1-regression-gate`.

## r166 clean-install baseline

CI `35719843739` for `1bb4a3f96dce3529e66ab9ae6482238d662d7a5c`
completed successfully. All three artifact hashes and manifest identity
passed before flashing only `super` and `userdata`; all 17 userdata chunks
completed. Installed U-Boot `bf75c572e1` in `lk_a` was retained. No write
to `lk_b`, stock firmware or calibration partitions was made. The manifest
still names the older generic minimum bootloader, not this diagnostic build.

Boot `b87021dc-297e-4872-b9ab-15cd3669f265` reports kernel #167, systemd
running, zero failed units, USB/SSH up, rootfs 104.5 GiB. The user confirmed
normal display and touch. SCP/sensorhub/HF modules remain unloaded; the
warm preflight guard disables SCP as expected. The subsequent cold test is
recorded above; this installation alone does not prove sensors work.
Pre-flash transfer passed at
`local/live-logs/20260922T121212Z-172.16.42.1-regression-gate`.
Installed package database confirms `7.2.1-r166`. Post-install 32 MiB transfer
also passed at `local/live-logs/20260922T122221Z-172.16.42.1-regression-gate`.
Full poweroff and manual power-on preceded the cold test above. No SCP
module was loaded during the initial installation baseline check.

Artifact SHA256:

- boot: `a49713e71557b8525b9e23d7a818436cc8061ac852317c49b38dbf3624a0e063`
- root sparse: `727b555f731cee55cd6f261486f4259b8b59d18a090f46076f6f8e8935548d54`
- FIT: `02a4929826e013e212c6936b1b4f63c7b419bd3969ecda6b497e50cf62b58732`

Only obsolete downloaded r164 images were removed to make host disk space.
Their metadata/logs, the r165 rollback images and all U-Boot images remain.

## r166 candidate: register SCP logger before firmware startup

The audio handoff candidate passed cold ATF registration, but the single
SCP probe panicked Linux in `mtk_mbox_isr`, not in the earlier firmware
audio ASSERT. At kernel time 62.365983, the mailbox reported a missing
receive buffer for IPI 21 (LOGGER_CTRL); `BUG_ON` at mtk-mbox.c:561 followed.
The phone rebooted. Recovery boot `8eb5aae7-1ba1-4fc3-9838-fcd56b9f1a01`
has systemd running, zero failed units and USB/SSH available. No probe was
repeated. The first console panic was preserved as
`/private/tmp/tetris-bf75-panic.txt`, SHA256
`25b6fe64bd244e1185fb612143d73089359939a8bd3229925fe214e2daf4751d`.

Root cause of the AP panic: the external SCP module was compiled without
`CONFIG_MTK_TINYSYS_SCP_LOGGER_SUPPORT`, so no LOGGER_CTRL receive buffer
was registered. r166 enables that C feature only for SCP. This uses the
existing vendor logger initialization before `reset_scp(SCP_ALL_ENABLE)`;
it does not remove mailbox BUG checks, invent a dummy receiver, autoload SCP
or change watchdogs. Host tests verify both disabled/enabled feature-header
paths and the pre-reset initialization order. Package validation passes.
Full kernel/module/rootfs compilation remains CI-only. Sensors are Broken;
neither READY nor sensor data was captured in this test.
Commit `1bb4a3f96dce3529e66ab9ae6482238d662d7a5c` passed CI
`35719843739` and is now installed as recorded above. The recovery 32 MiB USB/SSH transfer passed at
`local/live-logs/20260922T110925Z-172.16.42.1-regression-gate`.

## SCP audio-memory fix built and installed; cold registration passes

Candidate U-Boot `bf75c572e16079a36ab43a032be3360c3e93250c` is on the
existing `codex/scp-handoff-inventory` branch. Diagnostic CI
`35718518185` passed with prepare/TCM/secure options enabled.
No new pmOS kernel/rootfs build is required for this boot-only candidate.

It adds the missing four-entry audio table, separate bank 5 registration
and stock EMI region 29. Memory is allocated by LMB and published as no-map;
there is no handset-specific physical address. Bounds, overlaps, duplicate
ownership and each secure-call failure are tested with ASan/UBSan. The
firmware/ATF hash gate and default-off diagnostic policy are unchanged.
This is not yet hardware-verified and has not been merged to master.
All artifact checksums and the commit manifest passed. LK image SHA256:
`7fd5bb218af3d3371dca59930f320ba98d38ddba6cbf7229851c33ba746d62fe`.
Flashed only `lk_a`; `lk_b`, installed r165, userdata and stock firmware
remain unchanged. Warm boot `784d3c79-2771-481c-99d5-0603a688971d`
reports systemd running and USB/SSH healthy. SCP remains disabled at the
expected warm `preflight` guard. The pre-flash 32 MiB transfer gate passed
at `local/live-logs/20260922T105717Z-172.16.42.1-regression-gate`.
Cold boot `614a39d4-2533-4686-87b4-f11263c2d155` passed preparation and
secure state 3/error 0; the allocator selected `0x9d000000`, size `0x9c0000`.
The one probe then exposed the logger panic recorded above. This proves
registration acceptance, not complete audio/SCP readiness or sensor support.
Post-flash transfer gate also passed at
`local/live-logs/20260922T110014Z-172.16.42.1-regression-gate`.
The user confirmed normal display and touch before the cold SCP test.

## r165 baseline passes; SCP dump identifies audio-memory assertion

CI `35707613091`, commit `395d7f63d9373372fbf6128503ea1f9b275f801c`,
completed successfully. Manifest identity and all image hashes passed before
writing only `super` and `userdata`. All 17 userdata chunks completed.
The existing diagnostic U-Boot `9177841177` in `lk_a` was retained;
`lk_b`, stock firmware and calibration partitions were not changed.
The generic artifact manifest references the older minimum U-Boot profile,
not the diagnostic bootloader actually used in this test.

Boot `c8110874-a77a-4381-a1f1-c18801d6f161` reports kernel #166, a 104.5 GiB
root filesystem, systemd running, USB/SSH up, and the `bootstrap_26m` module
parameter present. The user confirmed normal display and touch. The 32 MiB
USB/SSH regression gate passed at
`local/live-logs/20260922T103428Z-172.16.42.1-regression-gate`.

Cold boot `1e5a3f0d-cc0d-41d5-a358-6ec813d779f0` passed secure handoff.
One `modprobe scp bootstrap_26m=1` acquired the resource vote, but SCP hit
watchdog approximately 0.202 seconds later. The first complete dump identifies
core1 ASSERT in `drivers/RV55_A/mt6878/audio/utility/utility.c:149`:
`audio_get_common_shared_mem()` received AP address 0 and size 0.
The resource vote alone does not fix startup. Sensors remain **Broken**.
See `SCP_LOADER_TRACE.md` for dump identity and the separate audio-memory
registration path; adding a sensor-table entry is not yet a justified fix.

Recovered by clean reboot to `1c647422-1fca-4bcf-b7a7-6f4d7f3f6ed1`:
USB/SSH healthy, no SCP/sensorhub/HF modules, zero failed systemd units.
Warm-boot preflight guard disables SCP as expected. Verified r164 images and
known-good U-Boot rollback images remain available locally.

Artifact SHA256:

- boot: `89a1092b1e31bb158ed1b3eac447372dd7d3e58e38e58745b5d64ebc1c4faf4c`
- root sparse: `90c6976fef76c1b40c84cdbd74c1dc2a9e6363c8178b8ca9e43ace4eee279b15`
- FIT: `5d1e3e3f2d07948596b1fb2b1eccd79e37c3c2c9c7ea00397488ab8242baa504`

## r165 candidate: isolate the missing bootstrap resource vote

Patch 0102 adds the default-off, read-only `scp.bootstrap_26m` module
parameter. With SCP DVFS disabled, it requests the same `SCP_REQ_26M` vote
that the matching vendor init normally issues before SCP register access.
The diagnostic keeps the vote until module exit/reboot, deliberately avoiding
DVFS, voltage changes and oscillator calibration. It rejects simultaneous
DVFS ownership, propagates secure-call errors, and cleans up owned votes on
init failure and module exit. Failed release is reported as requiring reboot.
Normal boot and the default manual probe are unchanged.

Exact-source patch application, existing memory tests and the new UBSan
resource-ownership/error tests pass locally. Full ARM64 build is CI-only.
This is a **tested diagnostic, not a sensor fix**. Its accepted resource vote
did not prevent the audio-memory ASSERT, as recorded above.

Test plan: verify the r165 artifact, install it without replacing the pinned
U-Boot, obtain a full cold boot and successful secure handoff, then perform
one manual `modprobe scp bootstrap_26m=1`. Capture the first failure/dump and
readiness state. Success requires a real ready IPI followed by sensor samples,
not a successful module load. On watchdog, lost USB/SSH or secure-call error,
stop and cleanly reboot, without module reload. Retain r164 for rollback.
Holding this vote increases idle power and is not a suspend/power policy.

## SCP executes after secure handoff, but readiness fails

U-Boot `9177841177`, CI `35703856720`, is installed in `lk_a` with
kernel/rootfs r164 unchanged. LK SHA256:
`659f360ffd561e9959d26e7e855fc8c03298d17ef03eda335ff2a013dadfd96a`.
After a complete poweroff and manual power-on, boot
`84392df4-d857-48ed-b457-ae99ebdacacf` reported
`secure-handoff-prepared`, prepare error 0, secure state 3, secure error 0,
region-info `ok`, and the SCP node enabled with secure dump enabled.
All pinned boot-time secure calls completed. This does not prove runtime
recovery correctness or sensor operation.

One manual `modprobe scp` returned 0, but firmware watchdog recovery started
about 0.2 seconds later, before a confirmed ready event. First-failure PC/LR:
core0 `0x2e9da`/`0x1431a`; core1 `0x139f4`/`0x139ec`.
No sensorhub/HF manager was loaded and no sensor samples were obtained.
USB/SSH survived; the failure log was saved before a clean reboot.
Sensors remain **Broken**. See SCP_LOADER_TRACE.md for the bounded code trace.

Warm reboot retains TCM contents: the strict preflight rejects that state
with `-16` and leaves the Linux SCP node disabled. Cold boot was required
for the successful secure handoff. Warm-start ownership remains unresolved;
do not remove the guard or advertise this diagnostic as production support.

## Earlier decryption and TCM hardware checks

U-Boot `8066a9a1ee`, diagnostic CI `35701102610`, was flashed to `lk_a`
only after manifest/checksum validation. LK image SHA256:
`691164969062e9728178de4a8da7c9e7ee48b5185908def7e1f1bb150596a22d`.
The installed kernel/rootfs remain r164; `lk_b`, firmware and calibration
partitions were not modified. Previous `ba0a2763ef` image is retained for
rollback, not assumed to match the unrelated stock image in `lk_b`.

Boot `ccf7199a-cd40-401b-a0c8-90e8f7b3018d` reports
`nothing,scp-prepare-stage=plaintext-verified`, error 0 and plaintext
region-info size 60. Both core and DRAM passed certificate, ciphertext and
post-ATF-decryption plaintext hash checks. The diagnostic pins the actual
slot-A ATF/SCP version and reads DT/LMB reservations; it is not a universal
firmware selector. No TCM writes or SCP reset release occurred in this build.
Systemd is running, no SCP/BUG/Oops/call-trace/panic lines appeared in the
checked kernel log, and the 32 MiB USB/SSH regression gate passed:
`local/live-logs/20260922T080034Z-172.16.42.1-regression-gate`.

The user confirmed normal display/touch after this decryption build.

The TCM follow-up `d965233d2f`, CI `35702796137`, was then verified and
flashed to `lk_a` only. SHA256:
`5d12bbe40474a362459fe8e93ecc1133e86fb6c6996a8bff23323943dec60530`.
Boot `7249e562-fff9-4cb8-bd1c-32c492064ae2` reports
`tcm-verified-reset-held`, error zero, region-info `ok`, size 60. The full
8192-byte loader readback matched. `/soc@0/remoteproc@1c400000/status` is
`disabled` and no SCP/transport module is loaded. The 32 MiB USB/SSH gate
passed at `local/live-logs/20260922T081548Z-172.16.42.1-regression-gate`.
The earlier TCM CI `35702366933` failed on a callback/macro name collision;
that image was never flashed. The fixed build also corrects the FDT physical
address conversion warning.

These intermediate checks preceded the full secure-handoff test above.
Do not confuse firmware decrypt or TCM readback with sensor functionality.

## Clean r164 installed: baseline regression passes

CI `35692283994`, commit `68516ccf406f7ed8c3ac2ee276c10b0e04d25e4d`,
completed successfully. Manifest identity and all three image SHA256 values
passed before flashing. Only `super` and `userdata` were replaced; existing
U-Boot `ba0a2763ef`, firmware and calibration partitions were not written.
The previous r163 audit passed at `20260922T071751Z`.

Both fastboot writes succeeded (17 userdata chunks). Reboot returned the
known USB disconnect; Linux and SSH subsequently recovered. Current boot
`b8eddccf-112e-40a9-942e-13c67fc8b23c` reports kernel #165,
`linux-postmarketos-mediatek-mt6878-7.2.1-r164`, device `8-r16` and a
104.5 GiB root filesystem. The user confirmed normal display and touch.
The regression gate, including a 32 MiB USB/SSH transfer, passed at
`local/live-logs/20260922T072618Z-172.16.42.1-regression-gate`.
USB, wlan0 and hci0 are present; this is not a Wi-Fi association or Bluetooth
pairing test. Systemd reports `running`; no Oops, BUG, call trace or kernel
panic appeared in the checked logs.

SCP, sensorhub and HF manager were not loaded. Region-info remains `zero`,
size 0. Patch 0101 is packaged, but its valid-handoff recovery path has not
run on hardware. Sensors remain Broken pending authenticated SCP loading
and a valid TCM handoff. No SCP reset, module probe or reload was attempted.

Artifact SHA256:

- boot: `d2fdcc11c67922674c2f159d258553bd48abcb2e9405aaceb26aed7db300d477`
- root sparse: `c4f90389f1d3736e465fc6cd9be8f4e8f5a8376b3f73964b6601813047d794fb`
- FIT: `a39888049e02e09a03ada67aabc73c146bd8f9fb37ae0a7a8dce9b0dc01ecc04`

## Clean r163: first SCP error-cleanup test passes

CI `35633921256`, commit `437e9998ccb94717969240b8ff1a76cd2d4f411b`,
passed manifest and SHA256 verification. Only `super` and `userdata` were
clean-flashed; U-Boot remains `ba0a2763ef`, with LK, firmware and calibration
partitions unchanged. Boot `50a3889c-1971-4920-8fdb-90ed310684e8` reports
kernel #164, package `7.2.1-r163` and device `8-r16`.

The hardware-frontier baseline passed at `20260921T203338Z`; the user
confirmed normal display and touch. One manual SCP probe still rejects
`region-info too small: 0 < 56` with `-71`, but now modprobe exits 1 with
`Protocol error`, not SIGSEGV. SCP is absent from the post-probe module list;
USB stays up and the boot ID is unchanged. No Oops, BUG, call trace or kernel
panic was found in the captured probe log. Transport modules were not reloaded.
This is one successful cleanup test, not SCP startup or sensor functionality.
The post-probe 32 MiB USB/SSH transfer gate passed at `20260921T203510Z`.
A normal reboot after the test also passed the hardware-frontier baseline at
`20260921T203642Z`; the phone is left in that clean boot, not the probe session.

Artifact SHA256:

- boot: `7a6715e794878b5c6e47ac7b24d5edf66821d058e01ee71d18452fac20af3bce`
- root sparse: `7aec76804ff20164b03825acf3e14c0edc7c93b2237b5e4213924c4b6a5574ab`
- FIT: `76142ba99ab07867d127ebf31188fac33bf3b658cd7c40d4290c5e60b9dc751e`

Probe evidence: `/private/tmp/tetris-r163-scp-probe.txt`. Authenticated SCP
firmware loading and the TCM region-info handoff remain the next blockers.

## Clean r162 test: SCP cleanup still fails

CI `35605918332` (`f1c657c21417688937b6c467e608d10e451e67f7`)
passed artifact/hash verification and was clean-flashed to `super` and
`userdata` with user authorization to discard the test system. LK and all
firmware/calibration partitions were unchanged. Boot
`e419ca4f-266c-44bb-8b8e-e5aae562d216` reports kernel #163, package
`7.2.1-r162`, device `8-r16`. Hardware-frontier baseline and 32 MiB USB/SSH
transfer passed; the user confirmed normal display/touch. The full SCP memory
region remains reserved.

One manual SCP probe rejected empty region-info, then Oopsed again in
`kfree -> scp_device_remove`; modprobe returned 139. USB/SSH transfer still
passed, but that does NOT mean the SCP cleanup or kernel-health test passed.
No module unload/retry was attempted. A normal reboot was requested; the first
SSH checks timed out despite Linux USB enumeration. SSH subsequently recovered
on new boot `47b4b160-6a65-4450-a020-65cbdb3b59f1`, with no SCP/transport
modules loaded and systemd reporting `running`.
The post-recovery hardware-frontier baseline passed at `20260921T174516Z`.

Root cause: patch `0100` was declared and checksummed in APKBUILD but never
applied by `prepare()`. r163 adds the missing application, plus an overlay
validation guard requiring every declared vendor patch to be explicitly applied
exactly once. Five guard tests pass; the original r162 APKBUILD fails this guard
on `0100`. The full overlay validation passes after correction. Runtime validation
of the corrected artifact remains pending; sensors remain Broken. Commit
`437e999` is building in CI `35633921256`; no local kernel build was run.

Evidence: local logs `20260921T173751Z` (frontier), `20260921T173842Z`
(pre-probe transfer), `20260921T174010Z` (post-Oops transfer); probe log
`/private/tmp/tetris-r162-scp-probe.txt` and pre-probe memory inventory
`/private/tmp/tetris-r162-scp-before.txt`.

## Live U-Boot SCP boundary

**Memory collision fixed on-device:** U-Boot `ba0a2763ef` (CI `35611810150`)
now imports DT firmware reservations before allocating the initrd. After
flashing only lk_a, boot `a081e530-e467-4cea-8c49-2d89d97da9cf` moved the
initrd from inside SCP to `0xb746a000..0xb7fffe38`; the complete
`0xb8000000..0xba2fffff` SCP region is now reserved. USB/SSH recovered.
The new read-only CRC-checked boot-control observer reports recorded `scp_a`.
Fastboot's existing constant `current-slot=a` is not independent slot proof.
SCP startup and sensor samples are still missing; do not mark sensors Works.

The same memory placement survived two further warm reboots. USB/SSH regression
checks passed on all three boots, including 32 MiB transfers on the first and
third; the user confirmed normal display and touch. The isolated bootm fix is
published on U-Boot `master` as `e8cee3eaa6` (CI `35613343412` pending).
Experimental SCP observers and crypto transport are not included in that commit.
Cold-power, suspend/resume and second-device validation remain outstanding.

Implementation update: U-Boot `2a693ef204` adds the experimental C secure
decryption transport. Host sanitizer tests and CI ARM64 object compilation
pass. It remains default-off and uncalled; board integration, authenticated
metadata, memory ownership, TCM preparation and SCP startup are still missing.
Sensors remain **Broken**, not fixed by the existence of this transport.

Offline security follow-up: U-Boot `0748fe7afc` adds an eight-test verifier
for SCP certificate chains and ciphertext hashes. Both components from the
active-slot dump pass consistency verification. Secure AES backend selection
is now traced against the installed ATF, but runtime loading and actual sensor
samples remain unavailable. This is not a new working sensor image. Details:
[SCP_LOADER_TRACE.md](SCP_LOADER_TRACE.md).

Update: U-Boot `0d71414af7` from successful CI `35606234615` fixes the
incorrect block-device descriptor lookup in the container observer. After
flashing only `lk_a`, both `nothing,scp_a-container-status` and
`nothing,scp_b-container-status` report `ok`, with size `0xa43070` on boot
`f628eee9-5439-4913-bdcd-adf50c958b38`. The transfer regression gate passed
at `20260921T133626Z`. SCP region-info remains zero and sensors remain
Broken. See [SCP_LOADER_TRACE.md](SCP_LOADER_TRACE.md) for the reproduced
storage fix and exact stock-loader call chain; secure loading is not yet
implemented.

U-Boot commit `9c93aa3f24b46443a01b1514440e2146706c844e` from CI run
`35602069118` was flashed only to `lk_a`; `lk_b` remains the previous rollback
image. Linux boot ID `26fe2a00-696b-43d0-aff5-bc042501912f` came up with
`usb0` and SSH, and both the hardware-frontier and exact 32 MiB transfer gates
passed. The read-only pre-Linux observation published
`nothing,scp-region-info-status = "zero"` and size zero. This proves the SCP
handoff is already absent before Linux loads `scp.ko`; the kernel DT validator
is not erasing it.

Read-only Linux inspection then confirmed 16 MiB `scp_a` and `scp_b`
partitions. Both start with a valid MediaTek container header named
`tinysys-scp-RV55_A`; their full SHA-256 values differ. The active `scp_a`
container has six bounded sections in this order: SCP payload, `cert1`,
`cert2`, SCP DRAM payload, `cert1`, `cert2`, ending at `0xa43070`. No payload
or certificate was committed to the repository. U-Boot commit `366f8ab913`
adds a read-only, host-tested parser and UFS header observer for both slots.
CI run `35604799868` passed and published artifact `10641192508` with digest
`7915cc7accabb0799f986b86904945c94b295a50753b1db8e862d5ae7d99be0c`;
the verified `u-boot-tetris-lk.img` SHA-256 is
`2f4c7fecac986a07f75cd57f6cec1972bef8bdff4afdec834cbb9a90690aa45a`.
It was flashed only to `lk_a` and booted Linux as boot ID
`bca2a305-20e1-407c-bb7e-838cc2479eb4`. The hardware-frontier and exact
32 MiB transfer regression gates passed at `20260921T132741Z` and
`20260921T132814Z`. Region-info remains correctly reported as zero, but the
new container properties are absent, so the board-stage UFS observer needs an
explicit storage/partition/read failure status before it can be considered
live-proven. It does not authenticate, decrypt, copy or start SCP, so sensors
remain `Broken` rather than being overstated as working.

## Clean r161 SCP handoff result

CI run `35590748657` for commit `4c84c11b6b57ca1d38c0400e620662fb3a8901a2`
completed successfully. Its artifact `10637188685`, digest
`20325d9c5383f633672131478596cfbed67609d49e53be75da5b44111c7ce800`,
passed `verify-ci-install-artifacts.sh` and was clean-flashed to `super` and
`userdata`; no LK, modem, NV or calibration partition was changed. The phone
booted `6.18.0 #162` with `device-nothing-tetris-8-r16` and kernel package
`7.2.1-r161`; `usb0` and SSH returned on boot ID
`bfd63396-f3b4-4d7b-8a8a-cf48544891c8`.

Manual loading of `mtk-mbox`, `mtk_rpmsg_mbox` and `mtk_tinysys_ipi` passed
with `usb0` still up. Loading `scp` reached the new handoff validator and
reported `region-info too small: 0 < 56`, proving that the current U-Boot does
not publish the expected SCP TCM handoff. The ensuing probe-error cleanup then
hit a separate allocator mismatch: three tables created by `vzalloc` were
released with `kfree`, producing an Oops in `scp_device_remove`. Patch `0100`
changes those releases to `vfree`. Sensorhub was not loaded and no sensor
functionality is claimed. The next runtime prerequisite is an authenticated
active-slot SCP firmware/region-info handoff in U-Boot, followed by the same
manual fail-closed probe on a clean build.

## Latest clean next-SCP installation

r16 is the latest clean-flashed unified image. CI run `35577386901` for
commit `67da4fd057569637d0d3f28dea748a8b4725b32b` completed successfully and
published `nothing-tetris-images` artifact `10631878514` with digest
`fe1aefba03cea31df4b5aaffd67d63b4ab55dec1f3b5d6c75e4b0f38b9d8e40d`.
`scripts/verify-ci-install-artifacts.sh` passed before flashing. Only `super`
and `userdata` were written on slot `a`; LK, trusted firmware, modem/NV and
calibration partitions were not changed. The manifest requires U-Boot
`60bcf22fdc0a94526424db59fc7640298ea8f0dd` and reports kernel `6.18.0`.

The clean image booted kernel
`Linux nothing-tetris 6.18.0 #159-postmarketos-mediatek-mt6878` with
`device-nothing-tetris-8-r16` and
`linux-postmarketos-mediatek-mt6878-7.2.1-r158`. USB NCM appeared as `usb0`,
Wi-Fi associated automatically, Bluetooth exposed `hci0`, no systemd units
failed, and the exact 32 MiB SSH transfer passed. DSI is
`connected`/`enabled` at `1080x2400`, `fb0/blank=0`, touch is `fts_ts` on
`event0`, and the packaged greeter display gate passed. The user confirmed
that the phone booted and the display remained visually correct. Evidence is
in `local/live-logs/20260921T100513Z-172.16.42.1-regression-gate`,
`local/live-logs/20260921T100518Z-172.16.42.1-hardware-frontier` and
`local/live-logs/20260921T100548Z-172.16.42.1-greeter-display-gate`.

The same clean r16 frontier confirms the remaining boundary: only DRM
`card0` exists with no render node, ModemManager reports no modem, no user
sensor IIO devices are exposed, and no camera/media nodes exist. GNSS remains
manual and inactive on this baseline. No diagnostic hardware module was
loaded during this audit.

## Previous next-SCP installations

r15 is the latest clean-flashed next-SCP image. CI run `34775951132` for commit
`63d2b3917f83066ab75d836b56ffd7d9d7496832` completed successfully and
published `nothing-tetris-images` artifact `10324214249`; the downloaded ZIP
SHA256 matched GitHub's artifact digest
`3f99b720d49754d0fdb8c8e79d79c04681cb591329bb201221657a8bfe9015e2`.
`scripts/verify-ci-install-artifacts.sh` passed for `boot_image.itb`,
`nothing-tetris-boot.img` and `nothing-tetris-root.sparse.img`; the manifest
reports kernel `6.18.0`, required U-Boot
`60bcf22fdc0a94526424db59fc7640298ea8f0dd`, and fastboot mapping
`nothing-tetris-boot.img -> super`, `nothing-tetris-root.sparse.img ->
userdata`.

The phone was visible as `tetris-uboot` fastboot on slot `a`; `super` and
`userdata` were clean-flashed from the verified r15 artifact. `fastboot reboot`
returned the usual USB status-read error, but the phone booted kernel
`Linux nothing-tetris 6.18.0 #159-postmarketos-mediatek-mt6878` with
`device-nothing-tetris-8-r15`, restored USB NCM/SSH on `172.16.42.1`, reported
zero failed systemd units and automatically ran
`nothing-tetris-display-unblank.service`. The first clean r15 boot had
`fb0/blank=0`, DSI `connected`/`enabled`, mode `1080x2400`, touch as
`fts_ts` on `/dev/input/event0`, gpio keys and RT6010 haptics present. The
transfer regression gate passed at
`local/live-logs/20260914T043830Z-172.16.42.1-regression-gate`; the greeter
display gate passed at
`local/live-logs/20260914T043826Z-172.16.42.1-greeter-display-gate`; the
hardware frontier gate passed at
`local/live-logs/20260914T043830Z-172.16.42.1-hardware-frontier`.

The r15 live frontier still shows the remaining non-display boundary plainly:
ModemManager reports no modem, no `/dev/wwan*`, `/dev/cdc-wdm*` or `/dev/ccci*`
nodes exist, IIO exposes only PMIC ADC devices
`mt6369-auxadc.3.auto`, `mt6375-auxadc` and `mt6375-adc`, no user accel/gyro/
proximity/light sensor nodes exist, no camera/media/v4l-subdev nodes exist, and
GPU still exposes only `/dev/dri/card0` without a render node. These remain
separate subsystem gates.

The GNSS readonly gate also passed on the same clean r15 boot at
`../gnss-userspace-next/local/live-logs/20260914T043950Z-172.16.42.1-gnss-gate`.
Baseline reported `usb0` UP, zero failed units, connectivity active, GNSS
transport inactive, no GPS module and no modem runtime. The gate started the
manual transport, loaded `gps_drv_dl_v051`, ran the packaged readonly link0
diagnostic with `status=0`, `code_size=42505`, `fragment_count=106`,
`boot_time_ns=178477714548`, `arch_counter=2453158179` and
`cipher_key=redacted`, left no gpsdl owner, kept modem/CCCI/DPMAIF absent and
completed the final 32 MiB USB transfer with exactly `33554432` bytes. This is
repeatable GNSS transport/read-only evidence, not end-user GPS.

r13 was the previous clean-flashed next-SCP image. CI run `34752524434` for commit
`dcaa75d3bdd87606776d64b5e9509ade9ec350d7` completed successfully and
published `nothing-tetris-images` artifact `10316991883`; the downloaded ZIP
SHA256 matched GitHub's artifact digest
`7017cc873d8f7b721407441dd41ff7b207638a938e70e2001162c9c9226ab637`.
`scripts/verify-ci-install-artifacts.sh` passed for `boot_image.itb`,
`nothing-tetris-boot.img` and `nothing-tetris-root.sparse.img`; the manifest
reports kernel `6.18.0`, required U-Boot
`60bcf22fdc0a94526424db59fc7640298ea8f0dd`, and fastboot mapping
`nothing-tetris-boot.img -> super`, `nothing-tetris-root.sparse.img ->
userdata`.

The phone was visible as `tetris-uboot` fastboot on slot `a`; `super` and
`userdata` were clean-flashed from the verified r13 artifact. `fastboot reboot`
returned the usual USB status-read error, but the phone booted kernel
`Linux nothing-tetris 6.18.0 #159-postmarketos-mediatek-mt6878` with
`device-nothing-tetris-8-r13`, restored USB NCM/SSH on `172.16.42.1`, reported
zero failed systemd units and passed the transfer regression gate at
`local/live-logs/20260913T153822Z-172.16.42.1-regression-gate`.

r13 packages the live-proven greeter idle settings, but the first clean boot
still reached `fb0/blank=4` while DSI stayed `connected`/`enabled` and backlight
brightness stayed `1024`. A reversible live write of `0` to
`/sys/class/graphics/fb0/blank` changed the state to `0` without USB loss; the
greeter-display gate then passed at
`local/live-logs/20260913T154120Z-172.16.42.1-greeter-display-gate`, and the
hardware frontier gate passed at
`local/live-logs/20260913T154426Z-172.16.42.1-hardware-frontier`.

Device candidate r14 kept the same runtime hardware boundary as r13, applied
the greeter idle policy from the greetd session wrapper, and added a small
system service intended to safely unblank `fb0` after `greetd.service`. CI run
`34766698142` for commit `b8bfbdefcc8d904fbe8292a319498d9f66504747` passed and
published `nothing-tetris-images` artifact `10321339423`; the downloaded ZIP
SHA256 matched GitHub's digest
`60c1c792cd1110f92af2d6fb9fd124afb860a3e4d39b800d275d0dc29ee2d8db`.
`scripts/verify-ci-install-artifacts.sh` passed for the extracted boot, super
and userdata images. The phone was flashed from the verified r14 artifact,
booted kernel `6.18.0 #159-postmarketos-mediatek-mt6878` with
`device-nothing-tetris-8-r14`, restored USB NCM/SSH and passed the transfer
regression gate at
`local/live-logs/20260913T184902Z-172.16.42.1-regression-gate`.

The first r14 boot still left `fb0/blank=4`: systemd skipped
`nothing-tetris-display-unblank.service` because its
`ConditionPathExists=/sys/class/graphics/fb0/blank` was evaluated before fb0
appeared. A later manual start of the same installed service changed
`fb0/blank` from `4` to `0` and exited successfully, proving the helper is
correct but the unit condition is too early. Device candidate r15 removes that
condition and relies on the helper's existing bounded wait for the writable
fb0 node. r15 is the first clean next-SCP install where this automatic unblank
gate passed without a manual service start.

Clean-installed `codex/hardware-integration-next-scp` CI artifact
`10297439743` from run `34692383850` and commit
`3a016d36153d504f6b1002d29120bd84a8183533` on 2026-09-12. The image ZIP
SHA256 is
`a97f7dd37950e92279a27168fcdf667b607baec91cc00c34194865fccb86bf71`; local
artifact verification passed for `boot_image.itb`, `nothing-tetris-boot.img`
and `nothing-tetris-root.sparse.img`. The manifest reports kernel `6.18.0`,
required U-Boot `60bcf22fdc0a94526424db59fc7640298ea8f0dd`, and fastboot
mapping `nothing-tetris-boot.img -> super`, `nothing-tetris-root.sparse.img ->
userdata`.

The phone was in `tetris-uboot` fastboot on slot `a`; `super` and `userdata`
were flashed from the verified artifact. After reboot, USB NCM returned as
`usb0` at `172.16.42.1`, SSH answered, boot ID
`d597ba7f-f3f5-437b-bd0e-58a350ae7f3e`, kernel
`Linux nothing-tetris 6.18.0 #157-postmarketos-mediatek-mt6878`, installed
packages `device-nothing-tetris-8-r10` and
`linux-postmarketos-mediatek-mt6878-6.18-r156`, and zero failed systemd units.
`scripts/check-live-regression-gate.sh 172.16.42.1 user 147147 transfer`
passed and saved
`local/live-logs/20260912T170559Z-172.16.42.1-regression-gate`; the full audit
is in `local/live-logs/20260912T170639Z-172.16.42.1-audit`.

The user visually confirmed good display output on this clean image. A direct
live node check shows touch as `fts_ts` on `/dev/input/event0`, keys and RT6010
haptics in `/proc/bus/input/devices`, Wi-Fi as `wlan0`, powered BlueZ `hci0`,
and USB Type-C/gauge telemetry. It also shows the next remaining blockers
plainly: IIO contains only PMIC ADC devices, not accel/gyro/proximity/light;
`/dev/dri` has `card0` only and no render node; no `/dev/video*` or
`/dev/media*` camera nodes exist; ModemManager reports no modem. Wi-Fi is
present but not associated on this audit, and package index refresh produced
transient DNS errors, so routed Wi-Fi/DNS is not confirmed on this clean image.

One explicit manual GNSS transport start was then run on the same clean boot,
with the module not previously loaded. `nothing-tetris-gnss-transport.service`
loaded `gps_drv_dl_v051`, created `/dev/gps_emi`, `/dev/gpsdl0` and
`/dev/gpsdl1`, and exited successfully with zero failed units. The kernel
reported the LK GPS EMI handoff as `0x86a00000/0x100000`. The read-only
diagnostic with `--probe-link0` returned `status=0`, `code_size=42505`,
`fragment_count=106`, `boot_time_ns=570266810187` and
`arch_counter=7545944623`, redacted the cipher key, left no `/dev/gpsdl*`
owners and preserved `usb0`. This confirms clean next-SCP GNSS transport and
read-only boot-info access only; it is still not NMEA, GeoClue, satellite
acquisition or a position fix.

A later host check while the user reported fastboot found no fastboot device;
the handset still exposed USB NCM on `en4`, but the last SSH password probe
was rejected and fastboot continued waiting for a device. The baseline
regression gate from the earlier controlled SSH session passed at
`local/live-logs/20260912T175322Z-172.16.42.1-regression-gate`, and a full
audit at `local/live-logs/20260912T175403Z-172.16.42.1-audit` still showed
`device-nothing-tetris-8-r10`, kernel package `6.18-r156`, no failed units,
`/dev/dri/card0` only, no camera/media/modem nodes, GNSS transport
`active (exited)`, `/dev/gps_emi`, `/dev/gpsdl0` and `/dev/gpsdl1` present, no
`/dev/gpsdl*` owners, and no CCCI/DPMAIF/modem modules. Do not repeat GNSS
module load/unload on this boot; reboot before the next GNSS protocol or
navigation experiment.

`scripts/check-live-hardware-frontier-gate.sh` is prepared for the next clean
install. In baseline mode it preserves the hard regression checks for USB,
display, touch, Wi-Fi and Bluetooth while explicitly failing if GPU render,
modem, camera or user sensor nodes appear without a subsystem-specific gate.
This keeps GPS/GSM/sensor/camera/GPU promotion tied to evidence rather than to
accidental module packaging. The same read-only gate passed on the current r10
install at `local/live-logs/20260912T191835Z-172.16.42.1-hardware-frontier`:
USB/display/touch/Wi-Fi-device/Bluetooth-device stayed present, while GPU
render, ModemManager modem, camera/media and user sensor IIO nodes remained
absent.

## Latest GPS reliability result

Kernel package r155 from pmaports commit
97ffa53915955c26e2181f32c7688e8cd277d338 is now clean-installed from CI
34589225716 on the test handset. The downloaded image artifact digest is
57937ae30cfb2c5f762016838d66cbaab28ba2c711dae9525dbeeaaef2e33f4f; extracted
files match SHA256SUMS: boot_image.itb
bc3206f6e6207e06759f86ce6191067478ad5da420b43bfaa6a5e3df1dbbe859,
super image 3a2c6902143d4994ff77878ba247414a27343799280cf1dfa5ce2f23ada8c29c,
root sparse 866fbfc868ac428d8e8d74ae2cca3e154fa3e3a8d0e832dccaac348138c2f7cf.
The rootfs contains device-nothing-tetris 8-r9 and
linux-postmarketos-mediatek-mt6878 6.18-r155. A later live baseline on boot
d9d69266-fb08-464f-a7d7-fb7b2fdf1a7a still had `usb0` UP, zero failed
systemd units and a passing 32 MiB USB/SSH regression gate at
20260912T100523Z. APK index refreshes reported transient DNS failures on
that clean configuration, so routed Wi-Fi/DNS is not currently confirmed on
the live handset.

Three fresh boots passed the unchanged supervised GNSS BINFO/download/stop
cycle with no repeated module load on a single boot:
9ab1397d-748d-460f-930e-fe15d6a1789c,
bbba0f14-74d2-4231-b8f1-71c18d7e41dc and
d9d69266-fb08-464f-a7d7-fb7b2fdf1a7a. Each run started with no GPS module or
gpsdl node, loaded gps_drv_dl_v051 once, completed DOWNLOAD_COMPLETE,
STOP_WRITTEN, CLOSED and exited zero. The kernel published the complete
OFF -> ON -> RST -> WORK -> RST -> OFF FSM sequence without the previous
post-stop observation timeout. The last two boots had no matching forced
A-die off, connsys reset, GNSS error, Oops, BUG or panic; the first boot had
one early `emi_mng_get_gps_emi failed to find gps node` warning before the
successful cycle. No gpsdl owner remained after any run, failed units were
zero on the final boot, and the 32 MiB USB stream matched
83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302 after
each run.

This promotes the r155 GNSS transport/download/shutdown reliability gate, not
end-user GPS. There is still no NMEA stream, GeoClue/gpsd integration,
satellite acquisition, timed position fix, autostart service or suspend/resume
result. The CI manifest still declares required U-Boot 60bcf22, while the
test handset deliberately kept installed U-Boot c931695 to preserve the
known-good boot baseline; that bootchain compatibility boundary remains open.

The earlier display promotion candidate at
63a21acc0dcd6139af02e2c8294010571331e0dc fixed the greetd dconf ownership
mismatch by depending on `greetd` before the device package runs and resolving
the packaged `greetd` UID/GID at install time instead of baking one
builder-local numeric owner. That ownership repair is preserved in the current
r12/r13/r14 device package line. r13 proved the base image boots with the
packaged idle policy, but also proved that a separate boot-time framebuffer
unblank is required. r14 adds that unblank service and runs the idle policy
inside the greetd session wrapper before Phoc/Phrog starts.

## Modem and sensor prerequisites

Fresh pre-install live audit `local/live-logs/20260912T122321Z-172.16.42.1-audit`
on boot d9d69266-fb08-464f-a7d7-fb7b2fdf1a7a still reports
device-nothing-tetris 8-r9 and linux-postmarketos-mediatek-mt6878 6.18-r155
running kernel build #156, zero failed systemd units, USB NCM up at
172.16.42.1, wlan0 present but disconnected, Bluetooth powered, the GNSS v051
module already loaded, `/dev/dri/card0` only, no ModemManager modem, no
camera/media nodes and no sensor IIO devices beyond the existing PMIC ADC path.
PipeWire currently exposes no hardware sink/source, and the connected USB-C
source still reports 5 V with current_max=0 so the charger remains on the
conservative 500 mA fallback. This is the baseline for the next CI clean-install
candidate, not a new functional claim.

The modem producer audit, read-only C partition/member locator and bounded
stock-LK kernel-chain feasibility audit are now integrated on
`codex/hardware-integration-next-scp` through ccef88b. Exact B4.1 LK selects
the modem platform table, then the active slot suffix; the md1img table is a
bypassed fallback. Real B4.1 `modem.img` container validation finds md1rom,
md1dsp and md1drdi with unchanged-input ASan/UBSan coverage. The bootchain
audit passes two LK input hashes, 11 bounded instruction windows, 15
instruction checks and negative mutations. U-Boot CCCI diagnostic branch
codex/ccci-prev-fdt-diagnostic at 1b8c954dba accepts the stock 48-byte v3
descriptor only when the 16-byte extension tail is zero; CI 34686210064
passed and the downloaded LK artifact's SHA256SUMS verified locally. This
removes one handoff parser mismatch and records stock LK feasibility limits,
but no authentication backend, modem memory/reset ownership, DT runtime,
CCCI/DPMAIF module, SIM or network functionality is implemented.

The SCP DRAM recovery-span prerequisite is packaged on
`codex/hardware-integration-next-scp`: `0094` validates the complete four-bank
rounded recovery mapping before SCP setup. Its exact-source host gate
reproduced the previous defect (18 DRAM cases, 10 failures) and the candidate
passed all 18 cases under UBSan. The branch also carries the demoted
host-side sensor-list candidate in `patches/sensors/`, which changes the
reply correlation guard from all-fields-differ to any-field-differs. The
pinned-source gate passed:
the original source reproduced six false accepts, the packaged candidate
rejects all mismatches across eight combinations, all 65536 sequence pairs
including 255/0, and both single-operator mutations. After the r11 clean-boot
regression it is not packaged as `1201`; SCP, DVFS and sensorhub remain
disabled, and no sensor sample or IIO publication is claimed.

CI 34692383850 for `codex/hardware-integration-next-scp`
3a016d36153d504f6b1002d29120bd84a8183533 completed successfully and published
`nothing-tetris-images` artifact 10297439743. The downloaded ZIP SHA256 is
a97f7dd37950e92279a27168fcdf667b607baec91cc00c34194865fccb86bf71.
`scripts/verify-ci-install-artifacts.sh` verified the extracted artifact
against the expected GitHub SHA: `boot_image.itb`, `nothing-tetris-boot.img`
and `nothing-tetris-root.sparse.img` all match SHA256SUMS; the manifest reports
kernel `6.18.0`, required U-Boot
60bcf22fdc0a94526424db59fc7640298ea8f0dd, and fastboot mapping
`nothing-tetris-boot.img -> super`, `nothing-tetris-root.sparse.img ->
userdata`. Sizes are boot 536870912, root sparse 2114363112 and FIT 26578735
bytes. This passes the CI artifact gate for a future clean flash, not the
runtime gate: SCP, DVFS, sensorhub and phone-side regression checks remain
unproven.

The same run published `nothing-tetris-radio-live` artifact 10299131075. The
downloaded ZIP SHA256 is
ca99ac7a545805b108ae2f6469986fd0c58cdedf8cc5f57a80313092a9e3353a.
`scripts/verify-radio-live-artifact.sh` verified the payload SHA256
52b64cb76040de8a649367704e9d6bd0e0d33b6db0c58d395a554141260bb6b1, manifest
GitHub SHA, kernel `6.18.0`, connectivity source
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835, device-modules source
ee2be53cb75670b548948636a0db1d1ff112bf12 and required U-Boot 60bcf22. The
payload has 24 entries and is intentionally limited to Wi-Fi, Bluetooth and
GNSS transport files; the verifier rejects modem, CCCI, DPMAIF, WWAN and
navigation userspace entries. This keeps the next-scp candidate's live radio
bundle bounded while SCP, DVFS and sensorhub remain disabled.

Sensor reply candidate 67b481d on codex/sensor-startup-contract first proved
the same wrong-sequence/type/command defect offline. The packaged next-SCP
variant above supersedes that standalone candidate for integration tracking.
This is not a sensor startup fix: SCP loader/DVFS, firmware/calibration
ownership and samples are still unproven. Camera capture remains unproven.

Camera/GNSS prereq branch codex/camera-clk-prereq-v2 is published through
594dd75. It records the B4.1 GNSS startup/frame-sync/NMEA boundary and a
host-tested IMX882 active-low reset prerequisite. The reset test proves the
patched future identity probe keeps GPIO25 physically low while rails settle
and during shutdown, and rejects the unmodified inverted baseline. CI
34687402501 now runs this gate in validate-overlay and passed it. No camera
node, sensor power-on, I2C transaction, SENINF/ISP or media pipeline is
enabled.

GPU/Panthor prereq branch codex/panthor-compile-prereq is published through
8e9fbbb. The VGPU readback gate executes the vendor and mainline voltage
callbacks with read-only fake regmap access and proves the source mismatch:
vendor reads enabled VBUCK2 from DBG0 while mainline reads ELR2. CI
34687330355 now runs this gate in validate-overlay and passed it. The broader
Panthor compile-only gate could not be rerun locally because the prepared
kernel tree resides under a path with spaces that Linux Kbuild rejects; the
new CI image build is still running. No GPU runtime
node, rail consumer, firmware, render node or acceleration is claimed.

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
`codex/display-main-promotion` at `63a21acc0dcd6139af02e2c8294010571331e0dc`,
based on primary branch `main` at `ee994e4236d69c9f3eb18e81614dd0dff9e60266`.
It carries the display dependency series and fixes 0096/0097, with kernel
6.18-r155 and device 8-r13. It is not the installed full-integration r155
image and does not include the later unrelated hardware experiments.
All 72 kernel patches apply in package order; source/checksum, route and
rootfs greeter-owner tests pass. CI 34689206699 has passed overlay checks and
is building install images. They are not yet installed. Main has not moved.
Clean-install/regression and lifecycle
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
`patches/native-display/` and is published in codex/hardware-integration
commit 5d86361. Eight host configurations and a negative mutation pass; its
translation unit compiles for ARM64 against the prepared 6.18 diagnostic tree.
It adds MT6878-specific interrupt masking, shadow bypass and relay
configuration, preserving generic behavior. It is not packaged or enabled.
CRTC currently interleaves config/start, so activation also requires a reviewed
configure-before-start order, DT/clock/mutex/routing integration and
stopped-path live evidence. See the candidate README.

Candidate 0002 now supplies the MT6878-only configure-all-before-start
callback order. Reconstructed APKBUILD-order source passes 24 host traces,
a negative interleaving mutation and ARM64 object compilation with local
patched headers. It remains unreferenced; inherited engine quiescence,
POSTMASK DT/routing/clock ownership and live lifecycle are not proven by
the callback order test. Candidate 0003 adds the host-checked POSTMASK
topology and rejects the incorrect PQ route mutation across 768 route-state
comparisons. CI 34687864782 runs the DRM sequence unit test plus all three
native-display prereq gates in validate-overlay and passed them. Installed
r153 is unchanged.

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
Before any future clean flash, run
`scripts/verify-ci-install-artifacts.sh` against the downloaded GitHub Actions
artifact directory and pass the expected `github_sha`. The verifier requires
exactly one `BUILD-MANIFEST`, `SHA256SUMS`, `boot_image.itb`,
`nothing-tetris-boot.img` and `nothing-tetris-root.sparse.img`, checks every
SHA256 entry, checks the manifest keys and records the only allowed fastboot
mapping: `nothing-tetris-boot.img` to `super` and
`nothing-tetris-root.sparse.img` to `userdata`.

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
| Boot and root filesystem | Works | Clean flash boots pmOS; root is writable and expanded. r13 from CI `34752524434`, artifact `10316991883`, commit `dcaa75d3bdd87606776d64b5e9509ade9ec350d7`, kernel `6.18.0 #159`, device package `8-r13`, verified and clean-flashed on 2026-09-13. | Recheck after every candidate installation. |
| USB debug / NCM SSH | Partial | Automatic `usb0`, SSH and exact 32 MiB transfers passed after the clean #130 install and again on live r155 boot d9d69266-fb08-464f-a7d7-fb7b2fdf1a7a at 20260912T100523Z. A normal Linux reboot produced a new boot ID and restored USB SSH automatically with no failed system units. Clean r132 presents a valid CDC-NCM control/data pair; after the macOS session was unlocked, a host-side reset created `en4`, assigned `172.16.42.2` and restored SSH without rebooting the phone. A 2026-09-12 read-only r155/r9 check found `/chosen` still empty, root `serial-number` present without logging its value, `mediatek,mt6878-devinfo` present and `adie-sku = 1`. r13 clean flash restored `en4`/USB NCM and passed transfer regression at `local/live-logs/20260913T153822Z-172.16.42.1-regression-gate`; the post-unblank display gates preserved SSH. The random host MAC remains a locked-host reliability defect. | Review whether root `serial-number` or devinfo can be an allowed hashed seed without leaking unique data, then package stable per-device gadget identity and repeat clean install, locked-host reconnect, reboot, 32 MiB transfer and suspend/resume. |
| Wi-Fi | Partial | Clean #130 automatically reassociated with DHCP/default route/DNS/HTTPS and completed an exact 64 MiB SSH stream at `192.168.22.64` while USB and Bluetooth remained active. The r151 regression gate now distinguishes `wlan0` presence from usable Wi-Fi; the current clean r155 configuration has no user Wi-Fi association and `apk info` reports transient DNS failures while refreshing indexes. | Restore normal Wi-Fi config on the clean image, then repeat cold reconnect, DHCP/DNS/HTTPS, suspend/resume, sustained bidirectional transfer and second-unit checks. |
| Bluetooth | Partial | Clean #130 registers powered BlueZ `hci0`; `bluetoothctl --timeout 8 scan on` found 23 devices and exited with `Discovering: no` while USB and Wi-Fi remained active. The earlier stuck-discovery result came from an unbounded client invocation rather than the bounded lifecycle. | Pair/reconnect and test audio/data profiles across suspend. |
| Touch and keys | Works | Installed r132 binds `fts_ts` at I2C `2-0038` and exposes `/dev/input/event0`; the reported graphical failure is not a missing touch device. The current fbcon intentionally has no touch interaction. Balanced power/volume events passed previously. | Recheck sustained touch after the graphical display path is restored. |
| Haptics | Partial | The user physically confirmed the bounded RT6010 effect on clean #128; USB remained healthy. | Cold-boot repetition and suspend/resume. |
| Audio | Partial | Speaker playback remains historical physical evidence. On clean #130 a quiet five-second capture produced 387856 samples, 386262 nonzero, zero clipping and 193359 stereo pairs with different channels. After a reversible r6 overlay and normal reboot (`246b8a99-05bc-4ae6-8017-623314471cf9`), `greetd` had zero PulseAudio processes, no fresh ALSA/BlueZ ownership errors appeared, failed units were zero and USB/Wi-Fi/BT returned normally. On installed r151/r8 the new audio audit initially failed because `/var/lib/greetd/.config/dconf` was absent; after creating it live with `greetd:greetd 0700`, the audit passed with USB, ALSA card and zero greeter PulseAudio owner regressions. Later greeter logs still showed Permission denied creating sibling config directories and a stale root-owned `dconf/user` under `/var/lib/greetd/.config`. Device package r12 keeps the recursive private `.config` ownership repair, and the r12 hardware frontier snapshot still exposes the `mt6878-mt6369` ALSA card and playback devices. | Require zero greeter PulseAudio owners and one real graphical-user owner, then retest login/relogin, speaker/system events, capture, Bluetooth profiles and suspend. |
| Thermal | Partial | All 24 MT6878 zones return plausible polling-mode values without USB loss. | IRQ/trip routing and sustained load remain disabled/unverified. |
| Charging | Partial | Clean #128 uses AICR/ICHG 500000 uA when TCPM publishes no current limit. A later real PD session published 5 V / 2 A and drove the policy to 2 A. On installed r151, the source-aware power gate passed: this PD-capable computer attachment reports 5 V but `CURRENT_MAX=0`, so the conservative 500 mA fallback remains correct. These are contract/taper snapshots, not a full charge-rate result. Native BC1.2 SDP/CDP/DCP classification is absent. | Repeat PD from a partially discharged battery while logging battery/connector temperatures, rate, taper, termination and detach. Separately observe a USB 2.0 host, known Rp source and known 5 V BC1.2 DCP. Preserve USB2 DP/DM ownership; explicit PPS setpoints, higher voltages and OTG remain disabled. |
| Idle battery drain | Broken | Roughly half the battery was reported lost overnight. A live r147 capture found `dconf-service` at 5.1 GiB RSS plus 596 MiB swap and persistent CPU use because `/var/lib/greetd/.config/dconf` did not exist; Calls and Chatty retried failed writes continuously. A soft restart reclaimed the memory, but growth resumed until the directory was created. Device package r15 keeps the recursive private `.config` greeter tree repair, packaged idle settings and automatic display unblank; screen/greeter boot is now stable enough for a real idle-drain interval. Wi-Fi and USB suspend costs remain unisolated. | Run physically unplugged screen-off A/B intervals with Wi-Fi associated and disabled. Record coulomb, suspend and wake/IRQ deltas. |
| GNSS | Partial | Clean r155 from CI 34589225716 passed three fresh supervised BINFO/download/stop cycles on separate boots and preserved the exact 32 MiB USB hash. The integrated GNSS boot-protocol gate covers FE08/FE31/FE32 framing, checksums, split reads, truncation/overflow rejection and 1/106/256-fragment state. The live repository readonly gate passed on clean r13, r14 and now r15. On r15 boot `87e5ff1c-2e8b-4350-be62-57951a40e065`, baseline had `usb0` UP, zero failed units, transport inactive, no GPS module and no modem runtime; the gate loaded `gps_drv_dl_v051`, returned `status=0`, `code_size=42505`, `fragment_count=106`, redacted the cipher key, left no gpsdl owner and preserved the exact 32 MiB USB transfer. | Do not retry GNSS on the current boot with the module already loaded. Next clean boot can advance from read-only/download reliability to bounded startup command ownership and navigation/NMEA semantics before exposing gpsd/GeoClue. |
| Modem / SIM | Broken | Current live r15 inventory still reports no ModemManager modem and no CCCI/DPMAIF/WWAN device. U-Boot CCCI branch 1b8c954dba accepts the real stock48 descriptor form and CI passed, but this only publishes diagnostic handoff status. The combined compile-only modem inventory classifies remaining references and still ships no ECCCI/DPMAIF module or autoload. `codex/hardware-integration` now has CI-passing pinned B4.1 modem prereq gates for the CCMNI Linux 6.18 adaptation and DPMAIF page-pool DMA sizing candidates. | Validate actual configured-kernel exports, module ownership and final LTO/modpost; then cover page-pool and UDC provider lifecycle. Handoff memory, trusted-firmware semantics, power, IRQ/DMA isolation, DT, SIM detect and runtime remain later gates. |
| Sensors | Broken | Current live r15 inventory exposes only PMIC ADC IIO devices (`mt6369-auxadc.3.auto`, `mt6375-auxadc`, `mt6375-adc`); no accelerometer, gyro, proximity or light sensor is exposed. Sensor reply correlation and SCP DRAM span validation are host-proven prerequisites, but SCP/mailbox/IPI/HF/sensorhub remain disabled. | Establish authoritative active `scp1`/`scp2` authentication/selection and decode the live LK TCM region-info ABI. Only then integrate an observation-only U-Boot path; publication, disabled DVFS nodes and live probes remain separate later gates. |
| GPU | Broken | Current live r15 inventory has `/dev/dri/card0` only and no render node. Panthor compile/source prerequisites exist, and the VGPU readback gate proves a vendor/mainline enabled-rail source mismatch; shipped DT still has no GPU node, MFG RPC remains disabled, and there is no GPU regulator consumer or autoload. Commit `8db0d6e` hardens the Panthor default-off gate so MFG0/MFG RPC `KEEP_DEFAULT_OFF`, disabled MFG RPC providers and absent `vsram-cpum` runtime DT child remain enforced. | Complete MFG runtime sequencing, clock/reset ownership, coupled rails, DT consumer, CSF firmware and protected memory before any recovery-image probe. First live gate must be read-only rail/register observation, not a GPU probe. |
| Rear/front cameras | Broken | Current live r15 inventory has no `/dev/video*`, `/dev/media*` or `/dev/v4l-subdev*`. Torch channels work independently. The IMX882 reset-polarity prerequisite is host-proven, but no camera node, sensor power-on, I2C transaction, SENINF/ISP, CCU or media pipeline is enabled. | Complete final DT/clock/rail ownership, observation-only clean boots, then one bounded sensor identity probe before SENINF/ISP or preview/capture work. |
| Display | Partial | r15 from CI `34775951132` clean-flashed from hash-verified artifacts and fixed the r14 auto-unblank bug. The first r15 clean boot restored USB/SSH, reported zero failed units, ran `nothing-tetris-display-unblank.service` automatically, reached `fb0/blank=0`, DSI `connected`/`enabled`, mode `1080x2400`, and exposed touch as `fts_ts` on `/dev/input/event0`. Regression, greeter-display and hardware-frontier gates all passed without manual unblank. Prior user inspection confirmed visually good output after the frame-end synchronized buffer update removed redraw flicker. The bounded DPMS lifecycle failure (`QUEUE_SEQUENCE EINVAL` after off/on), fixed 60 Hz mode and missing render node remain open. | Get fresh user visual confirmation on r15, then test warm reboot, brightness lifecycle, DPMS/suspend-resume and later 120 Hz/render acceleration before marking display Works. |
| microSD | Untested | Controller probes, but no physical card I/O test was recorded. | Insert/remove, read/write and remount test. |

## Current installation test

The installed image is r15 from CI `34775951132`, not a daily-phone claim. Its
job is to prove the next-SCP package line clean-installs while preserving USB.
Current gate state:

1. CI artifact `10324214249` downloaded with SHA-256
   `3f99b720d49754d0fdb8c8e79d79c04681cb591329bb201221657a8bfe9015e2`; the
   local verifier accepted `BUILD-MANIFEST`, `SHA256SUMS`,
   `nothing-tetris-boot.img`, `nothing-tetris-root.sparse.img` and
   `boot_image.itb`.
2. Clean fastboot writes to `super` and `userdata`: passed.
3. Automatic USB NCM/SSH and exact 32 MiB transfer: passed at
   `local/live-logs/20260914T043830Z-172.16.42.1-regression-gate`.
4. First clean boot started Phoc and exposed DSI, touch, Wi-Fi, Bluetooth and
   ALSA inventory. Automatic display unblank passed with `fb0/blank=0`;
   greeter-display passed at
   `local/live-logs/20260914T043826Z-172.16.42.1-greeter-display-gate`, and
   hardware frontier passed at
   `local/live-logs/20260914T043830Z-172.16.42.1-hardware-frontier`.
5. Camera, GPU render node, CCCI/DPMAIF modem, user sensors and automatic GNSS
   publication remain absent from the runtime module/device set as required.
6. Wi-Fi interface presence is not treated as success; association, DHCP,
   routed traffic and suspend/reconnect still need their own gate.

Modem, GPU, sensorhub and camera pipeline stay disabled in the installed boot.
Native display is installed without any framebuffer fallback. The HWCCF and
SPM DISP-domain, DSI publication, mutex readiness, full route, OVL shadow and
DSC parameter-flow blockers are fixed or disproven, and the frame-end OVL
update removed visible redraw flicker in live testing. Automatic clean-boot
unblank is fixed in r15. The remaining display work is fresh r15 visual
confirmation, DPMS lifecycle, brightness lifecycle, fixed 60 Hz mode and the
lack of a render node. The next GNSS gate is userspace protocol integration and
a real position fix, followed by cold-start and lifecycle validation.
