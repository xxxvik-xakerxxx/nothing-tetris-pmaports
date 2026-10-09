# Disabled MT6878 CCCI First-Start Candidate

Status: offline integration candidate, not modem/SIM/call support. Patch 0117
adds a default-unset library, no probe, DT activation, transport driver or automatic
start. Frozen power provider 0113 and read-only preflight 0115 are unchanged.

## Evidence And Sequence

Vendor: Nothing device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`.
Sources: `drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c`,
`md_sys1_platform.h`, `modem_sys1.c`, `inc/modem_secure_base.h`, and
`arch/arm64/boot/dts/mediatek/mt6878.dts`.

The rail table orders VMODEM, VNR, VMDFE, VSRAM, VDIGRF. The B4.1 DT supplies
only VMODEM/VSRAM/VDIGRF, overriding voltages to 800000/800000/700000 uV.
All three supplies are mandatory here; missing hardware must not become a dummy
regulator. Validate/acquire all before writing; propagate set/sync failures.
Vendor's intended 2 ms delay compares `md_vsram` against `md-vsram`, so it
does not execute. Electrical sequencing remains a required ownership-gate proof,
not a newly invented sleep. Vendor shutdown specifies a 4 ms settling interval;
a physical-OFF snapshot alone does not prove that handoff has settled.

Vendor power-on order: rails; TOP offset 0 bits 8/9 clear; optional flow controls;
flight OFF; runtime power; optional PLL. Flow bits 0/1/2/3 mean SRCCLKENA,
SRCLKEN_O1, sequencer reversal, PLL. This candidate permits only flow 0/gen6299,
rejects all nonzero configurations, and never writes reset or second-power bits.

Kernel FID `0xc2000505`, POWER request 6: command 3 is the done predicate;
command 2 returns four **data flags**, including a0; command 0 releases boot
and returns boot-word readback in a3. Require done/flags before mutation, then
actual runtime-PM power through the dedicated provider, ON/readback, transport
preparation, final proof and boot release. No fabricated handshake or readiness.

Secure evidence: `test-atf-power-contract.py`, declared ATF payload SHA256
`05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
That fixture proves pinned inner POWER handlers only, not outer secure admission.
FLIGHT request 7 command 0 invokes a secure callback registry, **not a proven
no-op**. Its effects and admission must be established before BEFORE_POWER passes.
POWER/4 mutates a debug selector, POWER/8 is a pinned no-op, LK POWER/5 is
boot enable rather than reset: none belong in this transaction.

## Required Trusted Caller

1. AUTH: prove firmware/certificate identity, secure profile and admission,
   reservation/DMA/cache/EMI/remap correctness, and safe nonsecure access to
   exact SPM/IFR/NEMI/TOP resources. Mapping can fail or hardware can hang;
   register APIs do not turn an inaccessible bus into a bounded read.
2. OFF: acquire sole transaction ownership before mapping, secure reads or
   MD-state reads; prove settled physical OFF, isolation/protection, boot
   inhibition and no ATF/other-owner repower. Retain these invariants until
   intentional power/release, including across every validator callback.
3. RESOURCES: prove rail/provider identities, permitted voltage changes,
   electrical sequence, and exclusive authority over shared TOP clock bits
   **before any rail/clock write**. Regulator handles alone are not ownership.
4. BEFORE_POWER: revalidate authenticated/EMI/boot-inhibited state and audited
   flight effects; prove runtime PM is attached to the actual 0113 modem domain.
5. BEFORE_EXECUTION: prove IRQ/DMA/transport and memory protection readiness,
   with modem still boot-inhibited. A transport hook is not a modem handshake.

There is no implementation supplying these proofs yet. Do not wire dummy
validators into a shipping driver. A caller must prohibit unbind/unload/idle
cleanup: an acquired runtime reference and first fault are retained, with no
speculative rollback. Boot-release attempt is recorded separately from confirmed
readback because a failed SMC response does not prove execution stayed inhibited.

## Main Integration Gates

Local static/vendor check (no C compilation):
```sh
python3 patches/modem/check_first_start.py "$PRISTINE_KERNEL" --vendor "$VENDOR_TREE"
```
Ubuntu CI fault fixture, real backend plus frozen provider code:
```sh
CI=true python3 patches/modem/check_first_start.py "$PRISTINE_KERNEL" --native-ci
```
Compile-only CI target against the fully patched, configured ARM64 tree:
```sh
CI=true sh patches/modem/compile_first_start_ci.sh "$PATCHED_KERNEL" "$CI_OUTPUT"
```
Prepare a separate CI configuration with the backend `=m`; do not change shipping
config. The object target neither links a module nor builds a boot artifact.
Main owns APKBUILD/CI wiring and device approval. No live start is approved by
static application, mock fault tests, object compilation or preflight success.
