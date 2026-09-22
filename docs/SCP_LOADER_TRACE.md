# SCP loader trace, 2026-09-21

Sensors remain Broken. Authenticated loading and secure handoff pass cold
testing; the latest firmware reaches the READY handler, but host readiness
completion remains blocked.

## r166: READY handler reached, host completion blocked

With U-Boot `bf75c572e1` and r166 CI `35719843739`, cold boot
`e14bf361-3811-44fd-8776-0467b865f8da` passed secure preparation. One
manual probe with the unchanged 26 MHz diagnostic vote returned 0 without
the r165 IPI 21 null-buffer BUG. USB/SSH remained available. The first
collection produced no firmware dump and no sensor samples.

The source-correlated READY-path message `scpreg.scpsys error` appears at
104.199164. `scp_A_set_ready()` checks this pointer before cancelling the
ready timer; the queued `scp_A_notify_ws()` loops while it is absent, before
setting `scp_ready[SCP_A_ID]`. Logger IPI 17 then fails `scp_awake_lock`'s
ready precondition. Timeouts at 114.141321 and 124.637063 show this is not
a completed startup. Do not count module-load success as ready.

The auxiliary `scpsys` driver matches `mediatek,infracfg_ao`. Its mapping
also supplies INFRA_IRQ_SET/CLEAR at offsets 0xb14/0xb18 and diagnostic
register reads. Fix the resource ownership and mapping rather than removing
the wait, setting ready manually, or adding competing MMIO owners.
The exact integration is still unimplemented.

Host evidence `/private/tmp/tetris-r166-scp-evidence/kernel-journal` has
SHA256 `3e85b7edfed0845fd77e4e7afe4b6607c11dcdd4377751877c615e9ec8987694`.
After saving it, a clean reboot returned Linux to boot
`bf25f907-0541-44df-94e4-9a323653250b`, systemd running, zero failed units,
USB/SSH present and no SCP/sensorhub/HF modules. No second probe was made.

## Bootstrap resource hypothesis

Result on r165: the vote succeeds, but does not prevent the failure below.

The matching vendor `scp_init()` calls `scp_resource_req(SCP_REQ_26M)`
before SCP device registration only when `scp_dvfs_feature_enable()` is true.
The current manual DT explicitly bypasses DVFS, skipping that vote as well as
the clock mux and calibration setup. This is a concrete startup difference,
not proof that it causes the observed rendezvous failure.

The installed pinned ATF implements SMC `0xc2000232` at payload offset
`0x2b5b0`. Operation 1 reaches `0x2b618`: it checks the request is <=7,
shifts its three resource bits left once and calls the registered resource
manager acquire callback (or release callback for zero). The service record
handler precedes its 32/64-bit IDs; the adjacent SCP loader handler must not
be confused with this handler. Vendor `scp_dvfs.h` defines RESOURCE_REQ=1,
SCP_REQ_26M=1, SCP_REQ_RELEASE=0.

r165 patch 0102 exposes only an opt-in diagnostic using the existing vendor
request function, not a new raw SMC interface. It holds the resource vote for
the diagnostic module lifetime to isolate this one variable. Ordinary probes
are unchanged. Host tests compile the patched helper and cover default-off,
competing DVFS ownership, negative/positive firmware errors, double acquire,
successful cleanup and a failed release that must not clear ownership.
The live result does not justify expanding the vote mask. Do not
enable full DVFS or disable watchdog based only on the sampled delay loop.

## First secure execution failure, 2026-09-22

U-Boot `9177841177758007927fb9b687378868cfe4a1fc`, CI `35703856720`,
LK SHA256 `659f360ffd561e9959d26e7e855fc8c03298d17ef03eda335ff2a013dadfd96a`,
was flashed only to `lk_a`. Kernel/rootfs remain r164. Warm boot was rejected
with preflight `-16` because TCM retained the previous loader. After full
poweroff, boot `84392df4-d857-48ed-b457-ae99ebdacacf` passed
`secure-handoff-prepared`, error 0, secure state 3/error 0, region-info `ok`.
The Linux SCP node and secure dump were enabled only after this success.

