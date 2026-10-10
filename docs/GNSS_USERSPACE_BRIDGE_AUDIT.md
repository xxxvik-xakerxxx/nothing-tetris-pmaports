# GNSS v051 userspace bridge audit

## Current Integration Boundary

Installed r179 still has no verified navigation fix. The main branch now
contains a native receiver owner/controller: real gpsdl identity and descriptor
transfer, separate NMEA/application outputs, report/control event delivery,
source-derived native stop acknowledgement and bounded parent reap. It does not
start Android mnld or implement another NMEA parser. Native sanitizer fixtures
and the complete Bionic ARM64 link passed
[CI 38025448174](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38025448174).
Actual stock-code stop/join and mapped-library association fault checks also
passed [CI 38025485686](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38025485686).
Slot6 selectors0/1 now copy the source-derived NUL-string/control envelopes
into the same host queue and send through the existing owned IPC channel.
Native preparation binds this callback and selects its dispatcher before
starting the sole worker. Native fixtures, real callback/worker/socket delivery
and the complete Bionic link passed
[CI 38026751829](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38026751829).
Configuration/calibration, other assistance controls and actual receiver
responses remain missing; no engine initialization or position-fix success
is claimed. See [slot6 service](../patches/gnss-navigation-audit/SLOT6_STRING_SERVICE.md).
See [native integration](../patches/gnss-navigation-audit/NATIVE_ARGUMENTS_INTEGRATION.md).

The calibration reader now feeds exactly 16 bytes at offset160 of the same
unit's `ML4A_000` into the first constructor for the source-proven legacy
branch. It rejects changed/short/symlink records and preserves output on failure.
On installed r179 cold boot `eb3d9a5e-43b2-4bc8-8447-286a5de4f441`, the legitimate
NV partition was checked with `ro,noload,nodev,nosuid,noexec`: the expected file
is regular and 248 bytes. No calibration values were read, copied or published;
the temporary mount was removed. This establishes availability, not branch
selection or calibrated navigation. Native/Bionic reader tests passed
[CI 38027256621](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38027256621).
See [NV constructor bridge](../patches/gnss-navigation-audit/NV_CALIBRATION_BRIDGE.md).

