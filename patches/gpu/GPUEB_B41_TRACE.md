# Declared B4.1 RV33 Transform Contract

## Independently Verified Inputs

- LK: provided `stock-b41/lk.img`, first payload SHA256
  `431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a`.
  Root/delegation, both RSA-PSS signatures, header and payload digests verified.
- ATF: provided `gnss-b41/atf-declared-image.bin`, payload SHA256
  `05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
  This worker independently verifies the declared payload pin, not ATF certificate
  authentication: the supplied ATF container has no certificate pair.
- GPUEB a/b: supplied private 2 MiB images; authenticated primary RV33 payload
  is 156064 bytes in both. No private bytes, key material or plaintext are emitted.

`audit_gpueb_b41.py --lk <image> --atf <image> [--gpueb <image>]` checks these
identities and instruction contracts. `test_gpueb_b41.py --lk <image> --atf
<image>` requires real pinned inputs; there are no silent skips or downloads.
Dependencies are Python cryptography and capstone; no native build/emulator.

## Actual B4.1 Reader And Authentication

The real RV33 name is at `0xc9257`, not the earlier `0xc9352`. The first
RV33-prefix string at `0xb0e98` is **xfile**, not the loader target.
At `0x1ed94`, the boot function calls `0x74da0` with partition `gpueb`,
RV33 name, destination buffer+0x18 and maximum 1 MiB.

The MTK reader searches section names, takes payload size from header+4
(`0x75180`), and reads from section offset+512 (`0x7518c`). Read dispatch is
`0x67edc`, whose bounded block-device callback is at object+0x70; it does not
declare a decompressed output size. The security-enabled path invokes
certificate setup `0x7e338 -> 0x92b5c` before reading, and data authentication
`0x7e344 -> 0x93068` after reading. On successful ciphertext digest comparison,
`0x930e4` or `0x93148` branches to `0x931ac`; `0x931d0` calls `0x91fa0` with
the original pointer/length. Its transform result is returned through w21.
Success at `0x7508c` jumps to `0x750cc`, skipping the separate image-processing
call. The no-authentication branch instead reaches
`0x750c4 -> 0x7e348 -> 0x91f9c -> 0x91fa0`. Unlike the earlier reference,
B4.1's target is **not** `0x920e4`. This corrects the previously linear account
of authentication followed by the fallback transform; it does not add a
second transform. Authentication/transform errors stop loader success.

OID table base `0xd8df8`, entry 15 is `2.16.886.2454.2.9`. Its big-endian
INTEGER parser extracts selector bits16:19 at `0x94ea4` and mode bits20:23
at `0x94ea8`. Signed word 0x10000 selects **selector 1, mode 0**. Mode 0
chooses wrapper mode 1, and `0x92084 -> 0x88078 -> 0x8203c -> 0x820a0`
uses the same secure backend as the reference.

The descriptor page is PA `0x48401000`: image PA u64+0x40, byte count u32+0x48,
wrapped-material PA u64+0x50, material length u32+0x58 (32). Cache maintenance
covers page, image and material. SMC x0=`0xc2000133`, x1=1, x2..x7=0.

The ATF service record at `0x59440` independently associates both
`0x82000133`/`0xc2000133` and label `MTK_SIP_LK_AES256_CBC_DEC_FW` with
handler `0xafcc`. The handler is **before** the IDs in the record; the
pointer after its name belongs to the next service, not this handler.
`0xafcc -> 0x2bff4` obtains descriptor+0x40 through `0xde4c(1)`, requires
service readiness via `0xde80`, transforms wrapped material through `0x3c51c`
(selector low byte1 -> key class3), then invokes `0x5a04` with the descriptor
byte count, same input/output pointer and mode0. Its cipher-driver tail callback
is indirect; this audit does not claim an expansion operation hidden there.
The formerly indirect cipher callback is resolved below. There is no
output-length parameter allowing LK to learn a larger result.
The handler preserves its incoming selector in x1 and constructs its fixed
16-byte cipher parameter from ATF's own static bytes before passing x0=stack
to `0x2bff4`. LK supplies neither that parameter nor a plaintext key. No static
cipher/key material is copied into this report or a new kernel interface.

LK compares the post-transform digest from `0x252090` (signed context+0xf0)
using the original image byte count. Mismatch returns `0x10c007`; section
loader checks processing failure at `0x750c8` before its post-load callback.

## No RV33 Decompression Proof

`0x750f8` invokes post-load callback `0x7db00`. Its three name comparisons
are `pvmfw`, `atf`, `tee`, selecting modes0/1/2 of `0x978a0` respectively.
RV33 matches none and takes the return path; this is **not** an RV33
decompression callback. The boot function resumes cache maintenance then
copies exactly **0x3f2b8 = 258744** bytes, unchanged from the older reference.
No output-size check reconciles this span with current ciphertext **156064**.

Thus padding, guessed decompression, or copying 258744 bytes from the current
156064-byte transformed payload is not authorized by these sources. The correct
next diagnostic is authenticated **transform-only**, followed by private
plaintext-format inspection. Record exact length, digest result and bounded
structural metadata; do not publish plaintext. Establish whether the handset
firmware and fixed-span LK belong to different revisions before implementing
upload. A signed LK reference alone cannot resolve that mismatch.

## Resolved Producer Bounds (2026-10-12)

`producer_bounds()` in the existing audit verifies the pinned instructions and
selected ATF callback pointer. It reads only cached signed LK and hash-pinned
ATF; no emulation, native build, secure call or hardware operation is needed.

Partition callback installation `0x68acc` selects `0x68b34`, which translates
only the source offset and re-enters `0x67edc`. Parent installation `0x68088`
selects `0x680c8`. Partial blocks use a separate allocation; copies at
`0x68198..0x681a0` and `0x68324..0x68330` are bounded by remaining bytes.
The direct full-block path floors the remaining count at `0x681e0`.
UFS installation `0x3ad4c` selects `0x3afd4 -> 0x36114 -> 0x36478`
(last callback installed at `0x367d8`). READ(10) carries the requested block
count (`0x36528/0x3652c`), count <<12 transfer bytes (`0x364e0/0x364f0`),
and destination (`0x36534`). No larger staging output is requested.

ATF initialization `0x24d14/0x24d18` selects record 2 via `0x59d4`.
Its pointer at `0x464f8` is VA `0x48837fec`. Dispatch `0x5a9c/0x5aa4`
reaches `0x37fec -> 0x3801c -> 0x129c` in mode zero. The DMA command at
`0x14b0..0x14c0` writes input PA, original count, output PA and output
PA + count -1; the high-address extension uses the same count.
`0x1590..0x1598` invalidates that extent. Cache helpers
`0x27f8 -> 0x95ec` and `0x27fc -> 0xa1dc` do not initialize RAM.
No expansion length or tail initialization is supplied. Actual DMA behavior
is not measured by this static audit.

Together with the reservation/mapping trace in `audit_gpueb_allocation.py`,
the remaining missing producer is precisely payload-relative
`[0x261a0, 0x3f2b8)`, 102680 bytes. Relative to the mapping's base (payload
starts at +24), it is `[0x261b8, 0x3f2d0)`. LK's word-copy loop at
`0x1ee08..0x1ee18` reads this interval without an authenticated size check.
The SRAM clear at `0x1edfc` initializes the destination, then this copy
overwrites it; it does not initialize the staging source. The larger staging
reservation and cache maintenance likewise establish no contents for it.

No identified writer in the audited control path produces that interval.
This is a missing source-backed producer contract, not proof that the tail is
zero, BSS, xfile, decompressed data, or a valid executable extension. No loader
or SRAM-owner change is justified by these observations. GPU remains Broken;
no render node or accelerated rendering is established.

The stock success branch does **not** reveal a double transform in our
U-Boot checkout `3ef74f1ade1a4d6b5eabc0216ae67b3b9d3a171e`.
`tetris_scp_security.c:tetris_gpueb_authenticate` verifies signatures/header/
ciphertext only; its hardware callbacks are SHA256 and local RSA-PSS.
Both `tetris_gpueb_prepare.c` and `tetris_gpueb_flat.c` then invoke the single
SMC in `tetris_scp_crypto.c:tetris_scp_crypto_decrypt`. Their diagnostic
Kconfig options are mutually exclusive. `uboot-segments/test_draft.py` checks
this actual source chain. No loader correction is warranted.

## Main Integration And Next Gate

No kernel patch, DT activation, APKBUILD or workflow change accompanies this
audit. Keep 0120/0122/0123 frozen. Main may review transform-only U-Boot code
using its existing registered, unlocked LK service-page boot window. Require
root delegation/signatures, signed header, ciphertext digest, exact supported
signed selector/mode, payload alignment/bounds, unchanged byte count, secure
return and signed plaintext digest. Fail closed and erase output on error;
no retry, fake ready marker, SRAM write, MFG/rail write or GPUEB start.

First runtime gate, after CI/authentication fault tests: one controlled
transform-only boot, record exact U-Boot/firmware hashes and plaintext-digest
success or first failure, while retaining USB/sensor baseline. This audit does
not operate the phone or execute that gate. GPUEB upload still requires proven
plaintext layout, one controller owning the whole cleared SRAM including GPR
and mailbox, boot IRQ ordering and an independently proven physical OFF path.