One manual module probe returned 0. At kernel time 66.235881, roughly
0.2 seconds after initialization, watchdog recovery began. The first snapshot
shows c0h0 PC `0x2e9da`, LR `0x1431a`, SP `0xd4fc0`; c1h0 PC `0x139f4`,
LR `0x139ec`, SP `0xd4dd0`. Both hart1 snapshots are zero. Automatic recovery
then reset SCP and eventually timed out; this is not a successful ready test.
No sensorhub/HF manager probe followed. USB/SSH survived. The first log is
`/private/tmp/tetris-r164-secure-scp-dmesg.txt`; the next clean Linux boot was
`81cf0a74-46fc-4c19-9f23-cd1029caa7eb`, with no SCP modules loaded.

Bounded read-only U-Boot console reads of retained plaintext firmware DRAM
resolve the first PCs. Physical addresses in this experiment equal the
observed firmware base `0xb8000000` plus runtime PC, NOT PC plus 8192.
These are trace coordinates, not portable addresses for a driver.

- `0x2e9ba` multiplies the delay argument by 13 and polls a counter at
  `[*(u32 *)0xd9350 + 0x8c]`. PC `0x2e9d4` is the polling load.
- Caller `0x14300` stores 1 in a byte indexed by `mhartid >> 16` at
  `0xe3b24`. `0x14308..0x1431a` waits for the AND of the first two bytes,
  calling that delay with argument 5 between checks.
- The next path references the string `send ready IPI` at `0x580b6` and
  passes IPI ID 22. This places the observed wait before ready notification.
- Core1 executes `wfi` at `0x139f0`; its sampled next PC is `0x139f4`.
  This alone does not explain why the second initialization flag is absent.

Capstone does not decode all vendor instructions in these windows. Unknown
instructions must remain unknown, not be silently skipped or assigned guessed
semantics. A sampled delay loop does not prove a stopped timer: its caller
also loops. Next investigation must explain the startup rendezvous and core1
initialization, not blindly alter clocks, mailbox tables or watchdog timeouts.
The matching stock DT also omits optional mailbox send/receive-status resources
and READY0 ID 9; those startup notices are not evidence of the root cause.

## r165 first dump: core1 audio ASSERT

Cold boot `1e5a3f0d-cc0d-41d5-a358-6ec813d779f0`, installed r165 and
U-Boot `9177841177`, passed secure preparation. The single opt-in probe held
the 26 MHz resource at kernel time 106.701537; watchdog followed at 106.903879.
The first dump completed at 107.259970, before any manual reset/reload.
Evidence: `/private/tmp/tetris-r165-scp-evidence/scp-dump.bin`, 11,454,272
bytes, SHA256
`b02bc1be5190c076889d7c0a86b1bd42e2c99f6a50e38500a7e5ec7aef6f6f88`.

The firmware ring log at dump offsets `0xe2000..0xe3330` includes:

```
[0.024](1)[0] audio_get_common_shared_mem() fail, AP view: 0x0, SCP view: 0x50000000, size: 0x0
[0.025](1)[0] [ASSERT] task: ipi_s, file: drivers/RV55_A/mt6878/audio/utility/utility.c, line: 149
```

Core1's return address `0xc9f2cc` follows the ASSERT call at `0xc9f2c8`
to `0x14650`. Its WFI snapshot is therefore post-assert, not proof of normal
idle. The actual rendezvous bytes at `0xe3b24` are `01 00 00 00`.
The earlier `0xdfb24` address was a disassembly transcription error; those
bytes are not the rendezvous flags. Core0 also logs I3C DAA/transfer errors;
their effect on sensor discovery remains untested after this startup blocker.

DRAM code is at file offset `0x1c8000 + runtime_pc - 0x700000`; this mapping
resolves the ASSERT caller and its utility.c string. These are coordinates
of this exact dump, not addresses suitable for hard-coding in drivers.
The helper at `0xc9f2d4` reads descriptors at SCP `0xb0000080/84/88`,
then an offset/size table, rather than simply reading AUDIO_IPI_MEM_ID.
Unknown vendor instructions remain undecoded.

