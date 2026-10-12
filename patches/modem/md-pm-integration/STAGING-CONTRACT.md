# Native inherited-ON staging contract

`native-on-adoption.patch` is a self-contained follow-up to the exact packaged
0113 provider and the current packaged patch ordering. It changes only the real
native MD domain branch. The canonical helper is `mt6878-modem-adopt.h`; run
`stage.py` to check deterministic generation, actual patch application and exact
source equality. Nothing is added to APKBUILD, shipping configuration, DT, CI,
workflows, U-Boot, runtime-HIF resources or global documentation.

## Producer Contract Agreed For Parent U-Boot

Parent's personal-only producer revision is
`e2a916b716c593840291aad2e03de103bdb57e7d`. Its pinned final-producer source
was read locally and matches the two markers, disabled input supplier/sole child,
and provider/child-only activation in the unpublished final clone. Producer CI
was started by the parent; no result or installed revision is inferred here.
The installed-source permission basis remains the separately audited8d2 lineage.

- Input `/chosen/tetris,modem-native-on-adoption-diagnostic` exists and is empty.
- Input native MD supplier stays disabled so installed BROM preflight succeeds.
- In the successful authenticated final metadata/evidence clone only, resolve
  exactly one `mediatek,mt6878-modem-power-controller`, domain0 only, using the
  real existing SPM/IFR/NEMI relationship. Reject duplicate suppliers and a
  preexisting `nothing,modem-inherited-on-adoption` property.
- Set only that supplier to `status="okay"` and add empty
  `nothing,modem-inherited-on-adoption`. Make these edits before final full-FDT
  validation and cache-clean/commit, preserving failure atomicity.
- Keep the unique `mediatek,mddriver` EXACTLY `status="disabled"`, with its
  actual descriptor, 336-byte evidence, BROM report and retained reservations.
  No consumer/CCCI/transport activation and no hardware transition is performed.
- The disabled modem anchor may lack `power-domains`. If it has one, it must
  resolve to this exact native supplier with one cell0. The provider never
  removes or invents a relationship. Actual attachment requires that same
  explicit relationship and a separately activated real platform modem device.

The markers select a diagnostic path; they are not evidence of authentication,
permissions, ON state or readiness. The actual trusted-loader reports and
geometry are mandatory before the first register observation.

## Implemented Behavior

The staged provider copies and validates the 80-byte BROM report, all five
chosen completion/error scalars, 32-byte v2 descriptor and all 336 evidence
bytes. It requires successful loader11/bootstrap15/board16, zero first errors,
no cleanup, BROM status0 and four-one flags, exact preloader profile, enable1
and all eight policy words for each service range. Initial NS CPU241=RW is
source-defined positive permission evidence under ordinary trusted-loader
handoff. There is no new certificate, READY value or independent-ROM-read gate.

The four actual firmware/NC/cache/tag allocations must have the exact
source-defined capacities/alignment, static plain NOMAP nodes, matching
`reserved_mem` catalogue identities and no compatible/reusable/ops lifetime.
Positive top-level NOMAP iomem coverage and every retained PFN are checked;
a negative PFN query alone cannot admit holes. Full unused tails are checked
for overlap against every static sibling. Firmware/NC/cache must fit one actual
DT DRAM bank; tags must fit a bank. SIB is rejected for this producer profile.
No ROM, DSP, tags or SMEM physical memory is mapped, read, cleared or claimed.

Only after this does the provider read existing native regmaps: PWR_ON+both
ACKs must be set, EXTISO3 zero, and IFR9/IFR11/NEMI6:7 protection status zero.
Five reads stop on the first failure. It registers true software ON through
`pm_genpd_init(..., false)` and attaches no device itself. The staged MD data
and callbacks contain no native transition/cleanup write sequence.

`attach_dev` uses a supplier-owned mutex because core calls it before the genpd
lock. It admits one real platform device matching the unique retained modem
node, availability and exact supplier/domain0 relationship; revalidates reports,
full reservation identities/NOMAP and ON before retaining the device reference.
Wrong/duplicate consumers fail. A state/identity read failure latches its first
error. Both physical transition callbacks return `-EOPNOTSUPP` or that first
error. Error cleanup skips physical MD power-off. Late-unused/runtime/system
power-off therefore receives an actual veto, not fabricated OFF success.

