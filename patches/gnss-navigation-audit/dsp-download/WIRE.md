# B4.1 MVCD L1 Wire Boundary

Scope: immutable, SHA-pinned `libmnl.so` instructions; no DSO execution, phone
access or live metadata extraction. Addresses below are ELF VAs. This is a
specific sidecar implementation gate, not a working downloader. `wire.c/h`
provide bounded framing and matched-ACK decoding. `test_wire.c` is a synthetic
CI-only fixture. The codec has no file descriptor, DSO, ioctl or transport API.

## Serializer: Proven Length And Frame

At `554828`, arguments are command, halfword count, payload pointer and link
selector. `5548c8` shifts count by **one**, `5548d4` adds four, `554a04..554a10`
submits that length minus four. The bootstrap caller `4f2cd4..4f2ce4` supplies
command8, count0x35 and `sp+6b0`: **106 payload bytes,116 frame bytes**, not212.

| Frame offset | Proven bytes or rule |
| --- | --- |
| 0..1 | AA F0 (`5548cc`, `5548e0`) |
| 2..3 | LE16(106+4)=6E 00 (`5548ec`) |
| 4..5 | 08 FE (`5548dc`, `554908`) |
| 6..111 | Exact106-byte payload, not a native pointer on the wire |
| 112..113 | LE16(sum of bytes2..111 modulo65536), additive, not CRC/XOR |
| 114..115 | AA 0F (`5549bc`, `5549c4`) |

The SIMD checksum path at `554954..5549bc` is a byte sum; its scalar tail
sums the remainder. The payload pointer stored at stack+6 is an internal
descriptor: it is dereferenced at `5549fc`, never serialized as eight bytes.
Do not copy the descriptor layout as the wire layout. A future encoder must
be capacity-bounded. The supplied encoder requires an explicit106-byte payload
with subtype1a and initial sequence0, copies it byte-for-byte, and leaves output
and its length unchanged on error. It cannot certify dynamic field provenance:
the download controller must obtain the real values before invoking it.

## Complete Payload Layout

Offsets are relative to `sp+6b0`. All106 bytes have a traced destination;
that does **not** establish every dynamic value or its valid profile.

| Offset | Exact producer | Implementation gate |
| --- | --- | --- |
| 0..1 | LE16(0x1a), `4f2664..4f2674` | Proven subtype |
| 2..3 | `sp+e4/e0`, reset to0 at `4f263c..4f2640` | First bootstrap sequence0; later fragments advance only after matching ACK |
| 4..5 | `sp+cc/c8`, baud mapping `4f0e8c..4f0f8c` from context+1c | Full authorized context/baud producer not closed |
| 6..7 | `sp+130/131`, helper `4f05f4` output x5 | Clock/profile-derived, not ROM metadata |
| 8..9 | `sp+12c/12d`, same helper output x6 | Clock/profile-derived |
| 10..11 | `sp+c4/c0`, zero initialization `4f0cf8..4f0cfc` | Zero on inspected path; not inferred calibration |
| 12..13 | `sp+dc/d8`, zero initialization `4f0c94..4f0c98` | Zero on inspected path |
| 14..15 | Low16 of ioctl23/24 code_size (`sp+118`) | Same-session output; reject failed ioctl, preserve full metadata separately |
| 16..17 | Low16 of start_addr (`sp+11c`) | Same; not a hard-coded address |
| 18..19 | Low16 of exec_addr (`sp+120`) | Same |
| 20..21 | Low16 of cipher_key (`sp+124`) | Session secret; never log, fixture or replace |
| 22..23 | Low16 of frag_num (`sp+128`) | Must match same successful metadata query |
| 24..25 | `sp+f4/f0`, reset0 at `4f2600..4f2604` | Proven zero |
| 26..29 | LE32(0x00050000), `4f2734..4f273c` | Proven fixed value |
| 30..57 | Byte copy of `sp+750..76b` | 28-byte clock synthesis result from `4f05f4`, **not reserved zero** |
| 58..59 | `4f2824..4f28b0`: globals via GOT6e6670/6e6650, helper508d0c and context+30 branch | Runtime profile-dependent; not always7 or5 |
| 60..61 | `sp+d4/d0`: context+13==FE and zero (`4f2094..4f20cc`) | Need actual context mode |
| 62..93 | Byte copy of `sp+720..73f`, zeroed `4f20c0..4f20c4` | Proven zero on inspected path |
| 94..95 | Low16 global via GOT6e6688 (`4f29b8..4f29dc`) | Producer/validity not closed |
| 96..97 | Low16 context+30 (`4f287c`, `4f29d8..4f29f0`) | Native signed chip/profile identifier, not ADIE6631 substitute |
| 98..99 | `4f29e0..4f2a48`, context+30/+54 and global6e6670 | Branch-derived chip/revision bytes |
| 100 | `4f2a4c..4f2a74`, profile==4 and chip comparisons | Conditional0/1, not universal constant |
| 101 | Zero (`4f2a78`) | Proven zero |
| 102 | `4f2a7c..4f2acc`, helper508d0c, global6e6658 and helper5cc564(0xb2) | Runtime feature predicate; semantics/lifetime not closed |
| 103..104 | LE16(0x4e00), `4f2abc`, `4f2ad0` | Proven00 4E |
| 105 | 4F (`4f2ac4`, `4f2ad4`) | Proven fixed byte |

