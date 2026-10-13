# Native first-START full link gate

CI-only, uninstalled build continuation of real-boot and native-start. No runtime
code, frozen files, workflow or APKBUILD is changed. No target code is executed.
This directory does not enable a DT consumer, install/load modules or start a phone.

## Actual Build Chain

The helper requires the successful ordinary packaged object-smoke report and a
successful actual native-start compiler report. Setup/git/source failures are not
C compile success and cannot satisfy this prerequisite. Native `.config`, supplier
object, source patch hashes and all compiled vendor source hashes are rechecked.

1. Verify the same shipping d84 Linux archive against APKBUILD SHA512. Extract a
   fresh complete kernel outside the checkout; apply the actual ordered shipping
   patches and unchanged realON recipe (including rails and wakeup), then the exact
   native-start API patch. Compare native source bytes with the parent's prepared
   tree. No unknown files or object-smoke objects are copied into the full build.
2. Copy the successful native-start resolved config, not an r181/research-owner
   configuration. Check shipping security/code-generation ABI including ThinLTO,
   CFI, module signatures, architecture/page geometry and MODVERSIONS settings.
   `olddefconfig` must leave this inherited config byte-identical. No fallback,
   new merge, CFI/LTO disable or modpost weakening is offered.
3. Build the actual full `vmlinux` and kernel `modules`. The real native scpsys
   provider is built into vmlinux: both `mt6878_md_native_on_validate` and
   `mt6878_md_native_on_latch` must be defined and exported GPL by that vmlinux.
   `modules_prepare` and a copied/synthesized symbol table are not substitutes.
   Compile the first-OFF board DTB and keep the actual consumer and rails disabled.
4. Archive exact B4.1 `ee2be53cb75670b548948636a0db1d1ff112bf12`, apply the shipping
   vendor adaptations, frozen owner/ports/prepare/lifecycle/private-SMEM stack and
   exact native-start delta. Apply the genuine packaged AP-only util and mapped
   provider overlays to the same fresh tree; compare actual private-copy ABI.
5. Link the real `ccci_util_lib.ko` with METADATA_ONLY + RESOURCE_ONLY + MAP_ONLY +
   PROVIDER. Require the real `mtk_ccci_owned_mapped_copy` GPL export. This is the
   sole util instance; there is no second legacy util or OFF backend module.
6. Use the original ECCCI/HIF/CCMNI/RPS Kbuilds in one strict external modpost pass.
   Link eight actual modules: ccci_md_all, ccci_auxadc, ccci_ccif, ccci_dpmaif,
   ccci_cldma, ccci_fsm_scp, ccmni and rps_perf. OWNER + NATIVE_START + SMEM_CONSUMER
   defines are consistent across every vendor composite; original module defines,
   shipping compatibility flags and header paths remain in effect. PAGE_POOL's
   optional vendor implementation remains excluded by the shipping adaptation.
7. Inspect actual linked ARM64 ELF, dependency metadata, namespaces and exports.
   Check core composite membership includes the actual native-start object and
   excludes the old virtual-OFF owner/dispatcher. Core must import the real native
   APIs and mapped-copy provider and define/export the genuine post-bind adapter.
   No module may import the three obsolete 0117 OFF backend exports. Every strong
   import has one genuine table owner AND an actual linked owner definition/export
   marker. Used kernel-module providers must also exist as matching linked ELF.
   Unresolved optional weak imports are recorded explicitly, not invented exports.

These artifacts contain the actual probe/FSM/START implementations from the frozen
native-start patches. A linker PASS means ABI/build closure, not a call to START.

## CRC Semantics

Current shipping config has `CONFIG_MODVERSIONS=n`; it retains ThinLTO and CFI.
This helper preserves that setting. It requires absent CRC sections and zero CRC
rows for used exports and reports `crc_status=disabled_by_inherited_config`, NOT
successful runtime CRC enforcement. Symbol-owner/dependency/source/config/vermagic
closure still applies. A separate deliberate ABI/config change would be needed to
enable loader CRC enforcement; this gate does not silently change it.

When an inherited reviewed config enables MODVERSIONS, the ELF reader decodes
actual ARM64 basic and extended version sections, requires the exact resolved
import inventory plus module_layout and compares every CRC to the genuine build
tables. Missing, mismatched, duplicate, ambiguous or stale records fail. Parser
unit tests use explicitly synthetic scalar data, never compiled fixtures or fake
Module.symvers files as build evidence.

## Parent CI Call

Run after ordinary packaged smoke, realON and native-start actual compiler gates
in the same Linux GitHub job. Add `py3-pyelftools` to the existing Alpine tools;
the structured ELF reader is already used by the repository's evidence tooling.
No artifact downloads, SSH, emulation, execution of native fixtures or new remote
state are required. Required historical source objects remain cbb777 and 06fa224
as listed in native-start; no e0c67 backend/r181 archive or U-Boot fetch is used.

```sh
python3 -B patches/modem/md-pm-integration/native-link/link.py \
  --vendor /tmp/tetris-kernel-smoke/vendor-git-source \
  --pristine-kernel /tmp/tetris-native-start-pristine \
  --prepared-kernel /tmp/tetris-kernel-smoke/linux-d84b264a54a37611f2f46bc19363cb9b41606205 \
  --kernel-archive /tmp/tetris-kernel-smoke/linux-postmarketos-mediatek-mt6878-d84b264a54a37611f2f46bc19363cb9b41606205.tar.gz \
  --normal-report out/kernel-object-smoke/BUILD-MANIFEST.json \
  --native-report /tmp/tetris-native-start-evidence/BUILD-MANIFEST.json \
  --native-output /tmp/tetris-native-start-objects/native-start \
  --destination /tmp/tetris-native-link \
  --enable-native-link
```

Destination must be fresh and external to the checkout. Source inputs may not
traverse symlinks or overlap the destination. Build requires Linux, CI=true and
GITHUB_ACTIONS=true before any mutation/compiler. Inherited compiler/config/
modpost overrides are rejected. The full build uses two jobs for bounded memory.
Configuration and source differences are errors, not repaired behind the caller.

Retain BUILD-MANIFEST.json and phase logs on failure. After genuine success,
`artifacts/` contains nine linked provider/vendor modules, any used kernel-module
dependencies, all three actual export tables and the actual native supplier object.
Upload only `artifacts/`, BUILD-MANIFEST.json and selected phase logs. Do NOT upload
the destination recursively or include source/, vendor/, modules/, kernel-output/
or vmlinux. Config and compiled-DTB hashes stay in the manifest; those files and
the full vmlinux remain disposable workspace inputs, not uploaded artifacts.
No package installation, image signing or bootable deployment is included.

Local source-only checks:

```sh
python3 -B -m unittest -v test_static.py
python3 -B link.py --source-check \
  --vendor ../../../../../android_kernel_device_modules_6.1_nothing_mt6878 \
  --pristine-kernel ../../../../../linux-d84b264a54a37611f2f46bc19363cb9b41606205
```

The manifest explicitly retains unresolved hardware/operational blockers:
trusted final loader DT and firmware/SMEM ownership, secure admission/current NS
access, skipped util runtime initialization, real HIF IRQ/DMA/clock lifetime,
calibration ownership if firmware requests it, unsupported forced detach/STOP/
restart/exception/suspend, and actual HS1/HS2/SIM/network/lifecycle/SKU validation.
Permanent refs and successful module linkage do not turn those into safe runtime
operations. Native-link actual compilation/linkage is pending parent CI; no local
native compilation, emulation/JIT, phone access, commit/push or remote mutation was
performed by this worker.
