# Authenticated segment inspection review

Inspection was integrated in U-Boot commit
`d385921124b9e48a00d5e078d11b07dcdf311270` and is present in the pinned
`fdb0ee2994c62b6220e35dd1f75bbeee6e7d6f3a` lineage. The C/header here are
review mirrors, not another implementation to install. This is not GPU
activation or proof of a working SRAM image.

## Exact LK source resolution

For pinned B4.1 LK payload SHA256
431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a:

- Caller x23 is mapped firmware reservation +24 (0x1ed8c); reader receives
  that destination in x2 (0x1ed90). Reader preserves it as x21 (0x74dc8).
- Matching member size comes from the temporary header's size field
  (0x75180). Partition read offset is member offset +512 (0x7518c).
  0x75024..0x75030 reads exactly that payload into x21, NOT its header/certs.
- Destination adjustment at 0x75074..0x7507c applies only to legacy header
  magic 0xd7b7ab1e. Current signed member magic is 0x58881688: no adjustment.
- 0x75080..0x75088 and 0x750bc..0x750c4 pass that pointer/length to secure
  authentication/transform paths. Existing B4.1 audit traces in-place digest
  verification and excludes an RV33 decompression callback.
- 0x1ee08 copies from original caller x23 to SRAM. Thus fixed 258744 bytes
  refer to decrypted destination memory, NOT an enclosing six-member image.
  Current 156064-byte authenticated payload leaves 102680 bytes beyond the
  proven transformed interval. Container headers, certs and xfile cannot
  explain this excess, because they were not read into that interval.

This resolves the container-vs-payload ambiguity, not the provenance of the
excess. UNKNOWN format remains UNKNOWN. No padding/zero-BSS assumption allowed.

## Matching archive versus handset

Only gpueb.img was extracted from the already cached
Tetris_B4.1-260415-1709-image-firmware.7z, without network or phone access.
The 532480-byte image SHA256 is
58c337b0e713d643a1cb129fd444bce0b8bc00e38877c3f242ac9a7f5901ba22.
Existing verifier passed pinned root/delegation, certificate signatures,
primary header and ciphertext digest. Primary size is still 156064.
Its signed plaintext digest is
4cd3ac60605b30f92988a7606e95b7e4f82d70513bbd12923a0e562e9fc31702,
unlike the handset's independently verified
9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7.
Thus release-image and handset firmware are not identical plaintext variants;
neither variant establishes the static 258744-byte copy's excess provenance.

Actual auxiliary xfile starts with six u32 values: magic 0x58901690, header
24, data bytes 364416, alignment 4, ID99, reserved 0. Its suffix is END plus
40 lowercase hex characters. Whole auxiliary digest remains unproven; no
debug body was uploaded, decrypted, copied into the repository or treated as
executable firmware. B4.1 APUSYS reader 0x178c4..0x178f4 corroborates framing
offsets/roundup. Its APUSYS ID dispatch is NOT a GPUEB address/role map.

The draft now recognizes this bounded MTK PT framing alongside ELF. Reports
only file offsets/sizes, IDs/alignment and suffix length, with all memory-map
fields zero. This enables real primary framing identification AFTER the
existing authenticated transform, without assuming the primary matches xfile.
Malformed recognized PT fails atomically; UNKNOWN remains non-executable.

## Current integration contract

The obsolete `prepare-integration.patch` has been removed: against the current
tree its header hunks failed while its C hunk could insert a second inspector
call. Do not reapply the original integration. `check_integration.py` now
checks the actual checkout without modifying it. It rejects duplicate calls,
missing report ABI/object ownership, bypassed decryption failure handling,
incorrect inspector inputs, missing full-capacity erasure, and mirror drift.
`test_draft.py` checks both the pinned fdb0ee29 git objects and the actual
checkout, with negative mutations of those sources. No shared U-Boot files,
workflows or packages are changed by these checks.

The call occurs after signed plaintext digest validation. It accepts only
bounded static little-endian RISC-V ELF32/64 with <=16 disjoint PT_LOAD
segments, equal VA/PA, file-backed executable entry and <=256 KiB memory span.
This is an inspection profile, NOT proof that GPUEB accepts ELF or that its
address map is supported. Other ELF profiles fail; non-ELF/non-PT is UNKNOWN.
Only relative offsets/sizes/flags survive. No raw bytes or absolute addresses.
Output is atomic; malformed ELF follows existing full-capacity erase/flush.

Source-only gate: `PYTHONDONTWRITEBYTECODE=1 python3
patches/gpu/uboot-segments/test_draft.py -v` in pmOS. Set `TETRIS_UBOOT_TREE`
if the actual checkout is not the sibling `u-boot-mt6878` directory.

CI native gate: `CI=true sh patches/gpu/uboot-segments/run-native-ci.sh` in pmOS.
It checks the integration first, then compiles the actual U-Boot parser/header,
not this review mirror. Unset/empty/false/0/1 CI values exit before compilation.
Then compile actual U-Boot GPUEB prepare/segment objects with ARM compiler and
rerun existing transform fault tests plus SCP regression tests. No local C
build was run. Native fixture uses synthetic, unsigned ELF data to test the
parser only; it is not authentication or hardware evidence.

U-Boot already selects relative metadata for chosen diagnostics. This sidecar
does not edit board wiring, exports, CI, Kconfig or Makefile.
At the next controlled transform-only boot, expect UNKNOWN for the previously
observed plaintext unless it has the source-backed PT framing. ELF/PT metadata
would need independent validation;
neither outcome permits SRAM upload/reset release. Preserve erase-on-success.

## Physical caller boundary

Pinned device-modules drivers/remoteproc contain no GPUEB rproc_alloc/start
driver. Our 0123 is request_firmware ingress, not rproc_ops. Vendor GPUEB probe
adopts stock LK's already-running processor. Linux must eventually own full
SRAM clear/copy, GPR initialization, reset release/BOOTREADY, full-bank IRQ and
MFG/EMI lifetime. Current IPC power backend cannot bootstrap its own supplier.
No concrete physical start is added while payload map, persistent authenticated
firmware handoff and failure OFF procedure are still unproven.

The missing real producer is a source-backed complete executable SRAM image
for the selected RV33 firmware variant: the authenticated primary covers
156064 bytes, but LK's copy consumes 258744 bytes from that same destination.
The producer/initialization contract for the remaining 102680 bytes is still
unknown. A matching signed full image, or a verified stock memory-initialization
path explaining that interval, is needed before reproducing the copy. Segment
framing, the xfile debug body, reserved zeroed capacity, and a different release
image are not that producer. No filler or guessed SRAM bytes are introduced.
