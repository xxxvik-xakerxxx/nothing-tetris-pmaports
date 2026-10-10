# B4.1 typed EMI and bank-remap integration draft

Separate revision: frozen boot-stage, actual U-Boot and workflows unchanged.
No board hook, local C compilation/execution or phone operations. NOT shipping.

## Concrete changes

Bootstrap input now contains pointer-free source-derived typed rows and actual
firmware/NC/cache/SIB windows, not raw ranges or a dangling original-ROM pointer.
Current boot_plan has layout/smem only; it cannot reconstruct padding attributes.

Bootstrap calls tetris_modem_emi_rows_program EXACTLY ONCE after profile/strict
OFF. The old normal-policy loop is removed, not combined with pre-programming.
Every active row's reservation is bound to its actual allocation before access.

After firmware remap1/2, before request8 lock or power, it programs real LK banks:
* LK 0x22644..0x226bc: NC base+i*32MiB, indices0..7.
* LK 0x22cfc..0x22d38: cache base+i*32MiB, indices4..7 replacing upper NC
  entries while MD is still OFF.
* LK 0x279c8..0x27aa0: c200040b/3(low,high,index).
* ATF dispatcher0xbe9c..0xbebc, worker0x1be10..0x1bf40, table0x54a4d.
  Pinned payload SHA256:
  05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e.

ATF rejects out-of-DRAM addresses with -7 and locked admission with -15.
x0 is STATUS, x1 actual post-RMW register. Indices0..7 map to register indices
0,1,1,1,2,2,2,3 and bit shifts20,0,10,20,0,10,20,0: ten bits from address>>25.
Twelve replies retained; each checks its field AND earlier known fields in that
register. First error stops before lock/power. No retry/reset/guard rollback.

Final MD view maps 128MiB NC at0x40000000 and 128MiB cache at0x48000000.
Entire final mappings must fit separately owned reservations, not just used
service bytes. Both bases need32MiB alignment. Existing combined service reserve
has only64KiB alignment and cachebase=base+nc_capacity: NOT a valid substitute.
Producer rejects overlap with the FULL firmware reservation, including its tail.

Reviewed power/BROM and bounded cleanup semantics are retained. EMI/bank failure
does not permit cleanup writes on unowned state. Matching NS BL33 authority
remains source-scoped; there is no new permission/no-repower boolean.

## Authenticated snapshot lifetime patch

retained-source-storage.patch adds an explicit-slot loader reusing existing
private slot/storage/LMB/cache helpers. It does not enable a diagnostic/board hook.

1. Read once into independent LMB staging.
2. Run actual tetris_modem_prepare_bundle_b41 manufacturer-root verification ONCE.
3. Derive rows from retained authenticated ROM/member offsets and actual
   allocations/options BEFORE destination copies or snapshot release.
4. Copy ROM/DSP using verified cached layout/member offsets.
5. Release staging exactly once. Primary fault wins; release failure prevents
   output/boot even if verified placed bytes remain.
6. Flush payloads before publishing pointer-free boot plan and typed rows.

No guessed ROM offset, reauth of mutable placed RAM, duplicate firmware snapshot
or freed-source pointer. Patch apply-check passed against current U-Boot;
production compilation and loader lifetime/fault tests still require CI.

## Actual one-shot load owner

`tetris_modem_loaded_boot_once()` now implements the finite actual caller:
CurrentEL/profile/physical-OFF reads BEFORE any placed-RAM writes; firmware LMB
reserve; separate NC/cache128MiB32MiB-aligned reservations; optional real PHY
SIB allocation; actual DRAM-bank lookup; actual mapped slot loader; real existing
service initialization/cache flush; pointer-free typed bootstrap exactly once.
`aligned-service-reserve.patch` reuses existing transactional LMB/DT machinery
with separate fixed NC/cache/SIB node names and32MiB alignment, leaving diagnostic
combined-reserve API unchanged. Failed later stages retain earlier reservations.

The owner checks physical OFF again in bootstrap before EMI. Scope is synchronous
sole primary-CPU AP startup, not a fabricated global secure-world no-repower flag.
Actual ATF profile is checked through the existing storage verifier; manufacturer
root is pinned independently exactly as in current diagnostic load. No auth
success callback or caller-supplied readiness boolean exists in production.

Main still must produce real resolved CCB/PHY option text and independently
measured preloader identity, not hard-code PHY absence or pass a chosen digest
as runtime attestation. The owner accepts those internal values explicitly,
never derives them from unsigned chosen properties. Their platform producer is
NOT added in this draft. It preserves existing CONSYS-prefix initialization
contract; it does not claim conninfra ownership/initialization or rewrite that
prefix. SIB is not cleared, matching the traced LK allocation branch.

CPU mappings are released, final LMB/DT reservations are NEVER freed after load
or protection effects. Primary failure, load stage and bootstrap's primary/cleanup
reports remain available; a second call has no hardware/storage effects.
This closes allocation/admission/load/cache/bank/power/BROM caller wiring in
the owned draft. Full CCCI tag/handoff publication, concrete option/profile
producer and opt-in board registration remain main-owned and DISABLED. Boot
complete means actual four-one BROM replies, not SIM registration/calls.

## Validation

Local static checks only:
```sh
python3 patches/modem/drafts/bootstrap-integration/check_bootstrap.py
```

CI-only, after public manufacturer oracle:
```sh
CI=true python3 patches/modem/drafts/bootstrap-integration/check_bootstrap.py \
  --native-ci --uboot upstream/u-boot \
  --stock-container out/stock-modem/md1img.bin
```

41 process-isolated ASan/UBSan cases compile actual stock producer, typed EMI,
firmware remap and bootstrap. Synthetic hardware covers previous transition/
cleanup faults plus bank -15, bank readback failure, insufficient bank capacities,
first failure and no retry. Fixture frees ROM BEFORE pointer-free bootstrap.

Fixture does NOT authenticate firmware or exercise the added storage API.
AArch64 compilation must include rows C/program C plus bootstrap/secure and real
helpers. Storage patch needs separate real-header object/lifetime faults.
No revised C test has run locally or passed CI. Old boot-stage CI does not cover
this revision.

`check_loaded_boot.py --native-ci --uboot upstream/u-boot` adds17 CI-only strict
sanitizer control-flow/failure cases for the actual new owner. Slot authentication,
allocator and bootstrap are explicitly mocked boundaries in THAT unit fixture;
it is not an AUTH or combined whole-chain execution claim. The actual production
owner invokes the real existing APIs, not those fixture providers. Separate
storage-patch authentication/release/coherency faults and real-header ARM64
compilation remain required before any controlled boot experiment.
