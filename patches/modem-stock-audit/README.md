# Stock B4.1 LK modem producer and early-tag registry

Follow-up: [PRODUCER.md](PRODUCER.md) closes the actual modem descriptor and
suffix lookup, traces authentication order, and provides a tested native member
locator. It supersedes the fallback-table uncertainty and decoder next step below.

Offline static audit, 2026-09-11. Modem/SIM runtime: **Untested by this audit**.
No native modem implementation or runtime activation is delivered.

## Inputs and provenance

Input: `worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img`
relative to the workspace root. Independently checked local and Docker copies:

- Container: 5,353,472 bytes, SHA-256
  `29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f`.
- First payload: container offset `0x200`, 1,681,136 bytes, SHA-256
  `431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a`.
- First header: little-endian magic `0x58881688`, size `0x19a6f0`, name `lk`.
- Archive lineage as recorded in the existing GNSS research README:
  `Tetris_B4.1-260415-1709-image-firmware.7z`, SHA-256
  `2336875d0b1e7364f87690701706e0d8cd7149bcf8f05c6d295f6082cf949811`.
  The archive was not re-extracted or rehashed here. This is local B4.1-labeled
  hash provenance, **not signature validation**.
- The installed preserved `bl2_ext` (711,336 bytes, SHA prefix `17058309`)
  and stock B4.1 BL2 (1,384,080 bytes, SHA prefix `edf44835`) are different
  inputs according to the supplied evidence. Neither was analyzed here.

All offsets below are **first-payload file offsets**; add `0x200` for container
offsets. Linked pointers use `0xffff000050700000 + offset`, as independently
matched between pointer tables, strings and code. These are not live physical
addresses or portable allocation constants. Disassembly branch targets are
normalized to payload offsets; instruction windows are bounded, not whole-image
disassembly. Raw ADR/ADRP and branch scans cover only `[0, 0xa0000)` and report
candidates, not a complete CFG or proof of absence elsewhere.

## Early registry: high confidence

The table is `[0x199910, 0x199bf8)`: **31 records, 27 distinct tag IDs**.
Each 24-byte record is `<u32 tag, u32 zero padding, u64 callback, u64 name>`.
The GOT slots at `0x19a530` and `0x19a528` contain its start and exclusive end.
It is a bounded callback registry, **not a zero-terminated input tag stream**.

Dispatcher `0x16c00` proves use of this structure:

- `0x16c18/1c`: load the end/start pointers; `0x16c5c`: stride 24 bytes.
- `0x16c38/40`: form stock virtual input address `0xffff000048600000`.
- `0x16c44`, `0x16c7c`: read u32 size at +0, u32 tag ID at +4.
- `0x16c88`: advance the input pointer by the **byte size**, not size times four.
- `0x16c90`: stop scanning input on size zero.
- `0x16c50/54`: load callback at registry +8, `blr` with x0 pointing to
  the matched input header. Each registry entry searches from the first input
  tag, invokes the first matching tag, then advances to the next registry entry.

Duplicate IDs `0x20`, `0x1c`, `0x21`, `0x2b` each have two callbacks.
Deduplicating registry entries would discard real stock behavior. The full
mapping is in `evidence.json`. No CCCI/modem callback appears in this registry.
That does not exclude dependencies on general early memory/security state.

Example: registry `0x199a48`, ID `0x88610020`, callback `0x1bb70`, name
`boot_tag_emi_info`. At `0x1bb78..1bb9c`, the callback subtracts the 8-byte
header size, requires at least `0x98` bytes and copies `0x98` from input +8
to a global. Nominal valid total size is at least `0xa0`. Do not copy its
unchecked subtraction into native code: malformed sizes below eight must
be explicitly rejected, as must out-of-buffer sizes and pointer overflow.

The user's r153 observation (38 tags, masks `3b0c7fff` / `0026ff3b`) was not
re-measured. Its set contains IDs with no callback here:
`00 06 08 09 0a 0b 0c 0e 12 1b 25 28`. Unknown IDs therefore cannot alone
mean malformed input. These 38 incoming records and 31 callbacks are different
counts. Neither proves preservation of an LK-produced FDT or CCCI tag memory.

## Separate modem producer: high confidence on listed edges

`platform_load_modem` is identified at `0x25358` by its diagnostic string
reference `0x25500/04`, shared control flow and function prologue/return.
Direct calls to it occur at `0x84d8` and `0xecd4` (bounded scan).

| Call site | Destination | Observed role |
| --- | --- | --- |
| `0x2539c` | `0x27d9c` | `ccci_lk_tag_info_init`, checked for negative return |
| `0x253b0` | `0x25564` | Image-loading path, return checked at `0x253b8` |
| `0x256c4` | `0x74da0` | Partition/image names, destination and size passed in x0..x3 |
| `0x25468` | `0x27e70` | Insert `hdr_count`, four bytes |
| `0x2549c` | `0x27e70` | Insert `hdr_tbl_inf`, `0x18` bytes |

