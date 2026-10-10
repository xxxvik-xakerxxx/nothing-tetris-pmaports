# Owned runtime metadata candidate

Frozen for parent review, disabled draft; C CI remains pending. No board hook, DT enablement, firmware start, SMC,
MMIO, protected-ROM read, or claim of SIM/CCCI readiness. No local C build.

## Executable path

Overlay follows packaged adaptations, owner, runtime-ports, runtime-prepare and
runtime-lifecycle. It changes util import plus the resource dependency call;
it does not change any frozen files on disk. Vendor input is
`ee2be53cb75670b548948636a0db1d1ff112bf12`.

1. The actual util init propagates errors instead of legacy DT fallback.
2. Owned-mode collection validates chosen's exact 80-byte LE report, independent
   BE scalar fields, sole mddriver, and exact 32-byte LE descriptor.
3. Descriptor must name the actual early reserved 64KiB no-map AP tags buffer,
   matching `/reserved-memory/tetris-modem-linux-tags`. Before AP tag mapping,
   require source-created `tetris-modem-diagnostic` (full 512MiB),
   `tetris-modem-boot-nc` and `tetris-modem-boot-cache` (each full 128MiB).
   These are the pinned loader's allocation profiles, not phone addresses.
   Each exact reg/no-map node must match early `of_reserved_mem_lookup()` base
   and capacity, correct DT cells/ranges, alignment and physical bounds.
   All four source-created plain nodes MUST have no `compatible` or `reusable`.
   Catalogue match alone is insufficient: require actual full top-level NOMAP
   iomem resource coverage and reject any mapped PFN in the entire window. Reject
   overlaps against all static reserved nodes including unused tails, and require
   all MD windows in one common DT DRAM bank, with tags independently contained
   in one bank. Reject PHY/SIB node for this normal
   policy. No combined service-diagnostic adoption. Missing descriptor remains
   `ENODATA` before any bank lookup or mapping.
4. Only that AP buffer is mapped. One private copy validates the 21-tag chain,
   every name/offset/length/link, variable row strides/caps and count consistency.
   The CHKv6/B4.1 MD1 image14/normal-policy fields are checked before publishing
   arguments. Other versions/image policies fail; addresses and sizes remain
   producer-derived. Before private argument publication, semantic validation
   reconstructs the full firmware split map from retained CHK and compares every
   offset/size/info/attribute/physical address, including the retained full tail.
   NC/cache planners reproduce exact IDs, sizes, alignments, gaps/padding flags,
   zero-sized rows, AP/MD offsets and all legacy mirrors/summaries. This is not
   yet complete signed SKU/platform selector validation.
5. Existing args lookup consumes retained normal memory, not wiped/unmapped LK
   I/O. The AP mapping is unmapped without clearing. There is no legacy SMEM
   mapping, usage-bit/environment publication, or synthesized bootSIB/READY.
6. Real resource_prepare dependency admission calls the same DT validator before
   existing descriptor checks and before allocating HIF device links.

An accepted report is an observed boot result, NOT firmware attestation, AP SMEM
permission, transport initialization, or authorization to register/start CCCI.
Metadata has the same trust boundary as the DT from verified U-Boot; CHK copy
alone is not an independent signature verification.

## Exact remaining operational producer dependencies

Installed BROM-only `tetris_modem_brom_board.c` deliberately does NOT call
`tetris_modem_publish_final()`, and refuses an inherited CCCI descriptor. Even
four-one BROM success therefore cannot be converted to an operational descriptor
by Linux. The real final producer must encode from the still-owned authenticated
loader capsule after successful BROM, reserve/clean the full tag buffer, and
atomically publish its descriptor. Cold report must be reviewed first.

The tags contain `md_mem_layout` (24-byte rows) and NC/cache layouts (40-byte rows).
`semantic.h` now checks complete byte-field consistency with the source-derived
plan and actual per-bank reservations. `layout_model.h` is generated from pinned
pure U-Boot planner/annotation/padding code; generator verifies exact source and
does not synthesize or read a ROM-sized memory buffer. The small adaptation takes
the bounded retained CHK directly instead of fetching a footer from protected ROM.
The actual loaded DSP byte count is not in these tags: validation covers its CHK
capacity/placement, not a new payload-length/authentication claim.
NC/cache rows end at the last planned region, not the full bank tail: do not
fabricate rows for their unused 128MiB reservation. Padding rows legitimately
reuse the next real row's ID with flags=4; exact planner comparison distinguishes
them from forged duplicates. Memory attr/info comparison includes the producer's
post-EMI padding annotation.
The report has no authenticated platform/SKU field: CHK's platform bytes are
retained metadata, not a newly verified selector. A source-backed binding of
that selector to the verified boot firmware profile is also required before
any operational admission. Do not infer a universal SKU from the current phone.
Specifically, report80 contains only loader/bootstrap result/stage/SMC replies;
`hdr_tbl_inf` carries MD index/image type, not the selector or its authentication
context. CHK bytes24..39 are a platform string copied from the retained signed
input, but the current final ABI does not carry the loader's validated root/key
delegation or a binding to verified board/preloader identity. An arbitrary chosen
digest or caller-supplied "authenticated" flag cannot repair that producer gap.
The existing verified loader/final owner must retain and publish a traceable
selector binding from its real authenticated capsule before Linux may use it
for operational admission. No such producer is introduced in this bounded draft.

