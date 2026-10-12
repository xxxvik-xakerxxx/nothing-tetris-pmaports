# B4.1 L1 Clock Producer

Implemented: `clock.c/h`, a pure translation of `4f05f4` for its observed
L1 `secondary=0` call, and the exact `574f04` rounding rule. No opaque libMNL
context is constructed or needed by this arithmetic. All inputs remain explicit;
this closes the math, **not the board/profile selection**. No phone, ioctl,
DSO execution, native local compilation, firmware write or CI dispatch occurred.

## Authoritative Inputs

Both B4.1 ELF hashes and complete relevant routines are checked by
`test_clock_source.py`. Kernel evidence is read from git object
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835, with `TETRIS_MODULES_TREE` override
available. There is no dependency on a mutable checkout's source contents.

| Input | Exact producer | Meaning and remaining boundary |
| --- | --- | --- |
| context+18 | mnld default branch `62cc4..62ce0`:26000000; profile branch `62c30/62c48`:9bc3c u32; flag81 overwrite `624dc..624f4`:52000000 | Frequency in Hz, but profile choice and later libMNL override must be respected |
| context+24 | default branch `62cd4`:0; profile branch `62c44/62c54`:9bc3c+9 | Profile byte, not ADIE-derived |
| context+30 | mnld `63358..63370`:de304 ->de550 (first block+30) | Configured chip/profile ID; **not ioctl11/30**, not the ADIE value |
| retained record | libMNL `52e718..52e73c`:112-byte first input copied into71f1d0 | Offsets are unchanged; no synthesized record required for the pure producer |
| clock modew28 | `4f20d0..4f2120`:global6e6668 mapped0..2, global6e6670 and context+24 control bit2 | Independently produced small mode, not raw co-clock flag0x21/0x51 |
| effective_hz | `4f0648..4f0684`:when context+13==FE, call5523c0, retain context frequency only if result is-1 | Pass the **post-override** frequency into `b41_mvcd_clock_synthesize` |

The default profile branch is selected when de22c!=1, not by the phone name.
de22c=1 is set at `7b184` after the stock52-byte profile-record read and string
test. Profile9bc3c cannot be replaced by synthetic values. The source of the
configured de304 ID remains outside the proved constructor slice; copying it
from stock is proved, choosing its value from MT6878/ADIE6631 is not.

### ioctl11 And ioctl30 Are Different Contracts

mnld `62290..62298` invokes ioctl11 with no output pointer. Kernel
`gps_dl_link_get_clock_flag ->gps_dl_hal_get_clock_flag` returns conninfra's
schematic mapping:26M COTMS=0x21,52M COTMS=0x51,26M EXTCXO=0. mnld's low-byte
dispatch sets first+13 FF orFE and only flag81 writes52000000 at first+18.
The full dispatch is pinned; negative return must not be masked into a profile.

mnld `632e8..63328` independently invokes ioctl30 and saves its return atsp+90.
It does **not** store that integer at first+18. B4.1 v051 enables the getter.
`gps_dl_clock_mng_get_platform_clock()` gets the actual parent regmap of
`mediatek,mt6685-gps`, reads DCXO_DIGCLK_ELR0x7f4 bit0 and returns0=26M or1=52M.
Missing regmap returns-1; pinned source ignores regmap_read failure. Any parent
error-propagation patch must retain the selector ABI. No compatibility alias,
fixed Hz substitution or fabricated clock provider is added here. A physical
query still requires proof of the real board's PMIC/provider identity.

### Stock Frequency Override

`5523c0` first calls6628c0, which validates a private configuration record
checksum before returning its frequency word. If unavailable, it uses
context+18 (or stock26000000 fallback when zero), then consults662820 for a
private adjustment selector. The latter is reduced modulo3 and can adjust the
frequency via the double constants constructed at552478..55249c, followed by
unsigned truncation. This input is **not** the ioctl30 PMIC selector. Its real
configuration/provisioning has not been recovered in this scope. No private
record value is read, printed, committed or included in fixture vectors.

