# Review snapshot: retention + atomic DT + private analysis

Not enabled or packaged. No SRAM, reset, MFG, rail, EMI, mailbox or secure
execution operation is added. Existing production transform-only and frozen
flat producer are unchanged. Only the new publisher consumes the producer's
handle after a successful DT commit.

## U-Boot integration owned by main

Copy flat producer/header and new publisher/header into the reviewed board
tree; add objects under an explicit diagnostic opt-in. Supply the same real
registered/unlocked crypto context and independently pinned root as production.
Load a bounded gpueb container using the already reviewed partition loader.
Initialize handle to NULL; call retain, then publish with the actual writable
final DT capacity. Do this after DT replacement/overlays and before kernel
handoff. The very DT mutated here must be the DT Linux receives. Never publish
to an intermediate DT later discarded by FIT boot. Abort the diagnostic boot
path if publication fails; report its first error without plaintext/logged keys.

The publisher uses a private FDT copy and commits once. It checks two-cell
root/reserved-memory addresses and sizes, identity ranges, existing reservation
overlaps, a fresh phandle and DT structure. It inserts an exclusive no-map
reservation and a diagnostic consumer containing only its phandle, signed byte
length and plaintext SHA256. No chosen payload or pointer is created. Failure
discards/erases the producer allocation. If discard itself fails, the caller's
handle remains non-NULL; do not pretend release succeeded. Success keeps the
LMB range plus opaque owner until boot and consumes the caller's handle. There
is deliberately no post-publication rollback/reclaim API.

This is synchronous atomic publication, not a power-loss transactional protocol.
Caller must serialize the final DT, retain its buffer, and keep crypto ops alive
through publication/discard. No firmware consumer has been started, so there
is no partial-start hardware ownership in this diagnostic path.

## Real CI gates (not run locally)

`run-native-ci.sh` requires CI=true, HOSTCC, TETRIS_UBOOT_TREE and
TETRIS_GPUEB_FACTORY_CONTAINER. Native dependencies: libfdt development headers,
ASAN/UBSAN toolchain, and existing U-Boot Python RSA/ASN.1 test dependencies.
The factory container is the legitimate cached B4.1 532480-byte component,
SHA256 58c337b0e713d643a1cb129fd444bce0b8bc00e38877c3f242ac9a7f5901ba22.
Do not add it or private/decrypted contents to Git.

Native targets link actual GPUEB layout, ASN.1 security and crypto. Tests cover
real factory root/signature/ciphertext validation, corrupted input, wrong root,
allocation/map failures, secure failure, postdigest mismatch and complete erase.
Sanitized C publication fixtures use libfdt itself and cover insufficient DT
capacity, allocation failure, overlapping reservations, failed discard preserving
ownership, and successful phandle/no-map publication. Synthetic handles exist
only inside the native fixture, never in production APIs. Private plaintext is
not available yet: producer-success native test is explicitly skipped until a
matching privately verified factory plaintext is supplied. No fake successful
postdigest callback is used to hide this gap. Phone-a plaintext is a different
signed digest and cannot substitute for factory plaintext in this fixture.

`smoke-uboot-ci.sh` needs a throwaway prepared/configured ARM64 U-Boot checkout
TETRIS_UBOOT_SMOKE_TREE, TETRIS_UBOOT_OUT and its cross compiler. It copies only
candidate files into that CI checkout and builds both real objects. Main must
also wire/link these objects in the opt-in image to check final symbol closure.
`smoke-kernel-ci.sh` builds gpueb-flat-analysis.o against prepared packaged
TETRIS_KERNEL_TREE/TETRIS_KERNEL_OUT. Required config: OF_RESERVED_MEM,
CRYPTO_SHA256, CRYPTO_HASH and diagnostic module wiring. Object smoke is not
a successful module-link or runtime-probe claim; main must run modpost/link too.

## Linux analysis consumer and exact cold gate

The diagnostic consumer accepts the one phandle, exact reserved 1 MiB and signed
156064-byte length. ARM64 registers NOMAP DRAM as an IORESOURCE_MEM "reserved"
resource, not System RAM. Therefore validation requires BOTH full containment
in a DT memory node and a covering kernel-generated reserved resource, with
no System RAM overlap; it never silently substitutes an MMIO mapping.
Only authenticated bytes are read from that ordinary DRAM mapping. A private
snapshot is hashed before registration. The read-only misc node is mode 0600
and each read requires CAP_SYS_RAWIO. Reads stop at signed length. No mmap,
write, ioctl, physical pointer, payload logging, MMIO or firmware execution API.
Successful probe pins the diagnostic module through the boot and suppresses
manual unbind to keep file-descriptor lifetime safe. Memory remains reserved.

After native/ARM/module-link gates, main may install the diagnostic opt-in build.
Cold gate: screen/touch/sensors/USB baseline unchanged; dedicated no-map range
appears exactly once; consumer probe succeeds; privately read exactly 156064
bytes to an uncommitted host file and independently SHA256-check against the
signed digest. Expected phone-a hash is
9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7.
Then inspect actual reset vector/branches, initial data copies, stack, BSS clear
and GPR0/GPR6 accesses to decide the bounded-copy/cleared-tail experiment.
This build neither uploads bytes nor starts GPUEB. Recovery is a normal clean
boot of the previous diagnostic-disabled image, not module removal or rail writes.
