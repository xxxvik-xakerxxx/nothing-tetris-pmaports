# B4.1 Bootstrap Clock And Board Field Constructor

`bootstrap_fields.c/h` constructs 50 concrete bytes of the authentic106-byte
layout from typed owner snapshots: payload4..9,30..61,94..105. It calls the
existing clock synthesis and preserves all other bytes when applied. It does
not assemble a complete request, query a device, call libMNL, acquire a session,
send firmware, or claim DSP WORKING. Native fixtures are supplied for CI only.

## Pins And Producer Semantics

Both complete ELF SHA256 pins are those in [CONTRACT.md](CONTRACT.md).
`test_bootstrap_fields_source.py` also pins full producer slices, the feature
dispatch table and its out-of-line branches. All addresses below are ELF VAs.

| Bytes/input | Exact source | Constructor behavior |
| --- | --- | --- |
| 4..5 |4f0e8c..4f0f8c, first+1c | Low byte0; high byte9/8/7/6/5/4/3/2/1 for4800/9600/14400/19200/38400/57600/230400/460800/921600. Other baud values, including115200, produce stock0, not an inferred mapping. |
| clock mode |4f20d0..4f2120 | Selector717cb3 in0..2 is retained, otherwise0. Bit2 is set when717cb6==1, or717cb6>=2 and first+24==1. This is not raw ioctl11. |
| effective frequency |4f0648..4f0684,5523c0..5524ac | FE mode requires both actual private record snapshots. Non-FE uses first+18. See details below. |
| 6..9,30..57 |4f2120..4f2138,4f05f4 | Existing exact clock synthesis, now fed the constructed mode/effective frequency. |
| 58..59 |4f2824..4f28b0,4f3000..4f3010 | Profile717cb6>=5 writes setting717cb7=27 and emits7. Otherwise use setting's low nibble;5 becomes7 if5211a4 is true. The exact unsigned chip mask overrides this to5, as does chipfffe6735. High byte0 is source-proven. |
| 60..61 |4f2094..4f20c8,4f28b4..4f28c0 | First+13==FE yields1, otherwise0; second byte is source-initialized0. |
| 94..97 |4f29b8..4f29f0 | Low16 of actual word7178b0, then configured first+30 chip ID. No ADIE substitution. |
| 98..99 |4f29e0..4f2a48 | Chipffff6771 uses low8 first+54 and8 below profile4, otherwise10. Chipffff6632 always emits48/49. Other chips emit48/49 below profile4, otherwise low8 first+54 and10. |
| 100..101 |4f2a4c..4f2a78 | Byte100 is1 only for profile4 and chipffff6725/ffff6761; otherwise0. Byte101 is source0. |
| 102 |4f2a7c..4f2aac,5211a4,5cc564 | Feature predicate gives3 or1. Add bit2 only when717cb8 bit6 is set and configured chip isffff6789. |
| 103..105 |4f2abc..4f2ad4 | Exact bytes00 4E 4F. |

The mask uses unsigned32 `chip+9a90 <=22` and the exact64-bit mask400050007.
Its matching configured IDs areffff6570/6571/6572/6580/6582/6592, not the
positive16-bit lookalikes. No chip is selected from a phone marketing name.
The effective717cb7 setting is returned separately because stock mutates that
global; the pure constructor cannot publish library state for its owner.

## Effective Clock Record Closure

GOT6e85c0 points to retained configuration8ca018. Getter6628c0 inspects its
eight-byte record at+1670;662820 uses the eight-byte record at+1668. Each
decodes four bytes with the pinned XOR/LCG recurrence and checks their sum
against the first LE32 word. On success it returns the **raw** second LE32,
not the decoded-byte concatenation. The implementation preserves that distinction.

In FE mode a valid frequency record wins, ignoring adjustment. A checksum-invalid
frequency record selects first+18, or the exact stock26000000 fallback if that
field is0. A valid adjustment record selects unsigned word modulo3:0 leaves
the base unchanged;1/2 add/subtract binary64 bits408c6fffffffffff, exactly
909.9999999999999, then apply AArch64's unsigned32 saturating truncation.
A finalUINT32_MAX is the helper's-1 sentinel and retains the original first+18.
Zero effective frequency is refused by the existing synthesis API.

