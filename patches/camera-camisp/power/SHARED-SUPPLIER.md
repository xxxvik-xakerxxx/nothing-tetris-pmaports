# Shared VMM integration candidate: Untested

`mt6878-vmm-supplier.c` supplies executable native genpd callbacks, guarded
subdomain attachment and an exclusive regulator owner. It is an uncalled
integration library, with no initcall, OF provider, DT change or shipping link.
The prior leaf object passed ARM64 CI38245658821. Both real source objects now
also passed ARM64 compilation with KUnit enabled and disabled in CI38255895881
at 5379657. This is object-only: the composite/vmlinux link and hardware remain
untested. The KUnit-disabled supplier object SHA256 is
`54e9271c4630bb63db1a4a36a70b0d8f69469cb7588eb6af8778ee17df57f157`.
That result predates the checked CAM control adapter and explicit supply
selection below; the modified supplier source has source checks only and has
not been compiled or linked.

## Ownership and graph

The proposed software graph is MM_INFRA -> shared VMM -> CAM_VCORE / ISP_VCORE,
with CAM_VCORE -> CAM_MAIN retained. VMM is an aggregation domain for the common
buck/isolation transaction, not a newly invented hardware domain ID. The
existing direct MM_INFRA -> CAM_VCORE / ISP_VCORE edges may remain as redundant
prerequisites. VMM must itself retain MM_INFRA: independent sibling parents
would let generic error unwind release MM_INFRA despite a pinned VMM fault.

Native genpd counts active children and serializes supplier transitions. No
private CAM/ISP user counter is added. The exclusive regulator handle, selected
by the provider's explicit consumer supply ID, must resolve to the actual shared
USID-6 VBUCK1 provider. Exclusive acquisition
rejects existing Linux handles and missing supplies without dummy fallback.
All other Linux clients must move under this owner before activation, including
the B4.1 VMM isolation notifier and MMDVFS debug consumer. Firmware ownership
is not enforced by regulator exclusivity and remains a separate gate.

`mt6878_vmm_supplier_init()` takes the owning device, its verified consumer
supply ID, the existing SPM regmap and initialized MM_INFRA genpd. It checks the
regulator enable indication and all isolation
bits before deriving the initial genpd state, then checks both genpd init and
the MM_INFRA parent link. It accepts only an observed OFF buck with all three
isolation bits set. Inherited ON, inconsistent isolation or read errors stop
initialization without writes or an invented OFF state. Exclusive get can
adopt an inherited enable reference; that reference is deliberately retained
on rejection. Establishing a safe inherited-ON takeover is not implemented.

The pinned exclusive-get implementation does not propagate its internal
`_regulator_is_enabled()` error. The explicit post-acquisition read catches a
persistent failure; rejecting inherited ON avoids relying on a possibly
unadopted ON reference after a transient failed internal read. Quiescent
firmware ownership is still required: repeated reads cannot establish it.

### Consumer supply selection

The previous constructor requested `regulator_get_exclusive(dev, "vmm")`.
There is no `vmm-supply` property on either of the examined SPM nodes. B4.1
device-module commit `ee2be53cb75670b548948636a0db1d1ff112bf12`,
`arch/arm64/boot/dts/mediatek/mt6878.dts:2930` and `:2931`, describes
`isp-vcore-supply` and `cam-vcore-supply` on the real SPM owner; both reference
`mt6319_6_vbuck1`. That commit's `mtk-scpsys.c:1677` acquires the consumer supply
by the domain descriptor's name. A native owner reusing that device must request
`cam-vcore`, without the `-supply` suffix. A fixed `vmm` request cannot resolve
that DT binding and exclusive lookup has no dummy fallback on Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`.

The constructor now requires a nonempty `supply_id` and passes it unchanged to
its single exclusive regulator acquisition. Null or empty selection returns
`-EINVAL` before changing the owner or acquiring anything. Acquisition failures
retain the regulator core's exact errno, clear the error-pointer field, and
return before genpd initialization. No aliases are tried and no new regulator
handle is introduced. This changes the actual constructor acquisition path;
provider construction and consumers remain uncalled.

The read-only stock snapshot
`/private/tmp/tetris-stock-vendor-boot-b-base.dtb`, SHA256
`187c5b7e50842a33e24d3f7beb8b268bb24d8634c2adc04efebf9c547f2b3fd8`, has
`cam-main-supply` and `isp-main-supply` on its SPM node, and `vmm-pmic-supply`
on its VMM isolation node. All three local phandles resolve to the same
USID-6 MT6319 VBUCK1 regulator via the DT's `mt6319_6_vbuck1` symbol. This is
snapshot topology evidence only: the vendor slot's release is not proven, and
these names must not override the B4.1 source or become a universal selector.
The provider owner must choose the supply from matching board/release data and
prove CAM/ISP share it before calling this API. There is no default ID, phandle,
PMIC address or voltage policy embedded in the implementation.

The camera consumer trace is pinned separately to modules
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`: the CAMISP DMA/larb contract is in
`mtkcam/camsys/isp7sp/cam/mtk_cam-larb.c`, and `mtk_cam.c:1236` obtains a
runtime-PM reference for the camera device. That is a consumer PM route, not
evidence that this shared supplier is wired into its genpd. The existing
`trace-b41.py` verifies that module pin and the B4.1 device-module topology.

