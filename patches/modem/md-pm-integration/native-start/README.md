# Native platform CCCI first-start

Uninstalled, default-off continuation after real-boot/0188. No shipping autostart,
enabled DT, install image, phone operation or claim of modem readiness. Exact
NOS B4.1 device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`, companion
modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`, and checksum-pinned Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`. Only this directory is modified.

## Actual caller chain

The ordinary Linux platform attachment calls the real native genpd ON callback
before CCCI probe. `native-on-api.patch` retains that exact scpsys domain in the
successful real attach callback. Its GPL API accepts the actual device, checks
the retained first-OFF/native-ON owner, exact attached domain callbacks and current
binding/evidence/resources, then reads physical ON, TOP and all three live rails.
No caller supplies a success flag, calibration cookie or verification callback.

`ccci-native-start.patch.vendor` applies to the complete shipping adaptations +
frozen owner/ports/prepare/lifecycle + actual SMEM consumer stack. It does NOT
apply to resource-only HIF drivers. Those have no operational start callbacks.
The former files remain unchanged on disk; these are additive generated patches.

1. Actual CCCI common probe privately obtains the mapped-SMEM provider layout,
   prepares parked FSM/ports and pins operational HIF modules. Its last fallible
   operation calls `ccci_tetris_native_probe(md)`, validates native physical ON,
   sets runtime PM accounting active while disabled, gets a real no-resume usage
   reference before enabling PM, and retains the real platform device/module.
   Probe does not commit registration, request WDT, start HIF or call POWER/0.
2. Real CCIF and DPMAIF probes first claim their exact B4.1 MMIO inventory: two
   CCIF resources and four DPMAIF resources. Actual initialization then calls the
   checked registration API with its real controller, ops and device. Registration
   pins the provider module and seals registry identity. The old void registration
   path cannot overwrite it. First failures/claims are retained without retry.
   Shared infracfg/syscon ownership is not duplicated; claims do not prove NS access.
3. Explicit post-bind `ccci_tetris_native_first_start(pdev)` calls the real prepared
   registration transaction, then appends the real FSM START command. Success means
   queued, not released or READY. There is intentionally no probe/init caller of
   this explicit execution API. The probe handoff and existing FSM/md_cd_start
   call sites ARE patched and callable, not an isolated unused state machine.
4. Actual `fsm_routine_start -> ccci_md_start -> md_cd_start` selects the new native
   owner composition. Only native mode bypasses START's prepare-only veto; STOP,
   monitor/ioctl, diagnostic attributes and consumer lifecycle remain denied.
   The old virtual-device/OFF backend, `md_start_platform` power-off, duplicate
   PMIC/TOP/FLIGHT/power-on and unchecked `let_md_go` are not called.
5. START obtains the exported sleep lock before device locks, checks first-error
   and one-shot identity, revalidates physical ON, obtains a real platform runtime
   PM reference and revalidates again. It retains the source's bounded POWER/3
   BROM predicate poll (100 x 20ms), then POWER/2 four-equal-one flag check, without
   the legacy OFF tail. Unsupported replies fail immediately; timeout is retained.
   It locks both real HIF devices, checks bound
   driver/controller/ops/claims identity, requests the real WDT disabled, starts
   CCIF then DPMAIF with checked errors, publishes only BOOT_WAITING_FOR_HS1,
   revalidates native ON, and submits exact POWER/0.
6. Only a checked POWER/0 result permits host first-boot bookkeeping and WDT enable.
   Actual receive IRQ/port/FSM events still supply HS1/HS2 and READY. Failures retain
   original errno, PM/device/module/IRQ/clock/memory ownership for cold recovery.
   There is no guessed shutdown/reset/rollback or retry of a mutated start.

The code initializes source-backed load-type/image bookkeeping without calling
legacy `ap_md_mem_init` over a provider-owned mapped layout. Existing memory
provider claims, validation and module reference remain the concrete dependency;
an absent provider/layout returns ENODATA, not a fabricated grant.

## POWER/0, Not FLIGHT

ATF payload SHA256 `05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
Exact call: x0=`0xc2000505`, x1=6, x2=0, x3..x7=0. The tracked pinned POWER
fixture source establishes a0=status, a1/a2=two boot-status register words,
a3=boot-slave register readback after writing 1 at `0x21b20300`. This adapter
retains/logs these defined fields, stops on nonzero a0 or a3 != 1, and does NOT
interpret a1/a2 as four BROM completion flags. Outer admission is separate.
The fixture is read, never imported or executed here; no fresh binary decode or
Unicorn success is claimed. FLIGHT has only a0 defined and is not called again.

