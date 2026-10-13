# Dispatch lifetime prerequisite

Status: concrete lifetime API implemented; source checks pass. Native CI and
ARM64 object validation for this revision are pending. The parent's reported
CI38315471685 passed the preceding TX/RX fixture, not this revision. GPU remains
Broken. This API does not activate dispatch, start RV33 or adopt inherited state.

## Owned transition

`mt6878_gpueb_reset_dispatch_acquire(scope, parent)` returns an opaque handle
only after all eleven fixed channel consumers have been bound. It validates
the exact retained parent and every bound driver identity, suppressed unbind
controls, healthy whole-SRAM ownership and the actual disabled IRQ descriptor.
An externally enabled or contained IRQ cannot be adopted. Allocation, module
pin or inactive-PM failures unwind only the new software allocation/references.
Acquisition never resumes power, touches MMIO or clears firmware pending bits.

The handle pins the actual parent driver module, device and an additional
existing active runtime-PM usage reference. The scope's original SRAM/window,
control/IRQ and client pins remain held. Publishing under the scope mutex seals
the consumer set; concurrent acquisition has one winner. Scope destruction
returns EBUSY while this handle is published, before masking or changing state.
The non-hotpluggable parent must still serialize acquire/release/destruction
and prohibit forced driver/device removal: references do not prevent unbind.

TX and the threaded IRQ now require the lifetime handle in addition to private
activation provenance. Before SRAM access they validate every bound driver,
including event consumers which have never sent a command. This closes the
previous RX identity gap. Firmware MMIO use is recorded before the first TX
slot write or RX transaction; drain also records any active epoch before
closing it. An inactive sealed handle still gives EOPNOTSUPP on valid send,
without GPR/status reads, slot writes, ACK or doorbell.

`mt6878_gpueb_reset_dispatch_release(handle)` keeps the handle published while
masking and synchronizing the entire threaded IRQ/callback path. It waits
outside the scope/SRAM mutexes. Only an unused, healthy, never-reset handle can
be consumed, dropping its additional references. Any first fault, lost driver,
external SRAM quarantine, dispatch exposure/MMIO or reset write retains the
handle and every pin, quarantines SRAM, and returns the first errno or EBUSY.
Successful IRQ drain does not certify DMA drain or physical OFF. There is no
reopen/recovery transition and no caller-supplied proof callback or ready flag.

## Exact source boundary

RESOURCE-CONTRACT.json pins the newly used source hashes as well as commits:

- ee2be53cb75670b548948636a0db1d1ff112bf12, device modules:
  `drivers/gpu/mediatek/gpueb/gpueb_init.c` probes IPI before reserved-memory
  consumers; `gpueb_ipi.c` installs the complete eleven-channel table;
  `drivers/soc/mediatek/mtk-mbox.c` owns the exclusive whole-bank IRQ.
- e96f60dc081ae3525ef43d4bcf0ee5ee97e53835, vendor modules:
  `met_drv_v3/common/tinysys/v1/gpueb/gpueb_met_ipi_handle.c` consumes
  CH_IPIR_C_MET/CH_IPIS_C_MET (ee2 channels 8/9), checks existing ipi_inited,
  registers distinct event/ACK consumers and uses the existing transport.
  Its `gpueb_start()` sends MET logging commands; it is not an RV33 loader.

Requiring complete coverage before enabling a whole-bank IRQ is this candidate's
fail-closed policy, not a claim that vendor probe installs all consumers before
requesting the IRQ. Native test callbacks mock all consumers; production must
bind real channel-specific consumers and must not install discard callbacks to
satisfy the mask. No existing parent/provider wrapper is modified here.

## Still unmet before live activation

1. Actual parent binding with cold MFG0/supply/clock/reset ownership, exclusive
   whole-bank SPI273 ownership (also named Mali PWR), and all eleven real
   consumers must be integrated. The sealed handle alone proves none of these
   physical prerequisites beyond the previously acquired resource/PM scope.
2. A validated persistent authenticated RV33 producer and Linux reservation/
   digest consumer must supply actual bytes. Verified-erased diagnostics and
   unintegrated handoff drafts cannot authorize a firmware upload or adoption.
3. Flat entry/vector, SRAM upload span and retained GPR0 prefix24/lifetime ABI
   must be established. Authenticated 156064 bytes cannot justify LK's 258744
   byte copy; 102680 extra bytes and the unresolved tail remain untouched.
   No tail padding, assumed BSS or xfile execution permission is introduced.
4. The separate 6 MiB GPR6 reservation and its EMI/security protection result
   need real owners. Reset echo, PM usage, GPR2 or a permissive SMC zero result
   cannot replace them.
5. That real start owner must record uncertainty before SRAM clear/copy/reset
   release, retain all DMA/firmware/protection resources on failure, and produce
   an authenticated cold-start epoch before any enable/dispatch transition.
   This revision has no such producer, `enable_irq()` or production setter for
   dispatch_active. GPR2 BOOTREADY remains an actual per-transaction check, not
   authorization. GPR13/INIT_SHARED_MEM and command6 remain subsequent gates.
6. Physical OFF/DMA exclusion must be independently proven before releasing
   anything after a start attempt. Native CI, cold repetitions, clean install,
   lifecycle and SKU portability remain unpassed for activation.

## Parent CI entry points

Static: `python3 -B patches/gpu/reset-owner-draft/test_dispatch_owner.py`, plus
the existing test_dispatch.py, test_tx.py, test_reset.py and test_resources.py.
The new source test reads both pinned Git commits without executing firmware.
Use TETRIS_DEVICE_MODULES_TREE/TETRIS_VENDOR_MODULES_TREE for CI checkout paths.

The existing CI-only run-native-ci.sh compiles the same canonical C adapters
and now includes lifetime acquisition, allocation/module/PM failure unwind,
duplicate/concurrent acquisition, premature teardown, preactivation send,
external quarantine, replaced RX consumer, and a callback held across drain.
The callback fixture verifies destruction refuses while synchronize_irq waits
and that uncertain resources remain pinned afterwards. Existing TX/RX tests
acquire the real lifetime handle before their old private activation fixture;
that fixture still does not prove a production activation path. No native
compilation/execution was performed locally, and no shared CI file was edited.
