# SCP loader trace, 2026-09-21

Sensors remain Broken. The missing production implementation is the SCP
firmware loader, not another sensor-list or mailbox registration patch.

## Runtime preparation progress, 2026-09-22

Candidate kernel r164 adds patch 0101 for the recovery memory contract.
It replaces the unconditional four-bank mapping with one rounded image in
secure mode, or `core_nums + 1` rounded banks in non-secure mode. The latter
requires region-info's backup address to match the actual reset consumer.
Loader, firmware, DRAM mapping and backup must all fit the `no-map`
`mediatek,SCP-reserved` region returned by OF reserved memory. The address
and size are not hard-coded; sensor shared memory is a separate reservation.

The exact-source host suite now tests this helper with 49 checks under UBSan,
including two reservation bases, the observed four-bank overflow, secure and
non-secure layouts, wrong backup placement, missing/out-of-range memory and
integer limits. The older arithmetic regression cases remain tested too.
CI runs the exact-source patch application and tests before packaging.
This patch neither enables secure dump nor creates region-info. r163 remains
installed; no sensor samples or live validation of r164 are claimed.
Commit `68516cc`, CI `35692283994`: overlay validation (including the new
exact-source UBSan suite) passed; kernel build is in progress at this checkpoint.

### Bounded LK SRAM trace

Additional offline disassembly of the same pinned LK identifies the exact
write sequence in `0x2c0a4..0x2cfc8`. LK virtual MMIO addresses have prefix
`0xffff0000`; physical addresses below omit that prefix. This is trace
evidence, not authorization to execute writes on an arbitrary ATF/SKU.

1. Write 1 to `0x1cb30004`, then 1 to `0x1cb40004`, then 3 to `0x1cb21000`.
2. Read/modify/write `0x1cb50234`, setting bit 14 and preserving other bits.
3. For each offset from physical `0x1cb21000`, in this exact order, write
   `(1U << n) - 1` for n = 31 down to 0:
   `c0 c4 c8 cc d0 d4 d8 80 84 2c d8 88 8c 90 94`.

This is 15 groups of 32 writes (480 total), not a single zero write per
register. Offset `d8` occurs twice, separated by `80 84 2c`; do not deduplicate
it. Bounded Capstone constant propagation checked every stored value in
those groups against the descending mask sequence. The RMW source value
was intentionally left unknown. No delay or barrier occurs inside this
bounded straight-line sequence; that does not establish external prerequisites.

The kernel's exact region-info structure identifies offset `0x28` as
`scpctl`. LK obtains that value from `0x7eab8`, backed by dynamic global
`0x24e2f8`; it is not a universal constant. The source of that global still
needs tracing. After the loader returns, its caller also invokes `0x2d248`,
which passes the allocated base and base + `0x2300000` to `0x7ef84`, followed
by `0x2d58c`. These post-load operations must be audited before declaring the
loader chain complete; SRAM writes and the region-info snapshot alone do not
reproduce the complete LK handoff.

U-Boot `ccf6919569`, CI `35654594924` passed the runtime C certificate
parser tests, actual sandbox RSA-PSS salt-length regression and ARM64
compilation. The parser verifies delegated RSA-2048/PSS signatures using a
caller-provisioned root pin, checks ciphertext and extracts the signed
plaintext digest for verification after decryption. The vendor
fixture check is offline consistency only, not manufacturer-root provisioning.

U-Boot `4c15eec5f0` joins authentication and secure preparation in
`tetris_scp_prepare_component()`. Image address, alignment and capacity are
checked before service registration. Failures poison the context, failed
plaintext is erased, and successful components can share one registration.
CI `35655641033` passed. Follow-up `8e9a46d51d` validates image capacity
before authentication reads; sixteen local C-backed tests pass, plus the
sanitizer transport suite. CI `35656023815` passed the tests, actual ARM64
compilation and complete image build/packaging. No runtime board caller is
enabled and no new image was flashed; the phone still uses r163/ba0a2763ef.

### Recovery memory contract is not yet compatible

