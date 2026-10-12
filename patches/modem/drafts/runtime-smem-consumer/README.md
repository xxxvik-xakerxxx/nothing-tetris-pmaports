# Private CCCI SMEM Consumer

Default-off additive source candidate. No shipping files, frozen prior research,
workflow, APK, DT activation, SSH or hardware changes. Native C runs only in CI.
Preceding MAP_ONLY native/ARM64 and physical stable-boot evidence is accepted as
the existing mapper boundary; this candidate does not repeat or replace it with
a fresh certificate, caller READY flag or invented NS authorization callback.

## Exact Source Trace

Nothing B4.1 vendor commit `ee2be53cb75670b548948636a0db1d1ff112bf12`:

- `eccci/fsm/modem_sys1.c:ccci_md_alloc()` allocates private md/storage but does
  not configure memory. Current frozen `register_prepare.h` allocates this md,
  wake sources, FSM/ports, invokes `md->ops->init`, pins HIF modules, then retains
  only `tetris_prepared_md`, without setting `modem_sys` or platform_data.
- Existing post-bind `ccci_tetris_register_prepared()` marks exposure, calls
  `ccci_md_config()` and then publishes globals, FSM/ports/sysfs/syscore. That
  operation is now compile-profile-denied before device locking or exposure.
- `ccci_md_config()` uses `get_md_img_type()`/`get_modem_is_enabled()` and void
  `ap_md_mem_init()`. The latter fills shared static vendor arrays from
  `get_md_resv_mem_info()`, `mtk_ccci_get_md_{nc,c}_smem_inf()` and
  `mtk_ccci_get_smem_by_id()`, invokes the MDSS extra-file side effect and splits
  CCB a second time through `post_cfg_for_ccb()`.
- Those util getters use legacy `s_smem_hash_tbl`, global wire-row tables and
  sizes populated by `mtk_ccci_md_smem_layout_init()`/`map_phy_to_kernel()`.
  The isolated AP-only util deliberately never initializes those globals.
  Calling void memory init would therefore not consume the proven MAP_ONLY
  owner and could manufacture absent offsets via unsigned subtraction.
- `ap_md_mem.c:ccci_md_get_mem()`/`ccci_md_get_smem_by_user_id()` depend on
  published `modem_sys`, not the private md. They are intentionally not exposed
  or redirected by this candidate. No transport consumer is made operational.

## Ownership And Transaction

`common.overlay` adds one native interface header in `mediatek/include/mt-plat`.
It defines only copy-storage capacities matching actual B4.1 tables (26/11 with
tail guards); it duplicates no planner/template entries or physical addresses.

`provider.overlay` applies AFTER the frozen packaged AP-only metadata overlay.
`CONFIG_TETRIS_CCCI_SMEM_PROVIDER=1` requires MAP_ONLY, isolated metadata-only util
and a loadable module. It exports exactly `mtk_ccci_owned_mapped_copy()` as GPL.
Binding is a normal exported-symbol module dependency, not symbol lookup or a
global registry. It rejects capsule/output aliases and existing leases, takes
one real `try_module_get(THIS_MODULE)` reference, then calls the existing checked
`tetris_smem_export_mapped_private()`. Failed export balances only that reference
and leaves output unchanged. No fallible step follows successful copy. Actual
provider owner/mappings/claims retain their original independent boot pin.

`consumer.overlay` applies AFTER actual shipping adaptations, owner, ports,
prepare and lifecycle overlays. `CONFIG_TETRIS_CCCI_SMEM_CONSUMER=1` requires
OWNER. A tail field in the native `ccci_modem` retains one privately allocated
copy. Checked memory preparation occurs after both wake sources and BEFORE FSM,
ports, md init, HIF pins and the final private-md retention. Provider failures
reach the original quarantine path unchanged. Later failures first abort the
other private resources, then clear the md's table references, drop its provider
ref and free its private copy before freeing md storage. Provider mappings are
not destroyed by this consumer. Success retains the copy/provider reference
with the boot-pinned prepared md. No permanent memory publication occurs.

Bank0 retains source-derived physical address/size with NULL virtual address.
The consumer does not invoke legacy getters, clear SMEM, touch protected ROM,
repeat CCB partitioning, create MDSS debug files, perform SMC/CCIF writes or set
MD_SETTING_ENABLE. Image/runtime configuration is not synthesized. Legacy void
`ccci_md_config()` returns immediately in this profile so it cannot overwrite
the checked private layout. Post-bind commit is denied with EOPNOTSUPP until
complete core dependencies have a separately reviewed implementation.

## Source And CI Integration

Local source-only:
```sh
python3 -B patches/modem/drafts/runtime-smem-consumer/check_consumer.py \
  --vendor ../android_kernel_device_modules_6.1_nothing_mt6878
python3 -B patches/modem/drafts/runtime-smem-consumer/test_source.py
```

Generator verifies all old frozen reviews and exact generated prepare/lifecycle
and AP-only overlays before generating three independent additive overlays.
It checks application against the actual prepared inputs. `--emit` regenerates
ONLY this directory's overlays and review manifest. Apply `common.overlay` once
to each isolated source tree; then apply provider/consumer to their respective
roots. Never apply the packaged AP-only overlay onto the common OWNER util tree:
it is a separately linked provider, not a second legacy util instance.