Negative static checks reject fixed `vmm`, `cam-vcore` or `cam-main` names,
alias fallback, nonexclusive acquisition, missing validation, lost acquisition
errors and a stale public constructor declaration. They do not execute the C
code or establish physical rail ownership. Only the C/H source hashes in
`SHARED-STAGING.json` change; its object/link plans, activation and dependency
sets remain the same. The original `power/STAGING.json` is untouched.

## Checked transitions

| Transition | Ordered operations |
| --- | --- |
| First child ON | Check buck OFF and isolation set; regulator enable; check enable indication; clear isolation through the existing checked MT6878 W1C transaction |
| Additional child ON | genpd retains its shared parent reference; child's PRE_ON guard checks fault, enable indication and isolation before its power callback |
| Last child OFF | Check enable indication and isolation clear; set isolation through the checked W1S transaction; regulator disable; require disabled indication |
| Any transaction error | Retain first errno, stop immediately, veto subsequent transitions; no automatic rollback, retry, voltage change or SMC |

The readback is the native regulator's enable indication, not a measurement
of voltage, power-good, or a proven operating point. There is no voltage/rate
request in this candidate. Parent policy must establish one before calling it.

If isolation fails after enable, no balancing disable is issued. If disable
fails after isolation, no ABORT_DISABLE de-isolation is attempted: the buck
state may be uncertain. All existing handles and references are retained to
the extent the regulator core still owns them. A regulator call can fail after
changing hardware or consuming references (including an upstream-supply
failure); retaining a handle does NOT guarantee the rail is physically ON.
The post-disable indication also rejects a silently retained always-on rail.
These faults require an established recovery path, normally clean reboot.
The first fault is logged once and remains available through the checked API.
Native `genpd_power_off()` is void and does not forward its callback error to
every runtime-suspend caller; this candidate does not change that core ABI.
The sticky fault and explicit consumer check prevent treating a later resume
as successful merely because the generic PM call returned success.

## Genpd failure handling

After a failed power-off callback, pinned genpd leaves its software state ON.
A later child request can therefore skip the supplier's power-on callback.
`mt6878_vmm_add_child()` installs a checked child-domain notifier before adding
the native parent link. It requires an OFF, non-IRQ-safe child and a persistent
device attached directly to that child. A faulted supplier vetoes PRE_ON and
PRE_OFF even when genpd cached its state as ON. `notifier_from_errno()` carries
the error through the robust genpd notifier path.

On child callback failure, genpd emits the opposite completion event before
unwinding parent references. The guard tracks the pending transition and
latches a conservative `-EIO` on that path, preventing VMM/MM_INFRA power-off.
This also conservatively faults on another notifier's veto after our PRE event.
An explicit boolean tracks transitions because GENPD_NOTIFY_PRE_OFF is zero.
No notifier completion return value is relied upon to stop genpd unwind; the
latched error makes the supplier's power-off callback refuse that unwind.

The notifier receives no callback errno. Every checked leaf callback must
call `mt6878_vmm_fail_child(vmm, original_errno)` before returning a partial
transition failure, preserving the actual first error ahead of the guard's
fallback. This applies to CAM_MAIN and other descendants as well as VCORE.
Every bus-using consumer resume must call `mt6878_vmm_check()` after acquiring
its PM leases and before access, including when its own domain is cached ON.
A genpd callback guard alone cannot intercept that cached-ON resume path.

