# B4.1 MNL callback registration: static evidence

This is an ABI investigation, not a callable header or a tested GPS bridge.
Only the bounded ioctl veneer described below has been emulated, with every
external call intercepted. No vendor library was loaded or run on the phone.
Addresses are ELF virtual offsets for
these exact files only, not runtime physical addresses or universal constants.

- mnld SHA-256: 285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83
- libmnl SHA-256: 3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90

## Registration caller and storage

mnld at 0x61444 loads table address 0x88cb8 into x0; 0x61448 calls the
mtk_gps_sys_function_register PLT entry at 0x85900. It tests w0 afterwards.
The table contains 24 R_AARCH64_RELATIVE relocations. Reading raw file
words yielded zeros, as expected for RELA storage; relocation addends,
not raw pointer bytes, identify the callback targets.

The library's 480-byte registration function at 0x52f9d0 loads selected
8-byte slots through offset 0xb8 and stores them in global locations. It
does not copy the table address itself. The read set excludes offsets 0xa0
and 0xb0. The table storage is at least 0xc0 bytes, but this alone does not
prove a public structure definition, versioning or callback signatures.

It returns -1 for a null table. With a non-null table it performs global
stores BEFORE combining null checks for mandatory entries and returning.
Consequently a rejected registration is not transactional: do not test a
partial guessed table and assume failure leaves library state untouched.

## Relocation-derived slots

| Table offset | mnld target | Evidence-backed identification |
| --- | --- | --- |
| 0x00 | 0x5de00 | Event-code switch, w0 tested against 13; payload ABI unresolved |
| 0x08 | 0x7b240 | mtk_gps_sys_nmea_output_to_app, from referenced log-name string |
| 0x10 | 0x7b3f0 | mtk_gps_sys_nmea_output_to_mnld, from referenced log-name string |
| 0x18 | 0x7ba50 | Unresolved |
| 0x20 | 0x7bbc0 | Unresolved |
| 0x28 | 0x7b850 | Formats a PMTK command and calls the control callback; not a time getter |
| 0x30 | 0x5fa80 | A-GPS IPC dispatcher; low 16 bits of w0/w1 used, x2 holds data pointer |
| 0x38 | 0x5d910 | Immediate ret; return-value contract unresolved |
| 0x40 | 0x5d920 | Tail branch to 0x84c6c |
| 0x48 | 0x5d930 | Tail branch to 0x84d7c |
| 0x50 | 0x5d980 | mtk_gps_ofl_sys_rst_stpgps_req, logs and returns zero |
| 0x58 | 0x5d9c0 | mtk_gps_ofl_sys_submit_flp_data, logs and returns zero |
| 0x60 | 0x77ea0 | Unresolved |
| 0x68 | 0x5d940 | mtk_gps_ofl_sys_mnl_offload_callback, logs and returns zero |
| 0x70 | 0x52b70 | Unresolved |
| 0x78 | 0x60280 | Hardware suspend/resume bitmask callback; lifecycle details below |
| 0x80 | 0x60550 | Unresolved |
| 0x88 | 0x5ddd0 | Returns zero |
| 0x90 | 0x5dde0 | Returns zero |
| 0x98 | 0x5ddf0 | Returns zero |
| 0xa0 | 0x5dcc0 | Not read by this library registration function |
| 0xa8 | 0x846a0 | Unresolved |
| 0xb0 | 0x7c950 | Not read by this library registration function |
| 0xb8 | 0x5da00 | Reads doubles and a word from x0-backed data; semantic layout unresolved |

The NMEA callbacks preserve x0 as a byte-string pointer and w1 as a length
in their inspected paths. The app-output callback examines '$' and sentence
prefixes, and returns zero; it is gated by an mnld global flag. The mnld
callback feeds an internal parser at 0x684e0 with x0=buffer, w1=length,
w2=0. Buffer lifetime, length width/sign, validation, threading and complete
return semantics still need caller-side proof. These observations cannot
justify casting arbitrary functions to a guessed prototype.

The slot 0x30 callback references the literal log name
`mtk_gps_sys_agps_disaptcher_callback` at mnld VA 0x1729f (vendor spelling).
Inspected IDs 0, 1 and 7 call serializers at 0x39490, 0x39540 and 0x398d0,
respectively. Their leading little-endian u32 pairs are (1, 150), (1, 152)
and (1, 160). The transport helper at 0x380a0 uses AF_UNIX/SOCK_DGRAM and
sendto, not a GPS character-device write. Referenced socket names include
`/data/agps_supl/mnl_to_agps` and `mtk_mnl2agps`; destination-global
initialization is not yet traced. These IDs are A-GPS IPC, NOT DSP power
or firmware commands. Do not forward these messages to gpsdl.

## Bounded ioctl veneer verification

libmnl VA 0x52e3dc..0x52e480 is a 164-byte internal ioctl adapter:

- w0 low byte selects pointer mode 0 or scalar mode 1; other modes return 2.
- w1 low byte selects link 1 or 2, loading fd globals 0x6ee124 or 0x6edeec.
  Other links return 2 without an ioctl.
- w2 low byte is the request. Mode 0 forwards x4; mode 1 zero-extends w3.
- ioctl at PLT 0x6e5200 returning zero yields 0; any nonzero result yields 2.

`test-mnl-ioctl-veneer.py` pins the complete library SHA, extracts only that
code interval, and intercepts the ioctl PLT without issuing a host syscall.
All 450 combinations passed on Linux aarch64, Unicorn 2.1.4-r1,
Python 3.14.7, pyelftools 0.32: valid/invalid selectors, byte truncation,
scalar-versus-pointer arguments, success and nonzero errors. It checks
bounded execution, restored SP and unchanged fd globals. This tests the
adapter, NOT the kernel, device lifecycle, full library or GPS reception.

The macOS Unicorn 2.1.4 attempt exited 132 before executing vendor code.
A separate NOP-only setup also exited 132 after emulator construction and
before memory setup completed. Therefore that failure is a host-tool issue,
not evidence of a vendor-library failure; no cause beyond this is proven.

At libmnl 0x4f228c the boot-info call selects pointer mode, request 23/24,
and stack storage subsequently read as five u32 values. At 0x4f32d4 the
fragment-number call selects scalar mode and request 25/26. This matches
`gps_each_device.c` at modules commit
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835: 23/24 copy the 20-byte boot-info
structure, while 25/26 consume a scalar fragment number. It does not prove
the complete MVCD payload, acknowledgment or retry sequence. The inspected
boot-info path reads fields without an immediate error branch; do not infer
safe full-library error handling from the adapter test.

## Startup input extents

mnld at 0x63c34/0x63c3c passes x0=0xde520 and x1=0xde590 to
mtk_gps_mnl_run at 0x63c40. The exported library entry branches to 0x52b638.
Before its first memcpy call, that function copies seven 16-byte chunks
from x0 offsets 0x00..0x60 to global storage: a 0x70-byte readable input is
required. It then copies 0x444 bytes from the unchanged x1 to another global.
These are observed read extents, not complete public structure definitions.
The first block's word at offset 0x68 controls an additional startup call;
the second block has checks at offsets 0xcc/0xce/0xd0 against 0xce/6/0xaa55.
Field meanings, initialization and all nested pointers remain unresolved.
Do not call the entry with guessed zero-filled structures or treat callback
registration as sufficient initialization.

The first block's byte at 0x13 is populated by mnld's helper at 0x62280,
called with the GPS fd and block pointer at 0x632b4 or 0x632dc. Its referenced
name is `mnld_get_clock_type_from_ioctl`. It requests ioctl 11 with arg 0,
dispatches on the low byte of the return, writes Android property
`vendor.gps.clock.type`, then stores a mapped byte at 0x62534. Inspected
branches store 0xfe or 0xff; these are mapped values, not the raw ioctl
return or a complete clock enum. Negative ioctl results are truncated before
dispatch, so the future native bridge must not silently accept this fallback
as a successfully discovered hardware setting.

Pinned kernel `gps_each_device.c` defines 11 as GPSDL_IOC_CO_CLOCK_FLAG,
returning gps_dl_link_get_clock_flag(), then gps_dl_hal_get_clock_flag().
In `data_link/hal/gps_dl_power_ctrl.c`, gps_dl_hal_load_clock_flag() obtains
the clock schematic from conninfra and maps 26M COTMS, 52M COTMS and 26M
EXTCXO; the no-conninfra/default paths use a fallback. That source behavior
does not establish which clock path is active on the pmOS target.

The second block's four u16 values at 0xcc..0xd2 are explicitly initialized
by mnld at 0x639b8 from ELF literal 0x22b08: 0xce, 6, 0xaa55, 0x102.
This proves matching caller/callee bytes, not their semantic field names.

## Direct RX path and ABI constraints

Static inspection of the same hash establishes a non-NMEA receive path:

| Receive call | Source fd global | Requested bytes | Positive-data consumer |
| --- | --- | --- | --- |
| 0x525538 | 0x6ee124 | 512 | mtk_gps_data_input at call 0x52571c, or alternate helper 0x4f61c0 when the inspected mode flag is nonzero |
| 0x525be0 | 0x6edeec | 512 | mtk_gps_data_input2 at call 0x525cd8 |

These are the same two fd globals selected by the previously tested ioctl
veneer. Startup at 0x52b690..0x52b6a0 copies the second caller block into
the storage held by x19; 0x52b9e0 loads its u32 fields at offsets 0x10 and
0x14, then stores them in those globals at 0x52b9ec/0x52b9f4. This identifies
two fd fields in the 0x444-byte second block, not the whole startup ABI.
The later alternative fd-open paths and caller-side fd provenance still
need tracing before calling these fields usable device handles on pmOS.

The common read veneer is 0x508d14..0x508d48. It accepts fd in w0,
buffer in x1, low-u32 requested length in w2, and a result-u32 pointer in x3.
It calls __read_chk with object-size argument SIZE_MAX, stores the low u32
read result through the saved pointer, and returns -1 for signed low-u32
results below 1, zero otherwise. Thus EOF and read error share its status;
the stored result must also be inspected. Do not treat its return as a byte
count or turn EOF into a successful empty packet.

The first consumer is exported at 0x53cb28. The observed initial loop
feeds each input byte to 0x554f80, attempts frame extraction at 0x554da4,
then dispatches a completed frame through 0x53ccf4. Its optional third
argument is cleared initially and receives the input count at 0x53cbb8.
The second consumer is exported at 0x53cfa0; its parser is not yet audited.
No frame format, CRC, fragment reassembly or thread-safety guarantee is
inferred merely from these entry points. In particular, 512 is the caller's
read chunk size, not an established packet length or protocol maximum.

Separate offload loops use epoll and 2047-byte reads with indirect callbacks
(0x5284c4/0x5285a8, 0x528b4c/0x528ab4). Their referenced log strings name
mnl_thread_ofl_mcu2ap_proc_func and mnl_thread_ofl_mcu2ap_dbg_proc_func.
They are not evidence that this offload path replaces the two direct links
for the target's v051 transport. Another read at 0x52653c goes to
mtk_gps_nmea_input, but uses a different fd global; it must not be confused
with the direct driver receive paths above.

Import-table adaptation alone is insufficient: mtk_gps_data_input directly
reads TPIDR_EL0 and then offset 0x28 at 0x53cb48/0x53cb4c; startup does the
same at 0x52b654/0x52b658. Their return paths compare saved values and branch
to __stack_chk_fail. This is an inlined thread-local stack-guard ABI, not an
import a symbol shim can intercept. It strengthens the case for keeping a
matching Bionic runtime in a separate process, but neither that runtime nor
a loader/dependency closure has been validated. No full library code was
executed; this section is static disassembly evidence only.

## Caller fd ownership and optional queries

