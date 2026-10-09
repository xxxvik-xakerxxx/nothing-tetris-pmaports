# Scoped AP startup serialization candidate

Status: disabled, standalone compile-only sources; no shipping config, DT, CI,
bootloader or device changes. Frozen 0007/0117 are unchanged. Native tests have
not run locally and are awaiting CI. This component does not authenticate a modem
by itself, attach a power domain, write MD registers or release execution.

## Concrete operations

`mt6878_md_startup_scope.c` wraps exactly VCOREFS command0, FID `0xc2000506`.
It retains raw a0..a3 for the existing DVFSRC caller, pins the actual supplier
device, and records its driver and actual MEM0 resource identities. A nonzero INIT status is retained, not
cast to errno or silently erased by a later INIT.

Startup follows probe's lock order: supplier device lock, then the shared INIT
mutex. It waits for the actual probe to finish, requires its original driver and
non-null driver data, and retains the device lock/reference throughout startup.
INIT cannot overlap that transaction. INIT is rejected after the first startup
attempt for the remainder of the boot. This is scoped AP serialization, not a
claim that all secure firmware is globally locked or that driver data proves
firmware authentication. Source path: pinned vendor DVFSRC INIT at
`drivers/soc/mediatek/mtk-dvfsrc.c:1095/1105`, then driver-data publication and
child setup. The pristine selected Linux driver also has command0 at line425,
driver-data publication and command1 at line441.

The required authenticated owner supplies actual ROM base/size, shared-memory
base/size and authenticated ROM digest. No new bootloader wire format is defined.
The scope validates overflow/overlap, copies the record, and invokes the owner's
real authentication implementation. Immediately before execution it obtains a
fresh snapshot, compares each field explicitly (not struct padding), checks the
supplier driver/data and MEM0 start/end/flags identities, and authenticates again. Missing callbacks fail
with ENOKEY; positive callback results become EPROTO; first failure is latched.
The snapshot is not a trusted attestation merely because it contains a digest.

No production authentication provider is supplied: main's handoff owner must
verify the actual signature/secure authentication, reserved-memory identity,
EMI/remap and permitted NS access. It must retain immutable authenticated state
and resource ownership through release; snapshots alone cannot close a TOCTOU.
An unknown runtime ATF function pointer cannot satisfy this interface. Neither
these ROM/SMEM fields nor this scope establishes boot-enable OFF->ON semantics.

## Integration order for main

1. Apply generated `startup-scope-component.patch.kernel` in a disposable
   compile-only kernel. It installs both sources, the public header, default-off
   bool Kconfig/Makefile wiring and the pristine Linux DVFSRC INIT wrapper. Do not
   include it in shipping artifacts until kernel-object and native CI pass.
2. Replace every **selected** DVFSRC command0 call with
   `mt6878_md_scoped_dvfsrc_init(dev, flags, vmode, &res)`. Check the returned int
   before using `res`, then retain original a0 handling. The wrapper is called
   during probe, where the driver core already holds the supplier device lock.
   Do not wrap command1, debug GETs, or arbitrary SMCs as command0. Select exactly
   one DVFSRC implementation; the kernel component patch covers Linux, while the
   separate vendor follow-up covers vendor's two source branches.
3. In the FSM task, before 0117 AUTH and any mutable startup operation, call
   `mt6878_md_scope_begin(real_handoff_owner, owner_context)`. It must run in
   sleepable task context and never from the supplier's own probe or a callback
   which already owns that device lock. Failure must stop startup, not use a
   legacy fallback. Bind the trusted handoff module/owner lifetime separately
   through the retained CCCI owner already required by 0007.
4. In BEFORE_EXECUTION call `mt6878_md_scope_validate_execution()` before the
   existing real EMI/remap/transport proof and POWER0 release. Same FSM task then
   calls `mt6878_md_scope_end(first_start_result)` on every path after begin.
   Successful end requires execution validation; end does not power down, reset,
   retry, detach providers or erase the first fault.

`startup-scope-integration.patch.vendor` wires these calls in a follow-up to 0007:
both pinned vendor INIT branches check the wrapper result, bind requires the
real handoff operations, start acquires the scope before 0117, and execution
validation follows the existing verification callback before release. It adds a
default-off component dependency, not an AUTH success implementation. Static
apply succeeds against the pinned vendor plus frozen canonical owner sources.
The patch requires a real owner adapting its context to ROM/SMEM snapshot and
authentication; no example always-success provider is shipped.

This does not change the frozen bundle itself. The OFF-attached virtual-consumer bootstrap remains separate:
normal single-domain platform attach powers ON before probe. Do not activate a
normal mddriver DT consumer to reach these hooks.

## Remaining AP and secure boundaries

All selected AP command0 callers must use this wrapper. VCOREFS command1 and other
commands are not serialized by it; no unsupported assertion about their effects
is made. The LPM FID `0xc2000507` RC_SWITCH policy writer is another AP owner;
its false-success behavior prevents using CLR/GET=0 as an exclusive-OFF proof.
The real secure idle select/restore callbacks and boot-enable latch behavior still
need evidence. Pausing cpuidle or holding the system-suspend mutex transiently
would only cover those Linux-originated entries, not every firmware action, and
unwinding them after a partially mutated failure needs its own lifecycle contract.
No such global idle-disable code is added here.

## Checks

```sh
python3 patches/modem/check_startup_scope.py
python3 patches/modem/check_startup_scope.py --vendor "$PINNED_VENDOR"
python3 patches/modem/check_startup_scope.py --kernel "$PRISTINE_KERNEL" \
  --emit-kernel /tmp/startup-scope-component.patch.kernel
CI=true python3 patches/modem/check_startup_scope.py --native-ci
```

CI compiles the unmodified production C body with mocked device/SMC/auth boundaries
under Wall/Wextra/Werror, ASan/UBSan and pthreads. Cases cover INIT serialization,
missing auth, raw INIT failure, authentication/snapshot faults, overflow/overlap,
each immutable-field mutation, driver-data replacement, retained references,
module pins, wrong task and first-error preservation. Fixture-only authentication
success is never installed as a production provider. Main still needs a separate
AArch64 packaged-object check; native mocks do not prove kernel integration.