Exact stock LK trace identifies a missing handoff candidate: `0x172ac` calls
`0x2d418` with bank ID 5 and dynamically allocated `adsp_shared_reserved`
address/size. The wrapper issues SCP_BOOT operation 8. Its surrounding DT
lookup names `mediatek,reserve-memory-adsp_share` and `shared_memory`.
Pinned ATF operation 8 calls `0x2b740`, which validates the bank (0..5),
address and size before storing a 12-byte bank descriptor. Current U-Boot
does not issue operation 8. This is evidence for the next investigation,
not yet proof that registering any arbitrary buffer is sufficient: establish
the complete descriptor/table layout, DT allocation and memory ownership first.
Do not conflate this bank with SCP feature-memory ID 4 or bypass the ASSERT.

No sensorhub/HF modules were loaded after failure. Clean recovery boot
`1c647422-1fca-4bcf-b7a7-6f4d7f3f6ed1` restored USB/SSH without SCP modules
or failed systemd units. No further probe has been performed on that boot.

## Runtime preparation progress, 2026-09-22

Real ATF decryption now passes on r164: U-Boot `8066a9a1ee`, CI
`35701102610`, boot `ccf7199a-cd40-401b-a0c8-90e8f7b3018d` reports
`plaintext-verified`, error zero and firmware region-info size 60.
Both component plaintext hashes passed. The 32 MiB USB/SSH regression gate
passed at `20260922T080034Z`. This build does not touch TCM or release reset.
The default-off TCM diagnostic `d965233d2f`/CI `35702796137` also passed
on hardware: boot `7249e562-fff9-4cb8-bd1c-32c492064ae2` reports
`tcm-verified-reset-held`, error 0, region-info `ok`, size 60; USB/SSH
transfer passed at `20260922T081548Z`. Its ordered-write, bounds, clear/copy
and readback tests pass under ASan/UBSan. It disables the Linux SCP node until
the secure handoff is implemented. `9177841177`/CI `35703856720`
adds that registration; its later hardware result is recorded above. Earlier `c3700615cb` CI
failed on a compiler-macro collision and was superseded without flashing.

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
This patch neither enables secure dump nor creates region-info.
Commit `68516cc`, CI `35692283994` completed successfully, including the
exact-source UBSan suite, kernel build and image packaging. Verified images
were clean-flashed to super/userdata on 2026-09-22. Boot
`b8eddccf-112e-40a9-942e-13c67fc8b23c` reports package r164 and kernel #165.
Display/touch were confirmed by the user; the 32 MiB USB/SSH regression gate
passed at `20260922T072618Z`. No SCP module was loaded, region-info remains
zero, and there are no sensor samples. The new valid-handoff recovery path
therefore remains hardware-untested. See CURRENT_STATUS.md for image hashes.

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
`0x24e2f8`; it is not a universal constant. Additional trace at
`0x7e62c..0x7e668` resolves its source to the string DT property `scpctl`
passed through `0x694a4`; a missing property yields zero. The same function
reads `scp-sram-size` into `0x24e2f0`, `secure-dump`/`secure-dump-size`,
`scp-protect`, `scp-mem-tbl` and `memorydump`. After the loader returns,
its caller also invokes `0x2d248`,
which passes the allocated base and base + `0x2300000` to `0x7ef84`, followed
by `0x2d58c`. The latter allocates `0x3a0000 + secure-dump-size`, registers
it through SCP boot SMC operation 0, and then configures EMI region 27;
the former configures region 26 for the firmware reservation. The pinned
LK backend `0x7ef84` chooses SMC `0x82000415`, operation 0, with start/end
shifted right 12 and the region ID, rather than passing the local permission
words to this backend. ATF entry `0x58e80` dispatches this service to
`0x2f750`; operation 0 calls `0x2f618`. The deeper trace shows `0x10300`
validates/normalizes page boundaries, `0x10370` restricts region IDs to 1..64,
and `0x10380` makes all but IDs 8/10/11/19 one-shot per boot. Thus 26/27
cannot be retried after registration. `0x2d61c` writes their boundary/enable
registers. The new diagnostic preserves this exact boot-only call order.
These post-load operations must pass hardware tests before declaring the
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
