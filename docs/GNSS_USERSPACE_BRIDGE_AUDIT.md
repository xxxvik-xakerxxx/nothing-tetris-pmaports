# GNSS v051 userspace bridge audit

## Scope and source identity

This audit used local sources only. The authoritative connectivity source is
Nothing OS 4.1 Tetris commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` from the local
`upstream/android_kernel_modules_nothing_mt6878` object store. The pmaports
baseline is `1f8aef10668c62284ac4824eb334a67a14f6c1df` on the isolated
`codex/gnss-userspace-bridge` branch.

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

## Latest experiment and remaining gate (2026-09-11)

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
The full-download probe remains unexecuted; no new GPS hardware test ran.

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
and state/ring transitions. This is not yet a complete framing/parser audit:
checksum, length validation, overflow/reset, multi-byte stream behavior and
command semantics remain unverified. Direct thread-local stack-guard reads
also demonstrate ABI dependence beyond the dynamic import table.

Consequently this change does not send fragments, read raw payloads, start
`gpsd`, expose GeoClue, autostart GNSS, or claim satellite acquisition or a
fix. The next userspace step is to validate the remaining frame/parser and
startup contracts against these exact inputs or a bounded known-good Android
trace. A separate research clock-query patch reproduces and fixes silent
regmap-read error conversion to the valid 26 MHz enum in host tests; it is
not packaged or installed. Live metadata confirms MT6685 parent binding and
an existing unbound GPS child while the GPS transport is absent; no duplicate
DT child is required. Neither fact closes the hardware lifecycle gate.
