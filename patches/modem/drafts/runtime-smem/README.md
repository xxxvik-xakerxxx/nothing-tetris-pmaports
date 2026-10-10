# Transactional runtime SMEM candidate

DISABLED / UNTESTED ON HARDWARE. Only new files in this directory. No shared
headers, shipping recipe, Kconfig, DT, board hook or operational registration
changed. Physical START/STOP and monitor paths remain denied by the existing
owner/prepare stack. Native C runs only in GitHub CI; no local compilation.

## Concrete implementation

`arguments.c` reads the real `mtk_ccci_find_args_val()` API during the same sole
serialized util-init lifetime as the owned importer. It reads bounded counts,
CHK512 and complete NC/cache rows, retains the first error/short-read failure,
and frees staging on every exit. It NEVER maps ROM or SMEM. It requires banks
from the existing retained DT/reservation validator, not report address40.
The current importer has no public immutable bank-snapshot export: this adapter
is deliberately NOT called automatically from util init.

`smem.c` creates one private decoded owner, without retaining caller buffers.
It reuses exact pinned pure SMEM planner/profile functions, checks the current
producer's full firmware/NC/cache/tag reservation capacities and overlaps,
normal Linux CCBgear1/PHY-off/UDC-off/DRDI3 profile, CHK version/image/bind/size,
every real AND padding row's ID/AP physical/AP virtual/offset/size/alignment/
flags/MD offset, and exact row counts. An invalid/missing/alternate unsupported
profile fails before mapping; output is unchanged. This is layout consistency,
NOT authentication or a verified SKU selector.

`tetris_smem_preview()` provides concrete consumer-owned `ccci_mem_layout` and
all configured SMEM table entries, with NULL virtual addresses. Templates are
from the pinned actual B4.1 vendor, including absent zero-sized MD_POST_DUMP
and tail guards (26 NC, 11 cache entries). This differs from an older local
vendor checkout: working-tree tables are not authoritative. CCB aliases match
`post_cfg_for_ccb()` exactly: DHL/monitor/META share the first2MiB; RAW_DHL/MDM
share the remaining20MiB for gear1. Missing regions remain zero, without vendor
unsigned offset underflow. Flags retain real vendor clearing policy; this
candidate NEVER clears memory or emits a debug/runtime-file registration.

The bank totals are the complete USED wire extents, including padding, matching
vendor `md_*_smem_size_cal()`, NOT the rounded MPU capacities or full128MiB tails.
MD views are source-backed bank4 `0x40000000` NC / `0x48000000` cache; AP bases
come exclusively from caller-owned validated reservations. Firmware logical
size remains CHK memory_size, while overlap validation retains the full512MiB.

The **unattached internal transaction** in `private.h` is executable code but
has NO production caller or build activation:

1. Build page-rounded spans from real physical extents, covering intervening
   alignment gaps. Do not sum sizes across skipped padding (old vendor mapping
   can under-map such a span). Reject page aliasing into any NO_MAP region.
2. Use `ioremap_wc()` for retained no-map SMEM, matching the actual non-map
   branch of `ccci_map_phy_addr()`. No WB/vmap fallback or guessed DMA sync.
3. On first mapping failure reverse-unmap all created spans, clear all private
   virtual pointers, latch the first error and disallow retry/publication.
4. Only after all mappings succeed populate virtual pointers and CCB aliases.
   CONSYS remains NULL/unmapped; cache-total virtual is deliberately NULL.
5. Commit into one private slot under `slot -> owner` mutex order. No external
   callbacks or device/scope locks. Failed publication unmaps only its own
   unpublished owner, preserving the original slot and first failure.
6. Export immutable owner tables into consumer-owned copies. Reject short or
   overlapping outputs and aliases into the private capsule. Once published,
   destroy returns EBUSY: no resource release while consumers may exist.

Object owner creation/destruction requires the sole caller's lifetime ownership;
the mutex is NOT a reference count against concurrent destroy or module unload.
Slots initialize exactly once. No API here calls `ccci_tetris_register_prepared`,
`ap_md_mem_init`, HIF doorbells, SMC, firmware START/STOP, or publishes util globals.

## Exact source boundaries

- Vendor `ee2be53cb75670b548948636a0db1d1ff112bf12`:
  `drivers/misc/mediatek/ccci_util/ccci_util_md_mem.c`:
  rt_smem_region_lk_fmt (40 bytes), map_phy_to_kernel/map_and_update_tbl,
  SMEM_ATTR_PADDING4/NO_MAP8, real hash/getters and MD offset +0x40000000;
  `ccci_util_lib_fo.c:ccci_map_phy_addr` selects WC for non-map PFNs;
  `eccci/fsm/ap_md_mem.c` actual tables/post_cfg_for_ccb/ap_md_mem_init/clearing;
  `eccci/fsm/ap_md_mem.h` and include/mt-plat/mtk_ccci_common.h actual types/IDs.
- U-Boot `60cd9ade5b999732304f3b755c7dbe3d34307c13`:
  `board/mediatek/mt6878/tetris_modem_layout.c/.h`: exact smem_place and B4.1
  planner copied mechanically; `tetris_modem_loaded_boot.c` owns separate LMB
  banks and source-scoped boot initialization; `tetris_modem_emi_rows.c`:
  NC slot42 / cache slot43; `tetris_modem_bootstrap.c` programs/replies while OFF;
  `tetris_modem_final.c`/`tetris_modem_ccci_tags.c` actual final descriptor/tags.
