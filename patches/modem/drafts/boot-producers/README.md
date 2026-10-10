# Real Linux boot policy and selected-UFS preloader identity

New scope only. Frozen bootstrap-integration, EMI and shared U-Boot/workflows
untouched. No board hook, phone operations or local C compilation/execution.

## Policy is allowed to be ours

Normal native Linux explicitly chooses CCBgear1 and PHY capture size0. Matching
LK/planner supports those values: CCB0/1 uses0x1600000 and LK's PHY path skips
SIB allocation/setter when the computed size is zero. This is NOT a claim the
stock option was absent. No dependency on recreating Android boot-option text
is needed for this restricted policy. Factory/AEE/diagnostic modes are not
silently emulated. Firmware-derived service sizes/DRDI metadata remain signed,
and actual slot40/preset3 remains mandatory even with PHY39 explicitly disabled.

The wrapper calls the actual frozen load-owner chain with1 and literal"0" only
AFTER measuring its profile. It has no chosen digest/root/READY argument.

## Existing ATF check is not a preloader check

Current tetris_scp_prepare.c:218 checks tee_a at offset512 for PROFILE_ATF_SIZE
against its payload hash. It does NOT read/hash PL or prove actual executing EL3
identity. This producer restricts the first opt-in experiment to slotA, confirms
misc boot-control decoding via the existing CRC/slot decoder, then checks PL
independently. SlotB is rejected rather than measuring tee_a for a different slot.

## Actual identity producer

ufs-boot-identity.patch adds only READ_ATTR/READ_DESC operations through existing
UFS query implementation, one attempt per request (no added retry). Read actual
BOOT_LU_EN(0x00), then actual unit descriptor0..4: length/type/index/enable/bootID.
Unit bBootLunID offset4 is documented in upstream Linux:
https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/b91872c56940950a6a0852e499d249c3091d4284/include/ufs/ufs.h

Wrapper enumerates SCSI block devices, accepts only siblings/target of the actual
modem storage controller, and requires exactly ONE whose unit bootID equals the
selected boot attribute. No hard-coded scsi devnum, no assuming bootLUN0 is active,
no scanning other controllers and no fallback after descriptor/query errors.

On that real block descriptor it requires UFS_BOOT NUL at0, GFH MMM01 at0x1000,
load base0x02000f00, declared size+0x20 bounded0x38..4MiB and whole rounded extent
inside the LUN. Streams SHA256 over precisely declared GFH bytes (including GFH,
excluding UFS prefix/trailing sectors), using at most4KiB aligned read buffer.
Only exact5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f
allows the real load-owner call. First I/O/malformed/mismatch error wins; second
wrapper call does no work. Hash output cannot be supplied via chosen/command.

This is stored active-boot image identity, NOT hardware attestation of executing
preloader/ATF. Its boot-experiment scope assumes matching cold stock BL2/ATF,
no storage replacement between that cold boot and this synchronous sole-AP
owner. No device_lock/scope callbacks or nested locks are introduced. Actual
normal-vs-AEE policy must still pass the existing real EMI readback checks.

## Storage lifetime and actual tag payload producer

retained-handoff-storage.patch applies AFTER main's integrated rows storage
patch. It adds a separately named handoff loader, preserving the current API.
It invokes the existing manufacturer-root bundle verifier ONCE, derives rows
from that same immutable snapshot, and copies the signed512-byte CHECK_HEADER
from the verified ROM member offset before staging release. Plan, rows and
footer are published only after staging release and payload cache completion.
No RAM reauthentication, extra signed-input scan or secure permission change.
Main must switch its owned loader call to this API and retain the footer/plan
privately through bootstrap; this draft does not edit that frozen owner.
The duplicate rows/handoff function bodies should be unified behind one private
implementation during integration, preserving the old public API and faults.

check_storage_lifetime.py --native-ci --uboot PATH extracts the EXACT added
production caller, with pinned real headers. Fourteen strict ASAN/UBSAN cases
cover slot/size/allocation/read/auth/row/release/cache failures, first-error
retention on simultaneous read/auth+release failure, destination/output alias,
atomic outputs, exactly-once release and poisoned released snapshot. Boundary
crypto/LMB/cache providers are doubles, NOT alternative authentication. The
actual manufacturer signature oracle remains main's independent signed-input
CI. Neither native fixture has been executed locally or passed CI yet.

tetris_modem_ccci_tags.c builds21 concrete consumer tags from retained metadata
and the internal successful load/BROM report, never from protected MD RAM.
Source ABI is vendor ee2be53cb75670b548948636a0db1d1ff112bf12
drivers/misc/mediatek/ccci_util/ccci_util_lib_fo.c and ccci_util_md_mem.c:
hdr_count/hdr_tbl_inf, smem_layout, md1_chk/md1img, modern nc/c service tables,
24-byte memory rows, legacy cache/NC rows and actual cahce-offset typo.
It rejects active PHY/SIB or UDC outside this explicit normal Linux profile.
free_in_kernel is0: signed padding flags do NOT authorize freeing MD-owned RAM.
The memory layout covers the full owned firmware allocation, including the tail
beyond the signed logical memory size; hdr_tbl_inf retains that logical size.
Do not truncate the existing map or pass its smaller logical extent to the
strict encoder. The CI fixture verifies complete contiguous allocation coverage.
No guessed md_generation, table-version or secure-world MTEE success is emitted.
Legacy cache row offsets are relative to the cache view; the independent
md1_smem_cahce_offset tag supplies its128MiB bank4 placement. Cache-info's
md_offset is not consumed by cache parsing; address/size/count are actual fields.

check_ccci_tags.py --native-ci --uboot PATH --stock-container modem.img runs9
strict sanitizer cases using real public stock ROM/footer and the real layout/
EMI producer. Hardware report is synthetic: this tests ABI/atomic failures,
not authentication, actual BROM execution or SIM readiness. Snapshot is poisoned
and released before tags are encoded. Neither CI target changes shared workflows.

## Exact remaining integration gate

Run both native fixtures and real-header ARM64 object checks in main-owned CI.
UFS descriptor/streaming hash fault coverage is still pending; no UFS request
was executed locally. Local checks only parse/hash stored PL, inspect source
ordering, and dry-run patches. No complete CCCI publication exists yet: reserve
and cache-clean the tag buffer, then atomically install the actual little-endian
32-byte ccci,modem_info_v2 descriptor under the matching mddriver node ONLY after
successful BROM. Do not substitute FDT cells or emit environment-ready on error.
The production owner must retain actual authenticated footer/metadata privately;
this encoder's internal report input is not a public report-to-READY command.
There is no board caller or enabled Linux modem consumer in this draft.

For the next BROM-only opt-in experiment complete CCCI publication is not needed:
leave kernel modem provider/consumers disabled and retain actual first-stage
report for inspection. Do not publish partial legacy tags as modem-ready.
