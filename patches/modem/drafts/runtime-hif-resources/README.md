# Resource-Only HIF Candidate

Additive, default-off source candidate. Shipping config/DT and the provider/copy
ABI remain unchanged. The full-link helper and modem workflow build this
profile separately from the baseline. Native fault-fixture and ARM64 profile
results remain pending; no local native compilation is used.

Inputs are NothingOSS device modules B4.1
`ee2be53cb75670b548948636a0db1d1ff112bf12`, MT6878-mainline Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`, and actual r181 package
`e0c67c561ff7c1a0472da851edfafd5a0abb6cec`. The parent reports strict full
OWNER+CONSUMER linkage passed CI38255895881 at `5379657`: eight vendor modules,
real backend and provider with genuine exports. This candidate is a subsequent
source change and needs its own checks/link. It does not relax any gate.

The parent also reports stable actual r181 + UBoot8d2 mapped-provider/private
table-copy validation. Before the r182 installation, the parent reported retained
provider/copy modules on boot `2b17cde3` with reference count 2. That GPL copy ABI evidence is
preserved. This sidecar neither retests it nor infers full private CCCI probe,
transport, READY, physical OFF, SIM/calls or safe core unload from it.

Later parent update: r182 CI38248220709, source prefix `75a`, artifact
11750359310 (ZIP SHA256 prefix `61a1a42d`), has read-verified config SHA256
`edcbdf45d3201aef8ab71157bb485c074bc5c3457f564f0341a7eb410b9382a2` and
kernel export SHA256
`2e58e05288219f07094e88da49b9f12b1c06d2bf5875e87e1f557bc36c4e7cf3`,
byte-identical to r181, with the same d84 Linux base. These are parent-reported
read-only equivalence results; this sidecar has not inspected that archive or
installed root. Parent will record runtime ABI equivalence after installation.
The DT reconstruction below is explicitly OLD r181 evidence. Current board
nodes still lack runtime resources; no r182 physical preparation result is inferred.

## Executable Change

The new `CONFIG_TETRIS_CCCI_HIF_RESOURCES=1` research define requires MODULE,
OWNER and the existing private SMEM CONSUMER. No Kconfig or package selection
is added. Apply `resources.overlay` after the COMPLETE shipping adaptations,
OWNER, runtime-ports, prepare, lifecycle, SMEM common and consumer stack.

CCIF/DPMAIF probe bypasses legacy initialization completely. Actual platform
memory resources are checked for validity/overlap and reserved with device-owned
claims, without mapping. Actual named clocks are obtained without preparing or
enabling them. The generator derives the six CCIF and three v3 DPMAIF names
from the pinned vendor tables; it accepts only MT6878/v3 for DPMAIF. RX descriptor
count follows the actual LRO/2RXQ capability bits.

IRQs are retained as `of_irq_parse_one` OF descriptors with balanced controller
node references. Before calling the pinned parser, validate the controller,
cell count and complete property length; its legacy path otherwise copies
unchecked cells. Only direct B4.1 GICv3 SPI descriptions are accepted.
Effective address-cell counts, including inherited properties, must be one
complete u32 with value 0-2 before the parser's three-cell address buffer is
used. Extended descriptions and interrupt-map nexuses fail explicitly. Duplicate
line identity ignores trigger flags. The native fixture uses the real 16-cell
capacity and rejects overlapping claims across both suppliers and auxiliary
windows. No Linux IRQ number is allocated here, no mapping is disposed,
and no handler, wake or enable operation occurs. This replaces rather than
silently describes `platform_get_irq`, which can create mappings/program trigger
types. Earlier platform-device population or boot code may already have touched
the IRQ controller: the profile does not certify their side effects or physical
mask state. The modem WDT IRQ number remains zero until a reviewed activation.

The supplier retains real OF relationships: DPMAIF `dpmaif-infracfg`; CCIF
optional `ccif-pericfg`; uniquely available `mediatek,infracfg`; and the actual CCIF4/5
nodes. Dedicated CCIF4/5 windows are reserved; shared syscons retain node
references without mapping/claiming another driver's region. Any absent,
disabled, ambiguous, busy or malformed required resource fails with its first
error. Deferred clock errors propagate. There is no fabricated resource address,
success fallback, READY state or NS certificate.

In B4.1 MT6878 DT, `ccif-pericfg` is absent although legacy CCIF logs its lookup
failure and continues. Its only register user is the <=6297 clock-off branch;
MT6878's 6299 path uses infracfg instead. Therefore absence is not a new
prerequisite for this resource-only profile. A supplied phandle is validated;
malformation still fails. The private consumer continues to admit only 6878/6299.
The original sequencer index 1 is also absent; resource-only modem preparation
retains no sequencer pointer and never uses the legacy literal fallback. These
facts must guide future physical paths, not guesses of new nodes.

Only a completed supplier transaction becomes real drvdata under a distinct
resource-driver name. It never fills `ccci_hif`, `ccci_hif_op`, legacy control
globals or platform_data. The consumer creates managed dependency links without
runtime-PM flags, checks the bound resource driver under its device lock, validates
its actual record, and acquires balanced module/device leases owned by consumer
devres. Failure unwinds leases through driver core. Supplier exits unregister
their actual resource drivers, and remove/devres releases passive resources.
This avoids a new md_all -> supplier -> md_all module-import cycle.

Consumer probe uses the real leases instead of the old slot-based module pin
transaction. Its checked resource getter avoids all legacy MMIO/syscon mappings,
DMA-mask changes, PM activation and hard-coded sequencer fallback. It supplies
the actual generation type needed for private port-table selection, leaving
physical platform callbacks NULL. Existing B4.1 modem init only logs. The
existing checked memory-copy/FSM/port prepare transaction, failure latch and
boot retention remain in place. Memory preparation calls the same proven GPL
provider; publication/commit, workers, monitor, START/STOP, syscore and sysfs
physical callbacks stay closed by the prior stack. This is not a modem start.

## Separate Invocation And PM Gate

In this profile, loading `ccci_md_all` with the default read-only
`private_prepare=false` does not even register the consumer platform driver.
Setting this module parameter at insertion is an explicit request to run private
preparation, not proof of security or hardware readiness. Probe independently
checks that request before acquiring dependencies. There is no writable sysfs
activation switch, new exported entry point or automatic commit caller.

Linux platform_probe applies assigned clocks and powers a declared genpd BEFORE
calling a driver's probe. Preflight therefore rejects power-domains, assigned
clocks and IOMMU attachment paths on available targets before registering CCIF,
DPMAIF or an explicitly requested modem consumer driver. Probe also rejects an
already attached PM domain. Optional CLDMA/AUXADC/SCP companions register no
physical driver in this profile; their probe bodies additionally deny entry.
The source DT is assumed fixed: OF overlay/hot-add, manual platform-device
creation and forced driver removal remain outside this experiment.

The actual r181 `mediatek,mddriver` node is a disabled metadata-only anchor with
no MMIO/interrupt/clock/power resources. The reconstructed r181 source closure
contains no matching CCIF/DPMAIF/CLDMA/AUXADC/SCP targets. Enabling that anchor
alone cannot perform private preparation. The vendor B4.1 modem node declares
a power domain and is deliberately rejected by preflight. Do not delete the
real power relationship merely to make this check pass.

## Source Checks And Application

```sh
python3 -B patches/modem/drafts/runtime-hif-resources/check_resources.py \
  --vendor ../android_kernel_device_modules_6.1_nothing_mt6878 \
  --linux-archive ../linux-d84b264a54a37611f2f46bc19363cb9b41606205.tar.gz
