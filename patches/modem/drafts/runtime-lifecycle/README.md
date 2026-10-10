# Prepare-only lifecycle closure

New overlay AFTER frozen runtime-prepare; no change to its manifest, shipping
configuration, device tree, firmware, workflow or phone. Vendor base is B4.1
`ee2be53cb75670b548948636a0db1d1ff112bf12`, all packaged adaptations then the
owner, runtime-ports and runtime-prepare. Generator checks the frozen manifests
and byte identity before producing this overlay.

## Concrete missing prerequisite

`register_prepare.h:ccci_tetris_register_prepared` installs actual
`ccci_modem_sysops` after publication. Blocking platform dev_pm_ops alone does
NOT close its syscore callbacks: `ccci_modem_syssuspend` calls
`ccci_hif_suspend(md->hif_flag)`, and `ccci_modem_sysresume` reaches
`ccci_modem_restore_reg` -> `ccci_hif_resume`. Sysfs publication also exposes
`ccci_md_attr_show/store`: `md_net_speed_show` invokes HIF even on a read, and
`md_cd_dump_store` can request register/SMEM dumps. Software FSM GATED/INVALID
checks are not physical access permission. Quarantine retains these published
callbacks, so they must remain closed after partial commit too.

This overlay denies both actual syscore entry points and both generic modem
sysfs dispatchers at entry whenever TETRIS_OWNER is selected. Suspend returns
EOPNOTSUPP; resume's void callback performs no operation. Read/write returns
EOPNOTSUPP before converting/dereferencing attribute data. This intentionally
denies harmless modem sysfs attributes too rather than maintaining a mutable
allowlist. Existing boot_md_store already returns EACCES; the unrelated parent
sysfs status reader is not changed. No physical OFF or successful suspend is
reported. Normal non-owner vendor behavior remains intact.

To allow these entries later requires real power/IRQ/work/DMA lifecycle ownership,
including partial-start quarantine; registration_complete is not that proof.
Forced removal, overlay removal and unload remain unsupported. This is not a
claim that all exported vendor physical APIs are closed or transport is usable.

## CCCI64 staging review

The independent object helper stages the entire pinned vendor archive, applies
the APKBUILD's actual vendor prepare order, then the three frozen overlays. It
compares touched sources to the complete-stack generator and builds 49 eccci,
1 ccmni and 14 ccci_util actual translation units. Existing Kbuilds carry module
defines and vendor include paths; whole-tree staging retains conn_md, SCP, PMIC,
SLBC, memory-AMMS and other headers rather than stubbing them. Real upstream
generated config/headers and the packaged first-start public header are required.
The explicit owner define is isolated to research compilation, not shipping.

The hif dispatcher, CCIF, DPMAIF v1/v2/v3/helper objects and core FSM/ports are
included. CLDMA runtime and optional auxadc are not certified by the 64 count;
MT6878 selected transport is CCIF+DPMAIF. Kbuild CONFIG arguments select object
lists; they do not magically provide generated preprocessor CONFIG definitions.
Header/autoconf and strict implicit-declaration checks remain actual CI gates.
Object compilation does not link ccci_md_all/ccci_ccif/ccci_dpmaif/ccmni/util or
run modpost: external exports, compatible module ABI and module load order still
need a real packaged-module link/modpost gate. No Module.symvers is fabricated.
The camera dry-run failure occurred BEFORE compilation; CCCI64 is not a PASS.

## Next integrated hardware gates

1. Complete actual object CI, then real module link/modpost/export closure.
2. Read the pending cold BROM report; four equal-1 predicates and success-stage
   report are evidence for BROM only, not modem READY or SIM service.
3. Supply the actual validated complete CCCI tags/reservations to the existing
   metadata parser and authenticated lifetime owner, preserving full capacity.
   Descriptor shape checks alone are not permission to read protected memory.
4. Bind resource-only CCIF/DPMAIF suppliers and consumer with reviewed MMIO,
   IRQ, clock, DMA and NS access. No enabled DT or physical operation here.
5. Call explicit post-bind commit only through the real lifecycle adapter.
   Keep START/STOP/monitor denied until the actual power owner is wired and
   physical failure cleanup is proven. Observe HS1/HS2, then real ports; neither
   software GATED nor command completion demonstrates physical OFF.

## Verification and parent integration

Source-only locally:

```sh
python3 -B patches/modem/drafts/runtime-lifecycle/test_static.py
python3 -B patches/modem/drafts/runtime-lifecycle/check_lifecycle.py --vendor /path/to/vendor
```

Ubuntu GitHub CI ONLY (both CI=true and GITHUB_ACTIONS=true): add `--native-ci`
to the checker command. It extracts all four exact production callbacks from
the complete stack and builds strict Wall/Wextra/Werror ASAN/UBSAN fixtures in
both owner configurations. It checks unpublished/published/quarantined pointers,
absent callbacks, error propagation and zero HIF/attribute dispatch in owner
mode. No local C build was performed; these native results are pending.

Parent can apply `runtime-lifecycle.patch.vendor` after runtime-prepare in its
isolated vendor source, retaining existing three-overlay identity verification
before this fourth patch. Recompile the affected actual fsm/modem_sys1.o. This
directory deliberately does not change the existing frozen object helper or CI.
