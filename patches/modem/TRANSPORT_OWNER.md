# Disabled first-start transport owner

Status: **Untested compile-only candidate**, not SIM or call support. No shipping
Kconfig, DT consumer, APKBUILD, U-Boot, CI workflow or phone changes. Frozen 0117
and main's `STEP(stage_id, operation)` correction are not modified.

## Exact FLIGHT contract

Pinned B4.1 vendor source: `ee2be53cb75670b548948636a0db1d1ff112bf12`.
`drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c` submits kernel CCCI FLIGHT
request 7 with argument 0 before domain power-on. This is not a reset request.

Private B4.1 ATF payload SHA256:
`05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
Offsets below are payload-relative after removing the 512-byte container header,
with payload execution base `0x48800000`. Do not publish the binary.

* Kernel FID `0xc2000505`, dispatch `0xbf2c`, request-7 branch `0xbfa0`, wrapper
  `0x1bf58`: truncate the argument to u32, dispatch `(0, 7, &argument)`.
* Registry registration `0x1ebc8`, descriptor `0x5a7f0`, list `0x5a7d0`, registry
  `0xeef08`. Dispatcher `0x1efc0` stops on the first nonzero callback; missing
  registry returns -1; a null callback terminates successfully, not skip-and-continue.
* Registered callbacks `0x33d3c`, `0x33aec`, `0x33c5c`: first two do nothing for
  event 7. Third sets secure policy halfword bit `0x40` at `0x5a9fa` iff u32
  argument equals 1, otherwise clears it. Helpers `0x331b4`/`0x3313c` use the
  actual lock at `0xf73b4`. The third callback discards helper status and returns 0.
* Kernel dispatch zero-extends w0: -1 becomes `0x00000000ffffffff`, not a signed
  Linux errno. Only a0 is defined; FLIGHT does not populate result a1/a2/a3.

This exact inner path changes secure RAM policy and its spinlock, not MD power,
reset, boot-enable or other MD MMIO. It is **not** proof of outer SMC admission,
boot inhibition, retained exclusivity or absence of concurrent ATF repower.
The offline fixture executes the actual registration and handlers, includes
synthetic first-error injection, and maps no MD MMIO. Local Unicorn execution
terminated with SIGILL before its instruction hook; executable verification is
pending Ubuntu CI. Disassembly conclusions must not be reported as a fixture PASS.

## Real adapter and first-error handling

`check_transport_owner.py --emit-bundle` combines the integration diff and three
canonical new sources into one vendor patch. Apply after the currently selected
vendor patches, never directly to an unpatched vendor checkout. New Kconfig
`MTK_ECCCI_TETRIS_OWNER` is default off and restricted to the module composition.

The sole owner binds mandatory proof callbacks to the actual 0117 backend.
There are no proof bits or production callbacks that unconditionally succeed.
After provider ON/readback and a separate transport-access/lifetime proof:

1. Request the real WDT IRQ disabled; retain exact request/wake errors.
2. Validate and pin both registered HIF providers before any provider start.
3. Start actual CCIF then DPMAIF callbacks, preserving the first nonzero result.
4. Publish BOOT_WAITING_FOR_HS1, not a fabricated HS1, HS2 or READY.
5. Require the final execution gate; submit the actual backend release request.
6. Only after successful release enable WDT and clear host first-boot bookkeeping.

The remaining existing receive chain is CCIF/DPMAIF RX -> CCCI port dispatch ->
FSM `MD_INIT_START_BOOT` handling -> real `CCCI_EVENT_HS1`/`CCCI_EVENT_HS2` ->
READY notification to ports. This candidate does not inject these events or invent
SIM readiness. Port registration, modem firmware/NVRAM, actual handshakes, RIL
transport and Linux telephony integration are separate gates before SIM/calls.

Legacy early HS1 transport startup, pre-start vcore calls, pre-proof EMI-clear,
clock-request/release SMCs and startup-failure dumps/resets are bypassed only in
this candidate. CCIF clock, queue-allocation, IRQ, wake and ring-init errors are
checked. DPMAIF checks late init, nonempty clock inventory and every clock enable,
driver/RX/BAT/TX startup result. Positive errors become EPROTO, not success.
CCIF's inherited `ccif_irq1_enabled=1` is reset to 0 before requesting NO_AUTOEN;
otherwise the real atomic enable guard would leave its data IRQ disabled. The
native fixture executes that real guard and checks duplicate-enable suppression.
No compensating shutdown or retry after mutation. Runtime, IRQ, clock and module
ownership is retained for controlled cold recovery; no hot unbind is provided.

The callbacks must establish lifetime ownership of modem/control/runtime objects
and registered HIF resources, including free-running-clock state and source-defined
CCIF reset profile. Module pins alone do not protect device detach or HIF replacement.
The bind API does not construct that ownership. Existing CCIF reset operations are
transport resets, not invented MD_RESET_B writes.

## Boot-inhibit and bootstrap proof boundary

Physical OFF means PWR_ON clear, both ACK bits clear, external isolation 3 and all
three protection acknowledgements set. It excludes powered MD execution while
maintained, but does not hold a guessed reset bit and does not prove no repower.
POWER5 boot-enable 0 and FLIGHT 7/0 are not substitutes for that proof.

Linux `drivers/base/platform.c:platform_probe` attaches a normal platform consumer
before driver probe. `drivers/pmdomain/core.c:genpd_dev_pm_attach` requests power-on
for the single-domain case. Thus a normal enabled mddriver consumer violates the
strict OFF preflight. `genpd_dev_pm_attach_by_id` creates a separate virtual genpd
consumer with `power_on=false`, but schedules idle power-off; provider cleanup must
remain harmless for unowned OFF state. `dev_pm_domain_attach_by_id` rejects a
control device already attached to a domain.

The candidate rejects such a powered control device and requires a distinct genpd
virtual runtime consumer with the same OF node. It neither attaches nor invents
the bootstrap. Minimum future sequence, each with real evidence:

1. Authenticate firmware/handoff; prove NS SPM/IFR/NEMI/TOP access. Establish
   exclusive physical OFF and a retained no-repower contract before MD access.
2. While that contract remains held, U-Boot/main verifies EMI/remap/authenticated
   firmware placement. Do not call POWER0 or enable MD execution there.
3. Construct non-autoprobed control/CCCI and OFF-attached virtual consumer safely;
   prove provider identity, PM cleanup, transport-resource lifetime and profile.
4. Bind this owner and invoke the existing start command, preserving OFF through
   0117 AUTH/OFF/resource/rail/clock gates. Perform FLIGHT 7/0 then actual domain ON.
5. Prove powered transport access, prepare transport, prove final authenticated
   EMI/remap/execution conditions, release via POWER0 and wait for real HS1/HS2.

No source-backed no-repower contract is established by this candidate. Trusted
bootstrap/proof implementations, IRQ/DMA probe ordering, shared memory sizing,
CCIF/DPMAIF lower-layer bounds, exception/stop/suspend/unbind ownership and actual
HS1/HS2 validation remain runtime activation blockers. No diagnostic DT should
enable this transport yet. The separate read-only preflight experiment is unchanged.

## CI handoff

Local static check and deterministic bundle:

```sh
python3 patches/modem/check_transport_owner.py "$VENDOR" \
  --emit-bundle /tmp/0007-ccci-first-start-owner.patch.vendor