This closes the decoder and frequency producer. It does not prove provisioning
of8ca018. NULL is refused in FE mode; it cannot stand for missing configuration
or justify26MHz. Only actual acquired checksum-invalid records establish the
stock fallback branch. Fixtures construct synthetic records from public numeric
words; no real private record, calibration, key or device data was inspected.

## Secondary Feature Predicate

508d0c branches to5211a4. That helper calls `__strlen_chk` on retained second
configuration75c99c+1ae, object bound0x296 (662 bytes), and requires length>4 plus secondary
GPS descriptor6edeec!=-1. The relocation at6e8c38 proves checked `strlen`,
not truncating `strnlen`. Short unterminated snapshots report missing input;
no NUL within662 bytes reports malformed input. Both preserve output.
52b9e0/52b9f4 copy second+14 into6edeec. An actual descriptor0 is valid for
this predicate; no descriptor is opened, duplicated or treated as ownership proof.

For selectorb2, table4ce055 entryb1 leads to5cc8e0, then5cc8f0 compares
first+30 with signed-0x9877 (ffff6789). This replaces an opaque feature query
with the pinned chip predicate, without a universal feature-success stub.

## Verification And Remaining Blockers

Run `test_bootstrap_fields_source.py PINNED_MNLD PINNED_LIBMNL` with
PYTHONDONTWRITEBYTECODE=1 and the existing Capstone5.0.6 directory on PYTHONPATH.
The test only decodes immutable instructions. `run-ci.sh` adds the independent
native fixture to the existing GitHub-Actions-only runner, with the same strict
warnings, floating-point flags and ASan/UBSan. No workflow is changed or launched.
New native compilation/execution is pending; prior wire/clock CI38315481513
does not validate this new constructor.

Local validation passed34 source tests (download8, wire9, clock8, fields9),
Python parsing, shell syntax and scoped whitespace checks. These are static
results; they do not claim native fixture or hardware execution.

Native fixtures cover all256 clock selectors against all256 profile selectors
and three first+24 values, every setting byte, mask/signed-chip branches,
feature flags and actual fd0/-1 predicate semantics, primary override priority,
checksum failure, modulo3, sentinel and saturating adjustment, name bounds,
exact offsets, unrelated-byte preservation and unchanged outputs on errors.
Their synthetic inputs are not board identity or a successful ROM session.

Precise remaining download blockers:

1. Acquire a legitimate complete first/retained context. mnld62bdc..62ce0
   selects profile9bc3c only when de22c==1; the52-byte NVM producer7b0d4..7b184
   and actual configured de304 identity cannot be replaced by absence/defaults.
   Preserve real ioctl11 errors; ioctl30 is a distinct PMIC selector contract.
2. Supply selectors at the actual consumer stage. Initialization52ea38..52ea80
   selects717cb6 via the50-entry table6ee1a8 and configured first+30.52ea94..52eadc
   derives717cb8/717cb7 from first+38 through PLT6e4b80, then717cb3 from717cb8.
   Later policy4fcb78..4fcc04 and chip branches4f0f90 onward can change717cb7,
   717cb8 and717cb3. Initial values alone cannot certify final snapshots.
3. Obtain actual8ca018 private clock records, retained second+1ae and the
   secondary descriptor owner, actual word7178b0 and first+54.52b6b4 initially
   clears7178b0, but its optional52ae60 route still prevents assuming universal0.
4. Assemble the remaining56 bytes from their traced constants/zero stores and
   one successful same-owner ioctl23/24 metadata query. The key stays private
   to that session. Prove MVCD/CW selection; neither ADIE nor ROM metadata
   proves it. The field applicator deliberately leaves these bytes untouched.
5. Implement the sole bounded gps0 TX/RX owner, complete frame reads and real
   sequence-matched ACK handling, integer ioctl25/26 fragment submission,
   first-fault preservation and deadlines. Stock ring waits/retries remain unsafe.
   Kernel MCUBbit0 RAM_CODE_READY and FSM WORKING must be observed separately
   before claiming download success, followed by the project GNSS lifecycle gates.

No phone access, local native build, DSO/firmware execution, commit, push or
workflow change is part of this constructor. Status remains Partial/Untested
for actual DSP startup and navigation.
