# Signed bundle caller draft

Not included in APKBUILD, kernel Kbuild, DT, or modem startup. Frozen PSS32,
MTK decoder, reservation and startup-scope files are unchanged. No phone
operations, SMC, protected RAM mapping, or local C compilation were performed.

## Concrete implementation

`mt6878_md_fw_request()` retains the immutable Linux firmware blob without a
second full allocation. `mt6878_md_fw_prepare()` makes one private snapshot
for caller-owned mutable input. Both use the same authentication routine for ROM,
DRDI and DSP headers through the public fixed manufacturer-root decoder,
checks the actual payload digests, and only then derives bounded CHECK_HEADER
v6 layout metadata. Publication is all-or-nothing; source and crypto contexts
are released on failure; on success the crypto contexts are freed and the
verified source is retained until the last reference is released (either
`release_firmware()` or `kvfree()`, never both).
`mt6878_md_fw_copy_payload()` copies bounded slices from that same verified
snapshot into ordinary caller-owned memory. It never reopens the firmware file
or relies on a mutable original input. No input pointer escapes. Authentication
runs outside device/scope locks. Firmware API clients must respect its const-data
contract; the firmware blob is not a protected MD RAM snapshot.

`mt6878_md_fw_place_b41()` now consumes that same verified source, the cached
layout, and signed service fields. It runs the **existing** B4.1 SMEM planner,
copies only ROM and DSP directly into exclusively owned ordinary staging RAM,
and returns the existing `tetris_modem_boot_plan` format. DRDI mode 3 is not
copied; gaps/tail are untouched. Aliases, insufficient capacity, unsupported
gear and service-planning failures are rejected before any output mutation.
There is no second bundle/header scan, crypto pass, firmware reread, snapshot
allocation or complete-image scratch buffer during placement.

The duplicate layout validator has been removed. CI consumes the existing
pinned `tetris_modem_layout.c`, `tetris_modem_layout.h`, and
`tetris_modem_bundle.h` directly from U-Boot git objects, verifies their SHA256s,
and links the planner into this draft. The only Linux adaptation is the layout
header's `stddef.h` include to `linux/types.h`; implementation bytes are unchanged.
The source hashes and revision are locked in `check_stock_input.py`.

This is a Linux staging adapter using the existing loader's data contract and
implementation, **not a change to U-Boot's shipping `load_slot_b41()` caller**.
It neither maps physical MD RAM nor synchronizes it for execution. A physical
consumer must separately establish NS access, execution exclusion, ownership
and coherency before copying staged data there. No API here fabricates those gates.

This is source-file integrity, **not installed-RAM authentication or hardware
admission**. Capacity is only a size bound. A successful result cannot satisfy
EMI, NS access, cache coherency, reservation ownership, or BROM readiness.
No chosen digest, synthetic positive AUTH, reset assumption, or generic
ENOKEY/EOPNOTSUPP startup adapter is supplied.

Profile/framing: U-Boot bffec9306e7c40a432d79deefb450230c2ee2360,
`board/mediatek/mt6878/tetris_modem_load.c` and its signed bundle/layout helpers;
trust chain: the frozen `mt6878_md_mtk_cert.c` and `mt6878_md_pss32.c`.
Only their supported B4.1 plaintext, RSA2048/PSS32 delegation profile is accepted.
Other firmware profiles require evidence, not permissive fallback.

## Independent CI Commands

From the pmaports repository (no workflow edit needed):

```sh
python3 patches/modem/drafts/signed-input/check_stock_input.py
CI=true python3 patches/modem/drafts/signed-input/check_stock_input.py \
  --native-ci --kernel ../linux --uboot ../u-boot-mt6878 \
  --stock-container /path/to/authentic/B4.1/md1img.bin
CI=true python3 patches/modem/drafts/signed-input/check_stock_input.py \
  --aarch64-object-ci /path/to/prepared/arm64/kernel --uboot ../u-boot-mt6878
```