The matching mnld provides the two direct-link fields as follows:

| Caller operation | Result |
| --- | --- |
| 0x630dc..0x630ec | __open_2(path at mutable 0x88a80, flags 2); stores returned fd in 0x88798 |
| 0x64804..0x64814 | __open_2(path at mutable 0xde73e, flags 2); stores returned fd in 0x8879c |
| 0x63af4..0x63afc | copies 0x88798 to second startup block +0x10 (0xde5a0) |
| 0x63b00..0x63b14 | conditionally copies 0x8879c to second block +0x14 (0xde5a4) |

The conditional helper at 0x56ce0 returns whether the byte at 0xde2fe is
nonzero. The second open path also requires its configured path length to
be at least five bytes (0x6479c..0x647b0). These observations do not establish
the configuration field's semantic name or the target's runtime value.
The first path is empty in file-backed initial storage and the second is
in zero-fill storage: neither is a trustworthy hard-coded device filename.
The exact vendor factory init file grants gps ownership of /dev/stpgps and
/dev/stpgps2, but that alone does not prove the paths selected on this boot.

The first open path retries and the pre-open cleanup closes only fd >= 1
(0x630c8..0x630d8); second-link cleanup has the same boundary at 0x647f0.
These are observed vendor behavior, not recommended native lifecycle rules:
fd 0 is valid, and an adapter must track ownership and avoid treating a
failed open/retry as harmless device discovery. The pinned kernel's open
calls gps_each_link_open and release calls gps_each_link_close. Reopening
an already-open link returns EBUSY. Therefore testing open/close would be
a hardware transition, not a read-only metadata probe; none was performed.

mnld queries ioctl 11 through the clock helper, ioctl 30 with arg 0 at
0x632f0, and ioctl 10 with arg 0 at 0x6332c. The latter compares its result
with 1 rather than requiring success. There is a conditional ioctl 27 with
arg 0 at 0x63088 before the direct open/cleanup path.

At exact kernel commit e96f60dc081ae3525ef43d4bcf0ee5ee97e53835:

- 30 is GPSDL_IOC_GET_PLATFORM_CLOCK_FREQ; v051 explicitly enables
  GPS_DL_GET_PLATFORM_CLOCK_FREQ and returns gps_dl_clock_mng_get_platform_clock().
- 10 is named GPSDL_IOC_RTC_FLAG, but its switch case is inside #if 0.
- 27 is named GPSDL_IOC_GPS_CTRL_L5_LNA, but has no switch handler here.
- Unsupported commands fall through to -EFAULT, not necessarily ENOTTY.

Thus presence of an ioctl constant or a call in mnld is not a requirement
to implement that command, and these optional unsupported queries must not
be converted into mandatory readiness gates. The platform clock query is
different: its implementation and input clock provider must be preserved
and audited. This is source matching only, not evidence that the current
pmOS transport or clock provider is functional.

## Platform frequency query failure candidate

The pinned gps_dl_linux_clock_mng.c does not use clk_get_rate for ioctl 30.
Its child platform driver matches mediatek,mt6685-gps, obtains the parent's
regmap, and queries DCXO_DIGCLK_ELR (0x7f4). Bit 0 yields enum 1 for 52 MHz
and 0 for 26 MHz, not a result expressed in Hz. No parent map returns -1.
The original query ignores regmap_read's return and initializes value to 0:
a failed read which leaves the output untouched therefore falsely reports
the valid 26 MHz enum. Missing regmap in probe and failed driver registration
also currently return success; those separate lifecycle defects are not
changed by this narrowly scoped candidate.

`0001-clock-query-propagate-read-error.patch.vendor` propagates the actual
regmap error and uses unsigned int for the register value. Successful bit
decoding, the existing no-map return, device registration, hardware accesses
and enablement are unchanged. This research patch is NOT in APKBUILD, CI,
autoload or the installed image. It requires review of caller handling of
negative ioctl 30 results before deployment, rather than translating an
error into a guessed oscillator frequency.

`test-clock-query.py` extracts the exact pinned source, applies the patch
with zero fuzz and whitespace tolerance for its CRLF formatting, then
compiles the actual query against a recording fake regmap. Of 21 cases,
the original has exactly 15 failed error-propagation cases; the candidate
passes all 21. Tests cover absent map, successful bit decoding and three
read failures (-EIO, -ETIMEDOUT, -ENODEV). No hardware access occurs. This
does not prove device-tree parent wiring, regmap lifetime, the real frequency,
kernel compilation or GPS startup on the phone.

## Live parent-provider check

A fresh metadata-only SSH check on the installed r153 phone returned
kernel #154-postmarketos-mediatek-mt6878 and U-Boot
2026.07-rc1-g60bcf22fdc0a. usb0 was up before and after collection. Local
evidence is hardware-integration/local/gnss-clock-provider-r153.txt.

The existing MT6685 parent is bound to /sys/bus/spmi/drivers/mt6685 at
/soc@0/spmi@1cc04000/pmic@9. Its child mt6685-gps exists and has modalias
platform:mt6685-gps, but no bound driver. mt6685_core and mt6685_audclk are
loaded; no GPS module appeared in the module list. This confirms the parent
and child creation, NOT an actual readable register or GNSS clock value.
No debugfs register dump, device open, module load, power change or calibration
read was performed.

The exact device-module source ee2be53cb75670b548948636a0db1d1ff112bf12
creates mt6685-gps through the MT6685 MFD child table, after successful
devm_regmap_init_spmi_ext. The existing 0010 audio DT patch already describes
the parent. A duplicate GPS DT node is therefore not justified by the missing
binding. The GPS child driver is registered by gps_dl_clock_mng_init within
gps_dl_devices_init, after platform registration, not independently loaded.
That parent initialization path also creates character devices and can set
up DMA/IRQ/control state. Loading the entire transport solely to bind the
clock child would not be a metadata-only probe and has not been attempted.

The missing binding is expected while the GPS transport is absent; it is
not proof of a probe failure or the sole cause of nonfunctional GNSS. Next
hardware work still requires the transport lifecycle gates, followed by a
bounded clock query with explicit failure handling. Fixing registration error
propagation alone is also insufficient: callers currently ignore the clock
init result and the public devices-init wrapper discards its callee's result.
Any lifecycle change must audit cleanup/ownership end to end.

## Bounded receive framing evidence

`test-mnl-rx-framing.py` extracts only byte-handler 0x554f80..0x55523b
and its four-byte jump table at 0x4c60d0 from the pinned libmnl. The jump
table [0,32,7,25] resolves states 0..3 to 0x554fd4, 0x555054, 0x554ff0
and 0x555038. Synthetic GOT pointers target fake state and a 512-byte ring.
The test rejects every external execution, bounds each byte to 128
instructions, and verifies return, restored stack, all six state fields,
and the entire ring. No linker, constructor, driver or full parser runs.

All 2060 cases passed under Linux ARM64 Unicorn in the local container:
four states times every byte times write positions 0/511, plus end-marker
minimum-count boundaries. The observations establish these transitions:

- State 0 accepts ordinary data, defers AA to state 1 and DE to state 2.
- AA F0 starts a frame: stores both marker bytes, records its ring start,
  sets type 1/count 2, and returns to state 0.
- AA 0F ends a frame only after accumulated count >= 8: stores both bytes,
  sets the ready flag, and enters state 3. Shorter sequences do not set ready.
- DE DF decodes to AA; DE E0 decodes to DE. Both return to state 0.
- Unexpected escape followers enter state 3, except AA which restarts
  marker handling. State 3 discards non-AA bytes; AA starts resynchronization.
- Ring writes wrap modulo 512. Consecutive AA handling resets frame count;
  this is not equivalent to simply splitting input on two-byte markers.

These tests cover a single input byte with controlled initial state, not
arbitrary complete streams. They deliberately keep count below 512; the
external reset path at/above 512 is forbidden and untested. The extractor,
frame-length checks, checksum, command dispatch, link2 implementation and
MVCD protocol still require separate validation. Do not infer a maximum
wire packet size from the ring size or use this test as permission to send
frames. No GPS reception/fix is established.

## Bounded checksum evidence

`test-mnl-checksum.py` executes only 0x554c64..0x554d38 from the same
hash-pinned library. The helper takes an internal descriptor in x0 and an
output-byte pointer in x1, NOT an on-wire contiguous packet:

| Descriptor offset | Observed use |
| --- | --- |
| 0x02..0x03 | Little-endian u16; low 12 bits encode payload length + 4 |
| 0x04..0x05 | Two further header bytes included in the checksum |
| 0x06..0x0d | Unaligned 64-bit payload pointer |
| 0x0e..0x0f | Expected little-endian u16 checksum |

The helper sums descriptor bytes 2..5 plus (low12(length)-4) payload bytes,
then compares modulo 65536. The upper four bits of the length word do not
contribute to payload length but ARE included in the header-byte sum.
The first two descriptor bytes are not summed. This is additive checksum
verification, not a CRC. A valid computation returns zero even on mismatch;
the separate output byte is 1 for match, 0 for mismatch. A null descriptor
or null result pointer returns 1 without writing the output.

135 actual ARM64 cases pass: 11 payload lengths including empty, scalar/
SIMD boundaries and 4091; three upper-nibble patterns; two data patterns;
matching/flipped checksums; and three null-pointer combinations. Execution
is bounded to 8192 instructions, every external instruction is forbidden,
and input descriptor/payload preservation is checked. The synthetic maximum
length test validates this isolated helper, not the receiver's supported
packet size. A small-length field below 4 is not validated here and would
underflow the helper's subtraction: that guard must be established in its
caller before using it on untrusted packet data.

Static extractor instructions 0x554f20..0x554f2c require accumulated frame
length == low12(length)+6 and low12(length)>3 before returning success.
This is a promising upstream guard, but the exact descriptor construction
and checksum call path still need proof. No hardware frame was sent and no
complete packet decoder, command protocol or GNSS fix is yet validated.

## Multi-byte extraction and checksum boundary

`test-mnl-rx-stream.py` runs the actual byte handler and extractor together,
preserving synthetic state between calls. It maps only those code slices,
the real jump table, synthetic GOT/state/ring, stack and output. The logger
at 0x50965c is intercepted without executing it; every other external target
(including overflow/reset and command handling) is forbidden. Each call has
a 16384-instruction bound and a stack restoration check.

72 stream scenarios pass: initial ring positions 0/511; payload sizes
0/1/15/31/128/240 with AA/DE/00/FF data; both upper-length-nibble extremes;
leading noise, seven-byte chunk splits, repeated frames, declared length
off by one with subsequent recovery, incomplete final marker, and flipped
checksums. Valid extracted frames match the original decoded bytes exactly.
The low12 length=3 case is explicitly exercised by the empty-payload negative
length case and rejected. Logging is observed on invalid declared lengths.
This extends the prior single-byte test but does not exercise overflow/reset,
all possible malformed streams, or link2.

Importantly, corrupted checksums are accepted by this extraction stage.
Checksum validation is a separate later stage, not a condition of extractor
success. Static tracing clarifies the previously labeled dispatch helper:
0x53ccf4 obtains a queue context via 0x651e50, copies bounded bytes into its
ring, and calls 0x651fa4; it is not itself the checksum or command decoder.
The two observed checksum calls are at 0x6832dc and 0x683970. Both first
check the reconstructed descriptor's AA F0 and AA 0F markers, call 0x554c64,
and then inspect its separate result byte (0x68334c / 0x6839e0). The entire
queue-to-descriptor path, its length guards and downstream command dispatch
have not been executed in the test. That remains the next proof boundary;
do not bypass it by feeding extractor output directly to command handlers.

## Consumer length and descriptor guards