The exact Nothing OS 4.1 source at
`ee2be53cb75670b548948636a0db1d1ff112bf12` shows:

- `scp_helper.c:2197` maps four rounded DRAM banks.
- `scp_awake.c:361` in the non-secure reset path clears `core_nums` banks
  and copies the backup from `roundup(ap_dram_size, 1024) * core_nums`.
- `scp_awake.c:345` instead uses `scp_restore_dram()` for secure recovery.
- Stock `mt6878.dts:11558` enables secure dump; the current manual pmOS
  node has `core-nums = <2>` but does not enable that secure path.

The audited LK copies a single backup at DRAM + rounded size, not at
DRAM + two rounded sizes. With observed encrypted payload size `0x924740`
and no size reduction identified in the loader, rounding gives `0x924800`.
The four-bank mapping plus the `0x700000` core offset requires `0x2b92000`,
exceeding the observed `0x2300000` reservation. This is a conditional layout
conflict, not evidence that a running SCP has corrupted memory: SCP is still
disabled and decrypted runtime region-info has not been obtained.

Do not reduce the mapping blindly or enable secure dump alone. The full
secure registration, dump allocation, backup ownership and restore behavior
must match the loader before enabling reset/recovery. Patch 0094 checks
arithmetic overflow only and does not establish carveout ownership.

In the pinned installed ATF payload, the runtime dispatcher at `0x3a944`
uses signed offsets at `0x48548` relative to `0x3a978`. Operation 5
(`RESTORE_DRAM` in the matching kernel enum) selects `0x3ad30`: its success
path checks state 4, stores state 5 at payload-relative `0x5af5c`, and returns
zero via `0x3aec0`. It does not copy DRAM on that path. Operation 4 selects
`0x3acc4` and begins clearing/restoring TCM; the remaining restore chain is
not yet fully traced. Do not infer backup-copy semantics from the kernel
wrapper's name or treat a zero return alone as proof of restored firmware.

The read-only lk_b header on the current phone declares payload size
`0x110d40`, different from the pinned offline LK's 1681136 bytes. It must not
be described as an identical verified stock fallback based on its name.

A final read-only SSH check still showed boot
`b7fa5874-d0ac-4a3e-8321-0f53a4787065`, kernel 6.18.0 and usb0 UP.
SCP, sensorhub and HF manager were not loaded. No secure call or module
startup was performed during these tests.

## Live storage correction

U-Boot 366f8ab913 passed a block-device child to blk_get_by_device(), which
expects a storage parent and searches its children. It returned NULL before
reading either partition. Commit 0d71414af7 uses blk_get_desc() directly.
CI 35606234615 passed. The LK image SHA-256 is
0d288d38ad8b48d2bcf76693cee3a5eef275c8aad23932c988cf095e604d966c.
Only lk_a was flashed. On boot f628eee9-5439-4913-bdcd-adf50c958b38:

- nothing,scp_a-container-status = ok
- nothing,scp_b-container-status = ok
- both container sizes = 0xa43070
- nothing,scp-region-info-status = zero, size = 0

The 32 MiB regression transfer passed; evidence directory:
local/live-logs/20260921T133626Z-172.16.42.1-regression-gate.
The properties use underscores in scp_a/scp_b; a hyphen-only glob misses them.
Container validity here means six header names and bounded section lengths,
not authenticated certificates, firmware execution or an active-slot decision.

## Exact binary evidence

The local stock LK first payload is 1681136 bytes, SHA-256
431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a.
It was read from the existing ignored stock-b41/lk.img under the
hardware-integration worktree. The directory label alone does not prove its
firmware release or suitability for every SKU. Offsets below are relative to
that payload, excluding the 512-byte MediaTek header. Capstone 5.0.6 was used
offline; none of these routines or secure calls was executed on the phone.

Observed call chain:

1. At 0x2d038..0x2d04c the SCP loader calls 0x74da0 with the name
   tinysys-scp-RV55_A and a 0x700000 destination limit.
2. At 0x2d060..0x2d07c it calls the same routine with
   tinysys-scp-RV55_A_dram and a 0xe00000 destination limit.
