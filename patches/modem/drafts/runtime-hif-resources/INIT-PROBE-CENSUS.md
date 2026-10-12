# Actual Module Init / Probe Census

Scope: the full eight-module OWNER+CONSUMER tree produced by the frozen full-link
stager, BEFORE this resource overlay, and the new resource profile AFTER it.
Vendor B4.1 `ee2be53cb75670b548948636a0db1d1ff112bf12`, Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`, r181 package
`e0c67c561ff7c1a0472da851edfafd5a0abb6cec`. Parent reports CI38255895881 at
`5379657` passed strict linkage. Source conclusions below do not authorize
loading its artifacts or claim that this new overlay was in that job.

This is explicitly the old r181 DT census. The parent subsequently reports r182
CI38248220709/source prefix `75a`/artifact11750359310 has byte-identical real
config/exports on d84. That read equivalence does not certify the installed r182
FDT or private preparation. Board nodes still lack the runtime resources; parent
owns installation and the later actual ABI/device inventory record.

SOURCE-EVIDENCE.json records exact adapted source hashes, actual init/probe
bodies, and global OF lookup locations for BOTH profiles. Paths below are under
`drivers/misc/mediatek`. This is a source-backed reachability review, not a
preprocessor/ELF execution result. Actual CI artifact profile/config and selected
SCP feature guards must still be inspected before any parent load.

| Module | Base automatic callback | Automatic action if no probe matches | Probe/runtime hazard |
| --- | --- | --- | --- |
| ccci_md_all | `eccci/fsm/md_sys1_platform.c:modem_cd_init` | Registers `driver_modem` | OWNER dependencies precede allocation; legacy HW getter maps registers/syscons and obtains IRQ IDs if dependencies succeed. Private copy does not close those suppliers. |
| ccci_auxadc | `eccci/ccci_auxadc.c:ccci_auxadc_init` | Registers ADC driver | `get_auxadc_probe -> ccci_get_adc_info` reads IIO raw/processed channels. |
| ccci_ccif | `eccci/hif/ccci_hif_ccif.c:ccci_hif_ccif_init` | Registers CCIF driver | Probe maps primary/auxiliary MMIO, obtains IRQ mappings, requests/enables IRQ0/wake and publishes HIF. |
| ccci_dpmaif | `eccci/hif/ccci_dpmaif_com.c:ccci_dpmaif_init` | Registers DPMAIF driver | Probe maps registers/syscon, initializes BAT/RX/TX pools/queues/tasklets/IRQs and publishes HIF. |
| ccci_cldma | `eccci/hif/ccci_hif_cldma.c:ccci_cldma_init` | Registers CLDMA driver | Probe maps primary/misc MMIO and initializes transport; later paths request IRQ/DMA. MT6878 selected consumer HIF bits exclude CLDMA, but that does not disable this separate module's probe. |
| ccci_fsm_scp | `eccci/fsm/ccci_fsm_scp_c.c:ccci_scp_init`, under `FEATURE_SCP_CCCI_SUPPORT` | Logs and registers SCP driver when that branch is compiled | Probe calls `fsm_scp_init`, maps CCIF2, gets clocks and registers callbacks/notifier/work; feature-disabled build may have no init callback. |
| ccmni | None in actual selected `ccmni.c` | Exports native network implementation | `ccmni_init` is called from port registration, not a module constructor. It creates network devices/wakes/sysctl. Commit remains denied. |
| rps_perf | None in actual `rps_perf.c` | Exports RPS implementation | `set_rps_map` is called from CCMNI; no automatic transport constructor. |

`eccci/ccci_core.c:subsys_initcall(ccci_init)` is under
`#ifndef CCCI_KMODULE_ENABLE`. Actual external ECCCI Kbuild sets
`CCCI_KMODULE_ENABLE`; the class/BM `ccci_init` body is an ordinary callable
function in this module profile. OWNER excludes its old automatic probe caller.
The real separately linked first-start backend has no module/platform init;
its exported operations still need actual lifecycle/access owners. The existing
AP-only MAP_ONLY provider has its separately reviewed real init/mapping boundary;
its stable table-copy result is not reclassified as a hardware-free constructor.

The six platform init bodies contain no direct MMIO, IRQ/DMA, SMC or global
compatible lookup. Driver registration can synchronously probe matching existing
devices, so those init callbacks are conditional rather than universally safe.
Disabled DT alone is not a proof of that condition: manually created platform
devices, overlays, enabled companion nodes, aliases and driver_override can
change which probes execute.

