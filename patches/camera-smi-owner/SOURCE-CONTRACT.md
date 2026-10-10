# Native SMI common31 reset operation

Default-off provider integration candidate. Combined CI stages the private
include/public header, applies provider.patch after packaged 0070 and compiles
the real provider plus consumer. No DT enablement, local C compilation or
phone operations are performed; successful compilation is still pending.

provider.patch inserts the private include into the existing upstream SMI
provider after struct mtk_smi, adds lease state and initializes its mutex at
probe. Stage the include into drivers/memory and header into
include/soc/mediatek/smi-camera-reset.h. No second driver or shared remapping.
The patch explicitly includes linux/mutex.h before the private struct fields.

## Provenance

Device source ee2be53cb75670b548948636a0db1d1ff112bf12:
- drivers/memory/mtk-smi.c lines88-90,3196-3219: clamp STATE0x3c0,
  SET0x3c4/CLEAR0x3c8, per-member write then state read, unused membership -1.
- lines4351-4356: mediatek,comm-port-id and mediatek,common-id provisioning.
- arch/arm64/boot/dts/mediatek/mt6878.dts lines4314-4324: common31,
  CAM_VCORE domain, one APB clock, mediatek,smi-supply parent and port list.
No physical address or one-phone membership value is embedded.

Parent link/one-clock override apply ONLY to MT6878 with common-id31 and
validated vendor DT shape. DISP commons and nodes without camera metadata
retain their existing probe behavior. Requires prior MT6878 GEN3 support
(existing package patch0070), the actual CAM_VCORE genpd/clock providers and
the supplier described by DT. Missing suppliers defer instead of guessing.

## Lease and failures

mtk_smi_camera_reset_clamp(common, camera_consumer, true) validates the whole
DT list before writes, acquires a managed supplier link and module/runtime-PM
references, and uses common->base owned by that provider. Existing foreign
clamp bits return EBUSY. Only one consumer may hold the lease; repeated ON is
EALREADY, another owner EBUSY. OFF requires that owner and unchanged membership.
SET/CLEAR readback mismatch records first EIO and retains the lease and all
references. No hidden retry, success stub, cached register read or force-clear.
Runtime/system suspend rejects an active lease. Successful OFF releases PM
and consumer/module refs; a failed DMA reset must not call OFF.

Device locking stabilizes provider/devres during each operation; a managed
device link orders supplier unbind after native capture consumer teardown.
The future native capture consumer MUST retain its supplier/own lifetime on
failed DMA stop. Linux forced unbind cannot be made safe by get_device alone;
do not activate an unbindable consumer without proven stop/remove behavior.
This source draft does not claim failed-DMA supplier removal is solved.

## Consumer integration

Replace the frozen hardware draft's regmap-only smi_clamp callback at its
backend construction site with this native API using its actual smi_device
and platform->direct->consumer. No regmap export is required anymore.
smi-backend.c/h implements that constructor and callback, without editing
frozen hardware. It preserves the parent shared-reset-lock assertion.
Parent capture controller continues to serialize CAM_MAIN and CAMSV resets;
the provider lease prevents competing users of this API between ON/OFF.
Frozen hardware still needs review/integration, not manual edits here.

Next CI gate: stage the two files, apply provider.patch after0070 and compile
drivers/memory/mtk-smi.o with existing native provider dependencies. Also
compile the actual consumer callback against the reachable MTK_SMI symbol.
The frozen CAM_MAIN resume-reset helper directly calls its old private regmap
clamp: do NOT invoke it. New mt6878_camsv_native_cam_main_reset implements the
same pinned SCQ/CAM_MAIN resume sequence with this native provider operation,
actual resource verification, no enabled IRQ/live DMA, and the existing shared
reset lock. Main should use this entry point, not the frozen regmap helper.
Activation remains off until PHY/MAC/TSREC/CAMMUX/stop owners are complete.