The actual retained B4.1 capability table selects the modern property branch
for all three MT6878 Adie records, not this legacy file path. A new constructor
reads that branch from the legitimate associated image and rejects unknown
identity; it does not accept a caller-selected calibration flag. Missing modern
calibration requires the source-derived modem MIPC message141 response
(tags0x101/0x102/0x103). A native adapter now makes that actual OEM request,
requires status0 plus all three tags and releases request/response once while
rejecting concurrent ownership. Its first-config bridge supplies only the
proven C0/C1 words, not fabricated calibration tail bytes. The matching
`libmipc.so` accessor is now pinned: argument3 is a `uint16_t*` length output,
and a non-null returned pointer alone does not guarantee a four-byte word.
The native adapter checks length for status, C0, C1 and temperature before any
copy. New exact-asset/static checks passed locally; the current Mac offline
emulator terminated with SIGILL; that run is not counted as a pass. The actual
getter's 72 bounded instruction vectors, exact ELF/ABI checks and native
sanitizer fixtures subsequently passed Linux
[CI 38030808388](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38030808388).
The same extraction located `libmtkrillog.so`, `libtrm.so` and
`libmtkproperty.so` in `vendor/lib64`. A versioned dependency audit resolves
294 bindings across these and the pinned Bionic providers; this initial bundle
lacked genuine `liblog.so`, whose two required logging symbols request `LIBLOG`.
An NDK import stub is not accepted as an implementation. New native fault checks
and Bionic compilation also passed
[CI 38030803840](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38030803840).
The new [MIPC supervisor](../patches/gnss-navigation-audit/MIPC_SUPERVISED_CHILD.md)
retains genuinely sealed dependency copies until actual terminal child reap.
One absolute deadline includes the OEM's unbounded init0x305 handshake and the
subsequent141 request. Traced STOP notifications cannot release resources;
timeout remains latched through incomplete cleanup and eventual reap.
Native ptrace/sealing fixtures and API28 object compilation passed
[CI 38038992764](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38038992764).
Actual vendor/system extraction now selects genuine `liblog` from the same
pinned public archive, checks both implementation exports and records its
digest. [CI 38039798135](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38039798135)
passed. The actual 102,352-byte `system/lib64/liblog.so` has SHA256
`dce4ece329f925cdc0b181b3e5f11b54d92a24e49b1b90b121a4e0f960df84fd`;
downloaded bytes match the extraction manifest. Resource acquisition with this
independently recorded pin now passes the complete versioned ELF closure,
including liblog's own dependencies. Provenance is pinned mirror hashes, not
OEM signature verification. No replacement logging stub is used.
The executable sealed-fd handoff now passed on actual ARM64 in
[CI 38050310221](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38050310221)
at `43b4a2d`: real isolation controls, original independently pinned load-only
probe, genuine B4.1 `libmnl.so`, successful terminal reap and empty containment.
Downloaded logs contain `LOAD_OK` and status0; the linker warns about absent
Android-generated linker configuration, but resolves the selected providers.
The run does not call an engine API or execute unload/destructors.
See [sealed CLI](../patches/gnss-navigation-audit/SEALED_PROBE_CI.md).
Legitimate property service, modem CCCI responder, full semantic configuration
and actual engine RX shutdown remain missing. No INIT or engine start is exposed
by this code; library loading is not a navigation fix.
See [MIPC closure](../patches/gnss-navigation-audit/MIPC_B41_CLOSURE_CONTRACT.md).
Earlier native/Bionic
adapter checks passed
[CI 38029177349](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38029177349);
the exact instruction oracle passed
[CI 38029707052](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38029707052).
Capstone mnemonic and numeric display aliases are normalized without relaxing
the image SHA, operands or call targets. The numeric constructor
also supplies the exact requested-buffer clamps and private-C-locale float
text for 38 configuration bytes without clearing other unresolved fields.
Native/Bionic checks passed
[CI 38028186248](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38028186248),
and stock-instruction checks passed
[CI 38028191300](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38028191300).
See [numeric and capability sources](../patches/gnss-navigation-audit/SECOND_NUMERIC_AND_CAPABILITY.md).

## Earlier Config Fixture Evidence

Standalone AArch64 Bionic config/query fixtures from successful job
`build-gnss-bionic-adapter` in [CI 37928044937](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37928044937)
passed on installed r175, boot `e6f6e126-94ff-49a0-a9ea-a1ad9e4eb68a`.
The overall run failed a separate Python path test and produced no image.
Config SHA256: `2f3e4b12c990a2492040ef906d3656bb6714d1ea7ecb0eb5e9fea69a2ff69d31`;
queries SHA256: `26fbcaf863759adccf5d6178b4a974e5ac9b0698a4e7e52d9bee06508dea754d`.
Both ran through the existing audited isolation launcher, with read-only
roots, dropped privileges, denied devices/ioctl/network and 128 MiB memory
limits. The eight-denial control returned zero failures. Config tested all
256 clock flags; queries used synthetic responses, not real device ioctls.
Both exited zero; peak memory was 880 KiB and 1.1 MiB. Boot ID, USB/SSH and
sensor services were unchanged. Missing linkerconfig warnings were retained.
Tar initially preserved the Mac directory owner; the launcher correctly
refused execution until the two newly staged roots were root-owned.

No vendor library was staged or engine initialized. Navigation/fix remains
unavailable: 27 first-config bytes, XML policy, LNA query support, second
configuration, transport lifecycle and mandatory host services remain open.
See [typed producer/query contract](../patches/gnss-navigation-audit/FIRST_CONFIG_BUILDER.md).

## Scope and source identity

