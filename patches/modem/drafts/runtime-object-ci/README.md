# Actual ARM64 CCCI runtime object closure

Independent CI helper. Frozen runtime-ports/runtime-prepare, kernel smoke,
packaging and workflows are not edited. No fixture/mock source is compiled.
This is object compilation, NOT modpost, link, load, physical startup or SIM/calls.
Forced removal remains unsupported; successful compilation supplies no permission.

## Integration

Parent applies `PARENT-INTEGRATION.patch` after review, or adds one command after
the existing successful `kernel-object-smoke.py --research-owners` invocation:

```sh
# Same Alpine LLVM21 job, repository root; add git to its installed tools.
python3 patches/modem/drafts/runtime-object-ci/check_objects.py
```

Run only for research_owner_smoke, never shipping images. Requires both CI=true
and GITHUB_ACTIONS=true. Default work is /tmp/tetris-kernel-smoke. A custom
--work must match the original smoke --work. --vendor may point to a git source
containing ee2be53cb75670b548948636a0db1d1ff112bf12; otherwise the helper fetches
that exact commit into a fresh CI directory. All vendor writes occur in the
fresh runtime-vendor directory, never in the input checkout. Refuses reused
staging/objects and does not clean or overwrite them on retry.

Output: out/kernel-object-smoke/runtime-objects.json. Existing artifact upload
already includes it, including failure reports. The report records object
architecture/hash, original shipping patch order/flags, frozen-review hashes,
generated overlay hashes, actual sources/headers, config/autoconf and parent
research evidence. --plan-only is read-only and permitted locally.

## Exact Stack and Real Kbuild

Reuses ci/kernel-object-smoke.py plan(), package checksum validation and
object_identity() (ELF AArch64 or LLVM bitcode AArch64). Requires its successful
research manifest, matching package pin/checksums, actual first-start object
hash and final video-KUnit-disabled config. Runs modules_prepare on that same
isolated kernel/output for generated headers; no full kernel build or symvers
fabrication. Module.symvers is NOT needed for direct .o targets; module-link
validation remains a separate prerequisite.

Archives the exact pinned FULL vendor tree with real include dependencies.
Applies every devmods patch from APKBUILD prepare() in actual shipping order
with the shipping patch policy. Then git-apply checks/applies owner bundle,
runtime-ports and runtime-prepare. Regenerates both runtime overlays and requires
byte equality with their frozen patches. Checks every touched final source
against the frozen complete-stack checker. Drift is an error, not skipped.

Preserves production vendor Makefiles/includes; no replacement Kbuild, extracted
functions, stubs or fake headers. External selection/owner C define follows
compile_transport_owner_ci.sh. _vendor_kcflags is read from the actual literal
APKBUILD function, retaining only its existing compatibility allowances; strict
implicit-declaration, pointer-type and integer-conversion errors remain enabled.

STAGING.json explicitly lists 64 real translation units:

- ECCCI (49): core/BM/modem/UDC; owner and owned HIF; full FSM, monitor/ioctl,
  poller/EE/sys, dumpers, platform/common and AP memory; all 13 port units,
  dispatcher/ringbuf/CCIF and complete 12-unit DPMAIF auxiliary closure.
- CCMNI (1): actual network registration implementation.
- CCCI util (14): actual sysfs, image/memory, bootargs and util support closure.

Native compile sees the complete port table and physical-operation guards.
llvm-nm checks actual defined prepare/owner symbols so a compiled-out owner
branch cannot pass. Kernel first-start backend was already compiled by the
parent research smoke. Required kernel config: ARM64, MODULES, PM, REGULATOR,
NET=y and MTK_MT6878_CCCI_FIRST_START=m. See manifest for exact external Kbuild
selections: ECCCI/CCMNI=m, owner=y, PAGE_POOL/security/anti-clone/AEE=n. The vendor
Kconfig is not wired into upstream autoconf; owner define stays invocation-local.

No firmware/DT activation, SMC, install, module link or .ko is produced. This
does not close HIF/modem/auth/runtime dependencies, callback drain or teardown.

## Static Validation

```sh
python3 -B patches/modem/drafts/runtime-object-ci/check_objects.py --plan-only
python3 -B -m unittest discover -s patches/modem/drafts/runtime-object-ci -p test_static.py
```

Local validation is source/manifest/Python/patch-only. Actual C compilation is
CI-pending. No phone operations or local C build performed.

Seven source-only tests passed, including a fresh full vendor archive with all
27 shipping devmods patches applied in real prepare order, all three overlays,
and final touched-source equality against the frozen complete-stack checker.
That test uses only source copies and patch application, never make/compiler.
The parent integration patch also passes git apply --check. Both frozen runtime
manifests validate unchanged. Do not interpret these checks as an ARM64 C pass.