Native CI only:
```sh
python3 -B patches/modem/drafts/runtime-smem-consumer/run_native_ci.py \
  --vendor /tmp/tetris-kernel-smoke/vendor-git-source
```
This extracts the actual copy-layout and mapped-private export bodies, compiles
the real new provider/consumer headers with exact vendor types, and mocks only
allocation/module/mutex boundaries. It covers missing owner, state/first-error,
alias/reentry/module-ref failures, allocation failures, six malformed native
outputs, private-copy isolation and balanced abort. A second fixture reuses
the existing registration kernel boundaries and executes the actual modified
`register_prepare.h` plus this consumer body: 12 allocation/wake/FSM/ports/init/
HIF/provider faults, first-error/no-retry, successful retention and commit
denial. Its provider export is mocked; the first fixture executes the actual
provider/export bodies. Four incompatible compile profiles must be rejected.
The existing actual MAP_ONLY producer/native fixtures remain a separate gate.

Actual ARM64/object and provider-link gates for parent CI:

1. Generate/check all overlays first, stage the canonical common header and apply
   provider after packaged AP-only sources. Build provider with the same exact
   r181 config/real kernel exports, MAP_ONLY+RESOURCE_ONLY+METADATA_ONLY and
   PROVIDER flags, `KBUILD_MODPOST_WARN=`. Require GPL export
   `mtk_ccci_owned_mapped_copy`, actual map/unmap and no legacy mapping caller.
2. Apply consumer to the complete OWNER+prepare+lifecycle tree, not raw vendor.
   Rebuild ECCCI with OWNER+CONSUMER consistently across ALL translation units
   sharing `ccci_modem` (its trailing field changes sizeof). Compile actual
   `fsm/modem_sys1.o`; require the real checked helper and direct undefined
   provider symbol. No changed clock/DT/START objects are selected here.
3. For a real ECCCI module link, supply the provider's genuine Module.symvers
   using `KBUILD_EXTRA_SYMBOLS`, plus every real existing CCCI dependency's
   exports. Strict modpost must resolve the provider, record the util module
   dependency and reject missing/incompatible provider builds. Do not fake
   symvers or suppress other unresolved CCCI symbols. An object-only result
   is not a linked/loadable full CCCI consumer. Do not load the old legacy util
   alongside this isolated AP-only provider with the same module identity.
4. Run both native fixtures above with sanitizer halt/leak checks. The second
   incorporates the actual modified registration transaction with the existing
   mocked kernel/FSM/ports/HIF boundaries; it does not emulate hardware or claim
   real FSM/ports/HIF initialization. Keep the provider boundary and full private
   transaction results distinct in the manifest.
5. Preserve source/kernel/config/export/overlay hashes and separate provider/
   consumer artifact scopes. Native linkage and hardware validation of this
   new consumer remain pending; no operational DT or autoload is authorized.

Next actual consumer step is running these native fault fixtures and real
ARM64/provider linkage, then a separately scoped private-md memory inspection
with all hardware publication still disabled. This is not SIM/calls support.

## Optional Actual-Kernel Copy Smoke

`private-binding-smoke.c` includes the REAL staged `modem_sys.h` and this exact
`consumer.h`; it never defines a replacement Linux/vendor struct. Its real
`kzalloc(sizeof(struct ccci_modem))` allocation has the same guarded trailing
field as the consumer overlay. Module init calls the checked copy helper once,
aborts its private copy/reference, frees md and logs only boundary completion.
It does not call `ccci_md_alloc`, private FSM/ports prepare, probe, HIF or any
registration/start function. No mapped memory contents are read or written.
Exit owns nothing. Success is ONLY a native ABI/private-copy/module-ref smoke,
not modem READY, actual FSM preparation or a complete CCCI probe result.

In CI, stage this directory's smoke source, consumer.h and Kbuild in a fresh
standalone external-module root. Stage `common.overlay` and `consumer.overlay`
on the canonical actual vendor source tree, preserving its real include closure.
Use the original r181 generated kernel headers/config AND real kernel exports,
not the separate research config. The provider must already have passed strict
linking with a genuine Module.symvers containing this new GPL export.

```sh
make -j2 -C "$kernel" O="$kernel_output" ARCH=arm64 LLVM=1 \
  M="$smoke_stage" TETRIS_VENDOR_ROOT="$consumer_vendor" \
  KBUILD_EXTRA_SYMBOLS="$provider_stage/Module.symvers" \
  KBUILD_MODPOST_WARN= KCFLAGS="$vendor_kcflags -Werror" modules
```

Kbuild explicitly uses OWNER+CONSUMER+CCCI_KMODULE_ENABLE, with REAL vendor
include roots `mediatek/include`, `eccci`, `eccci/{inc,fsm,hif,port}`. The main
native type closure is modem_sys.h -> ccci_core/modem/fsm/hif/port plus actual
ap_md_mem.h/mtk_ccci_common.h; none may be replaced with mock kernel headers.
All base vendor flags must match the proven kernel-module adaptation. Require
AArch64, exact r181 vermagic, GPL, strict modpost, genuine dependency on the
new AP-only util provider, and an import census without modem_sys, CCCI/HIF
registration, ROM/SMEM access or SMC symbols. Save source/header/overlay/config/
symvers hashes alongside both modules.

Loading the smoke adds the normal loader dependency reference while it remains
loaded; the explicit copy lease is acquired/dropped during init. Do not mistake
the remaining ordinary module dependency for a leaked copy lease. The provider's
boot pin remains regardless. No hardware execution is performed by this task;
parent must use the newly linked provider on a fresh boot for a controlled test.