The first queued consumer at 0x682ef8 obtains a queued pointer via
0x51bca8, chooses a ring context, and requires at least ten available bytes
at 0x683018..0x683020. It initializes an 18-byte descriptor at sp+0x30 and
a 1018-byte payload buffer at sp+0x44. The payload pointer is installed at
descriptor+6 by 0x68303c..0x683040. Six incoming bytes populate descriptor
offsets 0..5 before the length helpers run.

`test-mnl-length-guards.py` checks every possible u16 field against both
actual ARM64 helpers (131072 calls total), with no external execution:

| Helper | Accepted low12 field | Return/output |
| --- | --- | --- |
| 0x554770 | 5..1018 inclusive | return 0, output byte 1; otherwise return 2, output 0 |
| 0x5547ac | 4..1022 inclusive | return 0, validity byte 1; otherwise return 2, validity 0; always writes u16(low12-4) when these test pointers are valid |

The upper nibble does not affect acceptance. Counts are 16224 and 16304
accepted u16 encodings respectively. Caller 0x68312c runs the first helper
and requires its success/output before 0x68316c runs the second. Therefore
this consumer's combined accepted payload length is 1..1014, not the isolated
checksum helper's 0..4091 range, and not the extractor's looser minimum.
The zero-payload frame accepted by the prior extraction test is rejected
at this later guard. These are isolated helper tests plus a static caller
trace, not an end-to-end concurrent queue test. Full ring availability and
consumer recovery behavior still need validation.

The consumer then copies the derived payload length from its ring, helper
0x5547ec points the write cursor at descriptor+0x0e, and four subsequent bytes
fill checksum+end marker. Both AA F0 and AA 0F are checked before checksum.
After checksum status/output success, 0x683384 calls 0x554d3c. That helper
requires command high byte FE, derives the payload length from low12-4 and
the upper nibble separately, and chooses 0x509830 or 0x50acc8 according to
its fourth argument's low byte. The first consumer supplies selector 1.
Neither command handler nor the command's semantics were executed or proven;
this is not authorization to replay any discovered command on hardware.

## Command-stage index, not startup semantics

`inspect-command-tables.py` emits `command-tables.json` from the exact
hash-pinned binary. It decodes three bounded u16-relative jump tables in
handler 0x509830: preprocessing (105 entries), copy selection (126), and
post-copy dispatch (126). Every resolved target must lie inside .text.
These are conditional stages in one handler, not 357 independent commands
or entry points safe to call. No command name or startup meaning is inferred.

The post-copy table maps FE28 to 0x50a128, FE2A to 0x50a168, FE31 to
0x509f98, and FE90 to 0x509f4c. The first two set byte flags at offsets 2
and 3 of storage referenced by GOT slot 0x6e66e8; FE90 sets offset 4 there.
FE31 updates different state and copies two u16 values from its intermediate
buffer. Their meanings and required preprocessing/copy state remain unknown.
The generated table agrees with these four individually traced targets;
that is a static consistency check, not handler execution or a boot handshake.

The earlier alternative RX helper 0x4f61c0 is not proven to be a separate
boot parser: its inspected body updates counters and conditionally forwards
the supplied bytes via __write_chk using another fd from runtime storage.
Calling it a MVCD decoder would be unsupported. The normal framed handler
has not yet been connected to a specific successful startup response.

LLVM dynamic/relocation inspection also identifies ANDROID_RELA (96 bytes)
and ANDROID_RELR (296 bytes) in this library. A scan limited to SHT_RELA
misses its GOT relative relocations; missing scan results do not mean those
slots are absolute/null. LLVM's expanded relocation output confirms sites
0x6e6588, 0x6e66e8 and 0x6e7858. Any future loader or address-resolution
tool must handle these formats; no loader implementation is claimed here.

## Resolved relative state references

`inspect-relr.py` now uses pyelftools' existing RelrRelocationTable decoder
against DT_ANDROID_RELR/RELRSZ/RELRENT. It checks the binary hash/ABI,
file-backed table/slots, entry alignment and duplicate offsets, then reads
the implicit addends. All 1505 expanded slots match LLVM readelf's independent
ordered expansion. The result is in relr-summary.json. This is an offline
relative-address inventory, not relocation of executable code; load bias
must still be added. Android packed RELA and PLT relocations are not decoded
by this script and it must not be used as a complete loader.

Relevant GOT slots resolve to image-relative state addresses:

| GOT slot | Relative target |
| --- | --- |
| 0x6e66e8 | 0x7181c8 |
| 0x6e6588 | 0x717d05 |
| 0x6e7858 | 0x6ee920 |
| 0x6e66c8 | 0x717cfe |

This resolves the previously anonymous state used by FE28/FE2A/FE90 to
0x7181c8+2/+3/+4. The same base is cleared for 14544 bytes at
0x4f3014..0x4f3024 in the function containing boot-info/fragment submission.
A separate request helper at 0x4f36d8 clears its byte 0, invokes 0x50bbe4,
waits for byte 0 while calling 0x554748, then reads u16 fields at +0xcfc and
+0xcfe. This is concrete state sharing with request logic, but not proof
that the three indexed responses release that particular wait: they write
different byte offsets. Command semantics and sender/response pairing remain
unresolved, and no request helper or polling loop has been executed.

## FE14 request-state completion

The command tables and actual branch instructions now connect FE14 to the
wait above. FE14 bypasses the preprocessing table (below 0x29), selects
0x50a620 in the copy table, and selects 0x509a68 after copying. The copy
destination is state 0x7181c8+0xcfc with a four-byte capacity. The common
copy path uses the smaller of capacity and supplied payload length. After
optional reporting, 0x509b14..0x509b20 sets byte 0 of that same state to 1.
This is the byte read by 0x4f370c, not the flags written by FE28/FE2A/FE90.

`test-mnl-fe14-response.py` executes the actual complete 0x509830 handler
with FE14, its two branch tables, synthetic state/GOT/TLS/stack, and the
optional reporting flag disabled. All external execution is forbidden and
each call is bounded to 512 instructions. Fifteen cases (three byte patterns,
lengths 0..4) confirm the exact state mutation, return value 1, unchanged
input and restored stack. Lengths 1..3 still set completion while leaving
the missing result bytes unchanged. The zero-length case probes the handler
contract only: the previously traced common queue rejects zero payloads.
Lengths 1..3 are not excluded by that generic length guard, although complete
transport delivery and any other producer-side constraints remain untested.
Therefore this completion flag alone is not evidence of a complete two-u16
response. A future bridge must validate the command-specific four-byte
result before accepting it; no live response, GPS readiness or fix is proven.

The request helper at 0x4f3698 also returns zero after its timeout without
writing the caller's outputs. It must not be treated as a reliable success
indicator without separately verifying response completion and result data.
Its 0x50bbe4 call serializes the variadic value 0x18 into two little-endian
bytes, then calls 0x50bd60 with arguments (8, 1, 2, payload). The wire command
construction beneath that call is resolved in the following section; the
meanings of the two result fields remain unresolved. Do not label FE14 a
general startup-ready acknowledgement.

## Request wire serialization

`test-mnl-request-wire.py` executes the actual variadic sender 0x50bbe4,
link selector 0x50bd60, descriptor builder 0x554ae8, serializer 0x554bd0 and
byte-stuffing helper 0x683b9c. The only intercepted calls obtain a synthetic
link-1 context, append bytes to a recording queue, or record the final flush.
All other external execution is rejected; each call has a 4096-instruction
limit. No device, worker thread, real queue or write syscall is involved.

With the primary-link restriction flag clear, arguments (8, 1, 1, 0x18)
produce exactly:

```text
aa f0 06 00 08 fe 18 00 24 01 aa 0f
```

The fields are start marker, little-endian length 6 (payload plus 4), command
FE08, little-endian parameter 0x18, additive checksum 0x0124, and end marker.
Five cases compare the full recorded stream against an independent byte
construction, including parameter bytes AA and DE. Inside the frame those
bytes become DE DF and DE E0 respectively; markers remain unescaped. Each
case emits exactly one flush and restores the stack.

Together with FE14 state writes this supplies a concrete candidate request
and response layout for the two-u16 query. It is not a chip-confirmed pairing:
the firmware meaning of parameter 0x18, startup ordering, restriction flag
lifecycle and successful hardware response are still unverified. Do not
send this test vector to a device merely because the serializer test passes.

## Query purpose: version reporting, not navigation readiness

Caller tracing narrows the purpose of the FE08/0x18 query. Four direct calls
to 0x4f3698 are present at 0x50f798, 0x531b98, 0x531c30 and 0x5337d8,
inside mtk_gps_get_param, mtk_gps_run and mtk_gps_main_flow. Their output
pointers use GOT slots 0x6e66f0 and 0x6e66f8. The observed output use is
version reporting, not position/fix data:

| Image-relative string address | Exact format |
| --- | --- |
| 0x19191 | `PMTK701,%04X,%04X,L1` |
| 0x10722 | `PMTK705,%s_%d.%d,%s,%s,%x,%x` |
| 0xea28 | `PMTKVER,%s_%d.%d,%s,%s,%x,%x,MNLfn_ver,%s,HAL_ver,%s,MNLD_ver,%s` |

These strings were read directly through the pinned ELF PT_LOAD mappings.
At 0x509a8c/0x509a94 the optional FE14 reporting branch reads state+0xcfc
and +0xcfe and supplies them to the PMTK701 formatter. At 0x50f7a8/0x50f7b0
the get_param caller reads the two query outputs and places them in the final
two hexadecimal fields of PMTK705. The run callers likewise use the outputs
in PMTKVER formatting. This supports naming it a two-word version-report
query; the individual words' exact firmware/hardware meanings are still
unknown. It does not establish that this query is mandatory before the
navigation engine starts, nor that its completion means satellites can be
received or a position obtained. The next startup investigation must trace
engine-start ordering separately rather than promote this query to a
general readiness handshake.

## Host engine worker selection

The startup worker factory is 0x52a424, not the similarly shaped event helper
0x5085ec. The latter calls mtk_gps_sys_event_create and records event IDs;
it must not be counted as spawning navigation threads. The factory's first
11 branch targets come from byte table 0x4c4a19 with base 0x52a478 and stride
4. Direct instruction tracing plus the existing RELR inventory resolves:

| Worker ID | Factory branch | Entry | Observed role |
| --- | --- | --- | --- |
| 0 | 0x52a478 | 0x5252d4 (GOT 0x6e78d0) | Contains the primary RX path traced above |
| 2 | 0x52a534 | 0x526bb0 (GOT 0x6e78f0) | Immediate null return in this build |
| 3 | 0x52a54c | 0x5260cc or 0x4f5588 | Engine entry or alternate mode |
| 5 | 0x52a4d4 | 0x526bb8 (GOT 0x6e78e0) | Separate worker, not mtk_gps_run entry |
| 8 | 0x52a50c | 0x525958 (GOT 0x6e78e8) | Contains the secondary RX path traced above |

For worker 3 the value pointed to by GOT 0x6e6d08 selects 0x5260cc when
zero and 0x4f5588 otherwise. Both entry pointers are themselves resolved
through RELR slots 0x6e7900 and 0x6e78f8. The factory passes these pointers
to pthread_create; the tested serializer does not exercise any of this.
Inside 0x5260cc, 0x5261c0 reads byte +0xc of the second startup structure
for mtk_gps_set_agps_machine. At 0x5261e8 it calls mtk_gps_run with the
callback loaded indirectly through GOT 0x6e67e0 and the first startup
structure through GOT 0x6e6710. Those are distinct from a version query.

