# Unified SRAM owner candidate (not packaged)

Production files are `mt6878-gpueb-sram{,-core}.{c,h}`. No existing patch,
DT, APKBUILD, shared workflow or frozen U-Boot is changed. The candidate Kconfig
is bool/default n and is not sourced by shipping Kconfig. The external Makefile
is for object smoke only, not a shipping module or unload policy.

Provenance: device modules ee2be53cb75670b548948636a0db1d1ff112bf12,
`arch/arm64/boot/dts/mediatek/mt6878.dts` gpueb resources:

| Window | SRAM offset | Size |
|---|---:|---:|
| Whole SRAM | 0 | 0x40000 |
| GPR | 0x3fd1c | 0x64 |
| Mailbox data | 0x3fd80 | 0x280 |

The whole SRAM base is 0x13c00000. These are validated hardware-profile resource
bounds, not addresses harvested from one running unit. SRAM size and clear span
also match the authenticated B4.1 LK allocation audit. Mailbox control/reset
resources outside SRAM are not claimed or inferred by this candidate.

## Real ownership implemented

The owner validates the complete resource before allocation, claims the entire
SRAM exactly once, maps it and retains the parent device reference. It uses
explicit allocation, not devm cleanup. Failed map unwinds the claim; a failed
resource claim never maps. GPR/mailbox leases are typed, disjoint and limited
to one client per type. A controller mutex serializes lease creation, metadata
access, release, quarantine and close. Returned metadata has bounds/alignment
checks; no raw mapping is exported and no hardware register is accessed.

Live leases prevent destroy. The caller must serialize final destroy against
new calls using its parent lifecycle lock; a consumed raw controller handle
cannot safely be reused. Each lease must be released once and must not be used
concurrently with its final release. This is an ordinary explicit lifetime API,
not a promise to reject arbitrary platform-driver unbind callbacks.

Calling unknown_start **before** any future partial-start procedure irreversibly
quarantines the owner. Existing leases can be put but cannot obtain new resource
metadata. Even with zero leases, destroy returns EBUSY without unmapping,
releasing the resource or dropping the parent reference. No software OFFLINE,
reset or callback clears quarantine. No boot recovery API is supplied because
physical OFF is not proven. Owner integration must retain a quarantined handle
and prohibit parent removal; `platform_driver.remove()` cannot return refusal
on this kernel. Do not hide this limitation behind devm or module unload.

## Validation and integration

Pure static: `python3 patches/gpu/test_gpueb_sram_owner.py`.
It checks the exact pinned DT, single claim, disjoint windows, no MMIO/activation,
quarantine guard, actual production source inclusion and CI-only build guards.

CI native: `sh patches/gpu/run_gpueb_sram_owner_ci.sh` with CI=true.
The fixture compiles the actual adapter and core with mocked Linux resources,
ASan/UBSan and pthread mutexes. It exercises malformed ranges, partial-window
claims, duplicate owners/clients, map/allocation failure, bounded typed metadata,
concurrent same-window acquisition, active-client removal refusal and retained
resources after unknown start. No firmware, physical OFF or hardware is simulated
as proven. Quarantined mock memory is disposed by the fixture itself only after
asserting that the production API refused teardown; this is not a recovery path.

CI kernel object smoke: `sh patches/gpu/sram-owner/smoke-kernel-ci.sh` with
CI=true, TETRIS_KERNEL_TREE and TETRIS_KERNEL_OUT pointing to the existing
prepared/configured ARM64 kernel. Use the CI toolchain environment (for example
LLVM=1). Only production files are copied to a temporary external object tree.
This builds both touched objects, not a kernel image and not a modpost/load test.

Main must integrate those independent runners into a future CI snapshot. No
packaging is requested yet. Frozen 0120 still independently claims GPR; do not
enable it together with this owner. A later reviewed integration must remove
that duplicate claim and use parent-issued windows, then implement IRQ quiescence
and bounded MMIO access under the ownership lock. The present metadata leases
do not claim BOOTREADY or an active GPUFREQ transport.

Next hardware gate remains blocked by 156064 authenticated bytes versus the LK
258744-byte copy, absent authenticated persistent firmware handoff, real reset/
power ownership and missing physical OFF proof. No padding, SRAM clear, reset,
firmware start, mailbox IRQ acknowledgement, DT activation or phone operation
is performed here.