r168 candidate: packaged patch `1005` fixes the source-confirmed clock-query
bug in `gps_dl_clock_mng_get_platform_clock()`. A failed MT6685 regmap read
now returns its negative error through the existing ioctl rather than a
fabricated 26 MHz result. Successful 26/52 MHz enums and missing-map behavior
are unchanged. CI exercises the actual patched function with every 8-bit
selector, failed reads and a swallowed-error mutant. No new GNSS command,
firmware download or navigation provider is enabled; CI/live verification is
pending. This supersedes the historical "not packaged" clock-query note below.

This audit used local sources only. The authoritative connectivity source is
Nothing OS 4.1 Tetris commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` from the local
`upstream/android_kernel_modules_nothing_mt6878` object store. The pmaports
baseline is `1f8aef10668c62284ac4824eb334a67a14f6c1df` from the former
`codex/gnss-userspace-bridge` branch, retained under its archive tag.
This is protocol research; current status is in PORT_SUMMARY.md. Dated
experiments below describe their own software, not the installed r167.

The source exposes a private character-device ABI, not NMEA or the Linux GNSS
subsystem. Opening `/dev/gpsdl0` powers link0. Closing the final descriptor
drives its normal close sequence. The exact v051 source proves these bounded
userspace operations:

| Operation | Command/layout | Boundary |
| --- | --- | --- |
| Query status | integer ioctl `13`, argument `0` | Returns link state without requesting the reason `2`/`4` debug events. |
| Get DSP boot information | integer ioctl `23`, five 32-bit fields, 20 bytes | Calls the v051 ATF boot-info backend already exercised on the phone. |
| Get boot time | integer ioctl `28`, two signed 64-bit fields, 16 bytes | Copies boot-time and architectural-counter values to userspace. |

The kernel patch moves only those constants and layouts into a versioned UAPI
header. Kernel static assertions and a host C11 test lock every exported value,
size and offset. Assert/reset, suspend/resume, link1/CW-DSP, firmware control,
MVCD fragment submission and raw payload formats remain private.

## Manual diagnostic

`nothing-tetris-gnss-readonly` is a manual diagnostic, not a daemon or a
position provider. It accepts only `--probe-link0`, opens only
`/dev/gpsdl0` with `O_RDONLY | O_CLOEXEC | O_NOFOLLOW`, installs an eight-second
process deadline, executes the three allowlisted ioctls, validates the observed
fragment-count and clock bounds, redacts `cipher_key`, and closes the descriptor.
It contains no `read(2)` or `write(2)` call and has no service, preset, udev rule
or module-load entry.

Opening the node still changes GNSS power state. Therefore the diagnostic stays
manual until the complete lifecycle gate passes. On a clean boot with the
correct LK and current image:

```sh
sudo systemctl start nothing-tetris-gnss-transport.service
scripts/check-live-regression-gate.sh 172.16.42.1 user '<password>' baseline
sudo /usr/libexec/nothing-tetris-gnss-readonly --probe-link0
sudo find /proc/[0-9]*/fd -lname '/dev/gpsdl*' -print
nmcli dev wifi list --rescan yes
scripts/check-live-regression-gate.sh 172.16.42.1 user '<password>' transfer
```

The first live run must use one SSH control session and capture the boot ID,
kernel/package identities, pre/post `dmesg`, `/sys/module/gps_drv_dl_v051`, both
device nodes, Wi-Fi association/routing, Bluetooth power, and the exact USB
transfer hash. Stop after a timeout, firmware assert, remote-processor reset,
owner left on either node, Wi-Fi/BT regression, or USB/SSH loss. Recover by a
clean reboot; do not unload conninfra or retry in the same boot.

## Validation

`scripts/check-gnss-v051-readonly.sh` performs the local authoritative gate. It
archives the exact B4.1 GNSS tree, applies compatibility patch `1002` followed
by UAPI patch `1003`, compiles and runs the ABI test, compares the kernel and
device-package UAPI byte for byte, and host-compiles the manual diagnostic.

The repository validator additionally rejects extra UAPI commands, link1,
device reads/writes, write-capable opens, missing deadlines, service/preset
activation, and omission of the packaged diagnostic. The full kernel package
build remains the module compile/modpost gate, and image CI checks that the
manual executable and v051 module are present.

## Clean r155 repeat result (2026-09-12)

The r155 image from CI 34589225716 was clean-installed as the paired pmOS
super and userdata images, leaving LK/U-Boot unchanged at c931695. The GitHub
artifact digest and all extracted image SHA256 sums match the CI metadata; the
rootfs package database contains device-nothing-tetris 8-r9 and
linux-postmarketos-mediatek-mt6878 6.18-r155. A bounded sparse-image inspector
also validated the root sparse stream before flashing.

The unchanged supervised BINFO/download/stop protocol then passed on three
separate boots: 9ab1397d-748d-460f-930e-fe15d6a1789c,
bbba0f14-74d2-4231-b8f1-71c18d7e41dc and
d9d69266-fb08-464f-a7d7-fb7b2fdf1a7a. Each boot started with no GPS module or
gpsdl node, loaded gps_drv_dl_v051 once, completed the native FE08/FE31/FE32
download path, accepted one FE05/4 stop, closed cleanly and left no gpsdl
owner. The kernel published the expected OFF -> ON -> RST -> WORK -> RST ->
OFF sequence without the earlier supervisor timeout waiting for the post-stop
RESET_DONE record. USB survived each run with the exact 32 MiB SHA256
83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302, and the
final boot had zero failed system units.

This closes only the r155 transport/download/shutdown repeat gate. It does not
claim a satellite fix, NMEA/GeoClue integration, automatic service startup,
restart stress, coexistence or suspend/resume. One first-boot warning,
`emi_mng_get_gps_emi failed to find gps node`, remains to triage even though
the subsequent cycle passed. The clean image manifest still names U-Boot
60bcf22 as required, while the live repeat intentionally kept c931695; the
bootloader-contract validation is therefore not complete.

## Protocol and lifecycle experiments (2026-09-11)

### Candidate 1004: finalize the FSM log records

The source diagnosis now confirms a publication dependency: the vendor FSM
formats omit newline; Linux printk commits but need not finalize the newest
such record. The /dev/kmsg reader cannot observe it until another printk
finalizes it. The supervisor withholds close until that observation, making
shutdown completion depend on unrelated logging. This is not a measured
multi-second SMC delay. The failed repeat remains failed; other independent
stall causes have not been excluded on that untraced boot.

Patch 1004 changes exactly the two FSM format strings, normal and abnormal,
to end with newline. No severity, state ordering, hardware action, deadline,
retry or observer error handling changes. It is wired into r155 source,
checksum and prepare order after 1003. Installed r153 remains unchanged.

Nine pinned-source host tests pass, exercising the real observer with a
sequential ringbuffer model, not Linux atomics. Original quiet-log state
publication times out; the fixed phases need no subsequent printk; abnormal
and unarmed resets still fail. The initial patch header was off by one and
GNU patch reported relocation; the corrected hunk at line340 is checked
independently, with negative offset/fuzz cases. The packaged diff body is
byte-identical to this tested candidate. Audit/test commit: 56d50ac in
codex/camera-clk-prereq-v2, patches/gnss-navigation-audit/.

Targeted hal/gps_dsp_fsm.o compilation against the prepared 6.18 tree passes,
including LLVM-bitcode to ARM64 ELF generation with Clang21.1.8. The prepared
kernel records Clang21.1.2, so this is not a matching live module build.
The narrow source extraction also emitted a missing fw_log directory warning;
no complete module, modpost or load was attempted. Source SHA256:
ed0c133fe62dfd4899fe090e2595d753fe01ee183bb9c616815cd611ffbad1ac.
ARM64 object SHA256:
3563c9c8c3360711a866910e1fea3697ba97bdc6d272c437769c36e34515496a.
Package overlay and GNSS UAPI/manual-diagnostic checks pass. Next gate is an
exact-ABI module/image and unchanged supervised protocol on clean boots,
with raw-kmsg/source-time capture as well as trace. Navigation remains absent.

Subsequent c931695/r153 repetitions supersede the single-pass reliability
claim below: repeat 1 passed, repeat 2 timed out waiting for phase 4 after
STOP_WRITTEN. Its later normal OFF/CLOSED is retained but is not a pass.
The eight-second deadline and protocol were unchanged. No unload/retry was
performed; the phone was rebooted cleanly.

An isolated function-graph observation on the next clean boot passed. All
six function filters were verified, a no-op setup/cleanup passed before GPS
was opened, all CPU trace-loss counters stayed zero, and cleanup restored
nop with no remaining instance. At stop, MCUB handler duration was 115.693 us,
clear flag 4.923 us, FSM 16.615 us and state change 4.923 us. The FSM returned
at monotonic 767.019633, while the journal displayed its record at 767.296379.
This is an observation discrepancy, not proof of a slow SMC or driver lock.
The missing trailing newline in vendor FSM logs is a candidate explanation
under investigation. Tracing can perturb timing; the earlier timeout remains
unresolved. USB transfer and post-test ownership checks passed. No navigation
configuration or position request was sent.

Local evidence: gnss-supervised-c931-repeat-1/kernel.log,
gnss-supervised-c931-repeat-2/kernel.log, and
gnss-supervised-c931-stop-trace/{result.txt,kernel-active.log,LIVE-PLAN.md}.

The corrected v2 experiment now PASSED one observed download/start/stop
cycle after clean reboot and host USB recovery. On boot
3baa4f13-1c6d-4cf7-858a-6497d04f0de5 (unchanged r153/device8-r9), the
supervised child exited zero. Kernel events establish OFF -> ON -> RST ->
WORK -> RST -> OFF, with reset confirmed before release and normal CLOSED
state. History shows 107 reads and writes of 116/12 bytes, consistent with
the complete validated boot exchange and one FE05/4 stop. There are no
forced-off, off-done-failure or abnormal FSM matches in the bounded capture.
USB 32 MiB hashes match before/after, Wi-Fi remains connected, Bluetooth
powered, no failed units and no GPS owners. The module remains loaded,
unused; no unload or repeat was performed. Exact hashes and timestamps are
in local/gnss-supervised-r153-v2/LIVE-PLAN.md and kernel.log.

This supersedes the earlier recovery blocker, not the incomplete port status:
three clean repeats, navigation/fix, lifecycle and automatic integration are
still unverified. The following failed-run record is retained intentionally.

Latest supervised run: one full driver-assisted download reached the native
DOWNLOAD_COMPLETE checkpoint and the real kernel later reported RST -> WORK
on RAM_OKAY. This is the first observed DSP RAM-code readiness, not a GNSS
fix. The supervisor had already rejected a routine periodic read-history
warning in ROM state and terminated its child before any FE05 stop write.
Read history contains 107 received frames, consistent with BINFO plus 106
fragment ACKs. The WORKING transition occurred during cleanup, followed by
off polling failure, forced A-die off and an abnormal WORK -> OFF transition.
The supervised lifecycle FAILED; no repeat or module unload was performed.

Full local identity, four exact uploaded hashes and kernel evidence are in
local/gnss-supervised-r153/LIVE-PLAN.md and kernel.log. USB/SSH remained
available immediately afterward. A post-test transfer was sandbox-denied,
so its empty-stream hash is explicitly not transfer evidence. Clean reboot
was requested; the host sees the postmarketOS USB device but is locked and
has no en4. User unlock is requested; new boot/SSH recovery remains unverified.

The source-pinned history recorder emits its normal warning every eight
records, including during download. The local observer now accepts the
strict numeric history shape in ROM/WORK/post-stop/OFF phases, still rejecting
errors, unknown warnings, overflow and forced recovery. Its 23 tests pass.
This correction is not uploaded or rerun; the original experiment bundle
is retained unchanged. The separately hashed local candidate is under
local/gnss-supervised-r153-v2. It changes only the observer; nine supervisor
and five Linux ARM64 process tests pass again, and replay accepts periodic
history while rejecting the original premature close at session record 39.
A second experiment requires confirmed clean recovery.

The pinned B4.1 callback/framing research has advanced beyond the earlier
2060-case framing inventory below. A bounded native BINFO-only experiment
on r153 received a checksum-valid FE31 index-zero ACK, but its incomplete
download teardown timed out and forced A-die off. The phone was cleanly
rebooted; GNSS is inactive on the last verified baseline. No fragments or
navigation commands were submitted, and no position was obtained.

The separate `research/gnss-b41-inputs/` worktree now contains a native
full-fragment candidate with 29 passing mocked-I/O scenarios. It uses
ordered scalar ioctl-25 fragment indices and checks FE32 acknowledgements;
it is not installed, packaged or hardware-validated. The remaining blocker
is not another OTA download: it is proving DSP RAM-code readiness and safe
shutdown before allowing this probe to run. Vendor thread wake/join and
file-descriptor close do not by themselves prove DSP shutdown. The current
source trace and exact binary hashes are in that worktree's CALLBACK_ABI.md;
the live failure/recovery record is summarized in GNSS_BRINGUP.md.

Further bounded execution now verifies primary FE05 argument 4 serialization
and its real queue-flush/writer path to a substituted write syscall. Six
serializer and nine flush/writer scenarios pass. Short writes continue from
the remaining bytes, but repeated zero/error writes and invalid fd paths can
loop without a whole-operation bound. These vendor retry paths must not be
copied into the native probe. Mode/blocked/context guards can also suppress
delivery, so a sender return is not a firmware acknowledgement.

The exact-pinned FSM and MCUB handler are unchanged from e96f60dc081a:
RAM_CODE_READY is required for RESET_DONE -> WORKING; a fresh reset event
returns WORKING -> RESET_DONE before normal power-off. The next live probe
must observe these transitions, not infer them from FE32 or a successful
write. The primary stop packet is known, but its acceptance by this device
and safe close remain unverified. GNSS stays inactive, USB/SSH healthy on
the rechecked r153/38192f202c boot. No module load or device write followed
these tests.

An uninstalled read-only lifecycle observer now has 17 passing unit tests.
It follows fresh /dev/kmsg records from a cursor opened before gpsdl0, rejects
lost/stale/out-of-order records and primary warnings, and requires observed
WORKING before an explicitly armed stop boundary. A separate supervised
probe mode now waits for explicit readiness/reset tokens around a single
FE05 stop write; 33 native mocked-I/O scenarios and nine supervisor tests
pass. Cleanup is bounded and never retries or reloads the driver. A live
read-only preflight confirms Python and independent /dev/kmsg cursor access,
but no live readiness record has been seen and no new probe was installed.
Five actual C-child/Python-supervisor pipe scenarios now pass on Linux ARM64
with substituted GPS operations and synthetic log events. The observer has
20 tests after allowing only source-confirmed, phase-scoped routine warning
messages; a historical BINFO transcript is rejected at its premature close,
not at its normal open notice. A reviewed, hashed experiment bundle and
fresh hardware lifecycle evidence are the next gates. Legacy immediate-close/BINFO-only modes remain unsuitable for
another live run. Any partial-start or teardown failure still requires a
clean reboot; successful log observation alone is not a GNSS position fix.

## Earlier position-bridge audit

Follow-up: exact B4.1 switch tables now connect thread-ID-3 stop handling to
set_param(0,NULL), internal message 1001, and the run-loop sender arguments
(5,3,1,4). A bounded ARM64 execution test passes this dispatch chain without
executing the sender or any external call. This narrows the missing stop
contract to FE05 with argument 4 and conditional link selection, but does
not prove delivery or acceptance before RAM-code startup, nor safe close.
The research CALLBACK_ABI.md records table addresses and mode/queue caveats.
That isolated callback test did not execute the full-download probe;
the later r155 hardware result is recorded above.

### 2026-09-11 input provenance correction

**Later same-day update:** the matching vendor image has now been obtained
and its exact size/SHA-256 matched to the official OTA target manifest.
The former missing-binaries acquisition blocker below is superseded, not the
runtime protocol/ABI gap. See the isolated research report and
elf-summary.json for the measured files. mnld has 25 direct dependencies,
while the MT6878 libmnl has four (libc++, libc, libm, libdl). The upper-level
libmnl path is a symlink in this release. Next trace the actual callback
table and mnld initialization before deciding between a library-level Linux
adapter and a larger Android compatibility stack. No binary was run or
installed on the phone; signature authentication is not claimed.

The locally named stock-b41 proprietary-file inventory actually identifies
B4.0-260225-1904. Its mnld/libmnl paths are extraction candidates, not proven
B4.1 userspace dependencies. The local B4.1 firmware archive does contain
connsys_gnss.img, and its declared payload matches the packaged firmware
byte for byte; obtaining another firmware copy does not close the userspace
gap.

The parallel input audit verified metadata directly from Google OTA CDN for
incremental 2602251904 -> 2604151709. It identifies a concrete matching input:
`https://android.googleapis.com/packages/ota-api/package/a8b9fdc18fdcd81355f9c3dfa8b7c61a584b51f0.zip`.
Only bounded metadata was inspected, not the complete OTA, its signature or
partition operation manifest. Next inspect that manifest to determine the
required B4.0 base blocks before reconstructing target vendor userspace.
Do not assume an incremental OTA alone supplies a complete vendor image.