3. The section loader at 0x74da0 searches named MediaTek sections, checks
   the destination limit, dispatches certificate/security processing via
   0x7e334..0x7e348, and reads the selected payload before processing it.
4. At 0x2d0b8..0x2d0cc the SCP caller copies 0x2000 bytes into the TCM
   mapping whose physical address is 0x1c400000.
5. At 0x2d0f4..0x2d108 it fills loader, firmware, DRAM and backup members
   of region-info. Copying arbitrary encrypted partition bytes there would
   not reproduce the loader's input state.
6. At 0x2d10c..0x2d170 the caller prepares SMC 0xc200040f with operation
   1 and DRAM address/size, then operation 3. Later calls use operations 4/5
   on a conditional path. Their complete secure-side semantics remain to
   be established before adding runtime calls.

The image-processing dispatch includes 0x7e348 -> 0x91f9c -> 0x91fa0.
That routine builds a context containing the image pointer, length and other
security state, then calls 0x88078 -> 0x8203c. The latter selects a backend
using the result of 0x16ea0. Only one branch uses 0x820a0, which writes a
request into a mapped service buffer and calls 0x8216c. That wrapper invokes
SMC 0xc2000133 with a selector in x1 and checks the return value.

Follow-up: LK 0x16ea0 returns constant 2, selecting the secure backend in this
exact binary. The installed ATF payload (SHA256
05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e)
names 0xc2000133 MTK_SIP_LK_AES256_CBC_DEC_FW. Its handler is 0xafcc,
calling 0x2bff4; the handler pointer precedes the paired SMC IDs in the
service table. SCP boot service 0xc200040f similarly maps to 0x3b670,
not the adjacent runtime service 0x3a944.

The page-registration wrapper at ATF 0xb0b8 requires physical 0x48401000
and length <=4096. Registration and decryption fail after the service lock
flag is set by the 0xc200010c handler. Whether that lock is invoked on our
current U-Boot/Linux path is not established. A prior conversational claim
that Linux handoff necessarily closes it was too strong.

U-Boot commit 0748fe7afc adds tools/tetris_scp_security.py, dependency pins,
eight synthetic test cases and CI integration. Both components in the
existing scp_a dump pass RSA-PSS/SHA256 signature checks, cert1 image-key
delegation to cert2, and encrypted-payload SHA256 matching OID
2.16.886.2454.2.1. No vendor blobs or wrapped material were committed.
Results are explicitly self-consistent-only unless an independently obtained
root SPKI hash is supplied; this does not establish trust against device efuses.

This is an offline verifier, not the runtime loader. The origin/lifetime of
all context fields, certificate trust policy, service-page ownership, memory
reservation, cache visibility, TCM power-up and SCP boot-completion handshake
still need implementation/validation. The new U-Boot documentation
doc/board/mediatek/tetris-scp-loader.rst records the exact trace.

A subsequent read-only SSH check found the same boot ID
f628eee9-5439-4913-bdcd-adf50c958b38, usb0 UP, container status ok and
region-info zero. No module reload, secure call or flash was performed.

## Next implementation boundary

### Memory collision and slot evidence

Read-only checks on boot `f628eee9-5439-4913-bdcd-adf50c958b38` found:

- `misc+2048` contains version-1 Android A/B metadata with valid CRC32
  `d2190560`, recorded `_a`, bootable A and disabled B. The U-Boot fastboot
  current-slot handler is hard-coded to `a`; prior use of it as independent
  confirmation was invalid. Recorded metadata does not prove the running LK slot.
- `mediatek,crypto_hw` reserves `0x48401000..0x48402000`, matching the audited
  secure service-page ABI. This identifies its reservation, not exclusive
  permission to reuse it or proof that the secure service remains unlocked.
- `mediatek,SCP-reserved` declares `0xb8000000` size `0x2300000`, but the
  current Linux initrd is `0xba247000..0xbaddce38`, intersecting that region.
  `/proc/iomem` does not show the full SCP carveout reserved.

