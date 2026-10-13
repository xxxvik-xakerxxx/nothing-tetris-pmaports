# Exact1009 Opt-In Image Candidate

`ci/stage-gnss-tx-image.py` is a separate, explicit extension of a disposable
pmaports copy already staged by the unchanged `ci/stage-native-modem-image.py`.
It follows the isolation, parent-manifest and fail-before-write pattern used
by `ci/stage-native-modem-rails.py`. The CI workflow invokes it only when both
`native_modem_first_off=true` and `gnss_tx_image=true` are explicitly selected.
Omitting `--include-exact1009` refuses staging before any write. Shipping r182
and the default frozen r184 profile continue to omit 1009.

The extension accepts only the exact **unchecksummed r184 parent**. It rebuilds
that package snapshot in a temporary directory through the hash-pinned parent
helper and its frozen `cbb777d415b564c1e40598740288c0c9d953e745` git objects,
then compares the manifest, APKBUILD, config, five native patches, device
APKBUILD, deviceinfo and FIT selection byte-for-byte. Stage immediately after
the parent, before checksum regeneration or the build's retention append.
Altered parent inputs require review rather than an automatic rebase.

This helper does not compose with the independent r185 native-rails extension.
Choose an unused candidate package revision of at least 186; r185 belongs to
that extension. The revision is an explicit argument, not a reserved release.
The candidate uses profile `native-md-first-off-gnss-tx-exact1009-candidate` and
retains the parent's device package, DTB and required U-Boot identity.

## Exact Inputs And Changes

The pinned `STAGING.json` SHA256 is
`a613bf4fb1bc8ac046fdbfead9963cc0166719959017768a59b30a6ab021d571`.
The unchanged parent helper SHA256 is
`12a98bc5ff8bf135c21fac95e9d30ae4cc0e26a63db00db1fdb6098da0d705c5`.
The exact1009 patch SHA512 is:

```text
6989187ef229f8c7fe91024ad56a2a90d04e51b4f230373ce072b329da619f281c172b56b29da83d192c697af0590662fdb697d8b5511aa7a30235bcc3ea6602
```

The connectivity source remains
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. Each 1001..1008 prerequisite
must match the SHA512 recorded in the pinned manifest, in the same order in
both the source list and vendor prepare sequence. The helper copies exact1009
without regenerating it, adds it immediately after 1008 in both places, uses
`patch --fuzz=0 -p1 -d "$_connmods_dir"`, and changes only the candidate kernel
revision. It writes one patch, the copy's APKBUILD and a distinct report inside
the copy. Reports must be outside kernel/device package directories.

Config, DT, services, GNSS activation, modem activation, native rail activation
and image selection are unchanged by the extension. Existing parent exclusions
for camera/GPU, sleep, idle and hotplug remain. Checksums are deliberately
pending: regenerate with `pmbootstrap checksum` before package prepare/build;
never introduce `SKIP` or bypass validation.

## Matched Image Integration

`ci/stage-native-gnss-image.py` composes both helpers before checksum regeneration
or evidence append. Candidate kernel r188 retains the r184 device/DT and paired
startup-OFF loader. The published profile carries the actual revision and
exact1009 hash. The separate artifact `nothing-tetris-native-md-gnss-tx-images`
includes native and GNSS reports; BUILD-MANIFEST names the distinct profile.
Both new image paths preserve wakeup-source APIs and use a persistent kernel
sleep veto instead of the broken r184 PM_SLEEP=n exclusion. Without exact1009
the corrected profile is r187; with exact1009 it is r188. Frozen r184 staging
remains unchanged as the reproducible historical input, not the current CI
image profile. `stage-native-wakeup-image.py` applies the reviewed corrective
delta after exact parent validation. Distinct revisions prevent ABI mixing.

Both flags require a full image build, not validation/smoke-only mode. Kernel,
suppliers and all external modules are rebuilt and packaged together. Completed
image and physical DSP/navigation checks remain required; staging reports are
not hardware or ABI proof. The source GNSS report retains the pre-wakeup parent
profile and the correct final r188 package revision; the image report adds the
sleep-veto patch and API policy. The full r188 image must pass CI before flashing.

These are future CI integration instructions, not commands executed in this
work. A separately reviewed opt-in image job must make an isolated pmaports
copy, provide the existing frozen source repository via
`TETRIS_NATIVE_SOURCE_TREE`, and run the unchanged parent followed immediately
by this extension. For example, with an unused revision 186:

```sh
# Future GitHub CI only; /work/out/gnss-tx-pmaports is a disposable package COPY.
export TETRIS_NATIVE_SOURCE_TREE=/work/out/native-source
python3 -B ci/stage-native-modem-image.py \
  --pmaports /work/out/gnss-tx-pmaports \
  --report /work/out/gnss-tx-pmaports/evidence/native-parent.json
python3 -B ci/stage-gnss-tx-image.py \
  --pmaports /work/out/gnss-tx-pmaports \
  --parent-report /work/out/gnss-tx-pmaports/evidence/native-parent.json \
  --report /work/out/gnss-tx-pmaports/evidence/gnss-tx-candidate.json \
  --include-exact1009 --candidate-pkgrel 186
```

Point pmbootstrap at that copy, regenerate the kernel package checksums, and
prepare/build the kernel and **all external modules together** with the same
compiler/configuration. Retain zero-fuzz patch-application evidence, compare
the prepared pre1009 source hashes with `stacked_source_sha512`, and run the
existing actual-source IRQ/polling fixtures and applicable negative controls.
Retain strict module link/modpost evidence with real kernel exports, connadp
and conninfra; package kernel, modules, boot/FIT and rootfs as one matched image.
Record compiler, config, kernel, module, package and final artifact hashes.

The future job must also carry the new candidate profile/revision through its
image manifest, validation, artifact naming and sealing. Existing r184-only
manifest/DT checks cannot establish this candidate's identity by themselves.
Preserve the parent's paired U-Boot requirement and DT checks. Publish the
parent and candidate reports alongside final checksum/build evidence; the
staging report's APKBUILD hash is **before** checksum regeneration and any
retention append, so record the final APKBUILD separately. The frozen parent
helper and shipping package definitions remain unchanged.

## Evidence Limits And Static Tests

CI38357565018 at `f27228d3f101690e9f6592efa4c777b4b936363c` passed full
baseline1001..1008/candidate1009 module closure with genuine suppliers and
clang21.1.2. The installed phone kernel used clang21.1.8. This is historical
source/link evidence; those modules cannot be hot-swapped into the phone.
The staging report preserves that evidence under a historical key and marks
matched-image build, phone ABI compatibility, hardware testing, shipping
activation and end-user radio functionality false. No report asserts a fix,
hardware progress, GNSS readiness, a wall-clock TX deadline or serialization
of concurrent writes. Existing DMA/reset, full-ring/alignment and shared-buffer
limitations remain as recorded in the pinned manifest.

Run only the static suite locally:

```sh
python3 -B ci/test-gnss-tx-image.py
```

Tests first load frozen-source fixtures from local git objects with read-only
`git show`, then forbid external process execution while exercising the helper.
They exercise temporary package copies, exact hashes and
both orders, deterministic output, default/CI/source isolation refusals,
parent drift, revision collisions, symlinks, hardlinks and report collisions. They verify
the complete allowed package delta and false activation/proof fields. They
do not apply the vendor patch to real sources, compile, dispatch CI or touch
hardware. A later authorized clean-artifact test still needs USB/SSH baseline,
cold repeats, GNSS function, restart, coexistence, lifecycle and portability
evidence before any support claim.
