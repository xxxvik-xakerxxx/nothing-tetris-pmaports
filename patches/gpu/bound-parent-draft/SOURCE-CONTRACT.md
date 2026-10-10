# Bound-parent GPU ownership control transaction

Default-off draft, no platform registration/DT/package activation. One new real
kernel control caller connects the frozen SRAM/reset provider and revised MFG0
producer. No firmware, rails, nested MFG-RPC, reset assertion/release or OFF
claim. It does not replace unresolved boot dependencies with success flags.

## Caller and ownership

The fixed parent stores a zero-initialized opaque control pointer in its own
private state; this helper does not overwrite existing drvdata. A bound-parent
serialized work item calls prepare exactly once AFTER probe completion, never
inside probe/remove/PM callbacks or while holding device/consumer/reset locks.
All synchronous work finishes on that task before it returns. Parent shutdown,
overlay removal and forced device/domain unregistration are prohibited for the
whole diagnostic boot once a control object is retained. Module/device refs
alone do NOT prevent forced detach: main's parent must enforce that contract.

1. Revised MFG0 prepare validates attached sole native MFG0, bound parent,
   PM enabled and suppressed bind attrs; pins parent/modules and locks device.
2. Preflight exact ee2 full SRAM/control-bank resources, reset cells and owned
   named level-high IRQ. No new register mapping or duplicate IRQ claim here.
3. Claim/map full SRAM once using frozen sram_create before any PM transition.
4. Publish the control handle BEFORE the real native genpd resume. MFG0 resume
   failure retains usage/modules/device but unlocks the task-owned mutex before
   returning. No worker exits holding that mutex; failed handle cannot resume.
5. Existing reset provider borrows an independent active PM reference, claims
   the disjoint register bank/disabled exclusive IRQ and typed GPR/mbox windows,
   then publishes reset controller. Registration does NOT assert reset.
6. Finish only the synchronous MFG0 producer reference without idling. The
   provider's own PM/module/device/SRAM/IRQ ownership remains for this boot.

Before PM: failed preflight/SRAM claim balances pins/lock, returns NULL and no
hardware transition. After PM attempt/provider publication: first-error retained
control pointer, SRAM quarantine, MFG0 reference quarantine, no cleanup/retry.
A second call with that stored pointer returns EALREADY without touching PM.
Provider registration can itself retain an unknown partial IRQ scope on error;
the root therefore never assumes ERR_PTR means it is safe to dispose SRAM.
Cold reset is recovery, not logical remoteproc OFFLINE or reset echo.

## Exact source chain and gaps

Device modules ee2be53cb75670b548948636a0db1d1ff112bf12:
arch/arm64/boot/dts/mediatek/mt6878.dts defines GPUEB full SRAM at 13c00000,
control bank 13c60000/2000 and mbox0 level-high SPI273. Same interrupt conflicts
with an independent Mali PWR IRQ owner; no IRQF_SHARED workaround is introduced.
drivers/soc/mediatek/mtk-scpsys-mt6878.c defines MFG0's native SPM transition;
packaged 0035 keeps registration default-off. GPUFREQ MT6878 is EB-only, not a
source for direct AP nested-domain/rail writes. This is the ownership chain,
not evidence that generic genpd resume matches stock cold LK in every detail.

Remaining activation gates: actual parent binding/config, matching firmware
retention and flat execution map, secure/rail/clock ownership, whole-bank IRQ
dispatcher, upload/release/BOOTREADY handshake and physical-stop proof. The
unsigned 102680-byte copy tail is never uploaded or zero-filled here.

## Review and CI

Run test_control.py and revised mfg0-supplier-draft/test_supplier.py without C.
Parent CI must run revised MFG0 strict sanitizer fixture, and stage both new
control C/H and revised MFG0 C/H alongside existing SRAM/reset objects according
to STAGING.json. Link/modpost needs all actual helpers, not mocked exports.
No current object build proves running-phone ABI or physical power behavior.
