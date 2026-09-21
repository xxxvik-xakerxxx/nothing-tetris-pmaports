# SCP loader trace, 2026-09-21

Sensors remain Broken. The missing production implementation is the SCP
firmware loader, not another sensor-list or mailbox registration patch.

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

Trace certificate/context production and the secure backend against the
installed trusted firmware. Implement authenticated active-slot loading,
bounded memory allocation and error propagation as one loader operation.
Only after a valid region-info and SCP ready acknowledgement should the
mailbox/HF/sensorhub path be enabled and actual sensor samples tested.

The existing Linux SCP reset/recovery helpers consume prepared region-info;
they cannot replace the initial loader on a zero-handoff boot.