### Checked CAM control phase

`mt6878_vmm_cam_ctl_set()` now implements the supplier-owned control phase for
CAM_VCORE and CAM_MAIN, including the descendant whose failure would otherwise
reach the immediate VCORE guard without its original errno. It rejects an
uninitialized owner or any other domain before I/O. For both ON and OFF, it
holds the supplier mutex across the sticky-fault check, enabled-rail and
de-isolated readback, and the existing `mt6878_cam_ctl_set()` transaction using
the supplier's own SPM regmap. Any read, write or ACK failure reaches
`vmm_fail()` under that same lock before the adapter returns. The original
errno is therefore retained before genpd's opposite completion notification
or parent unwind; the guard's fallback cannot replace it. There is no balancing
disable or inverse leaf transition on failure.

This is one control-phase adapter, still uncalled. A sleeping, guarded genpd
callback must already own its parent references and serialize its leaf. For
ON, basic/LP clocks precede the adapter, then subsystem clocks, SRAM and bus
release follow it. For OFF, bus protection, SRAM shutdown and subsystem clock
disable precede it. Errors in those surrounding phases still require
`mt6878_vmm_fail_child()` before returning, and every error stops the callback
without releasing dependencies. The adapter does not acquire PM references,
install callbacks, migrate the direct supply descriptor or cover ISP controls.
Consumer resume checks and provider construction remain activation gates.

The sequence is grounded in the same frozen B4.1 device-module commit:
`drivers/soc/mediatek/mtk-scpsys.c:604` (ON) and `:776` (OFF), with the CAM
descriptors and CAM_VCORE -> CAM_MAIN edge in `mtk-scpsys-mt6878.c`.
The SHA512-verified native `drivers/pmdomain/core.c:831` and `:1043` show the
completion notification and parent unwind after a failed leaf callback.
Focused negative source tests reject skipped preflight checks, wrong owner or
domain, an inverted direction, dropped/replaced errno, early unlock and a
missing public declaration. They inspect source only; runtime serialization,
hardware retention and callback integration remain untested.

MM_INFRA's normal acknowledgement and HWCCF policy remain with packaged
0057/0074. A failure before VMM becomes ON may unwind MM_INFRA: no child leaf
has started at that point. Once VMM is ON, a latched child fault rejects VMM
OFF, so its native parent reference keeps MM_INFRA held.

## Construction and lifetime boundary

This API requires a permanent, zero-initialized owner, guard storage, device
references and SPM lifetime. Construct the graph while consumers are quiescent
and unpublished. It has no unbind, teardown or fault-clear implementation.
After exclusive acquisition, even failed init retains state. After notifier
registration, even failed graph attachment retains the guard. Do not put these
objects in a failing devm probe that frees them or retries construction. Such
partial states must remain owned until recovery. Failures before obtaining the
exclusive handle may be retried normally, including EPROBE_DEFER.

Activation requires a provider owner that satisfies this lifetime contract or
an independently validated teardown implementation. The original leaf
descriptor's DOMAIN_SUPPLY flag describes direct regulator ownership and must
not be combined with this exclusive shared owner. Migrate CAM and ISP supply
acquisition together; neither may keep a direct buck handle. The old leaf
payload and staging manifest remain unchanged for the existing CI consumer.

## Exact source verification

All B4.1 facts use device-module commit
`ee2be53cb75670b548948636a0db1d1ff112bf12`, release
`Tetris-B4.1-260415-1709`, through git objects rather than checkout HEAD.
`mt6878.dts` lines 2930/2931 share the buck between ISP/CAM; lines 2997/3954
also reference it for VMM isolation and MMDVFS debug. The same commit's
`mtk-scpsys-mt6878.c` lists both MM_INFRA -> VCORE parent edges.

Native objects come from Linux `d84b264a54a37611f2f46bc19363cb9b41606205`
inside the archive verified against the package SHA512. Relevant original
source locations (before packaged patches):

