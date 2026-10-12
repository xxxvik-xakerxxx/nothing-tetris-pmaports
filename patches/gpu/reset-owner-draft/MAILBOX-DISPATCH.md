# Unified native receive dispatcher candidate

Status: source wiring implemented; static checks only. GPU remains **Broken**.
This candidate supersedes the no-dispatch description of the resource-owner
snapshot in RESOURCE-CONTRACT.md. CI38287440390 compiled that earlier snapshot,
not these changes. No compilation, module linkage, C execution, firmware
execution, IRQ delivery or phone operation has validated this candidate.

## Implemented boundary

The bound parent's `mt6878_gpueb_control_bind_channel()` forwards through its
existing reset provider to that provider's existing reset scope. There is no
new platform driver, IRQ claimant, SRAM mapping or mailbox control claimant.
The same scope maps its four already-claimed control words and requests the
real `mailbox_irq_thread` with `IRQF_ONESHOT | IRQF_NO_AUTOEN`. Preparation
does not read/write the mapped registers or enable the IRQ.

Preflight now validates every cell in the complete eleven-channel send/receive
tables and the mailbox count/size, slot size and timesync mailbox before the
bound parent's MFG0 resume. Source is Nothing OS 4.1 device-modules commit
ee2be53cb75670b548948636a0db1d1ff112bf12; full DTS, mailbox and GPUEB IPI source
hashes remain pinned in RESOURCE-CONTRACT.json. The supplied base DTB agrees
with these properties, but its release identity remains unknown.
The supplied hash-pinned B4.1 LK's 0x1ee1c/24/30 GPR base construction and
0x1eedc/0x1eee4/0x1eeec/0x1eef0/0x1eef4 constant/read/compare path independently
check the dispatcher GPR2 address and marker in test_reset.py when
TETRIS_B41_LK is supplied. Those checks do not execute the reset-release store.

All receive offsets come from the source's cumulative TX-then-RX packing.
TX uses 216 bytes; RX uses 136 bytes; total occupied space is 352 of 640 bytes.
GPUFREQ is channel1, RX offset232, eight words. The dispatcher handles every
registered channel, including simultaneous response and event bits. It does
not interpret an event as a GPUFREQ command response or firmware readiness.
Clients must supply the appropriate channel-specific consumer.

The threaded IRQ takes the scope mutex, then borrows a synchronous read-only
accessor under the sole SRAM owner's mutex. The transaction validates both
typed leases, their common owner, quarantine state and bounded word ranges.
It reads actual GPR2 at offset8, requiring 0x55667788, samples mbox0_recv,
rejects any unknown/unregistered pending bit, and copies all indicated fixed
payloads into the thread's local snapshot. It rechecks actual GPR2 before
writing exactly the copied pending mask to mbox0_clr, then reads mbox0_recv to
flush the posted write. The SRAM mutex spans this entire sequence, so SRAM
quarantine cannot interleave between the snapshot and ACK. No raw SRAM
mapping or SRAM write API is exported.

Callbacks receive only copied words, outside both transaction mutexes, while
the threaded IRQ remains in flight. A binding pins the fixed client's device
and module; duplicate channels are rejected. Bindings cannot be replaced or
removed while published. Clients must remain bound for the entire scope
lifetime; automatic/forced driver removal and overlays remain prohibited.
Callbacks synchronously consume the payload and must not call lifecycle/bind
APIs on their own scope or retain the borrowed payload pointer. There is no
separate worker whose completion could escape synchronize_irq.
The native channel consumer performs the response completion; this candidate
does not supply a GPUFREQ request/reply or TX session adapter. A callback must
not acquire any parent/client lock held by its lifecycle caller during drain.

The target Linux kernel/irq/manage.c confirms that a NULL primary installs
irq_default_primary_handler, which only returns IRQ_WAKE_THREAD. Explicit
ONESHOT threads bypass forced-thread setup; irq_thread_fn calls thread_fn in
preemptible context, and __synchronize_irq waits for threads_active to reach
zero. test_dispatch.py checks this actual kernel API path, in addition to the
native adapter's lock order. The hard IRQ primary never touches the scope/SRAM
mutexes. Inside the SRAM transaction, snapshot_mailbox performs only bounded
reads and MMIO ACK, with no lock acquisition or IRQ wait. This is source-level
validation of the context/lock graph, not runtime lockdep/fault execution.

Quiescence closes dispatch, masks the owned IRQ once, drops the scope mutex,
and waits for the threaded IRQ including callbacks. Reset assertion invokes
this path before the existing latch write. Destruction drains before free_irq
and before dropping client pins or mappings. Synchronization/free_irq never
wait while holding the handler mutex. A failed snapshot preserves the first
error, masks the IRQ, quarantines SRAM and retains claims/pins; it never ACKs
an unconsumed bit. Reset assertion still does not prove physical OFF.

## Strict remaining blocker

There is deliberately no IRQ-enable, firmware-upload, TX or reset-release API.
Consequently ordinary preparation cannot run the dispatcher. The native
receive implementation is wired to the actual IRQ request and common parent;
an activated transport/session is not established. Static checks cannot prove
runtime acquisition/unwind or IRQ scheduling, and the earlier object-only CI
result does not validate these new cross-object symbols.

The next activation change must establish the authenticated cold-start upload
layout/provenance and independently owned power/protection/start/OFF lifecycle
before it can enable this IRQ. A GPR2 match alone cannot authorize adoption of
inherited firmware state. The 156064-byte authenticated primary still does
not justify LK's 258744-byte copy: the extra 102680 bytes and 73 unresolved
LK-tail calls are unchanged. Neither zero padding nor xfile permissions are
inferred. GPR13 and INIT_SHARED_MEM/command6 validation remain separate session
work, as do matching reserved-DRAM handoff and transitive RV33 startup needs.

Focused source tests cover the complete pinned layout, native parent/provider/
scope chain, actual GPR reads, copy-before-ACK order, sole mapping access,
quarantine exclusion, callback lifetime, mask/drain ordering and failure
retention. They do not execute C or model hardware. The existing host SRAM
fixture aborts on an unconfigured read instead of fabricating memory contents;
dedicated native read/IRQ fault coverage remains required in the parent's CI.

```sh
python3 -B patches/gpu/reset-owner-draft/test_dispatch.py
python3 -B patches/gpu/reset-owner-draft/test_resources.py --dtb /private/tmp/tetris-stock-vendor-boot-b-base.dtb
python3 -B patches/gpu/reset-owner-draft/test_reset.py
python3 -B patches/gpu/reset-provider-draft/test_provider.py
python3 -B patches/gpu/bound-parent-draft/test_control.py
python3 -B patches/gpu/test_gpueb_sram_owner.py
```

Changes remain under patches/gpu. The parent's two diagnostic FIT builder files
are reserved and untouched by this work. No shared CI, shipping patches, DT,
U-Boot or global documentation is modified; no commit/push or phone operation
is performed. No private firmware bytes are published.