python3 -B patches/modem/drafts/runtime-hif-resources/test_source.py
```

The generator archives the FULL exact vendor commit and reuses the actual
full-link staging order/frozen reviews. It generates one deterministic additive
overlay, checks/applies it in the full tree and compares every resulting touched
file byte-for-byte. It also records base/candidate init/probe bodies and all
global OF searches. Linux archive SHA512 is matched to the package before
checking the real core contracts and reconstructing r181 DT sources from the
actual committed package patches. No compiler/dtc/preprocessor is invoked.

For the parent's already staged complete vendor root:

```sh
git -C "$consumer_vendor" apply --check "$draft/resources.overlay"
git -C "$consumer_vendor" apply "$draft/resources.overlay"
```

Do not apply this to raw B4.1, a partially adapted tree or the isolated AP-only
provider tree. Provider common/header/export artifacts are reused unchanged.
`SOURCE-EVIDENCE.json` carries input reviews, patch/source hashes, constructor
bodies and the r181 DT-source census. It is source evidence, not a certificate
or an ELF/runtime measurement.

## Next Physical Gate

Parent owns all live work. First complete this profile's native fault fixture
and the same strict full eight-module/backend/provider link against unchanged
actual r181 config/exports, then inspect the actual constructor/profile artifacts
and boot FDT/platform-device inventory as described in INIT-PROBE-CENSUS.md.

Before requesting private preparation, review and supply the actual CCIF,
DPMAIF and modem DT/resource/provider relationships, including the unresolved
clock owners, auxiliary windows and modem PM attachment boundary.
No address or missing provider is invented here. A separate PM integration must
preserve the real domain relationship without pre-probe power-on; this directory
does not fake a PM domain or modify Linux to bypass its platform contract.

Then a fresh controlled parent boot can request only private preparation, with
the real mapped provider still owning memory, empty HIF slots, no IRQ mappings
from these helpers, no handlers/DMA/MMIO/START/publication, parked FSM/port workers
and healthy USB/sensors/one SSH control session. Record the exact resources,
leases, first error and unpublished private retention. Stop on the first fault;
unsupported forced teardown requires clean recovery. Only a subsequent reviewed
supplier/power/IRQ/DMA/SMEM lifecycle closure may allocate IRQ mappings, map
registers, construct real native HIF controls or permit physical activation.
