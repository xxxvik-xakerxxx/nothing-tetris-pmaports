# MFG0 cold acquisition candidate

Default-off, not packaged or bound. No phone operation, direct MMIO, regulator,
clock, SMC, firmware upload or GPUEB start. This is a real runtime-PM acquisition,
not another readiness flag. It fills the producer missing before the frozen
reset owner's pm_runtime_get_if_in_use().

## Matching sources

Device modules ee2be53cb75670b548948636a0db1d1ff112bf12,
drivers/soc/mediatek/mtk-scpsys-mt6878.c:
MFG0_SHUTDOWN uses SPM 0xEB4, SRAM PDN bit8/ACK bit12, SRAM isolation,
MD bus-protection bit4 then infrastructure bit9. BYPASS_INIT_ON means registration
is not cold power acquisition. Packaged 0035 describes that same domain with
KEEP_DEFAULT_OFF and does not activate its DT node.

The same pin's drivers/gpu/mediatek/gpufreq/v2/gpufreq_mt6878.c exposes EB-mode
callbacks only; its platform_eb_fp has no AP power_control. Do NOT power nested
MFG-RPC domains or enable VGPU/VSRAM to substitute for firmware ownership.
drivers/gpu/mediatek/gpueb/gpueb_init.c initializes inherited GPR/IPI/shared RAM;
it supplies no cold load/start/stop implementation.

Pinned Linux d84b264a54a37611f2f46bc19363cb9b41606205:
include/linux/pm_runtime.h documents that get_sync retains the usage reference
on failure; resume_and_get would drop it. drivers/pmdomain/core.c performs the
attached domain's power_on before start_dev/runtime_resume, and may fail after
partial transition. put_noidle only drops usage_count, not suspend/off.

## Executable integration order

Use an already bound fixed parent (not its probe callback), native PM enabled
and genuinely attached to the sole DT MFG0_SHUTDOWN domain. All calls occur on
one control task with no consumer/reset/queue locks held. Suppress bind attrs;
the transaction holds the real parent device mutex plus module/device pins.
Prepare validates the same phandle/profile as the frozen reset owner and pins
the bound parent under its device mutex, without power writes. The bound-parent
caller preflights the control bank/IRQ and claims full SRAM here. Resume then
calls the real pm_runtime_get_sync. Only a successful active result permits
reset_provider_register(parent, owned_sram) on that same task. That helper
borrows its own PM reference while this producer's reference is still held.
Finally finish drops only this reference without idling/powering down.

This candidate does not create a platform driver, change genpd registration,
enable DT, pretend successful probe on a failed resume, or auto-enable PM.
Parent main must review and wire the task and domain provider before a test.

## Failure/rollback

Before get_sync: every failure returns NULL and balances allocations/locks/pins.
After get_sync: negative return plus retained handle is an irreversible failed
transaction for this boot. Preserve the handle and PM/module/device pins;
the task-owned mutex is released BEFORE returning failure. Finish/resume on
the failed handle return the same first error without another PM operation.
No mutex remains held across work completion or a task exiting. No retries.
Do not integrate this as a probe-return-error path whose driver core would
detach the domain. Controlled cold reset is the recovery boundary.

On success, finish is reversible ownership retirement only: it invokes no
suspend callback and proves no physical OFF. Existing parent probe usage and
other suppliers can keep MFG0 active; zero usage is not proof of OFF either.
Reset-provider registration has its own retained IRQ/SRAM/PM ownership and
quarantine contract; this producer never unwinds that ownership.

## Next gates

Static tests check exact pinned vendor source and lifecycle ordering. Native
sanitizer fixture must run only in CI; parent stages the exact two C/H inputs
and one object from STAGING.json in the real ARM object closure with PM/OF and
packaged MT6878 power definitions, preserving its existing Makefile owner.
No native test or object compile proves native genpd physically correct.

Actual activation still requires reviewed cold MFG0 DT/provider attachment,
rail/clock ownership, retained authenticated flat firmware map, the whole IRQ
owner, and upload/reset-release/BOOTREADY semantics. The unexplained unsigned
102680-byte LK copy tail is not uploaded or fabricated. No full OFF service
is supplied by reset echo or unknown SMC operation returning zero.
