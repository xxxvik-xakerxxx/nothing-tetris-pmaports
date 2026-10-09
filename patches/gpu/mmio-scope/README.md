# Bounded parent MMIO scope candidate

New files only. No frozen SRAM/adoption/U-Boot changes, DT activation, packaged
Kbuild or shared CI edits. Config is bool/default n and not sourced by shipping
Kconfig. The external Makefile builds objects for CI only.

## Proven resource and transaction rules

Pinned device modules: ee2be53cb75670b548948636a0db1d1ff112bf12.
`mt6878.dts` gives GPR 0x64 and mailbox data 0x280 bytes inside the full-SRAM
parent claim. The new scope adopts both typed leases via the existing frozen
parent adapter, never independently claims those SRAM slices, and maps them
without touching registers. Separate parent control resources are each 4 bytes:

| Resource | Physical address |
|---|---:|
| mbox0_send | 0x13c62000 |
| mbox0_set | 0x13c62004 |
| mbox0_recv | 0x13c62078 |
| mbox0_clr | 0x13c62074 |

These resources are validated before acquisition, then claimed independently
because they lie outside SRAM. No guessed aggregate control span is mapped.
The gpueb_ipi.c helper's other bank at +0x84/+0x88 is NOT mbox0.

GPUFREQ channel 1 has eight words, TX byte offset 0x10 and RX 0xe8, calculated
from the pinned cumulative send/receive tables. The engine emits eight separate
ordered writel operations, then writes bit 1 to SET. It reads RX into a temporary
frame before clearing only bit 1 and publishing the output. Other channels are
never ACKed. No firmware memory writes or arbitrary GPR writes exist. The pinned
mtk-mbox.c ISR reads the direct-mode frame before IRQ clear; upstream GPUEB
mailbox also reads before ACK. Callback timing/whole-bank ownership are NOT
proven by this narrower fact. No response IDs are invented.

Bounds are overflow-safe, 4-byte aligned and exact per region. Fault tests
simulate failure at every TX/RX operation, atomic RX output, first-error retention,
no post-fault retries and channel-busy handling. Kernel readl/writel do not turn
bus aborts into recoverable callback errors; native fault injection is a logic
test, not a claim that an inaccessible live rail can be probed safely.

## Actual scoped lifetime

One IRQ-safe spinlock encloses each complete TX/RX/GPR operation, including the
ACK/doorbell, not one lock per word. Async users must acquire a scope reference
before publishing pointers, and release it only after callbacks/work finish.
Quiesce obtains that same lock, drains in-flight MMIO, blocks new references,
and leaves existing references preventing removal. A parent lifecycle lock must
serialize final destroy against unpublished/raw handle users.

An attempted transaction or unknown partial start latches physical uncertainty.
Quiesce does NOT prove OFF and cannot erase this latch. Destroy then refuses
without releasing control claims, SRAM leases or mappings, even after all users
leave. Unknown partial start is also forwarded to the frozen full-SRAM owner
in process context, never while holding an IRQ spinlock. A fault seen in an
IRQ-safe transaction retains scope mappings/leases immediately; a real future
owner must arrange process-context quarantine propagation and IRQ drainage.

## First unproven boundary: power and IRQ activation

The kernel scope initializes UNPROVEN. Production has no transition into the
transaction phase and no public activation setter, fake proof callback, boot
flag or automatic promotion from RPROC_RUNNING. Every public transfer therefore
returns EHOSTDOWN before MMIO today. Preparation only claims/maps known resources.
The transaction-phase fixtures are synthetic software preconditions, not a real
power/ownership acknowledgement.

The new IRQ entry stops at EHOSTDOWN for unproven power. Even after future power
proof it would refuse EOPNOTSUPP: mbox0 is GIC SPI 273, level-high and serves more
than GPUFREQ. The pinned vendor driver assumes stock LK already started GPUEB,
requests the entire bank and has no proven physical OFF/remove sequence. That
does not establish kernel cold-start power/clock ownership, safe level-line
masking, other-channel boot traffic handling, or IRQ release under partial start.
No request_irq, IRQ enable/disable/ACK test or IRQ reservation occurs here.

Thus this candidate implements real bounded MMIO functions and callback-reference
teardown, but does NOT claim registered IRQ lifecycle/whole-bank ownership or a
working transport. Existing frozen closed caller patch is not automatically
rewired; a future source-proven power/IRQ owner must integrate this scope rather
than export raw mappings or open a software-ready flag.

## Next gates

Static: `python3 patches/gpu/test_gpueb_mmio_scope.py`.
Native CI: `sh patches/gpu/run_gpueb_mmio_scope_ci.sh`, CI=true (ASan/UBSan).
ARM64 object CI: `sh patches/gpu/mmio-scope/smoke-kernel-ci.sh`, CI=true with
prepared TETRIS_KERNEL_TREE/TETRIS_KERNEL_OUT and the CI toolchain environment.
The smoke builds both new production objects, not a module/image or live test.

Before any hardware access: prove physical MFG/reset/clock ownership and complete
mbox0 IRQ ownership/boot traffic handling, then a real OFF failure path. The
156064 vs 258744 upload span and authenticated persistent firmware handoff are
still separate blockers. No padding, firmware start or guessed rail is added.