```

On Ubuntu CI only, after main's fixed 0117 is selected:

```sh
CI=true python3 patches/modem/check_transport_owner.py "$VENDOR" \
  --native-ci "$PRISTINE_KERNEL"
python3 patches/modem/test-atf-flight-contract.py "$PRIVATE_ATF_CONTAINER"
CI=true sh patches/modem/compile_transport_owner_ci.sh \
  "$PATCHED_KERNEL" "$CONFIGURED_ARM64_OUTPUT" "$DISPOSABLE_PATCHED_VENDOR"
```

Main applies the generated bundle to a separate disposable vendor tree containing
all existing vendor patches; retains the fixed backend and header in the kernel;
supplies `TETRIS_VENDOR_KCFLAGS` from the existing vendor compatibility function.
The script does not edit config, link modules, install objects or build boot images.
The changed HIF ABI must be compiled consistently across all candidate objects.
Keep all output out of shipping artifacts; a translation-unit pass is not modpost
or a runtime ownership proof.

Native ASan/UBSan tests reuse the actual backend/provider and compile the production
owner/HIF dispatcher plus extracted WDT/HS1/clock helpers and the actual CCIF and
DPMAIF start functions. They run both start functions through the owner/dispatcher
with mock lower hardware primitives, as well as synthetic HIF callbacks for focused
dispatcher tests. Proof providers are fixture-only. They test gated ordering, every
recorded external failure, invalid binding/provider inventory, first-error latching,
positive late-init errors, inherited ON rejection and no retry. Full hardware startup
is not emulated. Native compilation is
refused locally; actual kernel translation units and native fault tests await CI.
