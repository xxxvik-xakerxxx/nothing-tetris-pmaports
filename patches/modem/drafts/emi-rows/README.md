# Complete B4.1 EMI row producer and preset transaction

Owned new files only. Frozen boot-stage/signed-input files, shared workflows,
U-Boot sources and phone are untouched. No local C compilation/execution.
Not shipping/enabled; independent native/AArch64 CI and main integration pending.

## Source closure

Exact LK image SHA256:
`29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f`.
Exact preloader GFH image SHA256:
`5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f`.
Exact ATF payload SHA256:
`05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
LK/ATF offsets below exclude the MTK 512-byte header. Private images are not
committed. The CI producer input is main's manufacturer-verified PUBLIC B4.1
`modem.img`, not arbitrary unsigned CHK bytes or a chosen digest attestation.

### Actual table and active-row semantics

LK table at `0x198678` contains twelve 24-byte rows:
`u64 base, u32 size, u32 flags, u32 role, u32 slot`.
Slot order 32..43 has initial roles `0,4,5,6,1,2,3,7,0,8,10,9`.
Only slot40 starts with flags2; all start inactive (bit0 clear).
`0x8196c` sets base/size and bit0 for normal rows, or redirects an additional
region fragment into the selected preset row and sets flags3/its actual role.
`0x8188c..0x818c4` skips bit0-clear or bit7-set rows; an active row calls
preset6 first if bit1 is set, then range0 using end=base+size.

**Zero size is not generically absence.** The setter can create active zero-size
rows. This producer rejects such a row before hardware calls. Only actual
absence of a producer branch/metadata match yields `TETRIS_MD_EMI_ABSENT`.
No caller-supplied activation/readiness/ownership booleans select rows.

### Slot39: optional PHY-capture / SIB, not CHK region7

`0x222a0..0x22390` reads `md1_phy_cap_gear` through LK's option lookup
`0x34f60`, parses decimal (`0x69394`), shifts MiB and caps at 0x60000000.
Absent option or zero shifted size takes `0x22398` without allocation/setter.
Nonzero size requests actual `md1_sib_mem` allocation (`0x238fc`) and calls
`0x8196c(role7, allocation, size, -1)` at `0x22390`.

The new planner consumes the actual resolved option text and actual SIB resource.
NULL/empty/decimal zero means absent; a nonzero request needs a separate owned
nonoverlapping SIB window of sufficient capacity. Missing allocation is an
error, NOT an omitted active row. A stale SIB window with zero/absent option is
also an error. Numeric parsing is bounded and rejects malformed, negative and
32-bit-shift wraparound values instead of reproducing LK's truncation bug.
The producer performs no allocation and does not pretend to know stock options
from CHK: main's board option/allocation owner must supply the real resolved
data, not a guessed user acceptance bit or hard-coded zero.

Preloader table at VA `0x020bf058`, base `0x02000f00`, stride0x410, row39:
normal list `(AID47,RW),(AID240,RO),(AID241,RO)`; AEE list only AID240/241 RO.
The new producer uses the NORMAL list; real transaction policy readback must
match it. It does not OR in AEE permissions or claim the hash alone selected
the normal branch.

### Slot40: actual signed-padding fragmentation, not an optional debug flag

Initial map comes from existing pinned `tetris_modem_plan_memory()` using actual
authenticated ROM: regions `CHK+196/+200`, padding `+0x11c`, DSP, and windows
`+0x16c/+0x174/+0x164`. No second full firmware snapshot is allocated.

Producer implements LK `0x27128..0x27260` exactly:

1. Attribute8 blocks count as padding candidates. Attribute4 padding sharing
   low-byte info with the following block gains attribute8; otherwise it gains
   attribute0x10 (excluded from region protection).
2. Only ONE preset row exists in this LK (`0x81918` lists slot40). If candidates
   exceed that count, mark only the largest eligible `(attributes&0x18)==8`
   block with0x10. Strict size comparison preserves the earliest equal-size
   candidate. If there is at most one, mark every attribute8 block with0x10.
3. For roles0..3, walk contiguous matching info masks excluding attribute0x10,
   as `0x274fc..0x27668`. First run maps to slots32/36/37/38; a subsequent run
   consumes preset slot40 with THAT role as preset argument. Any further run
   fails ENOSPC atomically, never disappears from the plan.

In the available actual B4.1 v6 footer there are four regions. The large
`+0x11c` padding window is inside region3. The resulting slot40 is active,
role/preset3, begins at `firmware.base + pad.offset + pad.size`, and ends at
the declared memory end. This is derived from signed fields, not hard-coded
physical addresses. Merely setting slots39/40 to zero is incorrect.

Marking a block0x10 reproduces protection planning, **not** LMB free authority.
This code never frees/clears/publishes that memory or changes MD power state.

ATF preset path `0x2f510..0x2f618` accepts only slot40 and presets0..3:

| Preset | AID35 | AID47 | AID93 |
| --- | --- | --- | --- |
| 0 | RO | RO | No |
| 1 | RW | RW | RW |
| 2 | RW | RO | RO |
| 3 | RO | RW | RW |

Preloader normal/AEE table row40 has no permission entries. That is **NOT**
proof that hardware permissions reset to zero. ATF preset6 ORs permission bits.
The new transaction reads real slot40 enable/policy first and rejects enabled
state or any baseline bits outside the fixed desired policy. Compatible subsets
are accepted and OR to the exact source-derived target. It calls real
`c2000415/6(40,preset,0)`, checks actual status, then existing range transaction
verifies ALL resulting permission words BEFORE range0. No blanket allow policy.

### Other complete rows and SMEM resources

LK `0x27390..0x274dc`: role4/slot33 takes first attribute2 DSP block (reject
attribute0x100 conflict), role5/slot34 first info-bit8 block, role6/slot35 first
attribute-bit6 block (the signed `+0x174` window). These are actual searches;
absent matches are recorded as absent, not manufactured from region count.

Reuse existing `tetris_modem_plan_smem_rom_b41()` for signed service sizes and
CCB gear. `0x22a3c` maps the whole NC bank to role10/slot42; `0x22fe8` maps
the whole cache bank to role9/slot43. `0x22a88/0x23030` select actual id22/bit6
CONSYS cache prefix for role8/slot41. The id22 row exists even with size zero;
that active-zero case is rejected, not silently omitted.

NC/cache bases MUST be 32 MiB aligned: LK `0x22608..0x22620` and
`0x22cc0..0x22cd8` reject others before bank remaps. Their actual windows must
cover the computed capacities, lie in owned DRAM and not overlap each other
or the FULL firmware LMB reservation, including its unused CHK/remap tail.
SIB must likewise not overlap that full reservation.
Existing boot-stage's single generic window is insufficient for
separately allocated stock SMEM/SIB; do not loosen checks to accept aliases.

## Consumed ATF slots and failure lifetime

Range0's guard (`0x10380`, byte per slot at ATF+0xf7a25) is consumed before the
range writer. Repeat returns -4 before a range write. Neither disabled enable
readback nor compatible policy implies an unused guard. Preset6 is NOT that
guard: it OR-writes permissions, so a later range0 may fail -4 after preset
changes. Record the first fault; no rollback/guard reset/retry is possible here.

The transaction preserves actual existing range-helper replies/steps for every
active slot and initial slot40 observation plus preset status. One attempt;
after failure/completion another call returns the latched error/EALREADY with
no SMC. Normal boot-stage caller MUST stop before remap/power/BROM on any error.
Its LK failure cleanup remains applicable only after its own MD MMIO writes;
an EMI-only failure does not grant power-off writes on unowned inherited state.

## Exact integration for main (frozen files not edited)

1. Inside existing authenticated snapshot/load lifetime, call
   `tetris_modem_emi_rows_b41()` with actual immutable ROM/DSP sizes, actual LMB
   firmware/NC/cache/SIB resources, real resolved option text and the checked
   preloader profile digest. Do not expose this plan through a CLI/DT override.
2. Use resulting typed rows to replace frozen bootstrap's caller-supplied
   `ranges[12]` and generic normal-policy loop. Call
   `tetris_modem_emi_rows_program(...,&tetris_modem_emi_rows_hw_ops,...)` ONCE
   as its EMI phase, after profile/strict-OFF preflight and BEFORE remap/lock.
   Do NOT pre-program this table and then run the old loop: that would consume
   the same slots twice. No extra permission/readiness/ownership flag is needed.
3. Carry actual row transactions, source-derived memory map and SMEM identities
   to the existing handoff owner. They are not firmware authentication or
   transport READY by themselves. The producer does not configure stock NC/
   cache bank remaps; those need the already source-traced separate bank owner.
4. Keep source-derived LK cleanup, primary/cleanup fault separation and all
   display/sensors/USB invariants. No activation before CI and explicit live gate.

This removes the concrete unsupported slot39/40-policy/producer gap; it does not
claim that the unchanged frozen bootstrap already consumes the new typed API.
Main owns that integration and shared CI. No new generic owners or fake AUTH.

## Verification

Local static checks only:

```sh
python3 patches/modem/drafts/emi-rows/check_emi_rows.py
```

CI after main's public manufacturer oracle has passed:

```sh
CI=true python3 patches/modem/drafts/emi-rows/check_emi_rows.py \
  --native-ci --uboot upstream/u-boot \
  --stock-container out/stock-modem/md1img.bin
```

Optional private matching LK comparison adds `--lk /CI/private/lk.img` and
`unicorn` to that job. It executes ACTUAL LK region/padding/table-setter code
against the actual C planner's initial map, compares all final block flags and
core rows32..40, skips only logging/dump calls, and aborts on any unexpected
instruction/write. No actual SMC/MMIO/power/allocator/phone execution.

20 sanitizer cases use actual stock footer, existing planners and production
producer/SIP adapter: optional PHY absent/zero/present, real preset3, policy/
profile mismatch, active-zero CONSYS, invalid resource/alignment/overlap/header,
enabled/foreign-policy/consumed slot40, preset failure/missing policy write,
range readback failure, first fault and no retry, and separate NC/cache overlap
with the unused 480..512MiB firmware reservation tail. Manufacturer authentication
is separately main's frozen signed-input oracle, never bypassed by this fixture.
Actual C/LK cases and AArch64 real-header compilation are pending main CI.
