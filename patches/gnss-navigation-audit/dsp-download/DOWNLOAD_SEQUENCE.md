# B4.1 Secure L1 Download Sequence

Static evidence only. The supported route here is libmnl link selector1 (gps0,
kernel link ID0), with the byte at7178b8+33e nonzero. No hardware, vendor DSO,
firmware, native fixture, build or CI execution is part of this audit.

## Exact Pins

- ELF: `/private/tmp/tetris-b41-mipc-closure-ci38030808388/vendor/lib64/mt6878/libmnl.so`;
  SHA256 `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`.
- NothingOSS modules Git object `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` in
  `upstream/android_kernel_modules_nothing_mt6878` in the outer workspace.
  Every kernel reference below is relative to `connectivity/gps/data_link/`
  at that object, independent of checkout HEAD.
- Decoder: offline Capstone5.0.6 at
  `/private/tmp/tetris-gpu-offline-capstone-20261012`.
- Companion check: [test_download_sequence_source.py](test_download_sequence_source.py).
  It verifies the complete ELF, complete downloader4f0bdc..4f3634, ioctl wrapper,
  wire serializer and ACK decoder hashes, exact instructions/dispatch tables,
  complete source blob hashes and existing package1008 read-patch hash.
  All addresses below are ELF virtual addresses, in hexadecimal.

## Parent Controller Contract

**No extra userspace command08 trigger is sent before a secure fragment ioctl.**
The integer ioctl itself is the userspace submission operation. The secure
branch bypasses command0x0c and its payload constructor. That command belongs
to the distinct embedded-image branch where7178b8+33e is zero.
Stock rereads the secure flag and selector during submission; this contract
requires the same supported selection throughout the owned download session.

Let N be `frag_num` from the successful, same-owned-session ioctl23/24 metadata.
For positive N within the backend argument limit:

| Stage | Userspace submission | Required wire completion | Next host sequence |
| --- | --- | --- | --- |
| Bootstrap | Existing command08/FE frame; payload subtype LE16(1a), sequence LE16(0),106 bytes | command31/FE, payload first LE16 =0 | 1 |
| First secure fragment | ioctl25/26, integer argument0 | command32/FE, payload first LE16 =1 | 2 |
| Fragment index i,0 <= i < N | ioctl25/26, integer argument i | command32/FE, payload first LE16 =i+1 | i+2 |
| Last secure fragment | ioctl25/26, integer argument N-1 | Same command32/FE, sequence N | N+1 |
| Download loop termination | No extra command08/0x0c frame or final fragment ioctl | No distinct final wire ACK is awaited by this loop | Remains N+1 |
| Kernel running state | Independent MCUB interrupt/event handling | RAM_CODE_READY -> FSM WORKING | Not a wire sequence transition |

The ioctl carries **only the integer fragment index**, not a pointer, payload,
key or separate sequence argument. The expected ACK sequence is host state;
its relationship to the index is traced from this producer. Packet generation,
fragment data placement and sequence encoding *inside secure firmware* are
outside these source/ELF observations. Do not invent an ATF wire request packet.

## Bootstrap To First Submission

4f263c/4f2640 zero the low/high sequence bytes at sp+e4/e0. 4f2b58 zeros the
retained upper sequence component. 4f2cd4..4f2ce4 passes the complete bootstrap
to554828: command08, halfword count35 (106 payload bytes), retained link selector.
Bootstrap pending bit15 is set before transmission. The command31 decoder
clears bit15 and publishes payload LE16[0] through GOT6e66d0 ->7178a0;
payload LE16[2] is also published to717cf0 but is opaque to the immediate wait.
The complete downloader's sole GOT6e6638 ->717cf0 access is the initial clear
at4f0e0c/4f0e14. The count instead comes directly from metadata at4f22c4/4f22d0.
Thus neither an extra fragment nor a success predicate derives from that
auxiliary word on this path. Its wider firmware meaning is not established.

