# Actual retained-v1 metadata admission

Status: source-tested candidate, not installed or hardware-tested. All task
writes are new files in this directory. No phone, native build, CI or git
operation was performed. Parent's simultaneous r184 flash is independent.

The existing `flat-handoff-draft/gpueb-flat-analysis.c` already validates plain
NOMAP ordinary RAM, exclusively claims the complete 1 MiB reservation, rechecks
resources/PFNs, snapshots signed bytes, verifies SHA256 and retains ownership
until reboot. This candidate extends that same consumer; it adds no resource
owner, driver, firmware importer, MMIO, IRQ, reset or start operation.

The inspected sibling U-Boot producer is identified by the three exact source
hashes in `FLAT-METADATA-PRODUCER.json`. bd8950d and CI38356830921 are the parent's
reported identities, not independently queried git/CI results. Its actual
publisher emits one `nothing,tetris-gpueb-flat-analysis-v1` consumer with a single
memory-region phandle and ten metadata properties. The older review mirrors
in flat-handoff-draft lack the new properties and are not the ABI authority.

## Admission implemented

`tetris_gpueb_flat_metadata.h` reads exactly one u32 for version, payload offset,
authenticated length, SRAM offset and profile ID, and exactly 32 bytes for each
of the plaintext/header/ciphertext/leaf-certificate/container digests. It copies
all properties into a local value and publishes that value only after validation.
No DT property pointer survives into the mapping/hash phase. All five digests
and the profile/layout fields remain in the existing consumer's owned state
after successful private-snapshot verification.

Version must be 1, signed length 156064, and both offsets zero. LK's source +24
is not this producer's offset; header bytes, xfile, the zero arena tail and LK's
258744-byte stock copy are not admitted payload. The arena must be exactly 1 MiB,
64 KiB aligned, inside the actual producer's [1 GiB,2 GiB) allocation window.
Subtraction-based bounds also require the signed range to fit both the arena
and the source-defined pre-GPR SRAM interval. These are stable producer/platform
bounds; the actual base still comes exclusively from reserved-memory APIs.

Profile 1 must pair with signed plaintext 9628a446...aad86d7; profile 2 with
4cd3ac60...fc31702. Unknown IDs/digests and cross-paired profiles fail ENOEXEC.
Malformed metadata/ranges or missing/zero provenance fail EINVAL. A different
actual snapshot digest fails EBADMSG before misc registration; existing erase
and owned-resource cleanup handle rejection. Underlying crypto errors survive.

The four provenance hashes are retained identities with exact shape/nonzero
checks. Linux cannot reauthenticate their signatures from hashes alone. They
are not independently pinned certificate/header tuples or a grant of trust.
Trust remains the reviewed authenticated/decrypted bootloader producer plus
the pinned signed plaintext identity and recomputed snapshot digest. In
particular, container SHA256 identifies whole framing, including unauthenticated
auxiliary data; it does not authenticate xfile or extend signed payload bounds.

## Exact parent integration

Before changing the parent-owned consumer, run from the pmaports root:

```sh
python3 -B patches/gpu/uboot-segments/test_flat_metadata.py -v
python3 -B patches/gpu/uboot-segments/check_flat_metadata.py
patch --dry-run --batch -p1 -i patches/gpu/uboot-segments/flat-metadata-integration.patch
```

Then parent applies `flat-metadata-integration.patch` to the existing
`patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c`. The delta embeds the
reviewed header in that single translation unit, adds metadata to its existing
state, and substitutes admission for the old length/borrowed-digest checks.
It preserves every RAM-owner helper and failure cleanup byte-for-byte. No
Makefile or global CI helper edit is required to copy/link another object/header;
the existing isolated-module helper already copies this one C source.

Parent regenerates the complete existing package patch with
`patches/gpu/flat-handoff-draft/generate_consumer_patch.py`, replacing
`pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0120-misc-tetris-gpueb-authenticated-ram-analysis.patch`.
Before applying the delta, `integrate_flat_metadata.py --format patch` can
render the same complete replacement to stdout for review. Its `--format source`
and `--format delta` outputs are deterministic; all modes reject changed or
already-integrated base sources rather than stacking another implementation.

After applying, parent verifies the concrete source with:

```sh
python3 -B patches/gpu/uboot-segments/check_flat_metadata.py \
  --consumer patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c
```

Parent must reconcile the two legacy assertions that demand the removed
length-only check: `test_ram_admission.py:test_read_and_authentication_surface_stays_bounded`
and `test_publication.py:test_no_mmio_and_bounded_private_read`. Preserve their
root-only/bounded-read/no-MMIO assertions and substitute the new metadata and
snapshot checks. The existing generated-package equality test remains useful.
After review, refresh the consumer entry in flat-handoff-draft/SNAPSHOT.sha256
and audit_gpueb_b41.py:RETAINED_SOURCES; its old consumer pin intentionally
rejects this change. Do not promote the stale producer mirrors to the new ABI.
The rendered integrated consumer SHA256 is
`e0ac3e88c4a23faabf0cc80f406a52e7eda1ac44af0f9004df65de730a367204`.

The local new suite passes 14 tests and reruns 12 applicable existing
RAM/ownership source gates against the integrated candidate in memory. Tests
check actual producer source identities, all ten properties, profile pairing,
guard-removal mutations, output ordering, ownership retention, rejection
cleanup, generated patch equality and no parent-file mutation. These are static
checks, not execution of C or malformed-DT runtime fault tests.

Next parent gates are actual kernel object/module-link and malformed-property/
profile/digest fault coverage in CI, then a controlled retention-only cold boot
with the reviewed v1 producer enabled. Installed loader 322cf has retention
disabled according to the parent, so it cannot supply this input. An older
producer with the same compatible but missing v1 fields is rejected before any
claim or mapping. Missing consumer/reservation never becomes readiness. Success
admits only authenticated diagnostic bytes; it permits no upload, READY marker,
IRQ enable, reset release or GPUEB start, and does not solve stock's missing tail.