The exact-source audit also rejects two misleading shortcuts: ioctl 25
passes a fragment number, not a firmware payload, and the source's NMEA
channel belongs to MCUDL, disabled in the v051 build. Neither establishes
the missing MVCD or navigation framing. Preserve both candidate libmnl.so
paths and inspect ELF/linker dependencies offline before running anything.

Full provenance, hashes, source paths and extraction set are recorded in
the isolated worktree's `research/gnss-b41-inputs/README.md` under
`worktrees/gnss-userspace-bridge`. No phone or GNSS runtime state was changed.

The matching mnld/libmnl binaries and selected init files are now local,
with provenance recorded in the research report. The dependency closure,
redistribution notices and complete startup configuration remain unresolved.
No complete source implementation of the MVCD payload-container algorithm,
DSP RAM-code download sequence, navigation protocol or standard GNSS/NMEA
bridge is available. The older statements above about missing binaries and
pending vendor reconstruction are historical, not remaining acquisition work.

The research callback audit now traces the two direct fd fields, 512-byte
reads into mtk_gps_data_input/data_input2, and a bounded byte-framing handler.
2060 isolated ARM64 cases establish AA F0/AA 0F markers, DE escape handling,
and state/ring transitions. The integrated host gate
`scripts/check-gnss-boot-protocol.py` adds strict FE08/FE31/FE32 wire encoding,
checksum, length, split-read, truncation, overflow and 1/106/256-fragment
state-machine coverage. Direct thread-local stack-guard reads still demonstrate
ABI dependence beyond the dynamic import table.