The fallback descriptor table at `0xe15e0` has 32-byte records for
`(1, md1img, md1rom)`, `(2, md1img, md1dsp)`, `(4, md1img, md1drdi)`, then
a zero record at `0xe1640`. The loader selects this fallback at `0x255e4`
only after other providers return null. It is not a universal partition map.

The `modem_a` reference is actual code at `0x7e168/16c`, in a branch testing
the suffix byte against `'a'` at `0x7e154/15c`. However, full alias registration,
slot selection and authentication are not proven by that window. Loader
`0x74da0` calls a name-resolution helper at `0x74e18 -> 0x2a3ac` before
partition lookup/read. **Do not replace `md1img` with hard-coded `modem_a`.**

## CCCI handoff layout: high confidence on bytes; partial semantics

Initializer `0x27d9c` calls `0x238fc` with `"ccci_tag_mem"`, size `0x10000`
and an out-address pointer at `0x27dcc`. Allocation failure returns -1.
The out-address is stored at state offset `0x1b6190` (runtime/BSS, not payload
data). Stores at `0x27de8..27dfc` initialize size/count/errors and set the
version field at state +`0x10` to **3**.

Appender `0x27e70` establishes a concrete record ABI:

| Record offset | Content |
| --- | --- |
| `0x00..0x3f` | NUL-terminated name, at most 63 characters copied |
| `0x40` | u32 data offset from buffer base: previous used size +`0x4c` |
| `0x44` | u32 data length |
| `0x48` | u32 next offset from buffer base |
| `0x4c` | Payload bytes |

Next offset is `(used + length + 0x53) & ~7`; code compares it against
`0x10000` and accepts strictly less. At `0x27f54` it copies bytes, then updates
used size and count at `0x27f68/70`. The stock arithmetic is 32-bit and the
limit branch is signed; a native implementation needs checked additions and
explicit extents instead of transplanting this routine. Zero length/null
arguments can return zero without inserting; return zero is not proof of a tag.

Separate DT callback pair at `0x19a098` is
`(0x280a0, "ccci_update_md_arg_info_to_dt")`; adjacent `0x19a088` names
`ccci_update_ap_md_smem_info_to_dt`. Callback invocation timing is not yet traced.
At `0x280d0` / `0x28100`, function `0x280a0` looks up `/mddriver`, falling
back to `/soc/mddriver`. At `0x28118` it transforms the stored base via
`0x67114` (address-translation interpretation, not fully traced). At
`0x28120..28138`, it passes `"ccci,modem_info_v2"`, state pointer and **0x30
bytes** to `0x5aa68`. That helper copies bytes without swapping at `0x5aabc`.

Independent consumer cross-check: exact device-modules commit
`ee2be53cb75670b548948636a0db1d1ff112bf12`,
`drivers/misc/mediatek/ccci_util/ccci_util_lib_fo.c`, `_ccci_lk_info_v2`,
`_ccci_tag_v2`, and `lk_info_parsing_v2`. The consumer memcpy's its 32-byte
summary prefix and reads version/count/size/base. This agrees with a raw
little-endian prefix, not generic big-endian FDT cells. The producer's extra
16 summary bytes and all required tag payload semantics remain to be audited.

## Next minimal native prerequisite

Implement/test a bounded **offline decoder** for the version-3 summary prefix
and 64-character CCCI tag records, taking an explicit owned byte buffer and
extent. Reject length/offset overflow, overlap, cycles, out-of-range next/data
offsets, count mismatch and unterminated names. Preserve unknown early tags;
do not synthesize CCCI readiness from the early registry or tag masks.

Before any native producer or Linux publication, establish the `md1img` alias
and authenticated active-slot path (`0x2a3ac` and its registration callers),
allocation/reservation lifetime, required tag semantics, and DT callback order.
Do not replay stock power/reset/SMC or image-loader code to discover these.
The reported missing FDT is consistent with the separation above but this audit
does not establish which boot stage lost it. No SIM or modem-running claim.

## Reproduce and limits

From the workspace root (Python 3; existing Docker container with Capstone 5.0.6):

```sh
python3 -B worktrees/nothing-tetris-scp-region/patches/modem-stock-audit/reproduce.py worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img
python3 -B worktrees/nothing-tetris-scp-region/patches/modem-stock-audit/test_audit.py
```

The first command writes only `evidence.json` beside these scripts. Docker
receives our analysis script as an argument, reads the existing image and
creates no files. No vendor instructions execute; no Unicorn is used.
Tests cover rejected/truncated identities, string bounds, absent/invalid
registry anchors, duplicate callbacks and signed ADR decoding.

Previous untracked SCP patch/test work was present initially and is preserved.
All audit additions are in this new folder; no phone, SSH, fastboot, power,
SMC, firmware execution, full build, CI or push was performed. Docker socket
access required a sandbox escalation for the reproduction runner; it passed.