Native CI requires OpenSSL development headers and Python cryptography plus
the actual factory container supplied as a private CI input. It cannot pass
without an authentic public-root-positive input; no synthetic root substitution
is used. The Python oracle separately verifies the same input snapshot, then
the actual kernel ASN.1 decoder, production PSS32/MTK/caller C run with real
OpenSSL raw RSA and SHA256. Only ordinary allocation/refcount/firmware APIs are
doubled. These doubles do not model concurrency or hardware ownership.

Tests cover all three member header/payload corruption paths, incomplete
certificates, layout capacity rejection, first crypto errors (including positive
error normalization), source mutation after publication (both identity and
all three payload copies remain unchanged), copy bounds and unchanged outputs,
refcount lifetime, zero-copy firmware retention through the final reference,
allocation/algorithm faults and firmware release on success/failure. Placement
tests compare layout and SMEM output to the existing ROM planner, hash the two
actual placed spans, check gaps/tail/guard bytes and pre-write error atomicity,
and assert no crypto calls or additional tracked allocations during placement. They do
not claim exhaustive layout fuzzing or concurrency validation.
Native CI [37988706465](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37988706465)
passed at `10a651c` using the actual public B4.1 `modem.img` (90,214,400 bytes,
SHA256 `b15207a948125439a5957224d65774d9d44c558c6eb285372a520b27b8d7d6c5`).
The independent manufacturer-root oracle and production C crypto/lifetime/fault
suite passed with ASan/UBSan. The firmware API route avoids a second full
source allocation by construction; no handset peak-memory benchmark is claimed.
ARM64 object CI remains pending. Locally only static checks were run.

The native path reuses main's `check_mtk_cert.native_ci()` unchanged, including
its separate kernel-decoder TU and upstream warning policy; no second copy of
the OpenSSL ASN1_NULL/signedness fix is maintained. Temporary fixture paths and
unused synthetic-vector generation are redirected with scoped Python test
patches; verifier functions, source and public root are never patched. Main's
native fixture ABI (the fixture filenames and `HERE` input directory) is an
explicit dependency until it exposes a dedicated builder API.

Our production/native fixture still uses `-Wall -Wextra -Werror`, ASan and UBSan.
The ARM64 mode builds only a temporary
composite object; no source-tree edits, module installation or hardware calls.

## First Startup Blocker And Missing API

Pinned vendor ee2be53cb75670b548948636a0db1d1ff112bf12:

- `drivers/misc/mediatek/eccci/fsm/modem_sys1.c:145` calls `start_platform`
  before normal `power_on` and `let_md_go`; failure aborts startup.
- `fsm/md_sys1_platform.c:985` polls `MD_CHECK_DONE` (POWER_CONFIG request 6,
  subcommand 3) up to 100 times, then reads `MD_CHECK_FLAG` (subcommand 2),
  powers off, and returns the BROM-check result. Flag words are data, not errno.
- `inc/modem_secure_base.h:38` distinguishes `MD_LK_BOOT_UP` (1) from
  `MD_KERNEL_BOOT_UP` (0). `md_cd_let_md_go` uses the latter only later.

Therefore the stock kernel expects the initial MD BROM stage to have completed;
normal kernel POWER0 is not a demonstrated replacement for LK bootstrap.
The existing U-Boot loader explicitly reports `no reset/SMC/ready tags`
(`tetris_modem_load.c:135`). The main evidence plan records a cold observation
with all 12 EMI slots disabled: loading bytes alone has not established usable
protection/remapping or a completed BROM handoff.

The concrete missing binding is the **boot-stage production SMC transport and
caller** for the already implemented `tetris_modem_program_emi_range()` and
`tetris_modem_program_remap()`, followed by the matching first BROM boot/reply
sequence. The headers explicitly state that neither production caller is
installed. `tetris_modem_remap_ops.smc` needs the LK CCCI reply ABI, not the
kernel ABI: operation 2 returns register data in x0, not a status code. Range
operations additionally need genuine one-shot slot ownership and the exact
approved range/policy, not merely a disabled-slot observation.

Minimum dependency sequence for the main bootloader owner:

1. Authenticate source and platform, reserve complete ROM/SMEM windows and
   establish real NS access/coherency and exclusive startup mutation ownership.
