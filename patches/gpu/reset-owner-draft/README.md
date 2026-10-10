# Actual reset/IRQ pre-start checkpoint draft

Not packaged, bound or activated. Frozen SRAM/adoption/MMIO/U-Boot code is
unchanged. This is an actual Linux resource/MMIO adapter, not a full remoteproc
provider or a power-on proof. No native C/kernel build or phone operation was
performed locally.

## Executable API and boundary

`mt6878_gpueb_reset_prepare(parent, sram)` requires exactly one DT domain:
MT6878 SPM MFG0_SHUTDOWN (0035/0018 data). It does not attach/resume it or change
runtime status. `pm_runtime_get_if_in_use()` acquires an existing active usage
reference atomically; a real parent power owner must already have produced it.
The helper does not establish supplies/clock/secure ownership by itself.

It acquires BOTH real SRAM-owner window leases, preventing existing session
and mailbox clients from coexisting, claims/maps the pinned separate register
bank, and requests the real named mbox0 IRQ exclusively with NO_AUTOEN. Module,
parent-device and PM references remain owned. Failure before MMIO releases only
these newly acquired software resources, without a power-down operation.

`mt6878_gpueb_reset_hold()` writes 0 to bank offset 0x600, as B4.1 LK does at
0x1edf8. The readback fences posted register writes and verifies latch value
zero. It DOES NOT establish processor halt, physical OFF, AXI idle or firmware
DRAM/DMA drain. IRQ error check and MMIO are serialized under the same spinlock.
The write is recorded before MMIO; destroy always refuses afterwards, retaining
module/PM/resource/window references even if the readback succeeds. A mismatch
preserves first error and quarantines the full SRAM parent. No retry is allowed.

`mt6878_gpueb_reset_drain_irq()` synchronizes Linux handlers on the disabled
owned IRQ. It does not acknowledge pending firmware bits, stop DMA or drain
unrelated workqueues. There is no IRQ enable API or firmware receive engine.
Unexpected delivery latches failure and disables the IRQ without speculative
status reads/ACK; process-context paths forward quarantine.

Pinned vendor DT also names SPI273 as Mali's PWR interrupt. Therefore another
claim MUST fail EBUSY, not switch to SHARED. A future unified parent must own
that whole bank before exposing GPUEB or Mali power consumers.

Parent removal must be serialized through this helper and the existing SRAM
owner. `get_device()` alone does not prevent driver unbind. Main must use a
non-hotpluggable parent with bind/unbind controls suppressed and no devm cleanup
of quarantined resources. This draft installs no platform driver or DT binding.

## Exact authenticated-range overread

B4.1 LK 0x1ee00/04 sets counter 0x3f2bc; each iteration reads/writes 4 bytes,
then subtracts 4 and repeats while counter >4. There are 64686 iterations:
258744 bytes. Source is the original payload destination mapped-base +24,
not container headers/certs. Current authenticated payload is 156064 bytes.
The additional 102680 bytes are within the physical 1 MiB arena but outside
the authenticated/loaded interval. This is authenticated-range overread,
not an allocation OOB. Undocumented initialization is NOT a BSS proof.

LK's explicit 256 KiB SRAM clear is proven; its stale source overread is not
reusable initialization. A future reviewed flat loader can express full SRAM
clear followed by authenticated-byte-only copy as an intentional experimental
delta. Do not describe it as byte-identical stock or signed BSS initialization.
ELF absence alone is not a blocker: source LK uses flat SRAM copy. The primary
format/map and any dependence on the undocumented copied interval still need
runtime verification, with resources quarantined on failure.

## Concrete retained-payload handoff design for main

Main remains the sole shared U-Boot integration owner. The existing opt-in
diagnostic must retain its full staging erase on every path. A separate reviewed
retained mode must create the producer, rather than accepting caller flags:

1. Allocate a private LMB arena using actual available memory, source-backed
   64 KiB alignment and the source 1 MiB reservation bound. Keep payload at
   offset24 only to preserve observed source placement, bound bytes to arena
   size minus24. Prefix24 semantics are unproven: do not place a new manifest
   there or claim it is zero/BSS. Do not program GPR0 from it yet.
2. Authenticate root/delegation/header/ciphertext, transform with existing
   audited selector1 boot window and verify signed plaintext digest. Copy ONLY
   authenticated bytes into the private arena, then erase/flush staging as now.
   On failure erase any copied retained bytes and unwind before publication.
3. Publish only a reserved-memory no-map node, phandle and bounded metadata:
   version, payload offset/length, digest, stock profile identity and signed
   container/header identity. Never expose plaintext in chosen/logs or treat
   a boolean as authorization. Reserve the exact full arena against kernel,
   initrd, SCP, modem and other firmware allocations before transfer of control.
4. Linux obtains the arena through reserved-memory/resource APIs, validates
   immutable bounds/profile and recomputes payload digest before any SRAM write.
   Trust is the reviewed bootloader producer plus signed-digest provenance,
   not arbitrary DT data or this reset checkpoint's runtime-PM reference.
5. GPR6's separately allocated 6 MiB DRAM/EMI region and GPR0 prefix usage must
   have their own real owners/protection-result checks before reset release.
   The frozen source trace does not permit their fabrication or early freeing.

No retained producer or remoteproc .start/.stop is implemented by this reset
draft. The actual next start sequence needs retained bytes, exclusive whole-SRAM
upload access, GPR initialization, a full-bank receive owner, reset release and
GPR2 BOOTREADY polling. It must never equate reset echo/IRQ drain/SMC return zero
with physical OFF. Matching ATF 0xc2000530 handler 0x184c8 returns zero even for
unknown operations and supplies no such proof.

## CI and runtime gates

Run test_reset.py with pinned vendor tree and optional TETRIS_B41_LK. In CI,
invoke smoke-kernel-ci.sh with CI=true, prepared TETRIS_KERNEL_TREE and configured
TETRIS_KERNEL_OUT. It compiles the actual adapter object against existing SRAM
API and packaged MT6878 domain definitions. No shared CI/package edit is needed
inside this draft.

Do not test reset live merely because the object compiles. First establish the
actual MFG0 supplier/supplies/clock ownership on a cold boot, exclusively claim
SRAM and SPI273, and verify private firmware/EMI lifetime. A reset checkpoint
experiment can then require reset latch zero and Linux IRQ drain while retaining
all resources until clean reboot. It is not a successful remoteproc stop or GPU
acceleration test.
