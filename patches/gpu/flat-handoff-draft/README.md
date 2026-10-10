# Authenticated flat retention draft (not packaged or enabled)

The new cold result confirms raw primary bytes, not an ELF/PT load table.
This candidate uses the existing strict GPUEB root/leaf/header/ciphertext
verification and selector-1 transform with signed post-plaintext verification.
It allocates and retains a private 1 MiB LMB range aligned to 64 KiB below
2 GiB. No caller-supplied readiness or authentication flag is accepted.
Production transform-only remains unchanged and continues erasing its primary.
Only two reviewed signed plaintext digests of exactly 156064 bytes are accepted;
these are firmware identity pins, not per-device calibration.

## What the flat map actually proves

Independently authenticated B4.1 LK payload SHA256:
431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a.
The RV33 reader receives backing RAM +24 at 0x1ed90/0x1ed94. It reads the
member's declared size, transforms in place, verifies the signed postdigest.
The startup loop 0x1ee08..0x1ee18 copies from that same pointer to SRAM base
0x13c00000 in four-byte units, with no relocation or segment parser.
It copies 258744 bytes. The signed primary contains only 156064 bytes.
The extra 102680 bytes are not loaded by that member read and not authenticated.
The preceding full 1 MiB cache maintenance at 0x5e74 is not decompression.
No source-proven zero backing/BSS initialization makes that excess acceptable.

Thus the candidate describes signed bytes [0,156064) at SRAM offset zero.
It does NOT claim those bytes are the complete executable SRAM footprint.
LK explicitly clears the whole 256 KiB SRAM bank before copying, but that
does not prove firmware tolerates replacing LK's excess with zeros. Neither
the retention arena's zero tail nor the LK +24 prefix is an upload segment.
No entry-point value is invented. No bytes are uploaded by this candidate.

## Ownership and next executable integration gate

This is an independent opt-in U-Boot producer, not yet wired to board startup.
Copy C/header into the board draft and build its object in native/ARM CI with
existing layout/security/crypto dependencies. Native fault fixtures must cover
wrong signatures/digest/profile, allocation/map/range failure, crypto failure,
aliases and successful retention/discard. Local static tests are not these gates.
Root pin must come from the existing independently pinned board constant.
Only describe the opaque handle before transferring it; discard is a pre-transfer
operation. The crypto ops table must outlive the retained handle.

LMB is only U-Boot ownership, not Linux reservation. Main must atomically publish
a dedicated reserved-memory/no-map range plus a consumer phandle and bounded
length/digest metadata before transferring ownership. Do not put plaintext in
chosen. Any publication failure must erase/discard the private arena. The
consumer must validate full reservation, bounds and digest before using it.
This draft deliberately does not assert the unknown 24-byte GPR0 prefix ABI or
publish its base as GPR0. GPR6's separate 6 MiB EMI arena remains a separate gate.

Real startup remains blocked by the stock copy excess and GPR0 prefix/DRAM ABI;
retaining signed bytes solves input lifetime, not those boot dependencies.
The next controlled cold boot should test retention/reservation and digest only,
with no SRAM upload, reset release, MFG, rail, EMI or IRQ activation.

## Stop boundary

LK writes reset zero at 0x1edf8 and releases with 0x3f00000b at 0x1eee8;
BOOTREADY is GPR2 == 0x55667788, not the session-ready GPR13.
Reset readback and Linux synchronize_irq prove neither DMA idle nor physical OFF.
ATF GPUEB_CONTROL c2000530 has no proven OFF opcode: matching handler 0x184c8
returns zero for opcode zero and unknown opcodes too. Never interpret that return
as OFF. LK's timeout has no proven OFF cleanup. Any future partial-start failure
must quarantine SRAM/IRQ/DRAM/PM reservations, not free them on this evidence.