## CI Contract

First complete the ordinary packaged smoke and `real-boot/ci.py build`. On a Linux
GitHub CI runner, use its already-staged disposable kernel (NOT research owners):

```sh
python3 -B patches/modem/md-pm-integration/native-start/ci.py \
  --prepared-kernel /tmp/tetris-kernel-smoke/linux-d84b264a54a37611f2f46bc19363cb9b41606205 \
  --pristine-kernel /tmp/tetris-native-start-pristine \
  --config pmaports/device/testing/linux-postmarketos-mediatek-mt6878/config-postmarketos-mediatek-mt6878.aarch64 \
  --vendor "$pinned_device_modules_git" \
  --output /tmp/tetris-native-start-objects \
  --report /tmp/tetris-native-start-evidence/BUILD-MANIFEST.json \
  --enable-native-start
```

The explicit pristine input needs only `drivers/pmdomain/mediatek/mtk-pm-domains.c`,
`mtk-pm-domains.h` and `Kconfig`, each SHA256-checked against pinned d84. Extract
these three files from the parent's already SHA512-verified Linux archive before
patching it; no other pristine files or local archive path are needed by `ci.py`.

Historical source reads in this compile-only helper are from this repository's
`cbb777d415b564c1e40598740288c0c9d953e745` (native adoption patch, adoption header
and shared camera/provider patch) and `06fa22493cb8686e67c82236fdd26741e8da0378`
(post-OFF header/Kconfig).
The vendor Git source must contain exact `ee2be53cb75670b548948636a0db1d1ff112bf12`.
`e0c67c561ff7c1a0472da851edfafd5a0abb6cec` is read by `link_full.backend_sources()`
in the separate full-link gate, not by this helper's `closure.stage()` call.
No historical U-Boot object is read here. Source-only `audit.py` separately reads
ATF fixture SOURCE at `634789437e3f80a0129f00e5cff922bd8cdbb64b` and verifies the
companion `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` tree. Neither is ATF execution.

The helper requires fresh separate outputs and exact real-ON source bytes,
applies the native API delta once, compiles default-off and native-API variants
of the real shared scpsys object plus disabled-consumer DTB, then compiles seven
actual changed CCCI/HIF units from a fresh exact complete vendor stack. It uses
shipping compatibility flags, real generated kernel headers and explicit isolated
OWNER/NATIVE_START/SMEM_CONSUMER defines because vendor Kconfig is not sourced by
the upstream kernel. Defined symbols, AArch64/ThinLTO identity, config/source hashes
and actual logs are collected. ThinLTO/CFI remain inherited. Consumer and rails
must remain disabled; provider status is untouched. No full module link/modpost
or installed artifacts are produced. Compilation is refused outside Linux GitHub
CI before source mutation or compiler invocation. Global CI is owned by parent.

Local source-only checks, from this directory:

```sh
python3 -B audit.py
python3 -B stage.py
python3 -B -m unittest -v test_static.py
```

## Remaining Activation Gates

Actual native-start CI compile/report is pending. The earlier realON job does not
compile this new delta. Complete module link/modpost and exact export CRC/ABI
closure are still required; object compilation is not executable installation.
The API header/supplier must be installed together with the vendor composition.
Operational HIF modules must not be mixed with the resource-only profile or the
legacy OFF owner. Firmware/NC/cache/tag claims and trusted final loader DT must
remain genuine and retained, with matching secure profile and NS memory access.
No new authentication, secure admission or SMEM permission is inferred here.

Real HIF initialization's lower getters, DMA/IRQ/error unwinds and platform profile
still need whole-driver/hardware validation. Permanent refs and suppressed bind
attributes do not make forced platform removal safe. Forced detach, STOP, restart,
exception recovery, runtime teardown and suspend are unsupported, not simulated.
The r188 sleep/hotplug veto is retained, not replaced by a new proof flag.
Successful POWER/0 does not establish BROM/handshake/SIM/network service.
No phone/SSH/fastboot, local native compilation/emulation/JIT, commit/push or remote
mutation was performed by this worker.