The top-level startup creates worker 0 on the non-offload path at
0x52c124..0x52c128 and worker 3 at 0x52c3d4..0x52c3d8 on the corresponding
branch. Worker-creation failure selects startup return 9 for worker 0 or
7 for worker 3. This is static control-flow evidence, not successful thread
initialization or a safe shutdown proof. The next engine trace can start at
mtk_gps_run with this ownership map; do not invent a zero-filled startup
structure or conflate the worker-3 mode selector with first-structure +0x68.

## Engine initialization result chain

The primary engine worker calls mtk_gps_run(callback, startup). At
0x52fca4 it calls mtk_gps_system_init, then at 0x52fcb4 calls
mtk_gps_init(startup != NULL, 0, startup). Its accepted init result is
**18**, not zero: 0x52fcb8 compares against 0x12 and the matching branch
logs `MNLInit,L1 OK` (string 0x1aed8). Other results log
`MNLInit,L1 Status(%d)` (0x11975), call the supplied callback with w0=11
at 0x52fd08, and rejoin the subsequent run-loop setup rather than return
immediately. No null callback guard appears before this error invocation.
This callback must be implemented and observed; a worker remaining alive
does not prove initialization succeeded.

The deeper primary DSP path has three different return conventions:

1. 0x4f3634 routes link 1 to 0x4f0bdc. It preserves result 16 and maps
   other results to 20. Link 2 additionally requires helper 0x508d0c to
   return low byte 1; other link selectors produce 20.
2. 0x55471c rejects a null startup pointer with 1. Otherwise it calls
   0x4f3634 and maps 16 to 0, any other result to 2.
3. mtk_gps_dsp_init at 0x52f5ec sets the primary state through GOT
   0x6e6c50 to 1, calls 0x55471c with link 1 unless asynchronous state
   already equals 2, and maps a nonzero result to 17. Its normal completion
   path clears that state and returns 18.

mtk_gps_init reaches 0x52f264 at 0x52f19c. This helper calls
mtk_gps_dsp_init only when the first word of the structure through GOT
0x6e65b8 is nonzero; otherwise it takes an 18-result path without that
call. Thus even the accepted status is not independently proof of a DSP
transaction. The next unresolved causal step is 0x4f0bdc and the origin of
this first-word mode, not the already identified version query. These are
static instruction and embedded-string observations; none of these engine
functions has been executed on the phone or in a full userspace runtime.

## Deep-stop callback and initialization bypass

The beginning of 0x4f0bdc calls 0x4f0a18 with a link-derived mask and a
mode flag before building its initialization payload. A nonzero helper
result takes 0x4f0d94..0x4f0e04, updates state/counters, calls 0x4f0554,
and returns 16 without following the normal payload-construction branch.
The helper's embedded log at 0x1f1d1 explicitly names `DeepStopMode` and
`force_mvcd`; thus cold initialization and deep-stop recovery must not be
treated as an identical transaction.

Within that helper, 0x4f0ad8..0x4f0ae8 invokes the callback through GOT
0x6e65e8 with a bitmask in w0. Registration at 0x52facc..0x52fae0 copies
table slot +0x78 into this storage. That slot resolves to mnld 0x60280;
its embedded name at 0x1c87f is `mtk_gps_sys_do_hw_suspend_resume`.
This resolves a previously unknown callback using both binaries, rather
than inferring its role from the table offset.

The mnld callback uses helper 0x67bf0 with the primary fd and conditionally
the secondary fd when mask bit 4 is set and that fd is at least 1. Helper
modes map to: 0 -> ioctl 19 argument 0; 1 -> ioctl 18 with a boolean derived
from globals 0x88a04 and 0x88a0c; 2 -> ioctl 19 argument 2. The helper returns
1 for syscall result zero and 0 for failure/invalid mode. This is not the
return convention of the full outer callback, whose remaining IPC and
state paths still require tracing.

Pinned kernel source e96f60dc081ae3525ef43d4bcf0ee5ee97e53835,
connectivity/gps/data_link/linux/gps_each_device.c, independently confirms
18 as HW_SUSPEND and 19 as HW_RESUME. Suspend argument 1 requests clock
extension. Resume argument 2 selects the MVCD recovery path; the ioctl
explicitly converts an internal zero result to -EINVAL in that mode.
Therefore an EINVAL from this particular request is not sufficient evidence
of an unsupported ioctl or failed internal resume. Preserve the mode and
underlying state evidence when diagnosing it. No such operation was issued
to the phone; recovery sequencing, callback return semantics and safe
teardown remain unverified.

## Tested outer recovery callback results

`test-mnld-resume-callback.py` executes the actual mnld callback 0x60280,
helper 0x67bf0 and integer serializer 0x35410. Ioctl, logging, memset,
errno lookup and socket-sender calls are tightly bounded recording stubs;
all other external execution is forbidden, with 2048 instructions per case.
No actual syscall or IPC is performed. Eight cases verify ioctl order,
arguments, outer return, stack restoration, suspended-state clearing and
message bytes with primary fd 7, secondary fd -1 and factory modes disabled.

| Prior suspended flag | Mask | Stubbed ioctl results | Callback result | Control message |
| --- | --- | --- | --- | --- |
| 1 | 0 | resume(0): 0 or -22 | 0 | yes |
| 1 | 32 | resume(2): 0 | 0 | yes |
| 1 | 32 | resume(2): -22 | -1 | no |
| 0 | 0 | suspend(0): -22 | -1 | no |
| 0 | 0 | suspend(0): 0, resume(0): 0 or -22 | 0 | no |
| 0 | 32 | no ioctl | -1 | no |

The emitted message is exactly `07 00 00 00`, serialized at 0x60448 and
passed to 0x36b40 at 0x6045c. Its destination string at mnld 0x9c14 is
`mnld_gps_control_socket`; the sender uses an AF_UNIX datagram socket.
The receiver's action is not yet traced. Therefore replacing this callback
with a direct ioctl wrapper would omit internal coordination, while copying
its zero result as proof of hardware success would hide ordinary resume
failures. IPC-send failure is only logged in the inspected path and rejoins
the same result logic, but the test currently stubs a successful send only.
Secondary-link combinations and manufacturing modes remain untested.

## Control message 7: reset-listener teardown

The receiver of `mnld_gps_control_socket` is now connected to the emitted
message. Socket creation at 0x66c74..0x66c84 stores the fd at 0xdea50.
The event loop compares incoming fds against that storage at 0x662c8,
receives at 0x662fc, decodes the leading integer at 0x66314, and dispatches
through the ten-byte table at 0x2303a (base 0x66340, stride 4). Entry 7
is 0x664ac, which calls 0x67d40 and returns to the event loop. The embedded
name at 0x157bf is `gps_device_rst_listener_thread_exit_and_join`.

This helper sets stop storage 0xdea60 to 1. If the thread handle at 0x88d88
is not -1, it examines atomic completion storage 0xde4d0, signals the
thread with signal number 10 via pthread_kill while polling that storage,
then calls pthread_join at 0x67f28 and sets the handle to -1. The polling
loop is limited in its signal attempts, but the final join has no explicit
timeout: copying the loop alone does not establish bounded teardown.

The thread is created at 0x68238 with entry 0x67310, after successful
suspend helper results. That worker issues ioctl 20 on the primary fd at
0x6739c; this is GPSDL_IOC_GPS_LISTEN_RST_EVT. In the pinned data_link
gps_each_device.c implementation the case unconditionally returns -EINVAL.
Therefore this kernel variant does not provide the blocking reset-event
contract this Android worker was designed to consume. Message 7 is internal
listener cleanup, not a second DSP initialization request or a firmware ACK.
Porting must choose a real supported reset-notification mechanism (or
explicitly disable this unsupported listener path) rather than emulate a
fake reset event or mark GPS ready from this callback. No listener thread,
signal, join or reset ioctl was executed; these are static receiver/source
observations in addition to the earlier bounded sender test.

## Transport read failure candidate

Read-only runtime recheck during this audit found usb0 UP, kernel 6.18.0,
empty WWAN class, no gpsdl/ccci device nodes and unchanged modem handoff
`failure=no-fdt`, `observation-status=invalid`, `payload-status=not-checked`.
No runtime experiment or publication was performed.

The pinned data_link read path does not supply an alternative reset event:
gps_each_link_read loops on the RX DMA buffer and its read waitable, returning
data or errors such as ERESTARTSYS/EFAULT. Those errors alone cannot identify
a reset. Investigation also found a concrete failed-read ownership defect:
gdl_dma_buf_get acquires the reader, but a GDL_FAIL_NOSPACE from
gdl_dma_buf_entry_to_buf returns without releasing it. Subsequent reads can
then fail GDL_FAIL_BUSY even with a sufficient output buffer.

Candidate `0002-rx-release-failed-read.patch.vendor` uses the existing
gdl_dma_buf_set_data_entry(p_dma, NULL) abort operation on the copy-error
path. The pinned setter takes the DMA-buffer lock; its NULL branch clears
reader_working without advancing read/entry indexes or consuming the packet.
This avoids both the persistent busy flag and the packet-dropping workaround
mentioned in the vendor TODO. Successful reads are unchanged.

`test-rx-failed-read.py` applies the patch with zero fuzz to the exact source
pin. Its initial seven-case dependency-model test has been strengthened to
compile the actual get wrapper, acquire/commit functions and their inner
helpers, copy routine and original structure declarations. Only lock
primitives, DMA memcpy and logging are host substitutes. The 224 sequences
cover all 16 starting positions in a synthetic byte ring, both descriptor
indexes and seven undersized buffers followed by an adequate retry. They
verify failure status, unchanged output, preserved indexes/packet validity,
balanced lock calls, wrapped payload copying, a single commit, nodata flag
and an empty queue on the next read. Original: 224 failures; candidate:
0 failures. This is sequential real-code validation, not real DMA or
concurrent locking/reset validation. Full kernel
object build, concurrent ownership audit and live validation are pending.
The patch is not in APKBUILD and is not installed. It does not implement
partial reads or reset notifications and does not make GPS operational.

## RX candidate ARM64 object check

The corrected RX source also passed a targeted kernel object build. A fresh
archive of the pinned GPS/conninfra sources was extracted under container
/tmp/gps-rx-object, with the existing 1002 GNSS Linux-6.18 compatibility patch
and candidate 0002 applied with zero fuzz. No full driver/module was linked.
The command was:

```sh
make -C /kernel M=/tmp/gps-rx-object/connectivity/gps/data_link/plat/v051 \
  ARCH=arm64 LLVM=-21 CONFIG_MTK_GPS_SUPPORT=y \
  KCFLAGS=-Wno-error=missing-prototypes lib/gps_dl_dma_buf.o
clang-21 --target=aarch64-linux-gnu -c -x ir \
  /tmp/gps-rx-object/connectivity/gps/data_link/plat/v051/lib/gps_dl_dma_buf.o \
  -o /tmp/gps-rx-object/gps_dl_dma_buf.arm64.o
```

The first output is LLVM bitcode because this kernel configuration uses LTO;
the second step verifies code generation to an ARM aarch64 relocatable ELF.
Clang is 21.1.8, while the prepared kernel records 21.1.2. Three pre-existing
missing-prototype warnings concern gps_dma_buf_memcpy_from_rx,
gps_dma_buf_memcpy_to_tx and gps_dma_buf_memset_io. This targeted check is
not equivalent to CI, module linking, modpost, or live validation.

- Patched source SHA256: f53db31a3fe27fe68f620e49c2099d3cf432d0f58d90ab5d98248c2b34c5bcb4
- Bitcode SHA256: f7c581008f7bed0e3503d37ce0bca77799c935f660b8509653080e34df93bda9
- ARM64 ELF SHA256: 68a86646927042c6ac52e3b34eb1c61d7d4c110c7379db3f65d383d266bcf9c5

## Clock candidate ARM64 object check

