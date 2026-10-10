# Owned modem startup and final-DT publication draft

New scope only; frozen boot-producers194bb18/bootstrap/EMI files and actual
U-Boot/board/workflow/Makefile are untouched. No local C build/execution or phone
operation. Source/proof restrictions remain exactly those of the frozen loader:
matching cold stock BL2/ATF -> NS BL33, primary synchronous AP owner, measured
selected UFS boot-LUN GFH, independently pinned manufacturer root, real strict
five-register OFF preflight and actual EMI/SMC readbacks. No permission/READY
caller flags, invented reset, changed guard or calibration access.

## One storage transaction, private retained metadata

unified-storage.patch applies to actual integrated rows loader, INSTEAD OF
boot-producers/retained-handoff-storage.patch. Do NOT apply both. One private
load_slot_owned implementation contains the one prepare/auth/derive/copy/
release/cache lifetime. Legacy rows API is preserved as a thin NULL-footer
wrapper. Handoff API validates a non-NULL footer before entering that same
implementation. Footer capture uses the verified ROM member offset before
snapshot release; outputs still commit after successful release/cache sync.
No duplicate signature scan, snapshot allocation or auth/release/cache body.

owned-loader.patch changes only owned loader code: loaded plan and512-byte
footer become private static owner members, not exposed source pointers.
Owner calls handoff storage API and initializes shared banks from that retained
plan. They survive real BROM completion. tetris_modem_loaded_encode_tags accepts
ONLY an output buffer; it cannot accept arbitrary external firmware metadata,
report, digest, AUTH or READY. It calls the existing strict tag encoder using
the private owner/report after actual load completion. First loader failure
remains latched; no publication after auth/cache/bootstrap error.

Main's tag correction is mandatory: encode memory using FULL firmware.capacity
(512MiB on this profile), retain logical480MiB hdr_tbl_inf and free_in_kernel0.
Do not truncate the final reservation tail or restore the previous encoder call.
Corrected main-owned CCCI encoding and14storage/9tag cases passed38027600180.
This does not establish real BROM completion or Linux runtime readiness.

## Actual final owner

tetris_modem_final.c requires exactly one existing mediatek,mddriver consumer
and no inherited v1/v2 descriptors. No guessed node/provider/phandle is created.
Actual LMB allocations independently own64KiB tags and a bounded <=2MiB DT
clone. Allocations use the same existing below0x80000000 MAX/NOOVERWRITE policy
as the GPU final-DT owner, not handset-observed addresses.

Kernel ccci_util_lib_fo.c:659..710 maps MAX_LK_INFO_SIZE64KiB regardless of used
tag bytes. Therefore ALL64KiB are allocated, zeroed, mem-reserved, no-map and
cache-cleaned. Real21tag bytes come exclusively from the private loader owner.
Clone the CURRENT images->ft_addr; preserve earlier GPU/SCP/resource changes.
Add clone's own header reservation and tag no-map node (requires existing
reserved-memory with2/2 cells and empty ranges). Reacquire consumer offset after
DT edits. Encode exact raw little-endian32-byte _ccci_lk_info_v2:
base:u64, used:u32, error:0, version:2, count:21, ld_flag:0, ld_md_errno:0.
Kernel derives MD enable from successful actual hdr_tbl_inf; no READY bit added.

All changes occur on the unpublished clone. Clean entire tag allocation, then
entire clone, then commit images->ft_addr/ft_len once. ARMv8 cache.S:173..188
uses dc civac followed by dsb sy. No driver status is changed. On error old DT
and images remain unchanged, first fault is latched, and only unpublished AP
tag/DT allocations are released; release errors are logged separately. Never
free firmware/NC/cache or old shared DT. One attempt, no power operation.

## Default-OFF BROM-only caller

brom-only.Kconfig is a review-only fragment with default n, existing actual
TARGET_MT6878/LMB/OF_LIBFDT/security dependencies and mutually exclusive GPU/
old modem diagnostics. Main owns insertion and Makefile integration.
board-brom-only.patch is a standalone review patch; no actual board edits here.

tetris_modem_brom_board.c verifies disabled/absent mddriver, MD power provider
and read-only preflight nodes, rejects inherited CCCI descriptors, and uses the
same SCSI user descriptor2 as the existing pmOS boot path with actual modem_a/
tee_a partition checks. The existing producer then validates slot A and selects
actual boot LUN from UFS query replies, hashes declared GFH bytes and chooses
explicit normal CCB1/PHY0 policy. It is not a runtime executing-PL attestation.

Allocate/validate/reserve a roomy DT clone BEFORE any loader reservation. Commit
that initial clean clone before entering the real loader. Thus MD reservations
are always retained in the DT sent to Linux, including a bootstrap/cleanup
failure; do not revert the DT pointer on negative return. Firmware/service
allocations are never freed by the caller. BROM-only does NOT call the final
CCCI publisher. It leaves drivers disabled and descriptor absent.

Any old observation record is removed on the clone before starting, so a report
publication failure cannot leave inherited success evidence. Serial output
preserves real load/hardware/cleanup stage/error and all4 SMC
reply words. Observation-only /chosen/nothing,modem-brom-report is80 raw LE
bytes: version1@0, first result@4, report getter result@8, load stage/error@12/16,
hardware stage/error@20/24, cleanup stage/error@28/32, value@36, address:u64@40,
four u64 replies@48/56/64/72. It is not interpreted as CCCI/READY. Reacquire
chosen offset after reservations; report publication error cannot hide earlier
hardware failure. Clean reservation/report DT even on failure and continue the
existing Linux recovery boot path. No automatic reset/retry.

## Main integration and next gate

1. Apply unified-storage.patch and owned-loader.patch to integrated U-Boot.
   Use corrected main-owned CCCI producer plus measured policy/UFS producer.
2. Add final.c/header and brom_board.c via main-owned Makefile. Include the
   default-n Kconfig fragment and apply board-brom-only.patch manually alongside
   GPU owner's hunks. No shipping defconfig enable. Actual board caller symbol
   must be built whenever the board references it (or object guarded consistently).
3. Run check_startup_final.py --uboot PATH locally for source/patch checks only.
   In Ubuntu CI with libfdt-dev run --native-ci: exact unified implementation
   reuses main's14 strict storage faults; real libfdt publisher has10 strict
   ASAN/UBSAN atomic/ownership cases. Allocation/cache/private-owner responses
   are explicit boundary doubles, NOT firmware auth or hardware success.
4. Main CI must compile ALL actual AArch64 touched objects and full image with
   default OFF, then a separate BROM-only diagnostic image. Verify compiled DT
   keeps MD nodes disabled, CCCI descriptor absent and GPU experiment off.
   Revised native fixtures and AArch64 paths have NOT run for this draft yet.
5. Actual opt-in boot is main's separately approved single experiment after
   stock authentication, corrected21tag producer and preceding gates pass.
   Keep recovery USB/SSH and first-error report. BROM completion is NOT SIM,
   calls, runtime transport readiness or production power lifecycle support.

Future final-publication order: authenticate/capture -> real owned bootstrap ->
GPU final-DT owner if independently approved -> MD publish_final(images) LAST.
Always use current images pointer, refresh any borrowed board fdt pointer after
each owner, never reconstruct final DT from an old saved pointer. BROM-only
currently forbids same-boot GPU diagnostics; full CCCI publication has no board
hook/config here and cannot silently replace the BROM-only experiment.
