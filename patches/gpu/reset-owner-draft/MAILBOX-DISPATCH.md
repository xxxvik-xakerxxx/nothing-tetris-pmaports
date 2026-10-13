# Unified native receive dispatcher candidate

Current bounded follow-up: [DISPATCH-LIFETIME.md](DISPATCH-LIFETIME.md) implements
the opaque full-bank lifetime handle, frozen consumers, parent module/device/PM
pins, RX driver checks and refusal of premature/uncertain teardown. That handle
is now mandatory for both TX and RX, but it cannot activate dispatch. The
parent's reported TX/RX fixture CI38315471685 predates this lifetime revision;
the expanded fixture and ARM64 objects still need parent CI validation.

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
mapping or arbitrary-offset SRAM write API is exported. The bounded TX extension
below adds only a complete fixed channel slot transaction.

Callbacks receive only copied words, outside both transaction mutexes, while
the threaded IRQ remains in flight. A binding pins the fixed client's device
and module; duplicate channels are rejected. Bindings cannot be replaced or
removed while published. Clients must remain bound for the entire scope
lifetime; automatic/forced driver removal and overlays remain prohibited.
Callbacks synchronously consume the payload and must not call lifecycle/bind
APIs on their own scope or retain the borrowed payload pointer. There is no
separate worker whose completion could escape synchronize_irq.
The native channel consumer performs the response completion; this candidate
does not supply a GPUFREQ command/session adapter. A callback must
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

There is deliberately no IRQ-enable, firmware-upload or reset-release API.
Consequently ordinary preparation cannot run the dispatcher. The native
receive implementation is wired to the actual IRQ request and common parent;
an activated transport/session is not established. Static checks cannot prove
runtime acquisition/unwind or IRQ scheduling, and the earlier object-only CI
result does not validate these new cross-object symbols.

## Bounded native TX extension

`mt6878_gpueb_reset_trysend(scope, client, channel, words, count)` is a single
nonblocking submission by the exact pinned channel client, not a command/reply
completion. It rejects a missing/replaced parent or client driver, a quiesced or
reset scope, the sticky first fault, an in-flight response channel, or inactive
owned dispatch. Both internal activation provenance and the actual IRQ descriptor
must be active. No caller boolean or externally enabled line can authorize TX.
There is **no production setter** for `dispatch_active`: ordinary valid calls
currently return `-EOPNOTSUPP` without MMIO. An externally forced IRQ is masked
once without SRAM access/ACK while this owned gate is closed.

The actual send code is ready for a later reviewed cold-start/IRQ activation
transition. It copies at most nine words locally, takes the existing scope
mutex, then uses both exclusive typed leases under the SRAM mutex. The SRAM
owner's retained parent is checked against the actual platform parent during
scope preparation, before taking its runtime-PM reference. The SRAM
transaction accepts only a channel and its exact full word count; it returns
neither a mapping nor an offset-writing accessor. TX byte offsets are
`0,16,48,60,84,120,136,160,184,188,204`, derived cumulatively from the pinned
eleven-channel send table. Short messages, extra words and channels beyond10
are rejected, rather than leaving an implicit stale payload tail.

Before any write, actual GPR2 must equal `0x55667788`, the channel's SEND bit
must be clear, and a response channel must have no old pending RX bit. Then only
the exact TX slot is written. Actual GPR2 is checked again, `mb()` orders SRAM
stores, and `BIT(channel)` is written once to the owned SET word. A SEND read
flushes that posted doorbell; a cleared bit is allowed because consumption can
be immediate. The sequence follows ee2 `mtk_mbox_send`, `mtk_mbox_write`,
`mtk_mbox_check_send_irq` and `mtk_mbox_trigger_irq`, not a guessed register ABI.
The send and completion-layer source hashes are pinned in RESOURCE-CONTRACT.json.

Zero means **submitted**, never received/BOOTREADY/command success. Only channels
whose pinned `recv_opt == MBOX_RECV_ACK` acquire a software in-flight bit. These
remain busy even if SEND clears. The real dispatcher rejects an unsolicited ACK,
copies the actual bounded response, clears only its captured RX mask, invokes
the real client outside both locks, then retires the in-flight bit under the
scope mutex. No sender creates/completes an ACK. Message/event channels retain
their independent RX semantics; SEND status prevents overwriting unconsumed TX.
There is no invented ordering requirement between SEND clearing and RX arrival.
The client must still validate command-specific response contents; retirement
does not establish successful GPUFREQ command execution.

Busy returns `-EBUSY` without writing or latching a firmware fault. A real GPR,
lease/quarantine or protocol fault preserves the first errno, masks once,
quarantines the whole SRAM, and keeps resource/client/PM/module pins. A GPR loss
after slot writes is a post-write fault with no doorbell and no retry. Quiescence
closes activation under the same mutex before masking/draining. No firmware
upload/clear, core/reset release, power or SMC operation is added.

`test_tx.py` adds exact-source/order/lifetime/failure/CI-guard checks.
`run-native-ci.sh` is CI/GITHUB_ACTIONS-only; it compiles the canonical C adapters
directly with ASan/UBSan and pthread mocks. `test-mailbox.c` covers all slots,
inactive/externally enabled IRQ, driver identity, hardware/software busy,
immediate consumption without a fabricated ACK, real mocked response retirement,
lost GPR before/after payload writes, stale ACK, quarantine, drain and concurrent
same-channel sends. Its private fixture activation is explicitly **not a
production gate or hardware proof**. No native compilation/execution was run
locally. Parent CI must invoke this new runner and compile/link the actual ARM64
objects before use; existing canonical source copying needs no new kernel file.

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