- Metadata producer/consumer `190ea155e1a8343dbdb4f0992f06b92848c9cdac`:
  unchanged metadata_resources.h ABI and exact tetris_metadata_windows helper.
- Kernel `d84b264a54a37611f2f46bc19363cb9b41606205`:
  ARM64 retained NOMAP/resource validation is provided by the existing metadata
  candidate; mere reserved_mem catalogue presence is NOT admission/permission.

`source_model.h` mechanically extracts only used pure functions/types and actual
vendor templates. Complete positional initializers are padded with zeros to
match C semantics without relaxing strict native warnings. No unused general
memory-map planner is pulled into this translation unit.

## Real missing producer, not a new boolean gate

The current chosen80-byte BROM report and final21 tags bind layout/result but
do NOT carry authenticated platform/SKU or an immutable kernel-consumable
binding of actual EMI slot42/43 policy+range readbacks to these bank reservations.
The existing source-scoped NS BL33 startup proof is not silently promoted to
a runtime Linux admission record. No concrete NS denial is asserted here;
the real range/security/ownership producer needed for automatic Linux mapping
is absent from the current handoff ABI. There is no grant callback, chosen hash,
caller READY bit or newly invented global no-repower assertion in this code.

Coherency prerequisite: actual U-Boot service initialization/cache flush must
complete for the same retained allocations, all former WB aliases must cease,
and the reserved NOMAP lifecycle must remain owned. Map WC for BOTH banks (the
"cache" name describes MD view, not permission to use AP WB caching). A WC
mapping success is not secure access proof or DMA/transport readiness. CONSYS
is a separate owner and must not be mapped/cleared via this transaction. Pinned
CCIF register-write helper uses mb(); future runtime-data/doorbell ordering must
remain on the real source transport path, not be replaced by a guessed sync.

Until these producers and the reviewed cold/final publication exist, only the
pure create/arguments/preview path is admissible for integration. The private
mapping functions are review/CI candidates, NOT permission checks; calling them
early could fault despite a successful ioremap. Physical registration stays OFF.

Next actual integration, AFTER admission: retain/export the existing immutable
bank metadata under its actual lifetime; replace legacy util SMEM mapping/hash
publication with this transaction (do not run both); export into md-owned
tables inside the unpublished prepare transaction instead of the void legacy
ap_md_mem_init(); bypass its duplicate post_cfg_for_ccb and optional debug-file
side effect; retain real getters/MD-runtime ABI and first-error propagation.
Do not set LK_LOAD_MD_EN/READY or invoke registration from this sidecar.

## Validation and parent integration

Source-only checks:
```sh
python3 patches/modem/drafts/runtime-smem/test_static.py
python3 patches/modem/drafts/runtime-smem/check_smem.py \
  --vendor ../android_kernel_device_modules_6.1_nothing_mt6878 \
  --uboot ../u-boot-mt6878 --check-stack
```

New-file-only `runtime-smem.patch.vendor` applies AFTER the unchanged complete
shipping adaptations/owner/ports/prepare/lifecycle/metadata stack. It adds no
Kbuild objects, wrappers or shipping calls. For independent AArch64 object CI,
compile only `ccci_util/tetris_runtime_smem/{smem,arguments}.o`, using the real
generated kernel headers and existing research owner config, plus include paths
ccci_util, eccci/fsm, drivers/misc/mediatek/include. Do NOT link or enable a driver.
Required defined symbols: create/preview/destroy/map_private/publish_private/
export_private/slot_init in smem.o, from_arguments in arguments.o. Undefined
mtk_ccci_find_args_val is the real util provider, not a secure permission API.

CI-only native fixture (parent supplies the existing public plaintext md1rom
container produced by the manufacturer oracle; no download/extraction here):
```sh
python3 patches/modem/drafts/runtime-smem/check_smem.py \
  --vendor ../android_kernel_device_modules_6.1_nothing_mt6878 \
  --uboot ../u-boot-mt6878 --native-ci --stock-container out/stock-modem/md1img.bin
```
Runner requires BOTH CI=true and GITHUB_ACTIONS=true. It includes production
C bodies unchanged, actual vendor types/enum and generated source model, strict
Wall/Wextra/Werror + ASan/UBSan, 70 cases per4KiB/64KiB geometry. Only allocation,
arguments, mutex and mapping boundary APIs are mocked. Physical contents are
never read/written. Public stock CHK is a test vector, not authentication.
Cases include malformed CHK/policy/each row field/padding/ID/count, full-tail
overlap/resource profile/alignment/overflow, allocation and each map failure,
reverse unwind, first-error/no retry, premature/colliding/repeated publication,
published lifetime, output aliasing, immutable input lifetime, CCB aliases,
unmapped zero/NO_MAP rows, alternate allocation bases, short/error arguments,
page-rounded CONSYS exclusion and consumer-copy isolation.

Local result: 15 Python/source/patch checks PASS, including exact complete-stack
application. Native and actual ARM64 compilation
are still pending new CI; previous metadata59+64 CI does NOT cover these files.