2. Establish an execution-inhibited state throughout range/remap/load changes.
   Physical exclusive OFF may be an alternative to reset, but persistence
   across stock ATF callbacks and the OFF-to-ON/BROM boot-latch semantics must
   be established first. POWER5 boot-enable=0 alone is not reset. No global
   fictional no-repower flag is required or asserted here.
3. Program/read back the source-derived range/policy and remaps through the
   admitted boot-stage SMC ABI, preserving the first failure and not retrying
   a consumed/partially programmed transaction.
4. Perform the exact stock initial power/boot sequence and obtain genuine BROM
   completion. Only then publish a complete handoff and enter kernel first-start
   power/CCIF/DPMAIF/FSM handshakes; ports existing is not SIM readiness.

Steps 2-4 are not implemented by this draft. The first unresolved physical
prerequisite is the proven execution-inhibit/boot-latch contract for the
boot-stage mutation window, not a lack of another authentication boolean.
Bootloader changes remain with main; this draft deliberately does not install
a guessed SMC/reset sequence or relax hardware gates to make CCCI probe succeed.

## Actionable Matching LK/ATF Flow

Static disassembly only, no binary execution or phone access. LK full-image SHA256:
`29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f`.
ATF declared-payload SHA256:
`05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
Offsets below are relative to their payloads (ATF base `0x48800000`).

1. LK `0x253cc` calls `0x81804`, before power ON at `0x254ec`.
   The 12-row EMI loop reads flags at row+12: bit0 absent skips the row;
   bit7 skips programming; bit1 calls `0x7ee38` (preset) before `0x7ef84`
   (range). Row fields are base64, size32, flags32, logicalID32, slot32.
   It forms end as base+size. Neither helper result is propagated by the loop.
   A new caller must check its own exact range/policy readback and preserve the
   first failure; importing the loop's ignore-errors behavior is not acceptable.
2. LK `0x2542c -> 0x27bfc` submits **top-level** LK CCCI request8, the
   remap-lock request. This is not POWER_CONFIG subcommand8 (a no-op).
   The wrapper only distinguishes -15. Do not infer exclusive EMI slot ownership
   or full successful protection from this call or from a disabled slot alone.
   ATF range guard `0x10380` consumes a slot before programming, so absence of
   its enable bit is not proof that the one-shot guard is unused.
3. LK `0x254ec -> 0x8176c` clears TOP bits8/9 then invokes the exact MD ON
   routine `0x54ad4`. Next `0x254f0 -> 0x27cd4` sends
   `(FID=0xc200040b, request=6, subcommand=1, remaining args=0)`.
   The wrapper returns -1 for any nonzero x0, but this parent branch ignores
   that result. The ATF inner POWER/1 writes boot-enable=1 and IFR bits; this
   is a **boot trigger, not BROM completion**. A new caller must not publish READY
   because either the power routine returned or boot-enable reads as 1.
4. The matching kernel subsequently polls POWER/3. Its ATF helper `0x1a1ec`
   reads four words at `0x1040d834/838/83c/840` and returns x0=0 **only when all
   four equal 1**, otherwise x0=1. Helper `0x1a234` (POWER/2) returns those same
   raw words in x0..x3; x0 is flag data, not errno. Thus the exact completion
   predicate is known; its physical truth and correct admission still require
   a powered, owned, authenticated bootstrap, not manufactured values.

For main's bootloader experiment, LK POWER/7 exposes these flags in packed x2/x3
(`0x0000000100000001` each when all four are 1), with x0 status and x1 packed
boot-status words (`0xb668`). It also writes selector `0x1020e700` twice; it is
**not a read-only probe**, and has not been called here. Kernel POWER/3 cannot
simply be called at the boot-stage admission gate. An explicitly approved,
powered LK POWER/7 observation is a concrete candidate to test BROM completion
before an OFF handoff, not an already proven or implemented bootstrap policy.
The OFF-to-ON waiting-state semantics and EMI/remap ownership still must be
closed by main before the existing CCCI owner can be bound to a genuine handoff.
