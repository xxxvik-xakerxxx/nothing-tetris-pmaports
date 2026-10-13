# Exact MD Adoption + Camera Provider Composition

This profile applies the pinned MD adoption patch first, then the generated
camera overlay, producing one actual `mtk-pm-domains.c`. It preserves MD's
measured ON/OFF initialization, real attach/detach hooks and power-transition veto,
plus camera's observed-OFF initialization, VMM construction, callbacks, resume
guards and retention path. This is source/application evidence, not a link or
hardware result. KUNIT y/n use the same provider source; neither is compiled here.

OFF initialization is admitted only after the opt-in native MTCMOS first-OFF
transaction's actual readback. Ordinary callbacks remain vetoed. First-OFF
publication errors are latched before camera cleanup, and its hardware writes
remain restricted to the reviewed one-boot method. It does not perform full
vendor rail/TOP/FLIGHT shutdown. Joint CI uses the persistent first-OFF exclusion
profile so these writers are compiled rather than optimized away by idle/sleep
gates; shipping configuration is unchanged.

`MD-ON-ADOPTION-PROFILE.json` pins the MD stage generator, adoption/restart/test
helpers and staging patch, six pre-MD files, nine post-MD files, three source commits and frozen canonical
camera artifacts. The MD patch must exactly match the pinned stage generator's
pure candidate/diff output against the verified packaged baseline. Changed MD
inputs fail; there is no auto-repin or arbitrary rebase fallback.

The normal `native-provider.patch` and `evidence.json` remain unchanged. This
profile writes only `native-provider-after-md.patch` and
`md-on-adoption-report.json`. The overlay is camera-only and requires the exact
MD-applied baseline. Apply it instead of the canonical camera patch in this
combined path. Do not apply both camera patches or duplicate the old standalone
leaf/supplier smoke objects. The original default-off camera selector remains.

## CLI and Explicit CI Paths

Both `generate.py` and `check.py` accept the profile and explicit source paths:

```sh
python3 -B patches/camera-camisp/native-integration/check.py \
  --md-on-adoption \
  --kernel-archive "$CAMERA_KERNEL_ARCHIVE" \
  --vendor-repo out/infra-vendor \
  --modules-repo out/camera-modules
```

For example, the archive can be the parent's file under
`/tmp/tetris-kernel-smoke/`; its basename is immaterial. The supplied archive must
match the packaged SHA512 for Linux `d84b264a54a37611f2f46bc19363cb9b41606205`.
Vendor files are read from git objects at `ee2be53cb75670b548948636a0db1d1ff112bf12`,
and camera modules at `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`, in the supplied
repositories. Checkout HEAD is not used. No symlinks or sibling-path assumptions
are required when those options are supplied.

The CLI verifies canonical baseline inputs/pins before invoking the hash-pinned
MD stage's pure functions. It applies every MD hunk and every camera-overlay
hunk in a disposable tree, rejects offset/fuzz/skipped diagnostics, checks all
applied bytes and rejects extra/missing files. The digest report records both
input profiles, patch order, overlay digest, shared-provider digest and complete
combined payload hashes. Its `report_sha256` hashes the report without that field,
using sorted JSON keys and compact separators; the serialized report is stable.

Add `--write` to explicitly generate/update only the two composite artifacts.
Without it, the generated overlay and report must equal the stored artifacts.
After source review, `generate.py --md-on-adoption --write --refresh-md-profile`
explicitly refreshes only MD hashes against the unchanged packaged baseline and
canonical camera inputs. Ordinary checks and CI never refresh the profile.
The new restart staging retains TOP/rail node identities and the first errno;
it still stops before regulator acquisition and every ON write. The composition
validator forbids changing those helpers or inserting a hardware operation.

## Prepared Kernel Boundary

The parent first applies the exact MD staging patch through its own workflow.
Then add `--prepared-kernel "$CAMERA_PREPARED_KERNEL"` to either CLI to verify
that the prepared tree contains the nine exact post-MD files and no camera
payload. This option alone performs no writes to the prepared tree.

In GitHub CI only, also pass `--ci-apply` with `CI=true` and
`GITHUB_ACTIONS=true`. It applies only the camera overlay after those identity
checks and verifies every combined output file. This mode rejects `--write`.
No kernel command, compiler, linker, dtc, emulation, JIT, phone access or CI
dispatch is invoked by these tools. The parent retains responsibility for
compiling the actual combined provider/helpers and linking vmlinux.

Source/application tests:

```sh
python3 -B patches/camera-camisp/native-integration/check.py --md-on-adoption
python3 -B patches/camera-camisp/native-integration/test_md_on_adoption.py
```

The dedicated suite uses real sequential patch application and checks explicit
input-path forwarding, lost MD attach/transition veto, lost VMM callbacks and
constructor/retention, wrong initial state or cleanup, changed pinned inputs,
shifted context, partial application scope, already-applied camera payload,
wrong prepared preimage and rejection of local prepared-tree mutation. All
negative kernel tests inspect source in memory; no C is executed.
