# B4.1 Complete L1 Bootstrap Assembly

`bootstrap.c/h` closes all106 payload bytes and their116-byte command8 frame
for the secure L1 MVCD and CW paths, using the field constructor committed in
main5d507e5. Input acquisition and transport remain external. These pure functions
do not open/query a device, execute libMNL, send firmware or establish DSP WORKING.
Only the already-owned session may retain/use the private key-bearing outputs.

## Byte Coverage And A Corrected Producer

The earlier claim that62..93 were always reserved zeros was incomplete. The
full immutable downloader contains an out-of-line producer at4f35e8..4f362c.
It is reached for recognized reference-frequency windows before the metadata
query. `bootstrap_fields.c/h` supplied50 other bytes and remains unchanged.

| Payload bytes | Complete assembler's exact producer |
| --- | --- |
| 0..1 |4f2664/4f2674: LE16(1a) |
| 2..3 |4f263c/4f2640: reset initial sequence0 |
| 4..9 |Existing baud and effective-clock parameter constructor |
| 10..11 |4f0cf8/4f0cfc zero c4/c0;4f26b8..4f26c4 copies them |
| 12..13 |4f0c94/4f0c98 zero dc/d8;4f26c8..4f26d4 copies them |
| 14..23 |4f2290..4f22e8 extracts five query words;4f26d8..4f2724 serializes each low16 in ABI order |
| 24..25 |4f2600/4f2604 reset f4/f0;4f2728..4f2738 copies them |
| 26..29 |4f2734/4f273c: LE32(00050000) |
| 30..61 |Existing synthesis, profile and context-mode constructor |
| 62..93 |Original context-frequency windows4f2158..4f221c select immutable table27934;4f35e8..4f362c converts its first16 words to LE16. Only unmatched windows retain the4f20c0/4f20c4 zeros. |
| 94..105 |Existing board/feature-tail constructor |

No byte is unassigned or filled with an unexplained placeholder for these two
supported paths. All106 are constructed before any caller output changes.

### Frequency Table

4f213c loads the original first-context+18 into w21 **after** the clock helper.
This is separate from the helper's effective frequency after its private override.
4f2140..4f2154 copies ten72-byte records from27934. The exact inclusive windows
and selected rows are:

| Row | Original context Hz window |
| --- | --- |
| 0 |11999976..12000024 |
| 1 |15999968..16000032 |
| 2 |19199962..19200038 |
| 3 |19999960..20000040 |
| 4 |23999952..24000048 |
| 5 |25999948..26000052 |
| 6 |31999936..32000064 |
| 7 |38399924..38400076 |
| 8 |39999920..40000080 |
| 9 |51999896..52000104 |

The implementation preserves unsigned32 range subtraction, including row1's
inclusive upper comparison. The out-of-line loop uses source word byte1 for
columns5..8 and low16 for the other columns; an ordinary16-bit table copy is
wrong (column6 isD8, notCE). All ten records produce identical first16 halfwords
in this pinned ELF, so the implementation shares that exact16-word result.
The remaining two halfwords written to sp+740/+742 are not bootstrap bytes.
The full720-byte immutable table SHA256 is
ec85c275d49568c182872ba5d4f51f04f47bc815b126ed0eaa1b77b5b9c08290.

## Exact Selection And Same-Session Metadata

4f2244 reads7178b8+33e. Zero branches to embedded-image headers at4f2350.
This assembler reports `B41_BOOTSTRAP_EMBEDDED_IMAGE` without changing outputs;
ioctl metadata cannot substitute for that separate image/header producer.
For any nonzero flag,4f2268..4f227c computes `(selector717cb0-1)&ff <3f`:

| Actual selector byte | Boot information | Fragment submission |
| --- | --- | --- |
| 1..63 |ioctl24, L1 CW |ioctl26 |
| 0,64..255 |ioctl23, L1 MVCD |ioctl25 |

Selector64 is outside the CW range.4f32a8..4f32c4 independently proves the
matching fragment pair. `b41_bootstrap_route_select` returns only these real
commands; it never supplies an invented board/chip selector.

`b41_bootstrap_session` retains the actual gps0 descriptor, current raw selectors,
and legitimate typed field inputs for one exclusively owned open lifetime.
`b41_bootstrap_query` must identify that same object and descriptor, preserve
those raw selector bytes, carry the matching query command and immediate
normalized syscall status, and reference the complete20-byte output record.
Descriptor0 is valid. The descriptor and host object address are never serialized.
The pointer binding excludes another retained session object even when fd numbers
match; it is not a synthetic hardware session ID or an ownership certificate.
The external owner must prevent close/reopen, fd reuse, alias readers and snapshot
mutation. This pure constructor cannot detect violations of that lifetime contract.

