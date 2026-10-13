# Native Navigation Records And Encoders

Partial implementation, not a runnable sufficient navigation initializer or fix.
New scope only; frozen session API,1010 patch, image composers, existing output
workers and parent download runner are unchanged. No local C/native execution,
emulation, phone access, firmware writes, commit, push or CI dispatch.

## Actual C Interfaces

navigation.c/navigation.h implement pure native parsing/encoding; the two-file C
fixture is ready for parent CI. No vendor library is loaded or executed.

- b41_nav_packet_decode validates a complete primary AA/F0 physical frame,
  actual DE/DF and DE/E0 escaping, FE protocol,12-bit length and checksum. The
  high nibble is preserved, not promoted to a sequence or readiness selector.
 1014-byte payload capacity is a native bound; it is not a universal DSP maximum.
- b41_nav_epoch_accept consumes actual FE2C/66-byte begin, record packets and
  FE4C/10-byte end. It owns one absolute monotonic deadline, latches first errors,
  rejects truncated records, incomplete/repeated boundaries and source index
  overflows, and returns a typed epoch only after the end packet. It cannot be
  revived through epoch_init. Complete means grouping, not a solution or fix.
- FE41/32-byte and FE4D/47-byte fields are converted exactly as their source
  consumers; they have DIFFERENT halfword ordering. Other supported record types
  retain their actual bytes with source-derived lengths/index caps, not guessed
  units or default observations. Their physical semantics remain an explicit gap.
- b41_nav_post_init_reporting_encode encodes the established parameter42/subtype3
  reporting configuration: FE05 payload32 00 00 01 00. It does not emit or claim
  a new complete INIT sequence. This known step is included for composition with
  the new parser; the prior research is not recast as a newly discovered start.
- b41_nav_time_seed_build ages an actual supplied UTC sample with monotonic time,
  explicit GPS/UTC correction and supplied uncertainty. Manual human-approved UTC
  is accepted; no RTC/NTP task or clock query/setter is introduced. Adding full
  sample age to uncertainty is deliberately conservative native policy, not OEM
  private frequency correction or proof that the supplied time is accurate.
- b41_nav_time_message_encode creates the exact HOST message1016/232-byte payload/
  subtype8 used by mtk_gps_set_time. It is NOT an AA/F0 DSP time packet and must
  never be written to gpsdl. Its real consumer needs host algorithm state.
- b41_nav_host_position_decode parses the actual0xc60-byte host POSITION ABI,
  not a UART frame. It derives dimension2/3 or NOT_VALID from actual fields,
  checks finite/range coordinates, and checks civil time against GPS week/TOW/
  correction through libc gmtime_r. It does not generate a location, call a
  getter, authenticate its producer, or invent accuracy/NMEA. Invalid dimensions
  and quality0 never expose usable coordinates. The record is not present in a
  primary measurement packet merely because its checksum passed.
  Unknown quality values fail rather than becoming a generic nonzero success;
  source534cd4..534d00 also rejects field50>515 together with altitude>18270.
  No accuracy is derived from those output-admission bounds.

Only source-derived scalar packing and typed state are implemented. No generic
ready boolean, MNL FINAL snapshot resolver, whole-context substitution, private
calibration or caller-selected proof flag is added. Fixture coordinates are
synthetic conformance data, never a handset fix.

## New Source Closure

Exact current NOS assets, accepted before static decoding:

```text
libmnl.so  3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90
mnld       285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83
```

source_evidence.py pins whole assets plus nineteen immutable instruction/table
slices; addresses are ELF VAs, never addresses called at runtime. It reuses the
existing static PinnedImage/Capstone reader, not old Unicorn navigation tests.

Primary decoder554d3c routes FE packets to509830; secondary routes to50acc8.
The509830 copy table4c3f08 and dispatch tables4c3e36/4c4024 establish FE2C begin,
FE4C end and a SHARED record index. The source lengths/caps are2B46/11,3B14/12,
4132/11,4B47/15,4D47/20,5C113/17,91115/11. Native exact-length admission is
stricter than stock's min(payload,capacity) copy: no stale/short fields become data.

End504a24..80 reads byte0, word1, word5, byte9 from2fd0; each word is composed
as p0<<16 | p1<<24 | p2 | p3<<8. FE4D505250..5053fc composes a24-bit prefix
and ten such words starting at byte7. FE415040dc..5041d0 instead composes seven
words as p2<<24 | p3<<16 | p0<<8 | p1 starting at byte4. That distinction is
implemented and independently covered by the CI C fixtures. Units remain unnamed
where the retained instructions establish packing but not physical interpretation.

