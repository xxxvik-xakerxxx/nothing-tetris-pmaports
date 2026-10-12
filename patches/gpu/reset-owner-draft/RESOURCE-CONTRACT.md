# GPUEB mailbox control ownership correction

The current native receive source revision is described in
[MAILBOX-DISPATCH.md](MAILBOX-DISPATCH.md). The no-mapping/no-dispatch and CI
statements below describe the earlier e73b771 resource-owner snapshot; they
must not be applied to the revised dispatcher source as validation evidence.

Status: disabled native resource-owner draft, statically checked and ARM64
object-compiled in CI38287440390 at e73b771. This is not native C execution,
composite module linkage or hardware activation. No local native build,
firmware execution or GPU hardware operation was performed.
This revises reset-owner-draft and its bound-parent caller under patches/gpu;
shipping patches, DT, packages and shared integration remain unchanged.

## Exact evidence and uncertainty

Source is NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878 commit
ee2be53cb75670b548948636a0db1d1ff112bf12, whose commit message declares CMF
Phone 1 Nothing OS 4.1, Tetris-B4.1-260415-1709. RESOURCE-CONTRACT.json pins
the entire DTS, mailbox driver, GPUEB IPI driver and reserved-memory driver.
All reads use git show at that commit; the checkout HEAD is not the source pin.

Read-only fdtget inspection of the supplied base DTB (338342 bytes, SHA256
187c5b7e50842a33e24d3f7beb8b268bb24d8634c2adc04efebf9c547f2b3fd8)
corroborates the topology below. Its firmware release identity has NOT been
verified. It is a base vendor_boot-b artifact, not evidence of the tree after
LK fixups or the running phone. Agreement with source does not authenticate
the artifact or establish SKU portability. No raw stock binary is included.

## Resource and interrupt topology

| Named resource | Physical start | Bytes | Native ownership |
| --- | ---: | ---: | --- |
| gpueb_base | 0x13c00000 | 0x40000 | Single whole-SRAM claim |
| gpueb_gpr_base | 0x13c3fd1c | 0x64 | Typed lease inside SRAM |
| gpueb_reg_base | 0x13c60000 | 0x2000 | Reset bank claim/mapping |
| mbox0_base | 0x13c3fd80 | 0x280 | Typed lease inside SRAM |
| mbox0_set | 0x13c62004 | 4 | New exclusive control-word claim |
| mbox0_clr | 0x13c62074 | 4 | New exclusive control-word claim |
| mbox0_send | 0x13c62000 | 4 | New exclusive control-word claim |
| mbox0_recv | 0x13c62078 | 4 | New exclusive control-word claim |

The previous reset owner claimed [0x13c60000, 0x13c62000), which excludes
every mailbox control word. An exclusive IRQ alone did not reserve these
registers. Pinned mtk_mbox_probe independently maps/claims all four names;
its mbox0_init lookup has no corresponding resource in the pinned/base DT.
This correction does not invent one or copy the vendor's optional/error paths.

The source/base DT names mbox0 as GIC SPI273, level high, with four cells
<0 273 4 0>. Root interrupt-parent is phandle1, resolving to arm,gic-v3 at
/interrupt-controller@c000000 with #interrupt-cells=4. Mali's PWR interrupt
is the same tuple. Linux's mapped IRQ is obtained by name, not hard-coded
as 273; acquisition is exclusive and NO_AUTOEN, never IRQF_SHARED.

There is one mailbox, 160 four-byte slots (640 bytes), timesync mailbox0.
Vendor setup packs all eleven TX channels first (54 slots), then all eleven
RX channels (34 slots): 88 slots / 352 bytes occupied, within mbox0_base.
GPUFREQ channel1 is TX byte offset16/length32 and RX offset232/length32.
These are table-derived transport facts, not a ready firmware session.

## Bounded production change

