# Modem network candidates

These candidates are not in APKBUILD, emit no installed module and do not
enable modem, SIM, IRQ, DMA, firmware, regulator or secure-call execution.
They target Nothing B4.1 device modules
`ee2be53cb75670b548948636a0db1d1ff112bf12` and Linux 6.18
`d84b264a54a37611f2f46bc19363cb9b41606205`.

## CCMNI

0001 adapts the cellular network interface to size-aware sysctl registration
and the new NAPI GRO node. The sysctl remains `net/tcp_pacing_shift`; its
sentinel is removed because register_sysctl() supplies the array size.
Flush ordering, public receive-list delivery and queue reset are preserved.

The first unmodified ARM64 compile failed on ctl_table.child,
register_sysctl_table(), missing napi_gro_flush declaration and removed
napi_struct rx_count/rx_list fields. A first implementation using
gro_flush_normal() compiled but produced an undefined reference to
netif_receive_skb_list_internal(), which Linux does not export. That version
was rejected. The final candidate includes net/gro.h and retains the public
netif_receive_skb_list() path; the unexported dependency is absent.

The final ccmni.o compiled with clang 21.1.8 and hard errors for implicit
declarations, incompatible pointers and integer conversions. Four original
missing-prototype warnings remain. The prepared kernel used clang 21.1.2;
this is a targeted object check, not full modpost or a CI kernel build.

## RPS

0002 includes the Linux 6.18 headers that now own struct rps_map,
RPS_MAP_SIZE and struct netdev_rx_queue. The original rps_perf.o failed on
these missing definitions; the candidate compiled successfully. Its exported
set_rps_map() supplies the CCMNI vendor dependency. The newly inspected
kernel references __gro_flush, gro_receive_skb, netif_receive_skb_list,
netif_napi_add_weight_locked and rps_needed have exports in the pinned kernel.
The complete configuration-dependent symbol closure is not yet proven.

This header change does not validate the vendor RPS runtime algorithm.
Before activation, review its private mutex against the kernel's RX queue
map update serialization, CPU hotplug and full cpumask initialization. Do
not interpret object compilation as permission to invoke map updates.

## Reproduction and tests

Run `sh patches/modem/check-ccmni.sh /path/to/device-modules-git`.
It archives exact pinned source, checks/applies both patches and extracts the
actual CCMNI flush helper into a host harness. Forty-eight cases cover queued
packets, packets completed by GRO flush, empty queues and repeated flushes.
A stale-count mutant must fail. It does not execute the kernel network stack,
packet payloads, RPS, sysctl registration or concurrency.

Targeted build staging is local under the diagnostic Docker mount:
`/probe/modem-ccmni`, with drivers and headers archived from the pinned commit.
The object targets are `ccmni.o` with CONFIG_MTK_NET_CCMNI=m and
DEVICE_MODULES_PATH pointing to that staging root, and `rps_perf.o` with
CONFIG_MTK_NET_RPS=m. No .ko was built or copied to the phone.

Next: combine these dependencies with the exact ECCCI/DPMAIF object set and
kernel Module.symvers, classify remaining unresolved symbols and validate
runtime memory, firmware, secure-world and userspace contracts. A network
interface alone cannot provide SIM state, network registration, voice or SMS.

## Combined object inventory and optional MRDUMP

`object-symbol-audit.json` records hashes and consumers/providers for 64
diagnostic objects. It includes the final FSM/port/non-page-pool DPMAIF set,
core, CCIF, 14 ccci_util constituents, CCMNI/RPS, common modem/HIF, and the
newly checked `ccci_auxadc.o` and `udc/udc.o`. The latter two compile without
source changes. UDC here is callback registration/dispatch, not proof that a
compression provider has registered or that modem negotiation supports it.

New object builds explicitly select clang-21 (21.1.8), while the prepared
kernel reports 21.1.2. The default clang had moved to 22.1.8; the initial four
core/CCIF builds with that default were repeated with clang-21. Existing
missing-prototype warnings remain. The inventory reader is llvm-nm 22.1.8;
its version and the kernel configuration SHA are included in the report.

The inventory exposed an unconditional `mrdump_mini_add_extra_file()` call
in `fsm/ap_md_mem.c`. Candidate 0003 gates only MDSS crash-dump registration
on `IS_ENABLED(CONFIG_MTK_AEE_IPANIC)`, matching the existing conditional in
`hif/ccci_dpmaif_debug.c`. It does not stub the callback, modify shared-memory
layout, bypass MPU protection, or change modem power/boot behavior. The patch
is outside APKBUILD. Dry-run/application and checkpatch passed (zero warnings).
The actual ap_md_mem object was built twice: defining CONFIG_MTK_AEE_IPANIC=1
retains the undefined MRDUMP symbol, while the final build with it absent
removes that reference. Both builds passed without suppressing hard errors.