Position getter50e2bc clears0xc60 and writes header0x0c600000. Source50e4e0..50e50c
maps host grades to dimension at+19. Coordinates at+30/+38 are converted from
radians to degrees at50e744..764; output5351c0..535264 uses N/S then E/W.
The+10 halfword is rounded UTC correction, NOT a GPS week. +12/+14 are week/TOW;
68b094 computes week*604800+TOW-correction+315964800 before55391c/gmtime.
Source stores tm_year and tm_mon unadjusted; native decoding adds1900 and1.
The standalone decoder checks those fields coherently but cannot certify their
actual navigation producer or accuracy. Dimensional validity is not hardware PASS.

Time setter510aa4 creates232 zeroed payload bytes with subtype8 at+0, week+88,
binary64 TOW+90 and binary32 uncertainty+98, then queues header1016/length232.
Actual dispatcher5324d0 calls513080, which invokes host-time state5ba794.
No corresponding DSP wire packet has been proven. Public supplied UTC conversion
uses the source315964800000ms epoch and604800s week; no current leap value is
hard-coded. The actual library setter's residual return-1 is not a success token.

## Same-Fd Integration And Remaining INIT Boundary

Parent reports earlier real r188 ACK/WORK hardware progress. Separately, the
retained green CI38454201394 artifact is155112 bytes, SHA256
7500854c8bec407fed4135b301aaec8572929a39f4fae354e69661226033269f.
The new matched r189 snapshot module/image was still pending at that report;
the artifact is not promoted to a live run. These are supplied observations,
not tests repeated here, a fix or a clean lifecycle.

The existing sole GPS owner must retain the SAME exclusively opened gpsdl0 fd
through actual WORK, all protocol actions, continuous binary RX/output handling,
then frozen session FWSTOP ->real RST ->ioctl18 once ->real HW_STOP/SUSPENDED
before normal close. New code never opens, duplicates, reads, writes or closes
an fd; it adds no competing worker and cannot reuse the nominal ACK->close path.
Malformed/unsupported input or deadline failure must reach that owner's live
first-error recovery hold, not implicit close through process exit.

The seven packet forms are usable for bounded continuous classification and typed
epoch storage by that sole reader. The0xc60 position parser requires a real host
producer; it is NOT a measurement solver. No raw packet is cast to that record.
Do not log packet bytes, keys, calibration or private engine records; use only
allowlisted state/error/count observations under the parent's retention policy.

An existing sealed Bionic provider may supply the real host solver/output, but
ordinary mnl_run/mtk_gps_init is NOT a proven post-WORK attach: mnld63c40 calls
the run export and init52f19c calls52f264, whose52f2bc invokes the real dsp_init
export again on the configured branch. This could duplicate the completed
download. No global is zeroed, private boot flag invented or second GPS fd opened
to bypass it. A genuine host-only reuse/initialization route and its actual state,
remaining observation units and measurement-to-solver transformation still need
source closure. FE1C and FE05/41 from the older host-init trace are deliberately
not sent or packaged as a sufficient post-WORK sequence.

## Checks And CI Call Contract

Static locally, with Capstone5.0.6 available in PYTHONPATH:

```sh
python3 -B patches/gnss/native-navigation/source_evidence.py \
  --libmnl "$ASSETS/vendor/lib64/mt6878/libmnl.so" \
  --mnld "$ASSETS/vendor/bin/mnld"
```

Parent GitHub CI only; existing pinned assets, clang and Capstone required:

```sh
sh patches/gnss/native-navigation/run-ci.sh \
  "$ASSETS/vendor/lib64/mt6878/libmnl.so" "$ASSETS/vendor/bin/mnld"
```

The two native production/fixture sources are navigation.c + test_navigation.c,
linked with -lm, ASan/UBSan, strict conversion warnings and bounded20s execution.
The fixtures exercise actual C encoders/parsers with synthetic data, not a DSO,
hardware or boolean-ready mock. Optional arguments musl-gcc out/navigation-fixture
build a static AArch64 fixture after real musl-header and ELF checks; they do not
execute that target or create a GPS controller. Production linkage needs only
navigation.c and its header, plus the caller's existing sole stream/session owner.

Seven static tests pass; C fixtures have NOT been compiled/executed locally.
Full INIT, real position producer, native physical measurement/solver semantics,
fix/accuracy and complete lifecycle are not established by this deliverable.