## Concrete Failed Requirements

**Consumer unbind cannot be vetoed by this API.** Pinned `pm_domain.h:230` defines
`detach_dev` as void. `genpd_remove_device()` already removes the relationship
before calling it. The patch does not pretend a device reference prevents driver
unbind: detach retires the owner with `-ESHUTDOWN`, drops the retained reference,
blocks reattachment/start, and makes no physical transition. A failed modem probe
can also detach and permanently retire this observation. Consumer unbind/lifecycle
support remains FAILED; a real consumer lifecycle design is required before use.

The native supplier is built-in and already has `.suppress_bind_attrs=true`,
so it exposes no userspace supplier bind/unbind control. That does NOT prevent
arbitrary in-kernel `platform_device_unregister()`. Dynamic supplier removal is
unsupported, and this patch makes no claim that it can veto such removal.

The packaged kernel currently sets `CONFIG_OF_DYNAMIC=y` and
`CONFIG_MEMORY_HOTREMOVE=y`. This staged immutable-lifetime profile rejects
those configurations at runtime. `diagnostic.config` records the separate
static diagnostic profile for targeted CI, not a shipping configuration edit.
Do not turn these requirements into a caller permission boolean or claim
successful adoption with the present packaged configuration.

With the agreed supplier-only producer contract, the modem remains disabled
and cannot reach the attach callback through normal OF population. Actual
consumer attachment/activation requires a separately reviewed future contract;
this patch does not defeat the disabled-node/static-tree boundary to demonstrate
attachment. First shutdown, inhibited restart, suspend/secure-idle ownership,
current effective EMI policy and functional modem/SIM operation remain unproved.

## Local Checks And Targeted CI

Local source-only commands:

```sh
python3 -B patches/modem/md-pm-integration/stage.py --kernel <pristine-d84>
python3 -B patches/modem/md-pm-integration/test_static.py
```

Source checks passed: exact baseline reconstruction through six relevant
packaged patches including frozen0113, deterministic staging patch, real
`git apply --check`, GNU zero-fuzz application and byte equality; 12 source/static
tests, including rejected write/success/OFF/foreign-consumer/wire-width mutants.
They do not execute the C helper or validate concurrency/hardware behavior.

Parent targeted CI can use its full, freshly prepared packaged kernel:

```sh
CI=true GITHUB_ACTIONS=true python3 -B patches/modem/md-pm-integration/stage.py \
  --kernel <pristine-d84> --prepared-kernel <prepared-kernel> --ci-apply
```

This verifies exact pre-adoption C/data identities before applying the reviewed
patch; an existing helper or mismatched prepared source fails. It does not compile.
Merge the diagnostic fragment in that isolated build, resolve Kconfig normally,
and assert the required final settings in `STAGING.json`. Then compile the REAL
`drivers/pmdomain/mediatek/mtk-pm-domains.o` with the existing pinned ARM64 kernel
toolchain/config. The helper is included by this object; it is not a standalone
mock translation unit. Preserve final configuration, compiler, patch/source
hashes, object and full warnings/errors. Do not dispatch aggregate CI, build
images, install modules, enable DT or execute hardware from this staging step.

No local C compilation or native test execution was performed. Real object
compilation and behavioral/concurrency tests are pending parent targeted CI.

## Shared Camera Integration Order

Camera `native-provider.patch` also changes `mtk-pm-domains.c`. Apply this MD
patch first to the exact packaged baseline. Parent must then regenerate/adapt
the camera overlay against that MD result, or use a bounded combined staging
pipeline. `stage.py` keeps its exact package/0113 pins and intentionally rejects
a camera-modified pre-adoption source; it does not silently accept a different
base. Its `candidate()` result exposes the MD-first source for parent tooling.

Compile the shared `mtk-pm-domains.o` after BOTH overlays and link one actual
`vmlinux` against the combined configuration/providers. Independent MD/camera
objects are not aggregate readiness. This directory changes no camera source,
overlay, CI or workflow and starts no CI dispatch.
