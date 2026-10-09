# Original LK RV33 Boot Trace

## Identity And Scope

Public container: https://github.com/R0rt1z2/fenrir/blob/59b92eb6c1a82c0d5270f750b87e93758cad6d5f/bin/tetris.bin

- Container SHA256: `4468fb4af86cda62ff93050dfd85373fdb7222323d4b38737531117f4e58aa6b`.
- First LK payload: 1681136 bytes, SHA256
  `f8e8d492597ec13c7568f927832020c1e971f98ac8b5f8921eb0e3815bc25c50`.
- Signed payload and header digests, root signature, delegated leaf signature
  and independently supplied LK SPKI root pin are verified offline.
- This is NOT the earlier `431e0551...` LK payload. Every offset below is
  validated against the new exact signed payload; no old binary identity is assumed.
- The published container's Nothing OS build/SKU is not established by its
  signature alone. This is a pinned caller reference, not proof that its fixed
  SRAM copy span matches the current handset's signed firmware revision.
- No payload/certificate bytes are stored in the repository. No decryption,
  native compilation, hardware operation, or secure service execution occurred.

`audit_gpueb_lk.py` verifies the container and disassembles the actual RV33
caller/selector/backend/reset sequence. `test_gpueb_lk.py --lk <container>`
tests rejection and the exact trace. Dependencies: Python cryptography and
capstone. Unicorn is not required: the installed macOS Unicorn library exited
with SIGILL during the attempted synthetic fragment test; this is NOT hardware
evidence. The checked-in audit is explicitly static, with no emulation claim.

## Exact Transform Caller

The RV33 name is at LK payload offset `0xc9352`, with its caller at `0x1ed80`.
`0x1ed94` calls generic section loader `0x74da0`, passing partition `gpueb`,
component `tinysys-gpueb-RV33_A`, destination beginning at mapped buffer +0x18,
and a 1 MiB limit. This is NOT the BL2 xfile/EXPDB logger path.

The section loader's non-special-header path calls `0x7e348 -> 0x920e4` for
image security processing. OID table index 15 at `0xd8ee0 + 15*64` is
`2.16.886.2454.2.9`; its INTEGER parser is `0x94d3c`.

After big-endian INTEGER assembly, `0x94fe4..0x95000` extracts:

- selector = `(signed_word >> 16) & 0xf`, stored in global `0x251a94`;
- mode = `(signed_word >> 20) & 0xf`, stored in global `0x251a98`.

The verified GPUEB slots have signed word `0x10000`: selector 1, mode 0.
Mode 0 chooses wrapper mode 1; `0x921cc -> 0x88078` passes the selector through
`0x8203c`. Backend selection `0x16ea0` returns 2 and selects `0x820a0`.
That backend writes a descriptor into service page physical `0x48401000`:

| Page Offset | Type | Source |
| --- | --- | --- |
| +0x40 | u64 | image physical address |
| +0x48 | u32 | ciphertext byte count |
| +0x50 | u64 | physical pointer to wrapped material |
| +0x58 | u32 | material length, 32 bytes |

The caller cache-maintains page, image and material. `0x8216c` places
`0xc2000133` in x0 and selector 1 in x1, with x2..x7 zero before calling the
SMC wrapper `0x188dc`. This is a demonstrated **LK caller ABI**, not a kernel
permission to call the service after boot-stage/page locking.

Main's existing pinned ATF trace identifies this service as
MTK_SIP_LK_AES256_CBC_DEC_FW and service-page initialization as `0xc200010b`.
The underlying ATF payload was not available to this worker for re-auditing;
retain its exact existing pin and service-page ownership/lock restrictions.
No live transform is proposed until main reviews the full authenticated
RV33 component path using that existing ATF implementation.

## Actual LK Load And Reset Writes

The RV33 entry is `0x1eb88`. It reserves a 1 MiB firmware staging allocation
aligned to 64 KiB, and a separate 6 MiB `me_GPUmputab_PMA` allocation aligned
to 64 KiB. The normal allocation branch requests addresses below 2 GiB;
the alternate platform branch uses the range 0x240000000..0x340000000.
These are allocation constraints, not a fixed physical address handoff.