The final inventory has 242 distinct unresolved symbols. A literal export
search in the pinned Linux source finds 235; four additional symbols have
macro-based export evidence: get_random_u32 (drivers/char/random.c),
netdev_err/netdev_info (net/core/dev.c), and __tracepoint_sched_set_state_tp
(kernel/sched/core.c). __this_module is generated by modpost. The remaining
__bad_copy_from/__bad_copy_to are compile-time error declarations from
include/linux/ucopysize.h visible in LTO objects: they must disappear during
final code generation or fail the build, never be stubbed or ignored.

Source export matches are hints, NOT configured-kernel export/CRC proof.
/kernel/Module.symvers is absent in this diagnostic tree. No .ko was linked,
loaded or shipped. The earlier 241-reference count covered a different set
and must not be compared as a success metric. Multiple definitions in the
report include weak/strong fallback pairs and separate-module init/debug
symbols; the inventory does not flatten actual module ownership boundaries.

Reproduce the inventory inside the diagnostic container with:

```sh
python3 audit-object-symbols.py --config /kernel/.config \
  /tmp/nothing-devmods-0095-final/drivers/misc/mediatek/eccci \
  /tmp/nothing-devmods-0095-final/drivers/misc/mediatek/ccci_util \
  /probe/modem-ccmni \
  /tmp/ccci-common-r149/devmods/drivers/misc/mediatek/eccci/ccci_modem.o \
  /tmp/ccci-common-r149/devmods/drivers/misc/mediatek/eccci/hif/ccci_hif.o
python3 test-object-symbols.py
```

Five inventory unit tests passed, including weak-reference handling and
preservation of multiple providers. The next link gate needs the actual
configured kernel Module.symvers, separate composite-module ownership,
final LTO/code generation and modpost. It must also cover the page-pool
configuration, UDC provider lifecycle and runtime handoff prerequisites.

## Composite code generation and page-pool candidate

The next diagnostic gate generated actual ELF64/AArch64 relocatable objects
through the vendor Kbuild composition: ccci_md_all.o, ccci_util_lib.o,
hif/ccci_ccif.o and hif/ccci_dpmaif.o. This is stronger than individual LLVM
bitcode compilation, but is NOT final module linkage: no .ko, module export
validation or CRC check was performed. Clang was explicitly 21.1.8; ld.lld
and llvm-nm were 22.1.8. This mixed diagnostic toolchain is not CI equivalence.
Existing prototype and format warnings were retained, not suppressed.

`composite-symbol-audit.json` records these four objects with the non-page-pool
DPMAIF variant (195 remaining symbols). `composite-page-pool-symbol-audit.json`
records the same four boundaries with RX_PAGE_POOL enabled (207). These are
different input sets from the earlier 64-object inventory and their counts
must not be compared as progress percentages. The final code-generated objects
have no __bad_copy_from, __bad_copy_to or MRDUMP undefined references.

The first page-pool compile failed at the removed net/page_pool.h include in
ccci_dpmaif_page_pool.c; after that was addressed, the shared ccci_dpmaif_com.h
include failed too. Candidate 0004 updates both to net/page_pool/helpers.h,
explicitly includes linux/sysctl.h, and replaces the removed child-table
sysctl API with register_sysctl("net", devalloc_threshold_table). Its sentinel
is removed for size-aware registration. The setting remains
net/devalloc_threshold. No allocation, recycling or DMA policy is changed.

With 0004, the page-pool object and the complete hif/ccci_dpmaif.o composition
both pass. Kbuild CONFIG_PAGE_POOL=y adds RX_PAGE_POOL and includes
ccci_dpmaif_page_pool.o, rather than pretending the no-pool branch covers it.
Both 0003 and 0004 remain outside APKBUILD and autoload lists.

The existing page-pool runtime still needs a separate ownership audit:
it seeds the pool with CMA pages, directly writes page->pp/pp_magic and
pages_state_hold_cnt and peeks into private allocation/ring state. The original
fixed 1500-byte DMA mapping is addressed by candidate 0005 below. Pool destruction,
CMA release, allocation-failure unwind, concurrent recycling and DMA length
must be proven before enabling this path. Compile success validates none of
those contracts; do not load this candidate for a speculative DMA test.

All candidates apply to clean files archived from exact B4.1:

```sh
sh patches/modem/check-candidates.sh /path/to/device-modules-git
```

0004 checkpatch reports zero errors and warnings. The first hand-written
hunk length was corrected before application; the final patch applies with
zero fuzz and passes git apply --check against the pinned original files.

