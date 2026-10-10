# Pinned B4.1 XML policy and SET tail

Status: concrete bounded diagnostic serializer; full causal XML operation NOT
closed. All files are new in this directory. No published sources, workflows,
phone actions, native local compilation or vendor INIT. No assets committed.

## Critical startup ordering

Pinned libMNL SHA256:
`3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`.
Pinned XML SHA256:
`7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31`.
Sources are the existing selected B4.1 stock artifact; no new extraction.

`4fc22c ->4fd044` precedes `4fc230 ->4fd20c`. The former reads GOT6e6660
(actual global7178b8), then memsets3f8 bytes at4fd06c before installing defaults
from config/capability consumers. A separate reapply path4fcaf8/4fcafc has the
same reset-before-reader order. **Applying the sidecar globals before this OEM
initializer would erase those writes.** The supported global constructors must
not be promoted to an init gate without association with the actual reset phase.

The policy producer4fd20c stores byte3 at4fd248, NOT a fabricated property.
It constructs paths from actual config406/424, compares file versions using
500910, and selects/copies the alternate path and policy7 when required at
4fd568..4fd5d0; then invokes reader4ff868 at4fd600. Exact default paths and
version arbitration now have a bounded source-validated model and separate
CI-only selector/scanner oracle in [XML_READ_PROFILE.md](XML_READ_PROFILE.md).
Actual runtime filesystem exposure, reader integration and optional XML writing
remain unimplemented; replacing the producer with a caller boolean would not
close its contract.

Reader500198 loads the feature config byte,5001a0 skips config0, then5001a8
tests bit0 of the actual policy byte before SET500378 ->4fd870. Bit2 separately
enables opening a write file at4ff938; failure clears that bit at4ff958..4ff960.
SET global writes happen BEFORE serialization4fe320. The native serializer does
not install policy3/7 or perform filesystem arbitration/mutations.

## Actual category5 bytes

Header at13e75: `XML:%s,v%.2f,Cfg`; settings use16711 `,%f` (six decimals) or
22932 `,%.0f`. The serializer reproduces the15 enabled stock consumer recipes:

| Features | w25 integer | w23 sparse | sp+c include counted |
| --- | --- | --- | --- |
| IFB, GGTO, GNSSPower |0|0|1|
| DCB |0|1|0|
| Other11 enabled features |1|0|1|

Rows are20x25 binary64, contiguous200-byte row strides. Remaining count decreases
only on emitted values. Counted entries include zero. DCB sparse entries emit
only abs(value)>1e-8 while remaining count is positive, removing its zero slots
but retaining the XML chip-selector values. Output contains both XML profiles;
it is NOT chip calibration selection (that already happened in global SET).
The beyond-count comparison uses >=1e-8; this draft refuses a nonzero beyond-
count emission before unsigned/signed-byte counter wrap, and refuses count>127.
Stock GET's zero padding and counts1..16 do not enter either refused path.

Checksum50c130 XORs the body starting `XML:`, **not the leading dollar** (unlike
the ADC diagnostic checksum). Final formatf988: `$%s*%02X\r\n`. Tail4fe458..4fe46c
dispatches kind1,length,category5,level0,pointer; length excludes the NUL. This is
text without ADC260/2 or AGPS envelopes. Output construction is all-or-nothing
with a1024-byte body limit and explicit overflow/nonfinite/layout refusal.
Compile-time assertions require exactly500 values to fit0xfc4 GET storage and
the complete framing/NUL to fit1030 bytes. Sparse counts need not equal emitted
settings: zero DCB slots consume no count. No invented final-count equality is
required. The signed-byte positive count limit is127, not the500 storage slots.

Category5/level0 bypasses ordinary log filtering at50c224..50c240, calls508cfc,
which branches to5243a0, identified by its embedded
`[mnl_sys_alps_nmea_output] MNL not running!` warning. That routine includes
actual FD/log/app output effects; it is NOT proof of GPS DSP command transport.
SET ignores output status, optionally fputs to its retained XML log and advances
a16-bit counter at4fe470..4fe4a0, then returns1 even without delivery evidence.
This draft intentionally provides no success-returning sink and no log-policy
defaults. Correctly serialized text is not an engine acknowledgment.

## Code and closure

