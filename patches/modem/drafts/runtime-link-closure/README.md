# Full OWNER + private SMEM consumer module link candidate

Status: source checks and full strict ARM64 linkage passed CI38255895881 at
5379657. Eight vendor modules, the real backend and existing provider have
matching r181 ABI and genuine export/dependency closure. They were not loaded.
Nothing
in this directory installs, loads or starts a module, dispatches CI, changes
DT/config, or edits the parent helper/workflow. Frozen drafts remain unchanged.

The concrete missing exports are `mt6878_ccci_start_alloc`,
`mt6878_ccci_first_start`, and `mt6878_ccci_start_result`. r181 has
`CONFIG_MTK_MT6878_CCCI_FIRST_START` disabled and none of these exports. The
OWNER object directly imports them even though the prepare-only FSM denies
START. `backend.Kbuild` builds the **actual complete packaged backend** as a
separate external module against the unchanged r181 config/exports. The helper
checks its source and public header against patch 0117 at the actual r181
package commit, requires its genuine GPL export table, then supplies that table
to full ECCCI modpost. There are no substitute implementations or symvers rows.
The backend has no module init or platform-driver entry point; this still does
not authorize calling its exported power/start operations.

## Parent invocation

After the current job has successfully completed
`ci/packaged-smem-objects.py --link-r181 --smem-consumer`, add this separate step
in that **same CI workspace** (no workflow edit is included here):

```sh
python3 -B patches/modem/drafts/runtime-link-closure/link_full.py \
  --vendor /tmp/tetris-kernel-smoke/vendor-git-source \
  --work /tmp/tetris-kernel-smoke \
  --destination /tmp/tetris-ccci-full-link
```

Destination must not exist. Build requires `CI=true` and `GITHUB_ACTIONS=true`.
It consumes the parent's successful `packaged-smem.json`, exact r181 kernel
staging and checked provider module/symvers. It verifies provider hashes,
review/common-header identity, pinned config and kernel exports. The parent
provider is only read. Fresh vendor sources are archived from
`ee2be53cb75670b548948636a0db1d1ff112bf12`; all shipping APKBUILD adaptations,
OWNER, ports, prepare, lifecycle, common and consumer overlays are checked and
applied. Every selected translation unit receives OWNER+CONSUMER consistently.
No objects from the research configuration or the 64-object run are reused.

The complete original ECCCI Kbuild is used, including AUXADC, CLDMA and SCP
companion, plus CCMNI/RPS. This is eight vendor modules, the real first-start
backend, and the existing provider. One strict vendor modpost pass resolves
cross-module exports; `KBUILD_EXTRA_SYMBOLS` contains ONLY the genuine provider
and freshly linked backend tables. No old ECCCI/legacy-util table can satisfy
missing new exports. Do not add the old util alongside the provider.

Retain `/tmp/tetris-ccci-full-link/full-link.json`, `backend-link.log`,
`full-link.log` and `artifacts/` in the parent artifact upload, including on
failure. Artifacts are copied only after strict linkage, AArch64/vermagic/GPL,
required owner/preparation symbols, direct provider/backend imports and genuine
export-owner census pass. Failure records preserve the first build failure;
there is no retry, permissive modpost or configuration fallback.

## Actual dependency findings

Read-only ELF inspection used existing CI38117727546 r181 evidence, verified
against its member hashes. Kernel export SHA256 is
`2e58e05288219f07094e88da49b9f12b1c06d2bf5875e87e1f557bc36c4e7cf3`;
config SHA256 is
`edcbdf45d3201aef8ab71157bb485c074bc5c3457f564f0341a7eb410b9382a2`.
Linux source is `d84b264a54a37611f2f46bc19363cb9b41606205`, r181 package commit
`e0c67c561ff7c1a0472da851edfafd5a0abb6cec`.

| Native module | Genuine r181 module dependencies |
| --- | --- |
| ccci_md_all | ccci_util_lib, ccmni, ccci_auxadc |
| ccci_ccif / ccci_cldma | ccci_util_lib, ccci_md_all |
| ccci_dpmaif | ccci_util_lib, ccmni, ccci_md_all |
| ccci_auxadc | ccci_util_lib |
| ccmni | rps_perf (`set_rps_map`) |
| rps_perf / ccci_fsm_scp | None in this selected profile |

The old AP-only util table retains **all** legacy util exports. Their presence
does not mean its skipped logging/sysfs/legacy-memory initialization ran. The
private consumer continues to deny post-bind commit; linkage must not be used
to lift that denial. The new provider adds `mtk_ccci_owned_mapped_copy`; the
new full consumer must import it and all three real backend exports.

The shipping recipe lists soc/mediatek, rpmsg and SCP symvers, but the genuine
r181 modem modules have no imports requiring those tables. The selected SCP
companion is not evidence of functioning SCP transport. Configurations enabling
additional vendor features must provide their actual implementations/exports
in a separately reviewed extension; this helper must fail strict modpost when
such a dependency appears. Full compilation also covers Kbuild-selected objects
beyond the 64-object fixture; it may expose a new compile or link failure.

## Source-only verification

```sh
python3 -B patches/modem/drafts/runtime-link-closure/link_full.py \
  --source-check --vendor ../android_kernel_device_modules_6.1_nothing_mt6878
python3 -B patches/modem/drafts/runtime-link-closure/inspect_evidence.py \
  /tmp/tetris-r181-evidence-ci38117727546
```

The second command needs pyelftools and only reads genuine ELF files/tables.
It is optional and is not used by the CI linker. Source checks apply the entire
shipping/frozen stack and extract the real r181 backend with `git apply`.
No native compilation or emulation was run locally. The successful full link
establishes an ABI/build boundary only. A separate `--hif-resources` build
applies the reviewed resource-only profile, checks its complete source output
and validates the read-only `private_prepare` module parameter. Its output
directory must differ from the baseline; neither build changes shipping DT.
Private preparation still requires
reviewed resource-only HIF suppliers, authenticated memory/access ownership and
hardware lifecycle evidence; no READY, SIM, calls, safe unload or physical OFF
claim follows from these artifacts.
