# Canonical retained-v1 admission

The actual Linux call path is `module_platform_driver(flat_driver)` ->
`flat_bound_probe()` -> `flat_probe()` for
`nothing,tetris-gpueb-flat-analysis-v1`. Package patch 0120 installs this same
translation unit as `drivers/misc/gpueb-flat-analysis.c`. Successful admission
exposes only the existing root-only read of a private signed-length snapshot.
This source change is not evidence of installed loader retention or GPU startup.

The reviewed helper is embedded once, unchanged. It admits exactly five u32
fields and five 32-byte digests, version 1, zero payload/SRAM offsets, the
156064-byte signed primary and the two reviewed profile/digest pairings.
The full plain NOMAP 1 MiB arena must be 64 KiB aligned inside [1 GiB,2 GiB).
Existing resource/PFN checks, exclusive whole-arena ownership, failure erase
and cleanup, and boot-long module/claim retention are preserved. No DT digest
pointer survives to mapping. Snapshot hashing precedes misc registration.
Malformed metadata fails EINVAL, unsupported profiles ENOEXEC, and snapshot
mismatch EBADMSG; crypto failures are preserved. Provenance hashes identify
inputs but do not reauthenticate certificates, auxiliary framing or the tail.

## Parent integration

The canonical source SHA256 is
`e0ac3e88c4a23faabf0cc80f406a52e7eda1ac44af0f9004df65de730a367204`.
`SNAPSHOT.sha256` and the consumer entry in `audit_gpueb_b41.py:RETAINED_SOURCES`
cover it. The audit's other retained-source pins still identify historical
producer mirrors; current producer validation uses the sidecar manifest.

Parent must refresh APKBUILD's 0120 checksum and global CI snapshot pin after
integrating these files. Replace the old staging-suite invocation with
`python3 -B patches/gpu/flat-handoff-draft/test_canonical_metadata.py -v`.
The staging suite/renderer intentionally refuse the now-integrated base.
Run `check_flat_metadata.py` with
`--consumer patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c` and the
matching pinned producer tree. Do not weaken the staging base guard.

The canonical suite reuses all reviewed metadata/mutation cases, reconstructs
and verifies the old base only in a temporary fixture, checks full generated
package equality, and applies 0120 without fuzz or offsets to exact Linux Git
objects. `test_ram_admission.py` also reads pinned Git objects rather than an
unverified extracted directory. Set `TETRIS_KERNEL_TREE` to a repository with
Linux `d84b264a54a37611f2f46bc19363cb9b41606205` and available source blobs.
Set `TETRIS_DEVICE_MODULES_TREE` and `TETRIS_VENDOR_MODULES_TREE` to repositories
containing NOS B4.1 `ee2be53cb75670b548948636a0db1d1ff112bf12` and
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. Tests read those exact objects;
missing sources are failures, not skips. All local gates are source checks.
Actual malformed-DT runtime faults and ARM64 object/module linking require CI.

## Matching loader and next gate

In U-Boot `f25c01444a642c6fca857bd9678ef438ec371988`,
`tetris_scp_prepare_diagnostic()` conditionally calls
`tetris_gpueb_flat_capture_slot_a()` after SCP plaintext verification in the
pinned ATF/crypto window. The late board path conditionally calls
`tetris_gpueb_flat_publish_final(images)` on the final Linux FDT. The Kconfig
option `TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC` defaults off and excludes the
erase-only transform diagnostic. The user reports the installed f25c loader
has retention disabled; its source calls do not prove an enabled installed
profile. The v1 candidate's reported green CI38377639691 does not establish
an installed canonical replacement and has not been independently rechecked here.

Parent's next deliverable is a matching retention-only loader and canonical
consumer built in CI with exact source/config/artifact hashes. Require the
existing ATF/root/signature/decryption/postdigest chain, persistent crypto
state, retained arena ownership and atomic final-FDT publication. Then a
separately authorized cold test can verify reservation and snapshot digest
without activating GPUEB. Absent reservation/consumer must remain a failure.

NOS B4.1 `gpueb_init.c:__mt_gpueb_pdrv_probe()` calls `gpueb_ipi_init()` and
`gpueb_reserved_mem_init()`. These initialize mailbox IRQ/IPI ownership and
the distinct `gpueb_mem_addr`/`gpueb_mem_size` runtime DRAM table. Neither is
provided by this diagnostic reservation. The exact module-tree
`gpu/mt6878/Makefile` selects vendor Mali r44p1, not a Panthor power integration.

Before any executable route, resolve LK's uncovered [156064,258744) copy,
GPR0's separate +24/prefix ABI and GPR6's 6 MiB DRAM/EMI dependency, then join
one real full-SRAM/GPR/mailbox upload owner with the actual reset/IRQ owner.
Reset echo, IRQ drain and SMC zero do not prove physical OFF; uncertain starts
require quarantine. Zero tail/BSS assumptions and unauthenticated uploads are
not admitted. Only after a proven GPUEB session and power/rail/domain lifecycle
can Panthor probe/render be tested. No full GPU claim follows from retention.
