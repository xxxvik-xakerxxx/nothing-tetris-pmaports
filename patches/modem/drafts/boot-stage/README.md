# B4.1 BL33 modem bootstrap draft

Not shipping or enabled. No phone access, local C builds, shared source edits,
commits or workflow edits. Signed-input caller remains frozen/main-owned.

## Concrete NS write authority

The matching ATF payload SHA256 is
`05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
The matching complete LK image SHA256 is
`29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f`.
Offsets below are payload-relative, excluding the 512-byte MTK header.

* ATF `0x2761c..0x276a0` builds BL33's descriptor from the preloader parameter:
  descriptor attributes at +4 clear bit5 and SET bit0 (NON_SECURE); PC at +8
  comes from parameter +16; SPSR at +16 is 0x3c5 (EL1h) or 0x3c9 (EL2h),
  selected by `0x19bb4`, not by the LK image's contents.
* ATF context construction `0xc4cc..0xc5bc` selects the NON_SECURE case for
  `(attributes & 0x21) == 1`; `0xc598` ORs bit0 into saved SCR_EL3 at context
  +0x100. The same context stores descriptor SPSR/PC at +0x118/+0x120.
* Exit `0x9df4..0x9e14` restores that SCR_EL3, SPSR_EL3 and ELR_EL3 and ERETs.
  U-Boot replacing the same LK partition via the unchanged BL2/ATF handoff
  therefore executes in the SAME NS world/selected EL, not a new trust class.
* Pinned U-Boot `bffec9306e7c40a432d79deefb450230c2ee2360`,
  `arch/arm/mach-mediatek/mt6878/init.c`, identity maps low peripherals as
  Device-nGnRnE. `arch/arm/cpu/armv8/start.S` handles entry at EL1/EL2;
  this draft rejects any other CurrentEL before its first hardware access.
* Matching LK's `0x81794..0x817a8` directly writes TOP physical 0x10000000,
  then `0x54ad4..0x54b80` directly writes SPM 0x1c001e00/f24,
  NEMI 0x10270088 and IFR 0x10001c48/58 from that NS BL33 context.
  The higher virtual alias in LK is page translation, not secure-world entry.

These are source/binary-grounded permission evidence for this unchanged boot
chain. No concrete DEVAPC/NS-denial predicate has been identified on those
resources in that path. A separate caller boolean claiming permission adds no
evidence and is NOT required. This is not proof for arbitrary ATF, changed BL2,
different hardware security configuration or an inherited Linux state. The
existing stored-ATF profile check is a profile guard, not runtime attestation.

## Actual bounded caller

`tetris_modem_bootstrap_once()` copies its fixed-size input, validates every
active EMI range, policy and remap BEFORE hardware access, and performs:

1. Existing pinned ATF-profile verification; exact strict OFF preflight of
   PWR_ON=0, ACK30/31=0, EXTISO=3, IFR9/11 and NEMI6/7 protections set.
   Inherited ON or partial state returns EBUSY without corrective writes.
2. Actual existing EMI transaction per active slot: policy reads, ATF range
   command0 once, range/enable/policy readback. Preserve ATF -4 as first error;
   disabled observation alone never grants its one-shot guard.
3. Actual existing remap command1/2 and six masked register readbacks; then
   top-level CCCI request8 as LK `0x2542c -> 0x27bfc`. ATF `0xbec0..0xbed0`
   writes the remap-admission byte at 0x488f665c and returns zero. This is NOT
   POWER_CONFIG/8, which is a no-op. No invented lock-readback API is used.
4. LK ordering: TOP bits8/9 clear, EXTISO3 clear, ONLY PWR_ON bit2 set,
   bounded ACK30 AND ACK31, release NEMI6/7 -> IFR11 -> IFR9.
   Each write is followed by masked readback/poll; unrelated bits survive.
5. Actual LK FID c200040b/request6/subcommand1, zero arguments, status zero
   and boot-enable x3=1. This calls ATF `0xb598` and is NOT a reset assertion.
6. Actual LK POWER/7 up to 100 times with 20ms spacing. ATF `0xb668` selects
   status words (this query has selector writes) and returns four flag words
   packed in x2/x3. Require BOTH equal `0x0000000100000001`, exactly the
   four-equal-one predicate used by kernel POWER/3 at `0x1a1ec`.

Every loop is finite. One attempt per boot; snapshot contains first error,
failed stage/slot/address/value and last actual reply. No retries, generic
domain-off, reset, synthetic READY or DT publication on failure.
Power ACK waits are stricter than LK's ACK30-only wait. Bus-clear readback is
also added conservatively; neither strengthening has live evidence yet.
Finite polling does not catch synchronous bus/permission aborts. Source-backed
same-BL33 authority narrows that risk; only the separately approved controlled
hardware experiment can test it. Do not ship this as a USB-safe live result.

## Finite failure cleanup

Only AFTER our first MMIO mutation, and after strict cold OFF/profile/range
preflight, a failure invokes LK `0x54d28..0x54e44` OFF ordering once:
IFR9 set/ack -> IFR11 set/ack -> NEMI6/7 set/ack -> PWR_ON bit2 clear -> BOTH
ACKs off -> EXTISO3 up/readback -> TOP bits8/9 gate/readback. The last step is
LK `0x816d4..0x81768`, specifically the gate write at `0x81754`.
Each poll is at most 10000 reads at 10us spacing. Cleanup has no SMC, no
boot-enable change, no reset and no retry. A failed bus protection stops BEFORE
power-off; failed ACK-off stops BEFORE isolation-up or clock gates.

The real transaction's `mutated` flag records its own MMIO action, NOT permission
or an inherited-state proof. Inherited ON, failed input/profile/EMI/remap or
request8 admission NEVER enters cleanup. The primary report/error remains
unchanged; a separate cleanup record retains its own first failed stage,
register/value, poll count and error. Completed cleanup is hardware OFF closure,
not rollback of one-shot EMI/remap guards or permission for another start.
Both-ACK waits and added readbacks are deliberately stricter than LK. Synchronous
aborts still cannot be recovered by this finite polling path.

Success leaves power ON/boot-enable1, like matching LK. It does not substitute
for CCCI FSM's boot handshake. Matching vendor
`ee2be53cb75670b548948636a0db1d1ff112bf12`,
`drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c:md_start_platform()` then
checks kernel POWER/3, reads POWER/2, and powers OFF before normal CCCI ON/start.
Do not invent an OFF handoff/new power-cycle-latch contract in this caller.

## Scoped ownership, not global no-repower

Call only synchronously on the boot primary CPU inside the existing authenticated
loader/LMB/cache lifetime before Linux, AP DVFSRC/VCOREFS INIT, CCCI FSM, genpd,
suspend or SPM-idle entry. No secondary/AP task may start competing callers.
The real ATF boot-enable stores found are LK POWER/1, LK POWER/5 and kernel
POWER/0; this transaction invokes only POWER/1. FLIGHT is not required, not a
reset and not a universal no-repower bit. Enumerated MD idle callbacks are
invoked through explicit idle/SPM entry; this bootstrap invokes neither those
entries nor VCOREFS INIT. Unknown secure/PCM effects remain a profile/lifecycle
risk, not an invented global permission bit or a fake AUTH result.

## Integration and real remaining prerequisite

Main owns the existing U-Boot loader and packaging. This draft has no shipping
registration, board hook, Kconfig or DT consumer. Before enabling its caller:

* Keep the manufacturer-authenticated snapshot/private firmware lifetime through
  ROM/DSP placement, service-bank initialization and cache cleaning. Call after
  those actual operations, using their exclusively LMB-owned physical window.
* Produce ALL active stock EMI rows from that authenticated layout/service plan.
  The input is a 12-row slot-ordered table, NOT an authentication assertion.
  The helper's actual B4.1 policy supports 32..38 and 41..43 only. Any active
  39/40 fails in input validation before SMC/MMIO; do not silently omit required
  rows or replace slot40's preset path with the ordinary range command.
  Resolve stock role7/slot39 and slot40/preset producer/activation from LK before
  feeding the real bundle. This is an actionable incomplete mapping producer,
  NOT a speculative NS-write ban. Synthetic one-row fixture is not that producer.
* On success retain actual ROM/SMEM/layout identity, six remap readbacks, EMI
  evidence, and actual BROM words for the existing validated handoff/tag owner.
  This report alone is neither authenticated metadata nor a complete CCCI tag
  list. Do not export a READY boolean or mark SIM/calls supported.

## Verification

Local static check only:

```sh
python3 patches/modem/drafts/boot-stage/check_bootstrap.py
```

Independent Ubuntu native CI (no shared workflow edits here):

```sh
CI=true python3 patches/modem/drafts/boot-stage/check_bootstrap.py \
  --native-ci --uboot upstream/u-boot
```

It compiles actual draft caller/secure transport plus exact pinned existing
layout/EMI/remap helpers with Wall/Wextra/Werror and ASan/UBSan. Only profile
I/O, SMC, MMIO, timer and CurrentEL are synthetic. 37 process-isolated cases
cover every transition failure, both ACKs, stuck bus/clock/isolation, ATF -4,
readback mismatch, request8/release errors, wrong boot-enable, four-one BROM,
delayed completion, timeout, unsupported slot, bad profile/policy, inherited
states, each of six cleanup failure stages, first-error preservation, no late
isolation on ACK-off failure, and no second transaction's hardware access. It does NOT
authenticate firmware or prove functional SIM, live NS writes or portability.

For AArch64 packaged-object smoke include BOTH new C files and their headers
against real pinned U-Boot board includes and existing helper objects. No source
or host fixture substitutions in that compile. Native and AArch64 results are
pending main CI; no local C build/execution has been performed.