The five fields are code_size, start_addr, exec_addr, cipher_key, frag_num.
Pinned modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835 unpack each from an
unsigned16 ATF field into the five-u32 ABI. A successful ioctl copies exactly
that20-byte record; copy/backend/open failures return-EFAULT. The stock wrapper
52e3dc collapses failures to OEM2, then stock consumes/logs potentially stale
metadata. This implementation requires syscall status0, propagates negative
errno, refuses positive OEM status2/18 and checks complete data before assembly.
Constructor error codes are separate from normal negative errno, so a real
EINVAL failure cannot be mistaken for an embedded-image selection result.

Every metadata word must fit its source unsigned16 representation. Positive
code_size and frag_num are stricter host preflight, not claimed stock checks.
Zero start_addr, exec_addr or cipher_key is preserved when actually supplied:
there is no invented nonzero-address/key rule. The last numbered-fragment argument
is count-1 (4f32bc); the kernel rejects arguments **greater than256**, so the
preflight count limit is257. This is a transport limit, not a guessed relationship
between code_size, fragment count and the packaged firmware container.

The caller retains the actual full metadata; the assembler doesn't clear its
upper bits to disguise mismatch, synthesize a key, or turn failed output into
defaults. Real metadata must be acquired from the same ROM session as the
eventual transport. No actual metadata or session key was acquired in this work.

## Atomic Outputs And Private Storage

`b41_bootstrap_payload_build` constructs106 bytes in temporary private storage
and copies only after every input and field producer succeeds.
`b41_bootstrap_frame_build` passes that complete payload through the existing
AA/F0 serializer, producing command08/FE, length6e, additive checksum andAA/0F
trailer. It changes the output length only on successful full frame construction.
Both refuse insufficient capacity and overlap with session/query/metadata/field
storage, borrowed name/clock records, or overlapping frame/length outputs.
Bytes beyond the fixed output size remain untouched.

The key exists only in borrowed query storage, temporary payload and the private
caller output required by the actual wire protocol. Volatile stores wipe the
temporary payload after success or field/encoder failure. There is no logger,
diagnostic publisher, file writer, transport callback or key-bearing result dump.
Caller metadata and payload/frame buffers must remain private and be wiped when
their owned transport lifetime ends. A constructed frame is not a public artifact.

## Verification And Remaining Gates

Run `test_bootstrap_source.py PINNED_MNLD PINNED_LIBMNL` with the same offline
Capstone5.0.6 path and PYTHONDONTWRITEBYTECODE=1 as the existing source tests.
It pins both complete ELF hashes, the full downloader and query wrapper, and the
complete table. It checks actual zero writers, every remaining byte destination,
metadata ABI/provider failure, selector boundaries, table decoding, original
frequency windows and the wholly synthetic native fixture's frame checksum.
No native instruction, firmware, device or DSO is executed by these checks.

`test_bootstrap.c` supplies the full106-byte synthetic golden payload and116-byte
frame checks, all65536 raw-selector combinations, matching/mismatched queries,
every short metadata/output size, session/fd/snapshot mismatch, malformed words,
count256/257/258 boundaries, missing field producers, reference-window edges,
override-vs-reference distinction, output/input overlap and atomic failures.
Only synthetic numeric keys/metadata exist in fixtures. `run-ci.sh` adds this
fixture under the existing Actions-only guard, strict warnings, ASan/UBSan and
floating-point flags. New native compilation/execution remains pending parent CI.
No parent workflow or recovery work is changed or dispatched here.

Local static validation passed44 tests: download8, wire9, clock8, fields9,
complete bootstrap10. Python parsing, shell syntax and whitespace are checked
separately. These results do not claim compilation or native fixture execution.

Remaining gates are actual acquisition of first/retained context and final
selectors/private clock records; one successful same-owner ioctl23/24 query;
the sole bounded gps0 TX/RX controller with real matched ACKs, integer fragment
submission, deadlines and first-fault handling; and independent kernel MCUBbit0
RAM_CODE_READY -> FSM WORKING evidence. Native/clean-install/lifecycle gates still
apply. Embedded-image metadata/header construction is explicitly unsupported.
There are **no still-unjustified payload bytes for the supported secure L1 paths**;
this does not close physical DSP startup or navigation.