4f2dd4 waits for L1 bit15 to clear;4f2dec..4f2e0c compares the published low16
ACK sequence with the composed host sequence. Only the matched branch at
4f2e3c..4f2e5c increments that sequence. Thus the first fragment sequence is1.
A mismatch enters bootstrap retry handling without advancing. The successful
nonzero sequence skips the bootstrap resend at4f2f4c.

The stock path next clears private working storage and calls its baud helper
508d08 before4f30e4. These are not another command08 fragment frame. Retaining
an open gps0 ROM session and legitimate bootstrap inputs remains an external
owner responsibility; this document does not create or acquire that session.

## Secure Trigger And Numbering

4f30e4..4f3118 composes the current sequence and compares it with the complete
count. Count low bytes come from sp+ec/e8; its upper half came from metadata
sp+12a via4f22d4 and4f2ab0/4f2ab4. The pinned kernel sets `frag_num` from the
low16 of ATF res.a1 into a u32, so this upper count component is zero for the
real successful provider.

4f314c reads the secure flag. Nonzero takes4f315c/4f3160 directly to4f325c,
skipping the embedded data-copy producer4f3164..4f3258. At4f326c..4f3278 the
host sets pending bit5 in the selected link flags (L1 GOT6e6678 ->717cc0).
4f328c then selects the secure submission branch:

- 4f3290..4f32b4 reconstructs **current sequence**, not count.
- 4f32bc computes `argument = current_sequence - 1`.
- Selector717cb0 in1..63 chooses ioctl26 (CW);0 or64..255 chooses ioctl25
  (ordinary L1 MVCD), via `(selector-1)&ff <3f` at4f32a8..4f32c4.
- 4f32cc..4f32d4 calls52e3dc(operation1, link1, command, integer argument).
- 52e45c takes the retained L1 fd at6ee124;52e460..52e468 calls the real
  imported `ioctl` with fd, command low8, and argument in w2.
- 4f32d8 jumps over the embedded writer4f32dc..4f32ec. The skipped writer
  would send command0x0c with a sequence-prefixed image payload, not command08.

The complete downloader's554828 call sites are exactly4f2c84 (L5 bootstrap),
4f2ce4 (L1 bootstrap),4f32ec (embedded fragment). No per-fragment command08
serializer call exists in this pinned producer. On the secure path the ioctl
submission is followed by the common ACK wait, not a serialized trigger frame.

`linux/gps_each_device.c:490` and`:502` handle commands25/26, require an open
device and cast the syscall argument to unsigned int. They call
`gps_dl_hw_gps_send_dsp_fragement_num` with is_cw_dsp0/1, returning0 on backend
success or-EFAULT on failure. `hw/gps_dl_hw_atf_mvcd.c:50` maps link0 to L1/L1_CW,
rejects arguments greater than256 and invokes SMC_GPS_MVCD_SEND_DSP_FRAGEMENT
(0x20), passing dsp_type and fragment index. It treats res.a1==1 as failure;
other values return true. This is a secure-call return, not the wire ACK or
proof that RAM code is running. Stock52e46c..52e474 maps any nonzero syscall
result to OEM status2, losing errno.

For contiguous indices0..N-1, that backend accepts N up to257. This is only
the visible argument bound; it does not prove that any count/image is valid.
Positive count is host preflight, not a stock check: if real metadata supplied
N=0, sequence1 already exceeds the count and stock takes the finish branch.
No size/count relation to the packaged firmware container is established here.

## Matching, Advancement And Termination

Command32 copy dispatch is table4c3f08 ->509f20, capped at2 bytes in destination
GOT6e66e8+d00. Completion table4c4024 ->50a228 clears L1 bit5 and publishes
that LE16 to7178a0. Command33 goes to50a254, clears bit14 and also publishes a
sequence; it does **not** clear the bit5 awaited by this fragment loop.

4f3378 pumps receive,4f33a4 waits for bit5 clear,4f33dc..4f33e8 requires exact
sequence equality. The same path applies to the last fragment. 4f3410..4f3430
increments the composed sequence only on a match, retaining carry via w25 and
storing low/high bytes separately. For backend-supported N<=257 no16-bit
sequence wrap occurs. There is no reset to0 between fragments.

