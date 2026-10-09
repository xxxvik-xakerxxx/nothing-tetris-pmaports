# GPUEB SRAM ownership: next implementation boundary

## Authenticated transform result

Main reported a cold boot of U-Boot a329b442 with boot ID
9cb0bd00-c093-496d-a4cc-66d3a05c3fa5, USB/SSH recovered and SensorProxy active.
Chosen metadata: verified-erased, error 0, 156064 bytes, format UNKNOWN (0),
stock-copy-covered 0, plaintext SHA256
9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7.
This is main's runtime evidence, not a hardware test performed by this worker.
No plaintext survives the diagnostic. It is not a firmware handoff to Linux.

## Allocation/BSS conclusion

`audit_gpueb_allocation.py` checks the authenticated, pinned B4.1 LK payload
431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a.

- 0x1ec60..0x1ec74 reserves 1 MiB, alignment 64 KiB, upper-bound argument
  0x80000000 through the physical mblock reservation API, not calloc.
- 0x1ecfc maps that physical reservation. Mapping allocation flags are zero;
  0x67608 calls calloc(1, 0x58) for a mapping descriptor. Its 88 zero bytes
  are not firmware backing RAM.
- 0x1ed8c supplies mapped base +24 to the RV33 reader. The limit argument is
  1 MiB although backing remaining from this pointer is 1 MiB -24. Do not
  copy this interior-pointer bound into a new loader.
- 0x74e00 allocates a separate 512-byte temporary header, not a zeroed
  firmware arena. There is no explicit full firmware clear in the caller.
- 0x1edfc explicitly clears 256 KiB SRAM only after authentication and reset
  assertion. This does not establish that the source's unauthenticated tail
  was zero or BSS. A zero observed in RAM would not establish signed BSS either.
- The fixed SRAM copy reads 258744 bytes; authenticated transform covers only
  156064. The excess 102680 bytes remain unexplained. No padding, decompression,
  or stock copy is permitted from this evidence.
- 0x1ef08 unmaps and 0x1ef10 frees the physical reservation after the boot wait
  or reader failure. Linux must not treat the old GPR0 address as retained RAM.

This audit is complete for the allocation/initialization hypothesis: **no
source-proven BSS/zero-tail justification exists**. It does not prove the
contents of every earlier RAM writer. UNKNOWN plaintext is not executable
format compatibility.

## Concrete next code task

Implement a new, disabled MT6878 GPUEB SRAM controller, separate from frozen
0118/0120/0122/0123, with one real platform resource claim and mapping. Do not
add a second claim to the existing session. This is resource ownership work,
not an activation-ready remoteproc implementation.

1. Validate the DT resource's overflow-safe bounds against the source-backed
   256 KiB SRAM profile. Claim it once with request_mem_region/ioremap. Track
   ownership independently of remoteproc state; do not infer physical OFF
   from RPROC_OFFLINE, reset assertion, or a failed rproc_boot.
2. Expose checked, lifetime-bound child accessors for GPR and mailbox windows
   derived from that mapping. Reject out-of-range/overlapping windows and
   duplicate clients. Children never request the overlapping parent region.
   Their references prevent parent remove/unmap.
3. Before a boot transaction, revoke client access, quiesce receive work and
   wait for all in-flight users. Request/configure the real mailbox IRQ before
   reset release, but keep transport requests closed. Full SRAM clear includes
   GPR/mailbox: no session writes or reads may race clear/copy.
4. Separate BOOTREADY (GPR2 = 0x55667788) from GPUFREQ session readiness
   (GPR13). Only after actual BOOTREADY may INIT_SHARED_MEM and command 6
   clients obtain access. Neither IRQ arrival nor a software state flag is
   a substitute for the firmware handshake.
5. Any uncertain partial-start failure quarantines controller resources,
   shared DMA/reserved memory, mappings and client references. No devm cleanup
   or rproc shutdown result may silently release them. A future reviewed
   physical OFF proof is required to reopen/remove the controller.

CI tests must exercise production resource/window validation and lifecycle:
overflow, wrong SRAM profile, duplicate claims, GPR bounds, overlapping windows,
remove with active clients, RX during quiesce, access before BOOT, timeout after
partial start, and cleanup only with an independently established OFF condition.
Compile the actual objects in CI; keep DT disabled and perform no phone writes.

## Required activation follow-up

The SRAM controller alone must not clear or start hardware. Wiring 0120's
session to its windows is a separate reviewed snapshot. A remoteproc `.start()`
must fail closed until all of these are source-proven:

- actual firmware upload layout/span (current 156064 vs 258744 mismatch);
- authenticated persistent firmware reservation and provenance handoff, or
  reviewed kernel authentication path; current verified-erased metadata alone
  cannot supply bytes;
- physical MFG/reset/clock ownership, EMI protection result handling, and an
  observable physical OFF procedure for failed starts;
- one unified IRQ/GPR/mailbox owner with boot/session ordering validated.

No new DT activation, dummy regulator, forged ready flag, guessed rail, or
secure-service experiment belongs to the next resource-controller patch.