Candidate 0001 was also applied to the same isolated tree containing the RX
candidate and the 1002 compatibility patch. The vendor clock file uses CRLF;
GNU patch rejected the LF candidate without applying either hunk. Converting
only the temporary patch copy with unix2dos and using patch --binary --fuzz=0
applied both hunks. Preserve this format requirement in any future packaging
step; do not silently relax fuzz or normalize unrelated vendor files.

The targeted kernel command from the RX check, with target
linux/gps_dl_linux_clock_mng.o, succeeded. Clang-21 --target=aarch64-linux-gnu
then generated an ELF object from its LTO bitcode. llvm-nm confirms the real
gps_dl_clock_mng_get_platform_clock function and its regmap_read dependency
are present, so this was not an empty/disabled configuration check. There is
one existing missing-prototype warning for gps_dl_clock_mng_get_regmap and
the same compiler-version difference recorded above. The host query test
was rerun: original 15 failures out of 21 cases; candidate zero failures.

- Patched CRLF source SHA256: 3e6948b704ddc113188c1b10d5d6d24922c4f4d5f85c77abc8efe859dd781acb
- Bitcode SHA256: 089f7eb6fb75750a5d7320a2d572e6d3e9ab6237dd21e2ee715f2f391dc5355e
- ARM64 ELF SHA256: 89ef188335dda1b935fa9e2f9b730be83ed13eae30f45ee6f273b42aaac1711c

Neither candidate is packaged, linked into an installed module or live-tested.
This check does not establish that the GNSS transport can be safely loaded.

## Platform-clock userspace error boundary

The pinned mnld calls ioctl 30 at 0x632f0, retains w0 in w19, and stores
that result at sp+0x90 at 0x63328. At 0x64610..0x64618 that same stack
slot is passed to mtk_gps_set_param with parameter 131. There is no
0/1 validation in these observed save/pass sequences. A negative kernel
errno returned through libc ioctl becomes -1 plus errno, not the original
negative number in this four-byte parameter. Do not treat the raw parameter
as Hz or silently map a failed query to either supported clock enum.

The parameter's libmnl branch at 0x510224 selects internal command 0x438;
the common path at 0x510368 copies four payload bytes into a queued message.
Its run-loop branch at 0x530ddc..0x530e2c stores message+4 through GOT
0x6e73a8 (RELR target 0x8a0fbc), logs the value twice and rejoins the loop.
No enum range check occurs in that branch.

test-mnl-clock-message.py executes these exact handler instructions with
the two logging calls intercepted and all other external execution rejected.
Nine inputs (0, 1, 2, -1, -5, -19, -110, INT_MAX, INT_MIN) all preserved
their raw 32-bit value in the state and both log calls. State canaries,
message immutability, stack position and restored x20 also passed. Values
other than -1 are robustness inputs, not claims about libc errno behavior.
This test does not run the queue producer, dispatcher, ioctl or hardware.

The other direct GOT-slot reference at 0x51ce5c is NOT a clock consumer:
0x51ce6c stores w21, initialized to -1 at 0x51c81c, during a larger state
initialization routine. The static search has not established a subsequent
hardware clock selection from this variable; indirect aliases remain
unresolved. Therefore the clock-query candidate prevents a false successful
kernel query but does not by itself establish a GNSS startup fix. Preserve
that distinction and investigate the cold-start transaction instead of
assuming this parameter is the cause of the missing GPS fix.

## Cold-start BINFO and fragment contract

The normal branch of 0x4f0bdc is identified by its own strings:
0x2283d is `BotUrV2,BINFO(): stage 0`, 0x13d83 reports a stage-1
boot-code hang, and 0xabc6 reports BootDSP finished. These strings were
read from the pinned ELF's PT_LOAD mappings. The early deep-stop path
described above still bypasses this normal transaction.

The transport mode is selected by byte 0x33e of the configuration at
RELR target 0x7178b8 (GOT 0x6e6660). Default initialization at
0x4fd178..0x4fd194 obtains it from feature 179 via 0x5cc564. The real
dispatch table at 0x4ce055 selects 0x5cc8fc for this feature; that branch
returns `((startup_word_at_0x28 & 0x0ffffff0) > 0x30f)`. This is not a
file-existence check and must not be inferred solely from the SoC name.
The config-update path at 0x4fcd50 preserves an override when config+8
bit 7 is set; 0x4ff314..0x4ff354 writes such an override. The specific
external configuration key and effective runtime value are not resolved.

test-mnl-mvcd-selection.py runs the exact feature dispatcher and predicate:
144 cases passed, covering the 0x30f/0x310 threshold, low-nibble masking,
and masked high bits. Configuration memory is checked unchanged. The test
does not run initialization or establish which mode this handset selects.

For a nonzero mode byte, 0x4f228c queries ioctl 23 or 24 into a zeroed
20-byte stack buffer. Selection is based on the separate byte reached via
GOT 0x6e6618, not simply the primary/secondary fd. The return is logged
at 0x4f2318 but no immediate abort precedes decoding the buffer. The
pinned kernel handler requires an open device and successful
gps_dl_hw_gps_get_bootup_info, returning -EFAULT otherwise. Thus a failed
query must not be represented as valid all-zero boot metadata in a bridge.
The working-tree gps_each_device.c was verified identical to pin
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835 before using these source facts.

Stage 1 builds 106 bytes at sp+0x6b0, beginning with little-endian 0x001a.
At 0x4f2ce4 the primary path calls 0x554828 with command 8, word count 53,
that buffer, and the link. The sender converts the word count to bytes
and forms FE08. Before sending, the primary pending mask (GOT 0x6e6678,
target 0x717cc0) has bit 15 set. The receive handler for FE31 copies into
the generic response buffer, then 0x509f98 clears bit 15 and places the
response's first u16 into the primary ACK slot (GOT 0x6e66d0, target
0x7178a0). The wait loop requires the pending bit to clear AND the ACK
number to match before incrementing its fragment index. A successful
write alone does not satisfy this condition.

Stage 2 uses pending bit 5. In the driver-assisted mode it calls ioctl
25 or 26 with a scalar fragment index minus one (0x4f32bc..0x4f32d4).
The other mode sends FE0C containing a u16 fragment index plus bytes
from the selected embedded image. FE32's handler at 0x50a228 clears
bit 5 and stores its u16 result in the same primary ACK slot. The loop
checks the ACK against the requested index before advancing. Stage-1
and stage-2 failure paths return 20; completion reaches the existing
return-16 success path. Neither ACK is a satellite fix or NMEA output.

Next identify the actual startup_word_at_0x28 producer and mode override,
then validate boot metadata and both ACK paths before attempting a real
startup. Do not replace driver-assisted fragment requests with synthetic
ACKs, select the embedded-image mode speculatively, or interpret offline
predicate tests as permission to open/power the transport.

## MT6878 capability provenance for the startup mode

The startup field is now traced to the chipset capability table rather
than an ioctl hardware-version query. mnld passes the pointer pair at
0x887a0 to mtk_gps_get_chipset_capability_v2 at 0x579ec. Its .rela.dyn
entries are R_AARCH64_RELATIVE (1027), with addends 0xde230 and 0xde2f0;
the on-disk pointer bytes are zero and must NOT be read as null pointers.
The first structure contains the chip/A-die matching input, and the second
receives the capability record.

libmnl 0x51b560 calls mtk_gps_match_chipset. Its ordered 25-entry table
is at 0x6edd50, resolved through GOT 0x6e6ff8. Each entry contains two
RELR pointers: a 192-byte matching record and a 208-byte capability record.
The matching routine checks chip ID, optionally A-die ID, and optionally
the pair of words at input+0xb8/+0xbc when nonzero. The selected capability
is copied to the caller and cached. Matching input provenance and any
external config override still need validation before real startup.

mnld 0x63358..0x63370 copies capability+0x14 to startup+0x30 and
capability+0x18 to startup+0x28. Later 0x63484..0x634bc may OR the latter
with one of 0x80000000, 0x40000000, or 0xc0000000 (table 0x2323c).
All these flags are masked out by feature 179's 0x0ffffff0 predicate.

inspect-chipset-capabilities.py uses the pinned hash, ELF load bounds and
decoded RELR slots, and produces chipset-capabilities.json. All 25 entries
were decoded. The three MT6878 entries are:

| Index | Match / capability address | A-die ID | capability+0x14 | capability+0x18 |
| --- | --- | --- | --- | --- |
| 21 | 0x6ed710 / 0x6ed7d0 | 0x6631 | 0xffff6878 | 0x370 |
| 22 | 0x6ed8a0 / 0x6ed960 | 0x6637 | 0xffff6878 | 0x370 |
| 23 | 0x6eda30 / 0x6edaf0 | 0x6686 | 0xffff6878 | 0x370 |

Consequently all three matching MT6878 records default to feature 179 = 1,
including after the observed mnld OR operation. This establishes the
default driver-assisted MVCD path for those records, not the effective
running configuration or the A-die identity of this handset. The next
causal investigation should follow kernel boot-info/fragment handling and
its secure-world dependencies, not assume the embedded-image transfer is
the normal MT6878 path. No calibration data is in this inventory.

## Primary boot acknowledgement prototype

`mnl_boot_ack.py` implements an offline boundary for already-unescaped frame
bodies and the primary-link boot acknowledgement sequence. It verifies the
low-12-bit length and byte-sum checksum before interpreting FE31 (10-byte
payload) or FE32 (2-byte payload). A submitted BINFO request expects FE31
index 0; subsequent fragment requests expect FE32 indices 1 through the
reported fragment count. The driver ioctl argument is the expected index
minus one. This module neither opens the device nor submits a command.

`test-mnl-boot-response.py` executed the actual pinned handler at
0x509830..0x50acc8 and its dispatch tables in Unicorn. All 80 cases passed:
both commands, indices 0/1/106/256/65535, and payload lengths from zero to
one beyond each handler's capacity. Complete response indices match the
prototype. Whole synthetic state buffers and pending/ACK words were checked,
not only the handler return value. The oversized-input logger is explicitly
replaced by a return instruction; all other external execution is forbidden.
No upstream frame validation, startup wait loop or hardware is exercised.

The vendor handlers copy at most their capacity but signal completion even
for short payloads: FE31 clears pending bit 15 and reads the index from
generic state +0x231; FE32 clears bit 5 and reads large state +0xd00.
Thus a short response can reuse bytes from a previous response. The prototype
deliberately rejects both short and oversized payloads. This is a conservative
experimental boundary, not proof that future firmware cannot extend an ACK.

The five `test_boot_ack.py` unit tests cover complete synthetic exchanges
(1, 106 and 256 fragments), mismatches, unsolicited responses, corruption,
payload sizes and submission guards. The state must be discarded on
timeout/reset/close along with transport receive state: the protocol has no
transaction identifier that can distinguish a delayed identical ACK. Its
COMPLETE state means only that expected acknowledgements were received,
not that navigation is running or a position fix exists.

The remaining prerequisite for a controlled write-side probe is a verified
BINFO constructor and receive transport. BINFO is 106 bytes, not just the
20-byte boot-info ioctl result. At 0x4f2654..0x4f2ad4 the vendor constructs
subcommand 0x1a, copies boot metadata and additional startup fields, and
sets capability-dependent fields. Those inputs must be traced rather than
zero-filled or copied from one handset. No new prototype was installed on
the phone and no boot fragment was submitted during this verification.

## Full BINFO construction capture

`test-mnl-binfo-construction.py` now executes the pinned cold-start constructor
from 0x4f0bdc and stops at its first 0x554828 sender entry. This crosses the
real MT6878 selection, clock-parameter construction (0x4f05f4), rounding
(0x574f04), oscillator fallback (0x5523c0) and BINFO assembly instructions.
The captured call is command 8, 53 words, primary link 1: 106 payload bytes.
No sender, ioctl, firmware transfer, SMC or navigation code executes.