4f349c compares the updated sequence with the sequence used for submission:
unchanged re-enters4f326c to retry that same integer fragment; changed returns
to4f30e4 for the next count comparison. Submit failure takes4f32fc ->4f30b0;
timeout/mismatch leaves sequence unchanged and consumes stock retry budget.
These are stock behaviors, not a recommendation to adopt automatic retry or
discard a first fault. Stock receive/copy handling can retain stale fields:
bootstrap accesses at least4 payload bytes; fragment accesses at least2, with
no proven exact ACK length. The parent must require complete, checksum/trailer
validated, current-command/current-sequence ACKs and exclude stale/duplicate
completion. See [WIRE.md](WIRE.md) for the full AA/F0 receive grammar and bounds.

After matched ACKN, sequence becomes N+1. 4f3110/4f3114/4f3118 exits when the
sequence is unsigned greater than the complete count. The conditional compare
also treats sequence0 as terminal; normal supported secure progression never
takes that zero case. The finish block4f34a8..4f34f0 clears the downloading
byte (L1 GOT6e66c8 ->717cfe), calls clock/log helpers and branches to the common
epilogue4f0d94. There is no final execute packet, command33 wait, extra index N
ioctl, or reset of the protocol sequence in that finish block. Common epilogue
processing is not independent evidence of kernel WORKING.

## Kernel Ready And Transport Limits

`hal/gps_dl_hal.c:340` separately checks MCUB D2AF bit0
GPS_MCUB_D2AF_MASK_DSP_RAMCODE_READY. dat1 DEAD/BEEF causes a dump and `continue`,
not a ready event; already-WORKING state is skipped. Otherwise it calls
GPS_DSP_EVT_RAM_CODE_READY. `hal/gps_dsp_fsm.c:254` accepts that event in
RESET_DONE and moves to WORKING. A successful integer ioctl or final wire ACK
cannot substitute for this event. No relative timing between final wire ACK
and MCUB ready is proved; a same-session owner must retain independent evidence.

The shipping package's existing1008 read-boundary patch honors O_NONBLOCK:
device read chooses timeout0 and the empty-link branch returns-EAGAIN before
IRQ/polling waits. This is documented and generated in
`patches/gnss/read-boundary/README.md` and`generate.py`. It is distinct from the
unpatched vendor read wrapper, which uses GPS_DL_RW_NO_TIMEOUT(-1).
It does not implement a poll ABI, finite blocking IRQ deadline, partial DMA
entry reads, or complete device-buffer serialization across competing readers.
Use the sole-owner RX buffer/decoder boundary established by the parent.

At the pinned vendor object, device write ignores file flags; its link wrapper
calls `gps_each_link_write_with_opt(..., true)`. NOSPACE/BUSY/NOENTRY enters
`gps_dl_link_wait_on`, whose Linux wait is untimed `wait_event_interruptible`;
the polling TX-done branch also uses timeout-1. Its file_operations has no.poll.
Thus stock O_NONBLOCK plus userspace poll/deadline does not bound writes or
provide actual RX/TX readiness. Package1008 changes reads only. The separately
owned write-boundary/controller work is outside these two files; no claim about
its current implementation, build, elapsed syscall time or hardware is made.
The synchronous SMC fragment submission also exposes no timeout argument;
offline source cannot certify a wall-clock bound for that operation.

## Reproduce Static Checks

From the pmaports repository root, with the pinned vendor object available:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 \
python3 -B patches/gnss-navigation-audit/dsp-download/test_download_sequence_source.py \
  /private/tmp/tetris-b41-mipc-closure-ci38030808388/vendor/lib64/mt6878/libmnl.so
```

`TETRIS_MODULES_TREE` can override the local vendor repository for read-only
Git object access. The test reads pinned bytes/source and checks static
instructions; it does not invoke DSO functions or handle actual session keys.
Native controller validation, actual secure submission/ACKs, independent kernel
ready evidence, clean installation, lifecycle and portability remain untested
by this sidecar task.

Local verification: all13 companion static tests passed against the pins above.
No native controller test or build was run.