Do NOT call `ccci_tetris_register_prepared()` with this metadata-only candidate:
its `ccci_md_config()` still invokes `ap_md_mem_init()` which consumes actual
mapped SMEM globals. The required next implementation is transactional validated
NC/cache mapping with explicit range/security/coherency ownership, unwind before
publication, and only then the existing registration transaction. This draft
does not fabricate those globals or loosen START/STOP/monitor guards. Resource
prepare alone is not registration. Source absence here is a missing producer,
not a new boolean gate or a guess about physical reset.

## Source anchors

- U-Boot `board/mediatek/mt6878/tetris_modem_brom_board.c`: `publish()`, scalar
  record, disabled consumers and BROM-only loader invocation.
- U-Boot `tetris_modem_final.c`: 64KiB LMB allocation, `no_map_reservation()`,
  exact descriptor and cache-clean atomic final-DT publication.
- U-Boot `tetris_modem_ccci_tags.c`: `tetris_modem_build_linux_tags()` actual
  21 tags, CHK normal policy, genuine private loader report and full capacity.
- Vendor `ccci_util_lib_fo.c`: `collect_lk_boot_arguments()` and v2 parser.
- Vendor `ccci_util_boot_args.c`: real lookup lifetime/source field.
- Vendor `eccci/fsm/ap_md_mem.c`: `ap_md_mem_init()` / SMEM clearing.
- U-Boot `tetris_modem_loaded_boot.c`: actual separate firmware/NC/cache
  allocation names and capacities. `tetris_modem_reserve.c`: no-map publication,
  exclusivity, alignment and single-DRAM-bank allocator contract.
- Kernel `drivers/of/of_reserved_mem.c`: actual lookup by reserved-node basename;
  no fabricated phandle or device-region-init grant is needed for this lookup.

### Retained NOMAP lifetime (P2 review fix)

Pinned kernel `d84b264a54a37611f2f46bc19363cb9b41606205`,
`drivers/of/of_reserved_mem.c:fdt_init_reserved_mem_node()` clears NOMAP after
a failing compatible init, but leaves the catalogue entry discoverable. Rejecting
`compatible` restores the exact plain-node producer profile; it is NOT the only
retention check. No compatible means no reserved-memory init/device ops owner
with a release callback for these windows.

ARM64 `request_standard_resources()` creates top-level `IORESOURCE_MEM` resources
from NOMAP `memblock.memory`, and System RAM gets different flags. Exported
`walk_iomem_res_desc()` clips spans and preserves parent/flags, allowing an exact
gap-free coverage check; partial coverage, System RAM and child resources fail.
Then every page is checked with exported `pfn_is_map_memory()`. ARM64 selects
`ARCH_KEEP_MEMBLOCK`, so this API and its backing memory flags survive init and
are callable from the util module. A negative PFN query ALONE would accept holes;
it is used only together with positive complete NOMAP resource coverage, exact
DT DRAM containment and the matching plain reservation. Later NOMAP clearing
cannot be hidden by a stale resource entry. Module code does not directly call
unexported memblock helpers or assume init-only data remains live.

These plain boot reservations have no active release/hotplug owner in this
disabled bootstrap scope; this is an allocator/direct-map retention prerequisite,
not secure-world permission, a general kernel mutation lock, or firmware AUTH.
Page-unaligned windows fail closed (including a 4KiB-aligned tag allocation under
a larger kernel page size). No NOMAP mutation or physical RAM access is made.

## Checks

`check_metadata.py --vendor <pinned-vendor>` checks deterministic generation and
patch application without compilation. `test_static.py` checks the full installed
stack (shipping + owner + ports + prepare + lifecycle), the early bypass,
reservation-before-mapping and real dependency call. Native mode requires BOTH
`CI=true` and `GITHUB_ACTIONS=true`; public stock input and U-Boot source required.
It compiles actual producer/args lookup/import plus wire decoders with strict
warnings and ASan/UBSan: 59 producer-to-import cases (including relocated valid
allocations), wire decoder cases, and 53 actual OF/retention adapter cases with
reference balance and failure-output immutability. Native fixtures are proposed,
NOT locally executed. Actual ARM64-object CI remains required before acceptance;
mocked OF/rmem boundaries and scalar replies are not a physical cold report.
Retention fixtures include failed-init surviving catalogue entries with NOMAP
cleared (independently of compatible rejection), stale resources with one cleared
middle/last PFN, missing/partial/gapped coverage, child/System RAM resources, and
valid adjacent NOMAP spans. Output stays unpublished on every failure.
DT-only bank validation precedes AP tag mapping; payload semantic decoding
necessarily follows the single admitted AP tag copy and precedes private
publication. Firmware/NC/cache are NEVER mapped by this code.

For parent CI use the existing checker interface with `--native-ci --vendor
<pinned-vendor> --uboot <git-with-60cd9ade> --stock-container <public-modem.img>`.
No shared workflow change is included. `--uboot` also verifies the generated
model byte-for-byte against the pinned source; `--emit-model` is a review-only
regeneration operation, not an alternate producer or an admission override.