The existing reset owner now exports one shared, read-only memory-resource
validator. Both its prepare path and the bound-parent control path call it;
the latter does so before SRAM acquisition and native MFG0 resume. It rejects
a missing OF node, a disabled node or a node lacking the source-declared
mediatek,gpueb compatible before scanning resources. That generic compatible
alone establishes no chip identity: the exact endpoints and separately validated
attached MT6878 MFG0 supplier profile remain mandatory. It requires
exactly eight named memory resources with the pinned endpoints, rejecting
missing/extra/duplicate names and shifted, truncated, reversed or wrapping
ranges. It compares supplied endpoints to bounded static constants rather
than computing resource_size on unvalidated input. DT resources remain
immutable under the existing fixed-parent lifecycle/overlay prohibition.

After acquiring the active PM reference and typed SRAM leases, prepare claims
the reset bank and each of the four mailbox control words before mapping the
bank and requesting the disabled IRQ. It neither maps nor reads/writes the
mailbox controls. Acquisition failure releases only completed claims in
reverse order, then the bank, windows and software pins. A resource conflict
returns EBUSY; the root's existing post-resume quarantine policy still applies.
Preflight metadata validation alone does not reserve resources before resume.

Successful registration retains all control claims. Existing reset-write or
fault refusal paths return before releasing them; no new recovery/OFF path
exists. SRAM child aliases are never independently claimed. A future mailbox
dispatcher must consume this owner, since a separate driver now correctly
conflicts. The public API still exposes no mailbox register mapping or access.

## Memory handoff and next integration

gpueb-mem-table declares ID0 MEM_ID_GPUFREQ size0x4000, then ID1 MEM_ID_LOG
size0x180000: cumulative size0x184000. These are subregion sizes, not physical
addresses or a reserved-memory ownership grant. The base GPUEB node lacks
gpueb_mem_addr, gpueb_mem_size and memory-region. Its reserved-memory children
are only the two CCCI dpmaif pools and ssmr CMA; there is no GPUEB node there.
Pinned gpueb_reserved_mem_init reads those address/size fixups or state from
its reserved-memory callback, and rejects a missing base/size. No boot-time
fixup producer or post-LK reservation is proven by this inspection.

The base node also lacks power-domains and #reset-cells required by the
existing native draft. It cannot be enabled as-is. Main now stages the revised
reset C/H and bound-parent C together; actual ARM64 objects compiled in
CI38287440390. Next describe all eight resources on one disabled fixed parent
and complete real module linkage and acquisition-fault execution. The shared
validator export must resolve to the same reset owner; no stub or second
claimant is acceptable.

Before any start, establish the actual GPUEB DRAM handoff and protected owners
from matching LK/ATF and post-LK DT evidence, then implement the unified
disabled-IRQ dispatcher, GPR/transport ordering and independently proven OFF
path. The authenticated upload range is not changed here. lk-tail still has
73 unresolved calls; no complete producer proof or larger upload is claimed.
GPU remains Broken; neither render-node creation nor accelerated rendering
is established by this work.

## Reproduce and limits

```sh
python3 -B patches/gpu/reset-owner-draft/test_resources.py --dtb /private/tmp/tetris-stock-vendor-boot-b-base.dtb
python3 -B patches/gpu/reset-owner-draft/test_reset.py
python3 -B patches/gpu/bound-parent-draft/test_control.py
python3 -B patches/gpu/reset-provider-draft/test_provider.py
```

The focused resource tests compare production constants with full-source pins,
check aliases/disjoint claims, validation/claim/unwind/quarantine source order,
and verify every recorded DTB property through read-only fdtget. They do NOT
execute the C validator or fault paths. Without --dtb the actual-DTB test is
explicitly skipped. CI must compile/link the real objects and exercise busy
claims at each of the four positions, map/IRQ failures, malformed resources
and retained ownership after faults. Existing object runners include the
revised reset C/H without a shared workflow edit. Those runners passed in CI,
not locally; acquisition-fault execution remains unperformed.
