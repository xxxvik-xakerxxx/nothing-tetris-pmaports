# Fixed-salt RSA-PSS backend

New production `mt6878_md_pss32.c/.h`, native fixture and isolated object checker.
All reservation/startup-scope files remain frozen and unchanged. No consumer,
shipping config, shared CI, package or phone operation is added.

## Concrete implementation

The backend uses pinned Linux raw `rsa-generic` via crypto_akcipher_encrypt, with
CRYPTO_ALG_ASYNC masked out. It preallocates the request and kmalloc-backed input/
output buffers; no stack/vmalloc scatterlist data is handed to raw RSA. Key is
immutable after creation: exactly canonical 270-byte PKCS#1 RSAPublicKey DER,
2048-bit odd modulus, exponent65537. SPKI, other key sizes and BER variants are
rejected, not coerced. Signature is exactly 256 bytes; raw output must remain
256 bytes. No pkcs1pad, auto-salt, async wait or hardware crypto fallback.

SHA256 uses the exact pinned kernel software/library driver `sha256-lib`
(`crypto/sha256.c`), not the old vendor `sha256-generic` name. Missing algorithms
return their original negative error. SHA descriptor is allocated before use;
all constructor failure paths release only acquired resources.

PSS adaptation follows U-Boot `bffec9306e7c40a432d79deefb450230c2ee2360`,
`lib/rsa/rsa-verify.c:103-302`, retaining its copyright/license attribution:

1. Check trailer 0xbc and zero top bit for strict 2048-bit modulus/emBits2047.
2. MGF1 SHA256 over H plus four-byte big-endian counter; exactly seven hashes
   fill 223-byte DB. XOR maskedDB; clear the unused top bit.
3. Require 190 zero bytes, delimiter 0x01, exactly 32-byte salt. No scanning for
   arbitrary salt lengths and no algorithm/profile selection from input labels.
4. Compute SHA256(8 zero bytes || TBS hash || salt32); compare to H with
   crypto_memneq. Clear scratch and signature/recovered buffers after use.

Two intentional error-handling corrections to the source: U-Boot ignores the
MGF1 and hash-prime helper returns; this backend stops on the first error. Its
positive EINVAL/memcmp results become negative EKEYREJECTED for invalid padding,
and unexpected positive crypto API errors become EPROTO, never success. Negative
allocation/algorithm/key/hash/RSA errors are retained unchanged.

`verify` hashes immutable TBS <=16KiB, performs real raw RSA, then strict PSS.
`sha256` is separately bounded to accessible immutable input <=64MiB; it is a
hash primitive only, not an AUTH result. No physical address, mapping, secure
call, firmware request or MMIO API occurs. Signature verification under a caller
provided key is NOT trust-anchor/delegation authentication. Production DER/SPKI
delegation/profile integration is still separate, using SIGNED_RAM_AUTH.md's
exact MediaTek construction. No unsigned chosen digest is accepted here.

## Ownership and gate ordering

Create/destroy and signature verification run outside supplier/scope locks.
Each context has exactly one synchronized caller, immutable input throughout;
there is no mutable key setter or internal recursive mutex. Raw software RSA
can allocate MPI scratch internally and must not be treated as a lock-free
callback. Prepare certificate authentication/crypto contexts before entering
the startup transaction. The future owner may use a preallocated software hash
context for permitted installed-byte checks, but must separately establish OFF,
EMI/remap, NS-access/coherency and competing writer exclusion before any reads.

Neither backend nor fixture reads ROM/SMEM or grants hardware permission. The
current reservation provider still returns ENOKEY; no scope callback is wired.

## Main CI commands

Local static-only check:

```sh
python3 patches/modem/check_pss32_backend.py
```

Independent Ubuntu native CI, requires compiler, libssl-dev and Python
cryptography already provisioned by main:

```sh
CI=true python3 patches/modem/check_pss32_backend.py --native-ci
```

The fixture compiles the **unmodified production body/header**, removing only
includes, with -std=gnu11 -Wall -Wextra -Werror and ASan/UBSan. Linux API doubles
use actual OpenSSL BN_mod_exp for raw RSA and EVP SHA256. Generated synthetic
RSA keys/signatures are CI-only, not port trust or fabricated crypto callbacks.
Tests cover successful salt32, rejection of salt64/PKCS1v1.5, wrong TBS/signature,
noncanonical key and bounds, raw signature>=modulus, each constructor failure,
all nine hash failure sites, first-failure preservation, unexpected positive
status, short raw output, and trailer/top-bit/pad/delimiter/H mutations.

Isolated AArch64 API/object smoke with an already prepared ARM64 CI kernel:

```sh
CI=true CROSS_COMPILE=aarch64-linux-gnu- python3 patches/modem/check_pss32_backend.py \
  --aarch64-object-ci /absolute/path/to/prepared/kernel
```

Generates only a temporary external object Makefile/C/header; compiles against
real kernel headers with W=1/KCFLAGS=-Werror; verifies ELF64 little-endian
e_machine=AArch64. No install/modpost/link/runtime or shared packaging changes.
Prepared kernel build products are main-owned CI inputs, not reconfigured by
this checker. Runtime requires CRYPTO_RSA and CRYPTO_SHA256; this harness does
not activate them. Native/object execution pending; no local C compilation.
