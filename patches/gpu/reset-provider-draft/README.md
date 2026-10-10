# Parent reset-provider candidate

New draft only; no packaged patch, binding, DT activation, firmware upload,
power/rail transition, SMC, phone operation or local C compilation.

## Concrete integration

The future fixed GPUEB parent owns full SRAM once through the existing SRAM
owner. After its real MFG0/supply/clock owner has produced an active PM usage
reference, call mt6878_gpueb_reset_provider_register(parent, sram). The parent
must suppress bind/unbind controls, remain non-hotpluggable for the entire boot,
and never remove its supplier domain via overlay/forced teardown. The new
provider enforces suppressed controls and pins the parent and provider modules;
these pins do not by themselves make arbitrary device_unregister safe.

The existing frozen reset helper exclusively owns SPI273, the separate
0x13c60000/0x2000 bank and both full-SRAM-owner typed windows. The provider does
not request these resources a second time. Success registers a real Linux reset
controller on the parent OF node, requiring one #reset-cells argument and reset
ID0. There is no deassert, pulse-reset or fabricated status callback. Registration
does not invoke assertion. No platform probe or DT changes are included here.

Assertion quarantines full SRAM BEFORE the helper's exact LK reset write0 at
register offset0x600. Successful assertion means only the posted-write/readback
checkpoint, never physical OFF or DMA idle. All published references remain for
the boot lifetime; no unregister API permits an accidental remove/free path.

Future remoteproc .stop calls mt6878_gpueb_reset_provider_stop and propagates
its error. It asserts at most once and synchronizes the disabled owned Linux
IRQ; with no OFF producer it returns -EBUSY (or first actual failure), retaining
the provider/PM/IRQ/SRAM claims. Duplicate assertion returns EALREADY, not a
second write. An unexpected IRQ/readback failure halts later operations.

Pinned Linux remoteproc_core.c rproc_shutdown increments its power reference
back on rproc_stop failure and skips resource_cleanup/unprepare/IOMMU teardown.
However, rproc_stop calls stop_subdevices and resets its resource-table pointer
BEFORE the hardware .stop callback: those subdevices must drain callbacks only,
not free firmware/shared memory. Failed .start has a separate unwind path and
also requires parent quarantine; do not rely on .stop ever being called there.
This provider is NOT authorization to register a runnable remoteproc yet.

## Exact source boundaries

Device modules pin ee2be53cb75670b548948636a0db1d1ff112bf12:

- arch/arm64/boot/dts/mediatek/mt6878.dts gpueb block: full SRAM, separate
  control bank, mbox0 SPI273 level-high. The same SPI273 is Mali's PWR IRQ;
  an independent mailbox/Panthor claim must fail, never use IRQF_SHARED.
- drivers/gpu/mediatek/gpueb/gpueb_init.c maps GPR then initializes IPI and
  reserved memory; no request_firmware/rproc loader/reset-start routine, and
  remove is NULL. Suspend/resume only timesync; neither supplies OFF evidence.
- drivers/gpu/mediatek/gpueb/gpueb_debug.c GPUEB_CONTROL op0 triggers watchdog;
  it is not a proven power-off service. op1 is GPUACP CPU-PM. Do not issue
  speculative op selectors or interpret zero as successful OFF.
- gpufreq/v2/gpufreq_mt6878.c registers EB-mode callbacks, not the neighboring
  SoCs' AP power_control implementations. Those cannot fill this chip's stop.
- Signed declared-B4.1 LK 431e055... at0x1edf8 asserts reset0; the retained
  frozen helper implements that checkpoint without release0x3f00000b.

## Remaining executable prerequisites

1. Matching phone-ABI rootfs/analysis module and private retained156064-byte
   capture, recomputed digest9628...; do not upload/copy the unsigned102680 tail.
2. Flat entry/vector and GPR0 prefix24 semantics from those authenticated bytes;
   no ELF requirement, guessed entry, inferred BSS or invented secure selector.
3. Separate6MiB GPR6 protected allocation/EMI owner; GPR0 retained-buffer
   lifetime and shared-memory0x180000 LK versus0x184000 vendor-DT mismatch.
4. Real MFG0/RPC/supply/clock ownership producer. Active PM alone is not proof
   rails/firmware/secure permissions are ready. No automatic resume here.
5. One whole-bank IRQ dispatcher to replace the helper's disabled exclusive
   checkpoint before mailbox/GPUEB/Panthor coexist. No pending-bit ACK guessed.
6. Source-backed reset-held/AXI-drained/physical-OFF evidence and verified
   failure unwind before replacing stop's EBUSY with successful shutdown.

## Gates

Run test_provider.py (Python/static only). CI then invokes smoke-kernel-ci.sh
against the prepared pinned kernel with RESET_CONTROLLER, PM, OF and packaged
MT6878 power definitions. It compiles the actual new provider plus frozen reset
helper objects, not mocked native exports. Full link/modpost needs the real
SRAM/reset owner symbols integrated in the same kernel build. No matching-phone
ABI or live hardware success is implied by these objects.