For the actual Kbuild gate, use the existing exact-source staging with
ARCH=arm64 LLVM=1 CC=clang-21 CONFIG_MTK_ECCCI_DRIVER=m and the strict KCFLAGS
recorded above. Targets are ccci_md_all.o at the ECCCI root, ccci_util_lib.o
at the util root, and hif/ccci_ccif.o plus hif/ccci_dpmaif.o at the ECCCI root.
Run the DPMAIF target with CONFIG_PAGE_POOL=n and then y. Never substitute a
whole-directory symbol scan once composite .o files exist: that would count
constituents and their composed providers twice. The two composite inventories
use four explicit filenames.

CI r153 run 34492172863 currently exposes only install images, logs and the
radio live bundle; none is a configured kernel development-tree artifact.
The workflow does not preserve Module.symvers. Final modpost remains pending
actual matching kernel exports, plus the missing SCP/control and UDC runtime
contracts. No new full kernel build or phone action was performed here.

## Page-pool DMA length correction

Candidate 0005 fixes a concrete map/unmap size mismatch, independently of the
remaining CMA ownership problems. At pinned B4.1, skb_alloc_from_pool() maps
1500 bytes, while alloc_bat_skb() in ccci_dpmaif_bat.c stores the whole
skb_data_size() as data_len. Both receive completion (ccci_dpmaif_com.c) and
BAT teardown unmap that data_len. Linux Documentation/core-api/dma-api.rst
requires matching map/unmap sizes. The vendor packet-size options are 1024
and 1664 bytes, so the literal 1500 can also be shorter than the requested
packet buffer.

0005 checks pkt_buf_sz against usable skb capacity after the headroom reserve,
frees/recycles the skb on insufficient capacity, and maps the same capacity
that BAT records for later unmapping. The normal allocator fallback remains
available to the existing caller. It does not change BAT hardware settings,
MTU, physical addresses, pool sizing or runtime enablement.

check-candidates.sh now extracts the patched allocation function into the
page-pool-dma-test.c host harness. All 175 cases pass: capacities 0/1024/1500/
1664/3712, seven request sizes including UINT_MAX, and success/missing-pool/
page-allocation/skb-allocation/DMA-map failure. It verifies mapping lengths,
no DMA mapping for oversized requests, and cleanup on errors. Mutants restoring
the 1500-byte map or disabling the capacity check are both rejected. This is
a recorder model of allocation/DMA callbacks, not a real page-pool, cache,
DMA-debug, concurrent receive or kernel allocator test.

The patched page-pool source and complete ccci_dpmaif.o composition pass the
same diagnostic ARM64 gate (Clang 21.1.8, LLD 22.1.8), with the existing
missing-prototype warning retained. 0005 checkpatch reports zero errors and
warnings. Final diagnostic SHA-256 values after 0004 + 0005:

- ccci_dpmaif_page_pool.c: 3bbbe44558f4862f23fc510bcffa39b0af1bce9260f66fedbc7b4c56adefc6a4
- ccci_dpmaif.o: 3414e74401c2c77b45c33403df947fc1eda8999cd6a1b6dfe98d40c996cd3563

The earlier composite-page-pool-symbol-audit.json is a historical pre-0005
snapshot, not the hash of this updated object. 0005 is not packaged or run;
matching kernel modpost, memory ownership, DMA isolation and actual radio
functionality remain required gates.

## CMA pool ownership finding

Further exact-source review found no caller of
ccci_dpmaif_destroy_page_pool() and no cma_release() in the ECCCI subtree.
Pool creation is reached from ccci_dpmaif_bat_late_init(). This is not a
proven stop/restart cleanup path.

There is also an immediate initialization mismatch: vendor
dpmaif_put_page_pool() sets the normal page count, pp pointer and pp_magic,
then calls page_pool_recycle_direct() and increments pages_state_hold_cnt.
It does not initialize the separate pp_ref_count. Linux 6.18's
page_pool_set_pp_info() initializes that count to one via
page_pool_fragment_netmem(). Its page_pool_put_netmem() checks and decrements
that separate count before recycling. An initial zero would decrement to -1,
warn and skip recycling; an initial count above one would also skip the
enqueue. No guarantee that a CMA page arrives with pp_ref_count==1 has been
established. Normal init_page_count() does not supply that contract.

Do not fix this merely by forcing the missing count while leaving CMA release,
pool inflight accounting and single-producer requirements unreviewed. The
native allocation/ownership design needs the full lifetime, including pages
still held by the network stack, rather than a compile-only field update.
This optional page-pool path remains unactivated. The first current live
modem failure is earlier: U-Boot publishes no-fdt and payload-not-checked, as
recorded in docs/MODEM_SIM_EVIDENCE_PLAN.md. Resolve the boot handoff before
attempting modem power/DMA execution.