`b41_xml_set_tail.c/h`: synchronous borrowed decoded input -> immutable value
message; no retained pointers, allocation, callbacks or external dispatch.
Requires exact-asset GET provenance from published `b41_xml_config_get`; accepts
only the stock enabled names/versions and validates finite fields. It does not
authenticate XML or establish mapped global/transport ownership. Formatting
requires owned C/POSIX numeric locale/decimal point and FE_TONEAREST; no locale
or fenv mutation is made by production code. Unsupported environment fails.

`test_b41_xml_set_tail.c`: pure vectors and transactional fault checks, including
integer/float/sparse output, checksum, overflow, bad version/config/count/NaN and
rounding, plus count127, last-slot refusal and unterminated names. Optional
decoded-feature input prints exact wire bytes for the oracle.
Synthetic fixture values are not calibration. No C compilation performed locally.

Native minimum staging: these C/H/test/runner files, plus unchanged published
`../b41_xml_config.h` in the same relative directory structure. No libxml2,
OpenSSL, native host/worker/association/CLI linkage is required for serialization.
The real caller still needs the published authenticated XML decoder.

```sh
CI=true sh "$DRAFT/run_xml_set_tail_ci.sh" "$NEW_OUT"
```

Linux CI compiler, GNU timeout, libm; ASAN/UBSAN/assertions enabled. API28 cross-
compilation can build the same two C files with the pinned NDK plus `-lm`;
do not execute an ARM fixture locally or claim ARM execution from cross-build.

`test_xml_policy_evidence.py`: independent full pins,25 exact instruction-slice
hashes, concrete call order, strings/epsilon, XML profile table and admission
checks. Python3+pyelftools only; no Capstone or Unicorn necessary:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 "$DRAFT/test_xml_policy_evidence.py" "$LIB" "$XML"
```

`test_b41_xml_set_tail_oracle.py`: separate Linux-CI-only bounded ARM64 SET
slice; reuses unchanged published test_b41_startup.py/test_b41_xml_producer.py
with their full pin checks, and this bundle's b41_xml_read_profile.py for
independent pre-iteration ELF admission. Whole ELF and XML pins plus exactly15
distinct enabled names are required BEFORE any emulator import or iteration;
a zero-feature/disabled replacement cannot falsely pass an empty oracle loop.
Captures actual w25/w23/sp+c recipes at4fe320,
executes actual loops/checksum, mocks bounded libc formatting/alloc/free and
intercepts output before any callback/FD/log action. Optional logging is disabled
ONLY in this oracle fixture, never as a production policy. All15 enabled entries
plus second DCB chip are compared byte-for-byte with the native fixture.
Python3+pyelftools+Unicorn, existing tracked oracle modules; no Capstone needed.
Hook lifetime is explicitly detached before Machine destruction. No Mac emulator
attempts. Libc formatting mocks cover only pinned fixed format strings and stock
finite values, not arbitrary OEM printf/truncation behavior.

```sh
CI=true PYTHONDONTWRITEBYTECODE=1 python3 "$DRAFT/test_b41_xml_set_tail_oracle.py" \
  "$LIB" "$XML" "$NEW_OUT/test_xml_set_tail"
```

Native and oracle are independent CI steps; no workflow edit in this bundle.
Next gate: native sanitizer fixture and pinned SET oracle both run in Linux CI,
then actual startup reset/file policy integration with owned output/log services.
First-config XML policy remains unresolved; no missing mask or INIT gate cleared.

Local checkpoint: offline evidence/admission tests6/6 PASS against the pinned
cached assets, including all25 slice hashes. Shell syntax and Python AST checks
pass. Native sanitizer execution and the Linux-only SET oracle have NOT run
locally; they remain explicit parent CI gates, not silently skipped successes.
Parent's atomic b41_xml_config_get_many may supply the same decoded feature
objects later. This draft neither duplicates bulk parsing nor edits that API.

## Eleven-file staging closure

Freeze all eleven files in this directory together: the serializer C/H, native
C fixture and runner; SET oracle and evidence tests; this README; read-profile
producer, offline tests, selector oracle and XML_READ_PROFILE.md. No new shared
header or workflow edits. Native serialization requires only the four native
files and published ../b41_xml_config.h; complete Python oracle staging also
requires published ../test_b41_startup.py and ../test_b41_xml_producer.py.
Pinned vendor inputs remain libmnl.so, mnld and MNL_Config.xml (no new assets).
Read-profile offline checks6/6 pass separately. Native sanitizer fixtures and
both Linux-only oracles remain parent CI gates, never local execution claims.