Explicit synthetic inputs/limitations:

- The startup structure uses clock flag 0xfe, frequency 26 or 52 million,
  configurable baud, capability word 0x370 and chipset word 0xffff6878.
- Driver-assisted mode is explicitly enabled and the boot-info selector is
  zero (ioctl 23). Other global data starts from the ELF load image/BSS,
  **not** from a completed mnld initialization or a phone memory dump.
- The cold-path decision returns zero. Baud changes, logging, absent second
  link and time are intercepted. Optional oscillator adjustment queries
  return unavailable; the real constructor then uses its fallback.
- The ioctl returns five deliberately synthetic words
  0x1234/0x5678/0x9abc/0xdef0/106. No handset cipher or calibration is used.
- Bounded memcpy/memset are emulated. Execution outside the four explicit
  constructor/helper ranges and named test doubles raises an error.

All 33 captures passed. Differential checks modify every one of the
20 boot-info bytes independently and check the entire resulting message.
The first BINFO copies the low 16 bits of each 32-bit ioctl word into
payload offsets 14, 16, 18, 20 and 22. It does not include their high halves;
this does not establish later fragment-loop semantics for those high bits.
Baud mapping affects only payload byte 5 in these captures:
4800/9600/14400/19200/38400/57600/115200/230400/460800/921600 map to
9/8/7/6/5/4/0/3/2/1. An unsupported 12345 maps to zero in the vendor,
which is not a reason for a new client to silently accept unsupported input.

Additional traced payload ownership:

| Payload offset | Source |
| --- | --- |
| 0..1 | constant subcommand 0x1a |
| 2..3 | initial request index zero |
| 4..5 | encoded startup baud |
| 6..9 | two 16-bit outputs of clock constructor 0x4f05f4 |
| 14..23 | low halves of the five ioctl words |
| 26..29 | constant 0x00050000, little endian |
| 30..57 | 28-byte calculated clock parameters from stack+0x750 |
| 58..59 | capability/transport-dependent selector |
| 60..61 | whether startup clock flag equals 0xfe, then zero |
| 62..93 | first 32 bytes of selected oscillator table output |
| 94..95 | low 16 bits of global through GOT 0x6e6688 |
| 96..97 | low 16 bits of startup chipset word |
| 98..102 | chipset/transport/feature-dependent fields |
| 103..105 | bytes 0x00, 0x4e, 0x4f |

The oscillator table comes from file address 0x27934, copied as 720 bytes
at 0x4f2154 and selected/converted at 0x4f35e8..0x4f362c. The synthetic
captures are a reproducible reference for a future constructor, not a
literal packet to replay on the handset. Before a live BINFO submission,
resolve the effective runtime globals (notably GOT 0x6e6668/0x6e6670,
0x6e6650/0x6e6658/0x6e6688), optional oscillator-query state and the
remaining startup flags, then implement bounded receive/ACK handling.

### Initialization of mode globals before construction

The capture harness additionally executes 0x52ea50..0x52eae0 from the actual
mtk_gps_init sequence. It starts with table index zero, the startup chipset
word and the table pointer through GOT 0x6e7b00. It executes feature dispatch
0x5cc564 and resolves the known get_gnss_mode_config PLT entry to its actual
implementation at 0x5ccaa0, instead of inventing those functions' returns.
This is still an isolated slice, not full mtk_gps_init execution.

For startup chipset 0xffff6878 the table selects class **5**, stored through
GOT 0x6e6670 (target 0x717cb6). The mode comes from startup+0x38. The real
mode conversion writes flags through 0x6e6658 (0x717cb8) and a selector
through 0x6e6650 (0x717cb7); the initializer derives
`(flags >> 1) & 2` through 0x6e6668 (0x717cb3).

| Input mode | Flags | Selector before BINFO |
| --- | --- | --- |
| 0 | 3 | 3 |
| 1 | 49 | 6 |
| 2 | 51 | 7 |
| 3 | 1 | 5 |
| 4 | 48 | 23 |
| 5 | 2 | 3 |
| 6 | 63 | 23 |
| 7 | 13 | 3 |
| 8 | 15 | 3 |
| 9 | 12 | 3 |
| 10 | 63 | 23 |
| 11 | 62 | 23 |

All 12 initialized-mode captures reach the first BINFO sender. Together
with the previous cases the test now passes 45 captures. Entire messages
are compared: relative to the synthetic zero-global 26 MHz baseline,
payload byte 38 becomes `(flags >> 1) & 2`, byte 58 becomes 7, and bytes
98..99 become 0 and 10 for startup+0x54 = 0. The latter two bytes in the
uninitialized baseline were 0x48/0x49. Thus the earlier zero-global packet
is demonstrably **not** the initialized MT6878 packet.

The BINFO constructor itself overwrites the selector with 0x27 for class
>= 5 at 0x4f283c..0x4f2848 and emits selector 7. Do not confuse the selector
before construction with its subsequent global value. The remaining
startup+0x38/+0x54 provenance and later mode/config overrides still need
tracing in mnld/libmnl. Global 0x7178b0 is cleared at 0x52b6b4, but whether
later initialization changes it remains unproven. No runtime configuration
or hardware state has been inferred from these synthetic tests.

### Caller provenance for startup mode and legacy LNA field

The pinned mnld supplies startup+0x54 at 0x6344c..0x63498:
it calls ioctl 16 with `&stack[0x94]`, logs a negative return, then copies
the stack word to 0xde574 (0xde520 + 0x54) on either return path.
At 0x62bcc the earlier `stp w9, wzr, [sp, #0x90]` initializes that word
to zero. In the exact GPS source revision
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835,
`connectivity/gps/data_link/linux/gps_each_device.c` defines command 16 as
`GPSDL_IOC_GET_GPS_LNA_PIN`, but places its handler inside `#if 0`.
The enabled switch therefore returns -EFAULT without writing the output.
This establishes the stock caller's zero fallback for this source version,
not an actual GPIO number or a reason to change the live pin configuration.
In the class-5 construction traced above, payload byte 98 is the low byte
of this startup word and byte 99 is 10. No additional hardware query is
needed merely to reproduce this unsupported-query fallback.

Startup+0x38 has a different origin: at 0x634c0..0x6350c mnld initializes
0x88e10 from 0x88c20 only when the former is -1, initializes 0x88e14 from
that result only when it is -1, then copies the latter to 0xde558.
At 0x63510..0x63528 a return of 1 from helper 0x62a20 overrides the startup
mode to 4. The helper passes the `BD_PRIORITY` parameter record to
mtk_gps_get_MNL_Config_XML_param, first with directory `/data/vendor/gps/`
and, if unavailable, `/vendor/etc/`. These names were decoded via the
pinned ELF's PT_LOAD mappings (0x23214, 0x11b27, 0x20e4a), not guessed.
The helper checks the returned record byte at +0x1c for value 1.

Thus mode 0 in earlier synthetic tests is not yet an established stock
default. Resolve the source/default of 0x88c20 and the two -1 sentinels,
plus the applicable configuration path, before selecting the effective
mode for a Linux startup client. The ioctl-16 fallback and the configurable
GNSS mode are separate facts; neither requires obtaining handset NVRAM.

### Capability-derived default mode

The on-disk mnld words at 0x88c20, 0x88e10 and 0x88e14 are respectively
2, -1 and -1. However **2 is not the MT6878 capability-derived default**:
at 0x57c0c mnld calls 0x61300, whose instructions load capability output
0xde2f0 + 8 and replace 0x88c20 with that word. This precedes the startup
mode selection described above. `inspect-chipset-capabilities.py` now
includes `default_gnss_mode` from capability+8 in all 25 decoded records.

| MT6878 A-die | Capability address | Default mode |
| --- | --- | --- |
| 6631 | 0x6ed7d0 | 6 |
| 6637 | 0x6ed960 | 10 |
| 6686 | 0x6edaf0 | 10 |

The generated inventory was checked for 25 entries and these exact three
mode values. Mode 6 is the capability default for the A-die 6631 identified
in the earlier r153 live probe, absent caller/config overrides. The existing
actual-constructor tests include both 6 and 10: both produce flags 63,
pre-construction selector 23 and derived clock flag 2 for the primary
BINFO. This agreement does not make the modes interchangeable for the
rest of initialization (especially optional secondary-link decisions).

The -1 fields also have dynamic writers through mnld 0x73ce0/0x73a40;
therefore record the selected runtime mode explicitly rather than treating
the capability default as immutable. No per-device calibration is used
to derive these values, and no new on-device operation was performed.

### Bounded boot receive framing

`mnl_boot_wire.py` adds transport-independent framing to the ACK prototype:
AA F0 / AA 0F delimiters, DE DF / DE E0 escapes, incremental chunk handling
and a 508-byte unescaped-body bound (512-byte vendor ring minus delimiters).
Each input chunk is limited to 512 bytes. This conservative boot-only bound
is not a claim about maximum navigation message size or a driver read fix.
Malformed escapes, nested delimiters, short bodies and overflow make the
decoder permanently failed. Its caller must discard both decoder and boot
exchange on any error/timeout/reset/close, not automatically resume or retry.
Unframed leading noise is ignored; extracted bodies still pass through
`decode_boot_ack` for length, checksum and command validation.

The encoder matches the earlier actual-vendor FE08 version request vector
`aaf0060008fe18002401aa0f`. Six framing tests and five ACK tests pass,
including every split of an escaped FE31 frame, byte-at-a-time delivery of
the BINFO ACK and 106 fragment ACKs, concatenated frames, truncated frames
and terminal malformed-input handling. This synthetic complete exchange
does not establish DSP readiness. These modules have no device I/O and
were not installed on the phone; a bounded device-operation owner and
verified final BINFO inputs remain necessary before the write-side probe.

### Auxiliary BINFO word and unsupported ioctl 29

The remaining direct writer of the word through GOT 0x6e6688 is in the
startup-input routine: 0x52bb14..0x52bb2c calls ioctl 29 using the primary
fd at 0x6ee124 and an output pointer to stack+0x18, then copies that buffer
to the global. The routine zeroes stack+0x18..0x1f at 0x52b66c and clears
the global at 0x52b6b4. It does not store the ioctl return code in BINFO.

In gps_each_device.c at the pinned GPS revision, command 29 has no enabled
case and falls through to -EFAULT without writing an output buffer. The
disabled EAP/SAP time-sync definition is not an implemented query. Thus
the stock unsupported-query path retains zero for BINFO bytes 94..95;
this is not missing per-handset calibration. This statement is restricted
to the traced initialization path and pinned driver, not arbitrary future
drivers or external memory writes.

`test-mnl-legacy-query.py` executes 0x52bb14..0x52bb30 with an intercepted
ioctl. All five combinations passed: failure/success without a buffer
write, two successful synthetic output values, and failure with a synthetic
write. The latter confirms that the vendor copies the output regardless
of the return code. No actual ioctl or device operation is performed.

### Native single-BINFO probe (not installed)

`binfo-probe.c` is a separate experimental executable, not part of the
device package or boot service. It requires the explicit
`--experimental-binfo-only` option and a reviewed 106-byte template whose
metadata positions are zero. The caller must verify the template's
provenance, effective settings and hardware profile; structural checks
alone do not establish those facts.

The intended operation is: open primary link, require co-clock flag 0x21
and platform-clock enum 0, obtain fresh boot metadata, validate its bounds,
replace template metadata, issue exactly one FE08 BINFO write, receive a
checksum-valid FE31 index-zero acknowledgement, and close. It never calls
fragment ioctls 25/26 or starts another attempt. Reception is bounded to
512-byte reads, 508-byte frame bodies and 4096 bytes per attempt; SIGALRM
terminates userspace after eight seconds but cannot recover a kernel stuck
in an uninterruptible operation. Partial writes, malformed frames and wrong
FE31 indices fail without retry. Neither payloads nor cipher keys are logged.

