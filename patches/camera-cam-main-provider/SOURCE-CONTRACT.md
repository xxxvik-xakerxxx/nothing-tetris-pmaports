# CAM_MAIN clock-provider synchronous lease draft

Not frozen, enabled, or capture-ready. Apply provider.patch AFTER packaged
0092; stage cam-main-lease.inc and cam-main-lease-test.inc beside the actual
clk-mt6878-cam.c, header at include/soc/mediatek/cam-main-lease.h.
No extra object linked into production; the actual clock-provider TU parses
the include. Compile that object with KUNIT=y and n, plus lease-smoke.o.

## Mapping and PM producer

Pinned Linux d84b264a54a37611f2f46bc19363cb9b41606205:
drivers/clk/mediatek/clk-mtk.c __mtk_clk_simple_probe registers gates;
clk-gate.c mtk_clk_register_gates obtains device_node_to_regmap(node).
drivers/mfd/syscon.c caches this mapping. syscon_node_to_regmap on a NON
generic-syscon node is lookup-only: no second of_iomap/regmap is instantiated.
The extension rejects generic syscon nodes and never exposes a raw address.
Probe enables native runtime PM; prepare requires actual get_sync success
AND active state. Negative get_sync is balanced with put_noidle, preserving
the first failure. Lease is allocated independently of provider devres.

prepare uses device_trylock and leaves the provider device mutex held by
the calling task. regmap access and retire MUST use that same task. This
excludes driver-core removal during the synchronous transaction, not only
module unload; module/device references also remain held. Retirement clears
the handle before put_sync and unlock. PM put errors are returned; reference
retirement is complete, not evidence of power-off or hardware quiescence.
Manual unbind attributes are suppressed. Forced removal can proceed AFTER
retirement: no permanent supplier-removal veto is claimed.

## Deliberately limited ownership

This is NOT a persistent capture/root supplier lease. Do not keep it over
queue/work/IRQ waits or hand borrowed regmap to workers. No asynchronous
register users are registered here; retirement requires the caller's last
synchronous access to have returned. A caller must not hold queue/reset
locks before prepare or invoke it inside supplier/PM callbacks.
CAM_MAIN clock gates are still managed through native clk consumer APIs;
PM active does not prove their enablement, a camera route, or DMA stop.

Pinned ee2be53cb75670b548948636a0db1d1ff112bf12
drivers/clk/mediatek/clk-mt6878-cam.c supplies actual gate definitions;
packaged 0092 preserves its clock-only boundary. Pinned
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835
mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c sv_reset_by_camsys_top and
mtk_cam-sv-regs.h define CAM_MAIN reset at 0x58 ONLY after SMI clamp and
SCQ reset/ready poll. Our reset_pulse therefore returns EOPNOTSUPP without
MMIO. Existing mtk_smi_camera_reset_clamp has no public owner-query/token
interface; SCQ/route-off belongs to the actual CAMSV controller, not this
clock provider. Borrowing regmap is not authorization to bypass these gates.

## Next gates

Parent review of synchronous lock order and supplier genpd PM attachment;
patch application after 0092, actual clock-provider ARM object KUNIT=y/n,
then KUnit execution. Fixtures cover invalid-input/ownership failures and
real device-mutex exclusion between tasks, not a mocked successful power-on.
Native capture integration needs
provider-scoped synchronous regmap reset operations jointly bound to the
real SMI/SCQ controller before any DT activation or hardware attempt.