In `bootm_run_states()`, DT reservations were imported after initrd relocation.
Candidate U-Boot `ba0a2763ef` moves the reservation import before ramdisk
allocation, guarding DT-less boots, and adds a read-only boot-control decoder.
Host tests pass, including corrupted metadata, stale suffix and no-write checks.
The source-order guard is not a runtime allocation test.

Live test plan: flash CI output to lk_a only, preserve lk_b and the prior
0d71414af7 recovery image; expect initrd outside SCP and a reserved SCP interval,
then require Linux USB/SSH transfer regression PASS. No SCP reset, decryption
or module reload is part of this experiment. Baseline transfer passed at
`local/live-logs/20260921T142334Z-172.16.42.1-regression-gate`.

CI `35611810150` passed all tests and image packaging. The flashable image
SHA256 is `99cc4f5c3c771c26f145a9de5b0b812910823eadd495935dcd775fe9aa682a22`.
Manifest verification passed and fastboot confirmed writing only `lk_a`.
The reboot command returned the usual USB disconnect; Linux recovery is
checked separately rather than treating that return code as a boot failure.

Live result on boot `a081e530-e467-4cea-8c49-2d89d97da9cf`:

- Initrd moved to `0xb746a000..0xb7fffe38`, below SCP.
- `/proc/iomem` now lists `0xb8000000..0xba2fffff` as reserved, matching
  the entire SCP region; the prior overlap is eliminated.
- `nothing,scp-boot-control-error` is zero and
  `nothing,scp-recorded-partition` is `scp_a`.
- Linux USB and SSH recovered. The first SSH attempt was simply too early;
  USB inspection showed Linux mode before the successful retry.

This is a live-proven memory-placement fix, not SCP firmware startup. Crypto
transport remains disabled and no remote-processor registers were written.

Two Linux warm reboots reproduced the same non-overlapping initrd placement:
`d99e401d-979d-4986-a660-7517ba824ba5` and
`01d702e6-e42f-4298-b76b-2465f0fb4015`. Regression gates passed:

- First boot, 32 MiB transfer:
  `local/live-logs/20260921T142734Z-172.16.42.1-regression-gate`.
- Second boot, baseline:
  `local/live-logs/20260921T143044Z-172.16.42.1-regression-gate`.
- Third boot, 32 MiB transfer:
  `local/live-logs/20260921T143239Z-172.16.42.1-regression-gate`.

The user confirmed normal display and touch after the first boot. These were
warm boots, not power-cycle or suspend/resume tests. The isolated bootm fix,
source guard and documentation are on U-Boot master `e8cee3eaa6`; its CI run
`35613343412` is pending. The running image remains candidate `ba0a2763ef`,
not a separately flashed master artifact.

U-Boot `2a693ef204` now implements a C secure decryption transport in
`board/mediatek/mt6878/tetris_scp_crypto.c`, with real SMC/cache/SHA256
adapters, input/output integrity checks, physical bounds and overlap checks,
temporary-material erasure and a non-retryable state after secure failure.
It is default-off (`CONFIG_TETRIS_SCP_CRYPTO`) and has no board/command caller.
Caller-side authenticated metadata, ATF compatibility and exclusive reservation
of the service page and image buffers remain mandatory, not implemented by
this transport. It does not load or start SCP by itself.

The mock secure-monitor test passes under address/undefined-behavior sanitizers.
CI `35609751074` passed those tests, cross-compiled the actual ARM64 adapter,
and completed the full U-Boot image build and packaging successfully. The
preceding offline-verifier CI `35608462624` completed successfully. No new
image was flashed and no secure call was issued on the phone during this work.

Trace certificate/context production and the secure backend against the
installed trusted firmware. Implement authenticated active-slot loading,
bounded memory allocation and error propagation as one loader operation.
Only after a valid region-info and SCP ready acknowledgement should the
mailbox/HF/sensorhub path be enabled and actual sensor samples tested.

The existing Linux SCP reset/recovery helpers consume prepared region-info;
they cannot replace the initial loader on a zero-handoff boot.