Consequently this change does not send fragments, read raw payloads, start
`gpsd`, expose GeoClue, autostart GNSS, or claim satellite acquisition or a
fix. The next userspace step is to validate startup command ownership and
navigation payload semantics against these exact inputs or a bounded known-good
Android trace. Clock-query patch `1005` reproduces and fixes silent regmap-read
error conversion to the valid 26 MHz enum in host tests. It is applied to the
vendor connectivity build since r168 (`bf7e2f8`) and retained in installed r175;
that does not establish a live GPS clock query while the transport is absent.
Live metadata confirms MT6685 parent binding and
an existing unbound GPS child while the GPS transport is absent; no duplicate
DT child is required. Neither fact closes the hardware lifecycle gate.

2026-10-09: `scripts/check-gnss-host-boundary.py` now integrates the research
frame-sync and borrowed-output C helpers into native CI. It compares all 262
callback vectors against the pinned emulation digest, checks the required
24-slot callback table and bounded output copy, and rejects three mutants
(missing low-byte mask, missing required callbacks, discarded output bytes).
Native CI `37894001985` passed this gate at `a5d72a1`, including all three
negative mutants. These helpers do not supply the Bionic runtime,
complete startup configuration, firmware download or a position provider;
they are not installed on the phone and do not establish a GNSS fix.