The genuine archived r181 config was read here with SHA256
`edcbdf45d3201aef8ab71157bb485c074bc5c3457f564f0341a7eb410b9382a2`.
It contains no CONFIG_MTK_TINYSYS_SCP_SUPPORT selection. The real
`ccci_common_config.h` gates FEATURE_SCP_CCCI_SUPPORT on that symbol and the
full helper supplies no override. Thus this exact profile has five platform
constructors, with no constructor for SCP, CCMNI or RPS. The six source bodies
above include SCP's inactive branch for review; a different feature selection
invalidates this compiled-profile conclusion.

After artifact download, this source-only inspector checks the actual full-link
report, per-module hashes, AArch64 constructor symbols/aliases and matching
compiled source hashes. It rejects a different config or optional profile:

```sh
python3 -B patches/modem/drafts/runtime-hif-resources/inspect_init.py \
  /path/to/downloaded/full-link --profile base
```

For the later optional artifacts, use `--profile resource`. This reads ELF with
pyelftools; it never executes a module. Constructor instructions and actual boot
FDT/platform-device relationships remain parent review gates.

## Status-Ignoring Lookups

The real `of_find_compatible_node` lookup does not require an available node.
The lexical global census intentionally includes all these runtime/helper paths
without turning a source occurrence into a claim that its branch executed:

- CCIF `ccif_hif_hw_init`: `mediatek,mddriver`, `mediatek,infracfg`,
  `mediatek,md_ccif4`, `mediatek,md_ccif5`.
- DPMAIF v2 infrastructure lookup and v3 reset configuration; reserved-memory
  cache/noncache searches and QoS helpers reached from legacy transport init.
- CLDMA clock/misc searches from its initialization helpers.
- Port RPC, SWTP/kernel interface and SLBC lookups reached only by later
  initialization, registration or runtime operations in this stack.

In particular, a disabled metadata-only mddriver can still be found by CCIF's
legacy global search if CCIF's own probe runs. A disabled auxiliary register node
can still be mapped by a legacy helper. The source census therefore distinguishes
platform matching from global lookup; it never treats status as a universal
hardware-access guard.

## Actual r181 Boundary

The source-only generator checksum-verifies the pinned Linux tarball, applies
the r181 committed DT patch sections in package source order, and follows the
actual `mt6878-nothing-tetris.dts` local includes. It requires exactly one
disabled `mediatek,mddriver` metadata anchor with no reg/IRQ/clock/power consumers,
and zero matching CCIF/DPMAIF/CLDMA/AUXADC/SCP compatibles in that source closure.
This source result does not substitute for the parent's actual boot FDT or the
kernel's platform-device inventory. U-Boot adds real metadata to the disabled
anchor without making it an operational transport resource node.

The native-display `mt6878-nothing-tetris-native.dts` include closure is checked
as well. Historical DT patches use the real r181 default_prepare policy; the
recorded reconstruction had no offset/fuzz diagnostics. The new resource overlay
always uses exact git-apply context and final byte identity.

Before a base full-core load, parent must match downloaded ELF/module hashes,
vermagic/config/export evidence to the successful CI and check the actual
constructor census/feature guards. Verify every matching platform device is
absent or cannot bind, including manually created devices with disabled nodes,
and that no concurrent OF overlay/driver_override/hot-add will introduce one.
Do not load all modules and infer this condition from a lack of immediate faults.

## New Resource Profile

With OWNER+CONSUMER+HIF_RESOURCES consistently compiled, CLDMA/AUXADC/SCP are
export-only modules: init does not register a physical driver and probe also
returns EOPNOTSUPP. Core defaults to no consumer driver registration. Only an
explicit read-only module-insertion `private_prepare=true` request permits its
preflight/registration, and it is not an access certificate.

CCIF/DPMAIF init validates available target resources against pre-probe PM/clock/
IOMMU hazards before driver registration. Their probes reserve actual regions,
get clocks without enabling them, and retain parsed OF IRQ descriptors only.
Their PM pointers are NULL and old HIF initialization entry paths are denied.
No HIF global publication, DMA queue allocation or vendor MMIO mapping is reachable
through these new probe bodies. Normal core/device population may have performed
earlier platform/IRQ work; the source helper boundary does not erase that history.

A resource-only private-prepare experiment is separate from the base full-module
load. It requires this newly linked profile, real complete DT/provider relationships
and a reviewed modem PM attachment path. The current r181 anchor lacks those
resources, while the vendor modem node's power domain triggers platform power-on
before probe and is rejected. Publication/START stays denied even after private
prepare success. Forced removal and the prior retained private graph still need
clean recovery; resource-only supplier cleanup is not full CCCI teardown proof.
