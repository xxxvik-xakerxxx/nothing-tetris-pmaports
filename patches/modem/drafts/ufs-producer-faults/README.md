# Actual UFS identity and owned-loader fault checks

New disjoint files only, plus the specifically authorized update to
startup-final/check_startup_final.py. No shared U-Boot/workflow/old fixtures,
phone operations, local C compilation/execution or hardware access.

Main reports actual CI38027600180 passed14 storage/9 tag cases. This revision's
new native fixtures have NOT run yet; source/Python results are not C/AUTH proof.

## Baseline and integrated validation without skipped drift

Updated startup checker uses exact94ead1146c93fef603db5c85820f2fb04c559c10
file contents plus review overlays. Owned storage C/header and loaded owner must
match either original baseline or EXACT resulting integrated source. No applying
patches against already-integrated production; overlay is computed in memory
with unique full context. Drift fails instead of being silently skipped.

Final/publisher/board-owner C/header files, if installed, must match reviewed
bytes. Main-owned shared board insertion is deliberately checked by its unique
default-OFF IS_ENABLED gate, one call, header and refreshed DT pointer rather
than a whole-board hash that would conflict with the GPU owner's independent
changes. Integrated Kconfig must retain default n and every safety dependency.
Other main-owned board/GPU code is outside this checker ownership scope.

test_checker_modes.py UBOOT_PATH:7 read-only Python tests cover baseline+overlay,
integrated exact and rejected owner/storage/publisher drift, default ON and
wrong board gate. Fixtures mock file READS in memory, never create worktrees or
modify U-Boot. Both storage modes extract ONE identical private transaction.

## Real selected_boot/preloader_digest/UFS producer C

check_producer_faults.py --uboot PATH --native-ci extracts actual production
functions when integrated and validates them against review. On baseline it
uses the identical reviewed additions, not an alternative algorithm. Actual
ufshcd_map_desc_id_to_length, ufs_read_lun_boot_identity, word, selected_boot,
preloader_digest and exact UFS descriptor-size struct/protocol enums are used.
Any producer/protocol source drift fails before compilation. The low query,
enumeration/block-I/O callbacks and SHA context representation are host doubles;
SHA computation itself is real OpenSSL EVP SHA256, never a chosen digest.

35 strict sanitizer cases cover READ_ATTR failure/unsupported boot value,
initial/returned descriptor lengths and type/index/enable/boot-ID corruption,
descriptor error, ambiguous/missing boot LUN, enumeration errors, foreign target
exclusion, invalid parent/HBA, GFH prefix/magic/base/size/capacity boundaries,
4MiB exact bound, short prefix/GFH/stream reads, real mismatching digest,
allocation failure and512/4096-byte block sizes. Provider errors also traverse
real selected_boot: preserve first failure, unchanged outputs, no query retry
and no storage read after rejection. Hash streaming is checked against an
independent EVP one-shot digest over precisely declared bytes, excluding tail.

Synthetic valid-shaped data MUST return EKEYREJECTED, never fake profile success.
Optional --preloader-image DECLARED_GFH_FILE adds case32, the positive profile
gate with exact5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f
hash. Input contains GFH+precisely its declared bytes, not UFS prefix/trailing
LUN data. The fixture installs that public/source-backed image under a modeled
UFS_BOOT prefix; it does not assert executing-PL/EL3 attestation. If absent,
positive pinned case is explicitly NOT RUN. Do not publish private device dumps.

## Actual retained-footer owner, not frozen old loader

check_producer_faults.py --uboot PATH --owned-loader-ci compiles the exact
reviewed/integrated tetris_modem_loaded_boot.c containing private loaded/footer
members and real handoff storage call. The frozen17-case boundary fixture is
included unchanged with renamed doubles. New wrappers supply the handoff footer
and observe actual private-owner behavior; production owner code is not rewritten.
Its callee boundaries are explicitly doubled, as in the frozen17-case fixture.

19 strict sanitizer cases retain ALL17 original first-error/one-attempt checks
and add bootstrap-report retrieval failure and encoder error. Every case checks
encode rejection before load; actual bootstrap callback checks rejection even
AFTER metadata capture but BEFORE BROM report completion. Success asserts the
same private plan/footer addresses and512 retained bytes survive return, and
only the complete internal hardware report reaches the encoder. All earlier
failures leave caller output unchanged and never reach the encoder. No external
report/READY or footer argument is accepted by the production owner getter.

Firmware verification/reservations/hardware/tag encoder boundaries here are
explicit doubles, NOT fake production AUTH and NOT actual modem execution. Main's
signed-stock authentication, tag9, bootstrap and AArch64 gates remain mandatory.

## CI invocation and limits

Ubuntu CI requires compiler, libssl-dev and existing U-Boot checkout. Execute:

    python3 patches/modem/drafts/ufs-producer-faults/check_producer_faults.py \
      --uboot UBOOT_PATH --native-ci --owned-loader-ci

Optional positive GFH source can be provided as --preloader-image. Local invocation
without CI flags performs source/AST extraction only. All C flags remain strict
-std=c11 -Wall -Wextra -Werror plus ASAN/UBSAN. CI=true is required for either C
target. Workflow/build/phone sequencing stays main-owned. No physical BROM test
is justified merely by these boundary fixtures passing.