Before loading, `0x1ecd0 -> 0x7ef84` submits the protection-table range:
`start`, `start + 0x600000`, region 12. Backend 2 calls `0x82000415` with
x1=0, x2=(start >>12)&0xffffffff, x3=((start+0x600000)>>12)&0xffffffff,
x4=12, x5..x7=0. This is the precise LK call, not proof of secure-handler
permissions or inclusive/exclusive end semantics. Do not reinterpret it as a
generic EMI unlock. The matching ATF handler must be audited before reproducing
the call; its range and ownership must accompany the authenticated boot handoff.
The wrapper returns the secure result, but the RV33 caller proceeds directly
from `0x1ecd0` to address preparation at `0x1ecd4` without checking it. A new
owner must reject protection failure rather than reproduce this unchecked path.

At `0x1edd4..0x1ee18`, after successful security processing and cache upkeep:

1. Write `0x00010f00` to MFG-RPC address `0x13f91030`.
2. Write zero to GPUEB reset/config address `0x13c60600`.
3. Clear the entire SRAM range `0x13c00000/0x40000`.
4. Copy `0x3f2b8` bytes in 32-bit words from image data at buffer +0x18 to
   SRAM beginning at `0x13c00000`.
5. Set GPR0 to allocated firmware address (low 32 bits), GPR1 to zero,
   GPR23 (+0x5c) to zero, and GPR6 (+0x18) to allocated protection-table PA >>12.
6. Set GPR18 (+0x48) from the stock DT `gpueb-diagnosis-mode`, default zero.
7. Write `0x3f00000b` to `0x13c60600`.
8. Poll GPR2 (+0x8) for `0x55667788`, with an explicit timer-based timeout.

Addresses are source facts only. Do not execute them as a standalone MMIO plan:
MFG-RPC, supplies/clocks, EMI protection, reservations and exclusive processor
ownership must be established first. The current signed slot payloads are
156064 bytes, smaller than the stock copy span: validate transformed image
layout/staging capacity/zero padding for this firmware revision before any
upload. The 24-byte buffer prefix is a boot-loader allocation prefix; it is
NOT proof of an ELF header or an offset to discard from ciphertext.

The stock clear spans core, GPR and mailbox SRAM together. Therefore the earlier
disjoint-claim proposal alone is insufficient to reproduce cold loading:
a single controller/owner must coordinate all three regions before clear,
then lend GPR/mailbox access to session/controller clients. Do not combine
whole-SRAM remoteproc claims with the frozen client's independent GPR claim.

## Real OFF Still Unproven

On timeout the function prints diagnostic registers, writes marker
`0x5a5a5a5a` to GPR0, and returns error -13. It does NOT establish physical OFF
or acknowledge cessation of DMA. This is not a valid kernel `.stop()` routine.
The reset-hold zero write before upload is evidence of a reset sequence only;
it does not prove a complete OFF transition or safe rail/domain removal.

The cached 4 MiB UFS boot-LUN/preloader dump (SHA256
`0be9c0df9c5d5db641744996630b95920f6e69dcb1ca340511f7d75886676f00`)
contains a GPUEB_SHARED reservation label but no RV33 loader name or the
AES service label. This is not evidence of a preloader firmware/OFF path.
The stock LK entry also gates boot on capability bits at `0x1c001eb4`:
bits 31:30 must select 3 and bit 13 must be set (bit 12 rejects the path).
These source checks and actual reserved-memory allocations must be respected,
not replaced by hard-coded successful observations in a kernel driver.

The exact device-modules commit `ee2be53cb75670b548948636a0db1d1ff112bf12`
has no GPUEB stop/reset implementation in its GPUEB driver or MT6878 GPUFREQ
driver. `drivers/gpu/mediatek/gpueb/gpueb_init.c` only consumes inherited GPR,
mailbox and reserved-memory state; its platform `.remove` is NULL. The reset
symbol in `gpufreq_reg_mt6989.h` is another SoC's definition and cannot supply
MT6878 OFF evidence. No vendor module-unload path is a substitute for `.stop()`.

Keep `0120`, `0122`, `0123` frozen and inactive. Main can now review an actual
selector-1 GPUEB transform call against its existing U-Boot crypto helper,
requiring authenticated header/ciphertext and verified post-transform digest.
Then inspect plaintext layout privately, without committing it. The next
runtime gate remains closed until the matching GPUEB stop/reset acknowledgement,
resource controller ownership and boot-channel ordering are audited.