Clock helper call `4f2120..4f2138` takes modew28, second argument0,
context+18 frequency and three output pointers. Modew28 depends on globals
GOT6e6668/6e6670 and context+24 (`4f20d0..4f2120`). The helper can replace the
frequency via `5523c0` when context+13==FE (`4f0648..4f0684`), then uses float
arithmetic and `574f04` conversions before fourteen16-bit stores at
`4f0980..4f09c8`. The pure arithmetic/conversion is now implemented in
`clock.c/h`; see [CLOCK.md](CLOCK.md). Remaining closure is authoritative
construction of the context/global selectors and the effective override result.
Copying synthetic zeros would conceal this gate.

## Receive Grammar And Matching ACK

`554748(link1)` calls `682ef8`. It reads six header bytes, validates the masked
12-bit length using `554770/5547ac`, copies length-4 payload bytes, then reads
checksum and trailer separately. `6832a4..6832d0` checks AA F0 / AA 0F;
`554c64` checks the additive checksum including the full header length bytes.
`554d3c` requires command high byteFE, passes low command byte, payload length,
length high nibble and payload to decoder509830. That decoder does not consume
the high-nibble argument for these two ACK routes. The codec preserves it in
the result, without imposing an invented zero-only policy. The first stock
length guard `(length12-5) < 0x3f6` allows at most1014 payload bytes.

Three real dispatch tables matter, not just references to the sequence global:

| Low command | Copy route | Completion route | Correct use |
| --- | --- | --- | --- |
| 31 | table4c3f08 ->509984, inherited destination717d05+231 | table4c4024 ->509f98 | Bootstrap: clear bit15 at717cc0, payloadLE16[0] ->7178a0, payloadLE16[2] ->717cf0 |
| 32 | table4c3f08 ->509f20, destination from GOT6e66e8+d00, cap2 | table4c4024 ->50a228 | MVCD fragment: clear bit5 at717cc0, payloadLE16[0] ->7178a0 |
| 33 | table4c3f08 ->509984 | table4c4024 ->50a254 | Clears bit14, **not** fragment completion expected by4f33a4 |

Bootstrap wait `4f2dac..4f2e0c` requires bit15 cleared and exact sequence0;
fragment wait `4f337c..4f33e8` requires bit5 cleared and exact sequence before
increment. Bootstrap needs at least4 bytes for both observed fields; fragment
needs at least2. Stock copy caps are10 and2 respectively, but it accepts short
payloads and leaves stale destination bytes. Thus these are **minimum accessed
sizes, not proved exact ACK wire lengths**. The second bootstrap word is stored
but not checked in the immediate wait: do not invent success/error meaning.

The codec requires complete accessed fields (at least4/2 bytes), accepts larger
stock-bounded payloads, and reports their size instead of inventing exact4/2
wire lengths. It returns the second bootstrap word as opaque auxiliary data,
not a made-up success flag. It rejects truncation, wrong command/sequence and
checksum/trailer mismatch before modifying the result. This matches the
trusted-stock-kernel MVCD boundary; it does not add an authentication layer.
Ordered requests, duplicate/stale completion exclusion, deadlines, sticky first
fault and integer ioctl25 sequencing belong to the still-unimplemented owner.

## Static Checks

`test_wire_source.py PINNED_MNLD PINNED_LIBMNL` verifies both full hashes,
immutable routine hashes, exact copy instructions for all payload blocks,
length arithmetic, framing/checksum, all three table transitions, sequence
publication and awaited bits. It also asserts the unresolved helper inputs
and the absence of a stock exact4-byte bootstrap ACK guard. It neither builds
nor executes C, invokes the DSO, prints secrets, or fabricates a ROM session.

The C fixture covers the known116-byte frame/checksum, all undersized output
capacities, wrong212-byte input, overlap, matching/wrong command and sequence,
all sixteen preserved high nibbles, short and maximum-sized ACKs, every frame
truncation, over-limit length, checksum wraparound and single-byte corruption,
and unchanged outputs on failure.
Run `sh run-ci.sh` in GitHub Actions; no native compilation/execution occurred
locally and no CI run is claimed. The parent integrates this fixture job.

Next implementable work is the authoritative profile/effective-clock input closure.
The pure codec is usable independently, but a download controller must not
emit a synthetic bootstrap and rely on retries. Kernel ioctl25/26 submits integer fragment
numbers only after a real matched bootstrap ACK; RAM_CODE_READY remains a
separate kernel event, never synthesized from an ACK or send return.