Both executable and native framing tests compile for ARM64 Alpine with
`-std=c11 -O2 -Wall -Wextra -Werror`. The container initially lacked
linux/types.h; installing linux-headers resolved that build prerequisite.
`test-binfo-probe.c` checks valid FE31, a checksum-valid wrong index,
single-byte corruption, 256 BINFO payload patterns including escaping,
and terminal overflow. These are parser/encoder tests, **not** complete
open/ioctl/write/read/close fault-injection coverage. The I/O path has not
run on the handset. A reviewed template, additional I/O failure testing
and continuous live kernel-log capture remain prerequisites to execution.

### Native I/O fault injection

`test-binfo-io.c` includes the real probe main with only the filesystem,
device I/O and alarm calls substituted. It passes 20 scenarios: successful
whole/bytewise ACK, invalid/unavailable template, unexpected node type,
device-open failure, clock mismatch, boot-metadata errors/range violation,
short write, read error/EOF, corrupt ACK, checksum-valid wrong index,
close failure, sustained noise and receive-budget overflow. It asserts
single open/write, no fragment commands, no reads after a short write,
and one close for every successfully opened device. Synthetic metadata
must appear in the transmitted frame, replacing the template zeros.

The overflow regression first failed: after 4000 bytes of noise, a valid
ACK in a 512-byte chunk was accepted beyond the 4096-byte budget. The
probe now rejects that entire chunk before parsing it. Kernel reads stay
512 bytes to avoid the known small-buffer vendor RX issue: up to one
additional read chunk can be fetched, but no bytes from an over-budget
chunk are accepted. Error reporting now identifies the failed stage and
reports close failure separately rather than printing stale errno values
for protocol validation failures.

These tests do not exercise actual SIGALRM delivery, uninterruptible kernel
waits, DMA, driver teardown or a live ACK. No probe has been installed or
run on the phone. Template selection/review and continuous log capture are
still required before the single-BINFO hardware experiment.

### First live single-BINFO result

The native probe was subsequently run once on r153 with template SHA256
213d50947ae1c80977872dcb38522366dc26eb0328e8e3dc2162b4e5eb69a6e2 and
executable SHA256 dac1ef53afb64abd7f5d0c312f1229ee981494027a778449f5d25f0598fad76b.
The template generator uses the pinned constructor, initialized mode 6,
26 MHz and zero metadata; ioctl23 supplies fresh metadata on the same open
link. The program received a valid FE31 index-zero response and exited zero.
Kernel history records a 20-byte read. No fragment ioctl was called.

However teardown failed its evidence gate: at monotonic 4092.509 the driver
reported off-done=0 after 200 polls, l1 ret=-1 and forced A-die power-off.
Software state subsequently reached CLOSED and USB/SSH survived. A clean
reboot was performed before any further experiment; new boot ID is
3334a5ab-4658-4310-b07e-77b6fcaf0fa1, USB/SSH recovered and GNSS service is
inactive. The integration worktree's local/gnss-r153-live/binfo-only-plan.md
and binfo-only-kernel.log contain the detailed record. Thus earlier sections
labelled not-installed/not-run describe the preceding test stages, not the
current history. Firmware boot/navigation/fix remain unproven.

### Partial-download shutdown and staged fragment probe

The off-done code was compared against GPS source pin
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835. The relevant function is unchanged
(the working source only removes two unrelated dump wrappers at file end).
`gps_dsp_state_is_dump_needed_for_reset_done()` selects the diagnostic when
the preceding state was TURNED_ON and TX DMA has run. In
`gps_dl_hw_gps_dsp_is_off_done()`, that flag remains true throughout the
200-poll loop, and the function returns false. Thus this particular close
failure is consistent with deliberately stopping in partial-download state;
it is not evidence of a missing acknowledgement or a reason to suppress
the driver's error. The FSM separately requires RAM_CODE_READY to move
RESET_DONE -> WORKING. No such transition was established by the FE31 test.

The pinned libmnl success edge 0x4f34f0 -> 0x4f0d94 does not itself request
hardware deep-stop. It increments a counter, calls 0x508d0c (a trampoline
to 0x5211a4, which checks a bounded string length and a global descriptor),
updates userspace flags, calls 0x4f0554 for clock-related bookkeeping, and
returns 16. This corrects the earlier tentative interpretation of that
edge as a deep-stop operation. It is not yet a full navigation lifecycle
trace or proof that close immediately after the final FE32 is safe.

`binfo-probe.c --experimental-download` now stages the primary-link sequence:
one BINFO, FE31 index zero, then scalar ioctl25(index-1) followed by an exact,
checksum-valid FE32 index for each fragment from fresh ioctl23 metadata.
Only counts 1..256 are accepted. There are no retries, secondary-link
requests, firmware payload copies, raw SMC calls or navigation commands.
The original BINFO-only mode remains available for reproducibility, but
must not be repeated on hardware with the known incomplete shutdown path.
Both modes reject a duplicate acknowledgement or partial trailing frame
within a read before advancing; other well-formed non-boot frames are ignored.
The 4096-byte receive budget resets per expected acknowledgement; the
eight-second process alarm still covers the whole operation. A hung kernel
operation is not bounded by that userspace alarm.

The new mode is compiled but NOT copied to or executed on the handset.
`test-binfo-io.c` passes 29 substituted-I/O scenarios, including complete
1/106/256-fragment exchanges, bytewise escaped responses, fragment ioctl
failure, incorrect index/checksum, EOF, duplicate BINFO and partial trailing
frame rejection. Each failure prevents subsequent fragment submission.
The existing framing test also passes; both tests and the standalone probe
compile with `-std=c11 -O2 -Wall -Wextra -Werror` in the ARM64 container.

A read-only handset check still reports boot
3334a5ab-4658-4310-b07e-77b6fcaf0fa1, USB/SSH healthy, GNSS transport inactive
and no gpsdl device nodes. No module was loaded during this work. Before
the next live write, resolve the post-download readiness/close ordering and
record a bounded full-download test with continuous kernel capture and
clean-reboot recovery on any teardown failure. A full FE32 sequence alone
must not be advertised as firmware running, coordinates, or working GPS.

### Close ownership trace: do not execute the staged download yet

Further source tracing rejects the assumption that ordinary close requests
a running DSP to stop. `gps_each_link_close_or_suspend_inner()` changes link
state and ownership flags; the outer function queues LINK_CLOSE. The normal
event path disables writes, stops DMA, masks IRQs and clears active state
through `gps_dl_link_pre_off_setting()`. POWER_OFF then calls the DSP-off
poll described above, before disabling USRT and applying power controls.
These paths do not supply a userspace protocol stop request. The relevant
normal-close code matches the GPS source pin; differences in the working
power-control file concern separate deep-stop dump hooks, not this path.

The vendor application does more than close: mnld 0x680e0 calls
`mtk_gps_mnl_stop` at 0x68128 when its initialized flag is set, then tears
down listeners and finally closes device descriptors (primary at the
0x683bc path, secondary at 0x683ec). Its suspend branch instead uses helper
0x67bf0; this is not an interchangeable shutdown operation.

In the pinned libmnl, `mtk_gps_mnl_stop` at 0x52e2c0 conditionally performs
an offload stop exchange when configuration +0x68 is nonzero, then always
tail-calls 0x52c524. That cleanup clears a mode bit and calls 0x52c9b0,
which iterates 17 thread records at 0x6edef0 (stride 32). Their initial
stop callback is 0x529f18, their wake callback 0x529418. The former dispatches
per-thread stop flags/wakeup operations; the latter writes one byte to a
thread wake descriptor. The exported `mtk_gps_uninit` at 0x52f86c is just
RET in this binary, so its name does not establish a DSP shutdown command.
No complete device-stop protocol has yet been derived from these callbacks.

Next: trace the actual DSP-owner stop transition rather than copying the
whole Android cleanup or assuming that `close()` performs it. The staged
download executable remains an offline candidate. No new module load,
firmware submission, reset or handset filesystem modification was made
during this trace. In particular, a successful final FE32 must not trigger
a hardware test that assumes immediate close is safe without resolving
this remaining lifecycle dependency.

### Stop-message dispatch resolved, hardware contract still open

A subsequent exact-table trace identifies a missing part of the cleanup:
thread record ID 3 dispatches through the table at 0x4c4a08 to 0x52a094,
clears a userspace flag and calls mtk_gps_set_param(0, NULL). Thread ID 5,
not ID 3, selects the separate stop-flag/queue-wakeup branch at 0x529fdc.
Do not infer thread IDs from the lexical order of switch destinations.

In the non-offload path, set_param's table at 0x4c447e maps command 0 to
0x51036c with w24=1001 and w25=0. It allocates a six-byte message, writes
type 1001 and payload length zero, then passes it through 0x508d90. The
wrapper either frees it when its bypass flag is set or forwards to 0x651030.
Thus scheduling and mode flags matter; reaching set_param is not delivery.

The run-loop table at 0x4c4cf2 maps message 1001 to 0x5328b0. That branch
calls the existing sender at 0x50bbe4 with arguments (5, 3, 1, 4), before
freeing the message and leaving the loop. The sender uses command FE05,
one 16-bit argument 4, and link mask 3: bit 0 selects the primary queue;
bit 1 selects the secondary only when 0x508d0c reports it available. This
is a traced vendor stop-path request, not a reason to send to an unopened
secondary link or to assume boot-ROM/incomplete-download acceptance.

New test-mnl-stop-dispatch.py checks the pinned hash and executes the real
bounded dispatch instructions and callback prefix in ARM64 Unicorn. It
passes thread IDs 3/5, the actual set_param(0,NULL) arguments and flag clear,
message-1001 selection and final sender arguments. The sender and all
external calls are execution endpoints, not permitted I/O. Queue delivery,
full thread cleanup, firmware acceptance, RAM_CODE_READY, RESET_DONE and
safe close are not tested. No phone command follows this offline result.

Next trace the stop request's firmware-visible completion and prerequisite
state, including whether it is valid only after full RAM-code startup.
Keep the staged full-download probe disabled until that boundary and USB
recovery after the separate bootloader diagnostic are resolved.

### Primary stop delivery and retry hazards

`test-mnl-request-wire.py` now also runs sender(5,1,1,4) through the actual
serializer. Its primary-link stop packet is exactly
`aa f0 06 00 05 fe 04 00 0d 01 aa 0f`. This is the FE05 command with one
little-endian u16 value 4, not an ASCII PMTK sentence or a firmware ACK.
All six serializer cases pass; the recording queue still replaces actual I/O.

The actual registration at 0x4fb464..0x4fb474 gives context 1 the callback
from GOT 0x6e6960, whose RELR-backed word is 0x53d9fc. Helper 0x651e14
stores it at context+0x10, the slot invoked by sender 0x50becc. Its second
callback is 0x53db94 (RET). The primary flush at 0x53d9fc examines a mode
word, the context+0x28 blocked flag, queue cursors and context identity.
For an active primary queue it calls 0x508d00 -> 0x524d3c. That writer
uses fd global 0x6ee124 and 0x508d4c -> __write_chk; successful full
delivery returns zero to the flush, allowing cursor advancement.

New `test-mnl-stop-flush.py` executes these real flush/writer/write-veneer
instructions with only context-identity and syscall endpoints substituted.
Nine scenarios pass: full and short write, mode>=5 discard, blocked queue,
empty queue, context zero, repeated zero/error writes and invalid fd. The
test deliberately terminates retrying paths; it issues no host write/sleep.
The buffer and return stack are checked on completed paths. It does not
execute registration, the real ring allocator, scheduling or the driver.