Therefore a successful query11/30 alone cannot certify effective_hz for an FE
profile. The caller must establish the actual override or its legitimate absence,
then supply the resulting frequency. This is the concrete remaining gate.

## Exact Arithmetic Translation

The public result supplies payload offsets6..9 and30..57: parameter_a,
parameter_b and14 little-endian words. Existing wire codec inputs are unchanged.

- `574f04` computes floor/ceil signed64, converts their sum to binary64,
  halves it and selects floor only when the midpoint is greater than input.
  Exact ties select ceil, including negative half values. `round()` and
  ties-to-even are not equivalent. Nonfinite/overflow inputs are refused before
  changing output; all synthesis expressions fit the accepted range.
- parameter_a uses `(hz*0x91a2b3c5)>>47`, parameter_b
  `(hz*0x1b4e81b5)>>44`, with low16 output.16368000 has the exact288/426 special case.
- 16368000,26000000,40000000,12000000 and19200000 select the pinned halfword
  tables at27c0e/27c18. Selection compares **binary32** for26/40/19.2M but
  **integer** for16.368/12M. The coefficient selection is separately integer;
 26000001 and40000001 deliberately exercise this distinction.
- The unsigned32 range additions/comparisons select coefficients84/100/150/
 157/200/250/0 without changing the source's wrap or inclusive endpoints.
- Divider is integer1571328000/hz; fraction is nearest-up rounding of
  `(remainder*16777216.0)/hz`. Packed divider and output narrowing match the
  actual shifts, BFXIL and STRH, including wrap.
- Non-table timer calculations use separately rounded binary32 multiply and
  add, then binary64 division by1e11 and nearest-up rounding+15. The primary
  and companion constants have exact binary32 bits48b6e000 and489d8000.
- The two binary64 constants atA090/A7E0 have bits41905e353f7ced91 and
 41888d4fdf3b645a. They divide by the binary64 Hz/1e6 ratio and are rounded,
  stored high16 before low16; the first pair is repeated exactly.
- Final word uses `((hz*0x10624dd3)>>38)-1` with unsigned32 wrap and low16 output.

The `4f087c` conversion's return is discarded before the next conversion
at4f08a4; it contributes no serialized value. No code for its unused scalar
result is added. The function does not reproduce stock logging or library state.

The C implementation requires binary32/binary64, no excess evaluation precision,
no fast-math and FE_TONEAREST. It does not change the caller's rounding mode.
Volatile intermediates preserve each observed multiply/add/divide boundary;
CI uses `-frounding-math -ffp-contract=off`, ASan/UBSan and strict warnings.

## Fixture Boundary

`test_clock.c` has13 public arithmetic vectors spanning special tables,
non-table paths, binary32 boundary collisions,1Hz andUINT32_MAX truncation/wrap.
Each is exercised with eight explicit small mode values; these are numeric
vectors, not claims that every mode/frequency is a legitimate board profile.
It also checks positive/negative half ties, adjacent values, NaN/Inf/range errors,
zero frequency, invalid mode, wrong rounding mode and unchanged outputs on fault.
Expected vectors were calculated from the source formulas using independent
Python arithmetic with explicit binary32 packing; no vendor instructions or C
were executed. Native comparison is pending parent CI.

Run `test_clock_source.py PINNED_MNLD PINNED_LIBMNL` with the existing offline
Capstone directory on PYTHONPATH for immutable proof checks. `sh run-ci.sh`
now builds both wire and clock fixtures **only in GitHub Actions**.

Next input gate: actual first-profile selection, configured de304 ID, mode
selectors and final frequency override. Once those are closed, synthesize the
real fields and complete the remaining bootstrap bytes before a single parent-
owned guarded test. No firmware download or DSP WORKING claim follows from math
fixtures; MCUBbit0 remains required independently.