| Source | Verified behavior |
| --- | --- |
| `drivers/regulator/core.c:2200` | Exclusive get rejects other handles and dummy supplies, adopts an inherited enable reference |
| `drivers/regulator/core.c:2888` | ENABLE notification is ignored and omitted for an already-enabled buck |
| `drivers/regulator/core.c:3009` | PRE_DISABLE veto loses errno; disable failure emits ABORT_DISABLE; later failures can occur after accounting changes |
| `drivers/pmdomain/core.c:831` | Robust PRE_ON veto and opposite OFF notification on callback failure |
| `drivers/pmdomain/core.c:882` | Opposite ON notification on failed OFF callback |
| `drivers/pmdomain/core.c:949` | Failed OFF leaves software ON and retains parent references |
| `drivers/pmdomain/core.c:1043` | Cached-ON shortcut, parent-before-child ON and reverse parent unwind |
| `drivers/pmdomain/core.c:2055` | Device notifier registration attaches to the real child's notifier chain |
| `drivers/pmdomain/core.c:2386` | Initial genpd state comes from supplied observed `is_off` |

`supplier-evidence.json` extends the frozen leaf evidence with hashes of native
genpd core/header, regulator consumer header and MT6315 provider. It also hashes
packaged regulator patches 0105, 0108, 0109, 0110, 0111, 0113 and 0114. Those
patches provide active-selector reading, board phase masks, checked failures,
described-rail registration and an opt-in VGPU observer. The observer path
registers NO regulator and cannot supply VMM. Its current disabled fixture is
not evidence that the shared buck is available to this candidate.

## Checks and next activation gate

The current `ci/kernel-object-smoke.py --research-owners` integration is
**object-only; shared composite/vmlinux link untested**. It preserves the old
leaf route in tetris-cam-power-smoke and stages only the new supplier C/H in
tetris-vmm-supplier-smoke. Its generated Makefile includes the existing leaf
header directory and native MediaTek headers; Kbuild.shared is hashed but
never staged. Both KUNIT variants include each object exactly once, with
source-check results, payload hashes, staged hashes and ARM64 object identities
recorded by the harness. No parent Kbuild, workflow or DT is changed.

Run from the repository root with bytecode generation disabled:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 patches/camera-camisp/power/check_supplier.py --verify-sources
PYTHONDONTWRITEBYTECODE=1 python3 patches/camera-camisp/power/test_supplier.py
PYTHONDONTWRITEBYTECODE=1 python3 patches/camera-camisp/power/check.py
PYTHONDONTWRITEBYTECODE=1 python3 patches/camera-camisp/power/test_source.py
```

`SHARED-STAGING.json` also retains the separate, untested five-file/two-object
composite plan for a future authorized link experiment, including exact SHA256
payload hashes. That plan is NOT used by the current object harness. In that
future experiment only, stage Kbuild.shared
as Kbuild in the research directory. It composes mt6878-cam-power.o and
mt6878-vmm-supplier.o into tetris-vmm-candidate.o, with the actual packaged
MediaTek kernel headers. Enable REGULATOR and PM_GENERIC_DOMAINS as built-ins
and enter this research directory once from the parent's isolated Kbuild.
The final target is vmlinux, so unresolved regulator/genpd/leaf symbols are
checked by the real kernel link, not only an object compile or relocatable link.
Use this composite instead of the prior standalone leaf link: linking both
routes would duplicate the leaf symbols. The two KUNIT variants remain in the
manifest, without any claim of a runtime KUnit fixture.

This does not alter the original staging manifest, leaf additive patch,
parent CI, CCCI objects or shipping Kbuild/packaging. Source mutation checks
cover first errors, exclusive
ownership, ordering, initial state, cached-ON faults, child-failure unwind,
MM_INFRA retention, notifier registration and staging dependencies. They do
not execute C, emulate a kernel, or demonstrate concurrent/runtime behavior.

The next activation boundary is concrete: make the native USID-6 VBUCK1
supplier available with verified ownership/constraints; establish a VMM
voltage/rate contract; prove a quiescent OFF/isolation-set handoff; migrate all
buck users; wire checked CAM/ISP/descendant callbacks and consumer resume
checks; install every guard and parent edge before publication. Retain all
clock, SRAM, bus-protection and SMI dependencies. Then validate builds and the
live/cold-repeat/clean-install/lifecycle gates. None of those activation or
hardware claims is implied by this source-only candidate.