## Isolated Bionic Load Gate

The complete six-ELF B4.1 closure already exists in the local runtime audit:
linker64, Bionic libc/libm/libdl, system libc++ and libmnl. Their bytes match
the recorded hashes. No further OTA acquisition is needed for a load-only test.
These hashes identify the local inputs; OTA/APEX signature authentication and
redistribution permission are not established by this gate. None of these
vendor/runtime binaries is committed or packaged in a pmOS image.

The manual `gnss-runtime-probe.yml` workflow builds a static Linux isolation
launcher and a Bionic helper with official
[NDK r27d](https://developer.android.com/ndk/downloads). The download's published
size and SHA1 are checked before use. The helper has no libmnl DT_NEEDED and
only calls `dlopen(RTLD_NOW|RTLD_LOCAL)`, reports the result and uses `_exit`;
it never calls a vendor API or destructor. The pinned Android linker supports
`PROGRAM [ARGS]`, not glibc's `--library-path`; its explicit LD_LIBRARY_PATH
is supplied inside the private root, matching
[Bionic's loader](https://android.googlesource.com/platform/bionic/+/HEAD/linker/linker_main.cpp).

`scripts/stage-gnss-load-probe.sh` checks every pinned input and CI helper
checksum before creating a fresh root. On the phone, the trusted launcher
requires root-owned non-writable staging, creates private mount/network/PID
namespaces, binds the root read-only/nodev/nosuid, mounts a private read-only
proc, drops all capabilities and runs as uid/gid 65534. No device nodes or host
directories are supplied. Descriptors above stderr are closed. Seccomp is
installed before exec and denies sockets, ioctl, namespace/mount operations,
ptrace, process control, io_uring and privilege changes; clone/fork are also
denied for this load-only gate. CPU/address-space limits and an external
20-second kill/reap watchdog bound the attempt. Native CI exercises eight
denial checks; the same control must pass in the phone's full sandbox before
any Android/vendor code runs. A failed control stops the experiment, never
justifies relaxing the policy automatically.

CI `37897741457` passed and its archive matched GitHub's SHA256 digest.
All nine staged-file hashes passed on installed r173, cold boot
`a507d5d4-c1d4-4acf-9bba-c4724a6e1064`. The full phone control returned
`failures=0` for all eight denials. The single vendor load attempt failed in
Bionic Scudo before helper completion: a request for 8,650,752 KiB virtual
address space exceeded the 512 MiB RLIMIT_AS. Tombstone IPC/ioctl attempts
were denied as intended. USB/SSH and boot ID remained unchanged, with no
failed system units. This is not a libmnl loadability pass.

The revised launcher requires cgroup-v2 `memory.max <= 128 MiB` before any
namespace/vendor work, and permits 16 GiB virtual space for Scudo's sparse
reservation. The phone invocation must use a bounded transient systemd unit
with MemoryMax=128M, MemorySwapMax=0, TasksMax=4 and RuntimeMaxSec=25. Existing
seccomp, device/network/privilege denial, read-only root and watchdog remain
unchanged. The control must pass again in that same bounded unit before load.
CI `37898372984` passed at `2adc9cd94e7bcb6801b943990666fccf301ee1bd`.
Its archive SHA256 was
`647bb38280be748ce4f9407364f99aba2d5793d658c424f7727e2098bbd67003`,
matching GitHub; all nine staged files matched on the phone. On the same r173
cold boot, the bounded control passed all eight denials again. The single
load attempt returned `LOAD_OK` and exit zero in 18 ms, with 1.1 MiB peak
resident memory and no swap. Missing Android linker configuration remained
a warning, not a load failure. USB/SSH, boot ID and zero failed system units
were unchanged. No vendor API, destructor, device or network operation was
permitted; the staged root is temporary, not part of clean-install support.

This establishes library loadability only, not solver startup, transport ownership, firmware download,
satellite acquisition, gpsd/GeoClue or a fix.
