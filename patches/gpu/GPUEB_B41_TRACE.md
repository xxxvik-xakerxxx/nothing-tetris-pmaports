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
`0x7e344 -> 0x93068` after reading. Then image processing is
`0x750c4 -> 0x7e348 -> 0x91f9c`. Unlike the earlier reference, B4.1's last
target is **not** `0x920e4`. Authentication errors stop loader success.

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
There is no output-length parameter allowing LK to learn a larger result.
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