Important negative evidence: zero-length writes loop with sleep(0), errors
return through a 10 ms sleep into an outer retry, and fd=-1 can repeatedly
re-enter the writer without any syscall. No whole-operation bound was
observed in these paths. Do not copy these retries or run the opaque library
as a shortcut. A successful sender return also does not prove delivery when
mode/blocked/context guards discard or defer queued data.

The matching kernel FSM distinguishes ROM RESET_DONE from RAM-code WORKING.
Only RAM_CODE_READY moves RESET_DONE -> WORKING; a later RESET_DONE moves
WORKING -> RESET_DONE for restart/power-off. The close check rejects the
initial TURNED_ON -> RESET_DONE history after any TX, explaining why the
BINFO-only exchange is not a valid shutdown sequence. Therefore the next
full-download experiment must observe actual RAM_CODE_READY/WORKING before
attempting this runtime stop, then require a fresh RESET_DONE and clean
close with USB/SSH intact. FE32 completion alone is insufficient. No proof
yet connects FE05 to that firmware event on this handset, and no boot-ROM
or partial-download stop support is claimed. The staged probe remains
uninstalled and must not use immediate close after the final FE32 as its
success criterion.

### Fresh-session lifecycle observer

The native download candidate still closes after its final acknowledgement;
it must not be run unchanged. New `gps_lifecycle.py` prepares a read-only
supervisor boundary instead of adding an unverified driver ioctl. Its
KernelReader opens an independent nonblocking /dev/kmsg cursor and seeks
to the current end before the sole probe owner opens gpsdl0. It never clears
the log or writes a command. This is diagnostic infrastructure, not a stable
GNSS API, and requires readable kernel logs with the existing status messages.

The pinned name table uses OFF/ON/RST/WORK and FUNC_ON/RST_DONE/RAM_OKAY/
FUNC_OFF, not the longer C enum spellings. The observer requires the complete
fresh primary-link sequence OFF -> ON -> RST -> WORK -> RST -> OFF, with an
explicit supervisor stop boundary between WORK and the second RST. The live
BINFO-only log supplies the first two and final message formats; WORK and
runtime reset remain source-derived and have not been observed on this phone.

Record sequence gaps, duplicate/reordered records, backwards timestamps,
primary warnings/errors, split GNSS records, unexpected transitions and
log-overrun/read errors invalidate the session permanently. Other-link and
userspace-facility messages cannot establish readiness. Observations are
limited to eight seconds and 4096 records; the currently available queue is
drained before returning readiness so a following error is not hidden.
The stop boundary must be set immediately before the controlled request,
with no competing opener; it does not correlate kernel events to a file
descriptor and cannot prove that the request caused the reset.

Seventeen unit tests, including substituted kmsg open/seek/read/select/close,
pass. The subsequent read-only handset preflight confirms Python availability
and that an independent /dev/kmsg descriptor can read a bounded record with
four header fields and numeric priority/sequence/timestamp, seek to the end,
and close. No record content was printed or journal cleared. The same
38192f202c/r153 boot still has USB UP and no gpsdl0. No state transition,
device open, stop request or module load was part of this preflight.

### Supervised native download/stop handshake (uninstalled)

The probe now has a separate `--experimental-supervised-download` mode.
After all FE31/FE32 acknowledgements it emits DOWNLOAD_COMPLETE and waits
for exactly W-newline on its private input pipe. Only then does it issue
one exact FE05/4 primary write, emit STOP_WRITTEN and wait for R-newline
before ordinary close. Short/bad/missing tokens and short stop writes fail
without retry. The existing eight-second process alarm remains in force.
Legacy BINFO-only/immediate-close modes are retained as historical test
cases, not as live experiment entry points.

`supervise_gps_download.py` opens the fresh kmsg cursor before creating
the child and connects this handshake to phases WORKING, post-stop RESET
and OFF. It checks child exit status and extra output under a single total
eight-second deadline. On failure it terminates/reaps the child, escalating
to kill once with a bounded wait. A child stuck in the kernel is explicitly
reported as requiring recovery; no reset, module reload or retry is issued.
It has no CLI, service or import-time execution. The caller must validate
binary/template hashes, hardware profile, sole ownership and clean-reboot
recovery before invoking the explicitly side-effecting run_reviewed_probe.

The standalone ARM64 probe compiles with C11/O2/Wall/Wextra/Werror. Its
mocked main-path suite now passes 33 scenarios including the successful
handshake, rejected readiness/reset token and short stop write. Nine
supervisor tests verify ordering, missing/bad child messages, short token
write, state failures, child exit failure and bounded cleanup of a stuck
child. These are separate substituted-I/O tests, not a full process/kernel
integration run. Error cleanup may still enter the driver's known forced-off
path after partial firmware startup; any such failure requires a clean reboot.

The actual child/supervisor pipe protocol now passes five Linux ARM64
integration scenarios. A separately compiled BINFO_PIPE_TEST fixture retains
the real native probe logic, real stdout/input pipes and process exit, while
replacing GPS syscalls and kernel state records. Successful exchange, missing
readiness/reset/OFF and a short stop write all terminate with expected
outcomes and reaped children. The initial macOS compilation lacked the Linux
UAPI headers; the successful run uses the existing Linux container and header.
No actual GPS device or /dev/kmsg is involved in this integration fixture.

Real-log comparison found a preflight bug: the vendor prints routine open,
power-control, open-ACK, release and successful DMA-stop messages at warning
level. The observer now accepts only phase-scoped, source-shaped normal
forms, plus post-OFF read/write history records. Unknown warnings, DSP-state
warnings, reopen failure and failed DMA confirmation remain fatal. Twenty
observer tests pass, including these distinctions. Replaying the historical
BINFO-only text with synthetic record metadata reaches ROM RESET_DONE and
correctly rejects its premature release at record 26; this is a replay, not
fresh hardware or proof of kmsg metadata preservation.

Subsequent live experiment: the four hashed inputs were uploaded and verified,
v051 loaded once from inactive state, and one supervised process reached
DOWNLOAD_COMPLETE. Its observer rejected the periodic read-history warning
at 3531.940202 while still in ROM RESET_DONE, then killed the child before
FE05 could be sent. Kernel history records 107 reads and one 116-byte write.
At 3532.016165 the kernel reported RAM_OKAY and RST -> WORK, the first actual
RAM-code readiness observation. It occurred during failing close cleanup:
off polling failed, A-die was forced off and WORK -> OFF carried is_err=1.
This is full-download/readiness evidence, not successful stop, navigation or
lifecycle. The exact original bundle and complete journal are retained in
the integration worktree's local/gnss-supervised-r153 directory.

The exact-pinned gps_dl_hist_rec.c shows that its warning-level history dump
runs whenever eight records fill its buffer, not only at close. The local
observer correction accepts only the complete numeric record shape, n<=8,
in phases 2..5. Twenty-three observer tests pass, including the observed
download warning, overflow rejection and global forced-off rejection. This
new observer has not replaced the uploaded experiment input or been rerun.

USB/SSH stayed available after failure and the device had no owners. A clean
reboot was requested without module unload/retry. The locked Mac enumerates
the postmarketOS USB device but has no network interface; user unlock is
needed before verifying the new boot and any further hardware experiment.
No successful hardware lifecycle or GNSS fix is claimed.

### Corrected observer: first complete hardware cycle

After user unlock and a guarded host USB reset, boot
3baa4f13-1c6d-4cf7-858a-6497d04f0de5 was verified with unchanged r153/device8-r9.
The separately hashed v2 bundle changes only the observer (SHA256
52d18c1e7751c247da07d1252de55d10bc099df86bd9ebb466bc817a111c908e).
One supervised child, pid 2770, exited zero. Real kernel evidence shows
RAM_OKAY/WORK at 603.400218, subsequent WORK -> RST at 606.864141, then
release and normal RST -> OFF/CLOSED by 606.867874. Read history has 107
frames and write history 116/12-byte requests; the native validated exchange
and supervised stop checkpoints completed. No forced-off/abnormal FSM,
off-done failure or matching kernel crash appears in the bounded capture.

Both 32 MiB USB hashes match the expected zero-stream digest. The boot ID
is unchanged afterward, USB is UP, Wi-Fi connected, Bluetooth powered and
there are no failed units or GPS owners. This verifies one controlled
download/start/stop boundary, NOT a satellite fix, navigation initialization,
three cold repeats, suspend/resume or automatic packaged support. All prior
failed-run evidence is retained. Exact artifacts and complete kernel logs are
in the integration worktree's local/gnss-supervised-r153-v2 directory.

## Reproduction

LLVM 21 tools were used against local copies in the diagnostic Docker mount:

```sh
llvm-objdump -d mnld
llvm-readelf --relocations mnld
llvm-objdump --disassemble-symbols=mtk_gps_sys_function_register,mtk_gps_mnl_run libmnl.so
llvm-objdump -d --start-address=0x7b240 --stop-address=0x7b4a0 mnld
llvm-objdump -d --start-address=0x5fa80 --stop-address=0x5fd20 mnld
llvm-objdump -d --start-address=0x52b638 --stop-address=0x52b858 libmnl.so
llvm-objdump -d --start-address=0x62280 --stop-address=0x62544 mnld
llvm-objdump -d --start-address=0x525528 --stop-address=0x525730 libmnl.so
llvm-objdump -d --start-address=0x525bd0 --stop-address=0x525ce8 libmnl.so
llvm-objdump -d --start-address=0x508d14 --stop-address=0x508d4c libmnl.so
llvm-objdump -d --start-address=0x53cb28 --stop-address=0x53ccb0 libmnl.so
llvm-objdump -d --start-address=0x63020 --stop-address=0x63358 mnld
llvm-objdump -d --start-address=0x63af4 --stop-address=0x63b18 mnld
llvm-objdump -d --start-address=0x6479c --stop-address=0x6481c mnld
python3 test-mnl-ioctl-veneer.py libmnl.so
python3 test-mnl-rx-framing.py libmnl.so
python3 test-mnl-checksum.py libmnl.so
python3 test-mnl-rx-stream.py libmnl.so
python3 test-mnl-length-guards.py libmnl.so
python3 inspect-command-tables.py libmnl.so
python3 inspect-relr.py libmnl.so
python3 inspect-chipset-capabilities.py libmnl.so
python3 test-mnl-fe14-response.py libmnl.so
python3 test-mnl-boot-response.py libmnl.so
python3 test-mnl-binfo-construction.py libmnl.so
python3 test-mnl-legacy-query.py libmnl.so
python3 -m unittest discover -s . -p test_boot_ack.py -v
python3 -m unittest discover -s . -p 'test_boot_*.py' -v
python3 test-mnl-request-wire.py libmnl.so
python3 test-mnld-resume-callback.py mnld
python3 test-mnl-clock-message.py libmnl.so
python3 test-mnl-mvcd-selection.py libmnl.so
python3 test-mnl-stop-dispatch.py libmnl.so
python3 test-mnl-stop-flush.py libmnl.so
python3 -m unittest discover -s . -p test_gps_lifecycle.py -v
python3 -m unittest discover -s . -p test_supervise_gps_download.py -v
python3 -m unittest discover -s . -p test_gps_pipe_integration.py -v
python3 test-rx-failed-read.py /path/to/android_kernel_modules_nothing_mt6878
```

Log-name strings were read through ELF PT_LOAD address-to-file mappings,
not inferred from untrusted filenames. Full registration disassembly and
relocation output must be regenerated when the binary hash changes.

Next resolve control IDs, remaining startup fields, caller fd ownership,
binary framing and both sides of each essential callback. Keep hardware
power/DMA/ioctl execution disabled until the exact lifecycle contract is
known. Neither registration nor a host-only callback test proves a fix.
