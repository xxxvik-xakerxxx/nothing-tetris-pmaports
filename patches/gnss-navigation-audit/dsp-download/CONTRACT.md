# B4.1 L1 DSP Download Boundary

Status: bounded pure wire codec and complete secure L1 bootstrap assembler supplied;
**no hardware download callable exposed**. The r182
bbc28d61 open at 3175.908..3175.916 established ROM reset, ADIE6631, OPENED,
ioctl13=0 and ioctl23 metadata (code_size42505, fragments106), followed by
clean DMA stop/OFF/CLOSED. It did not establish transport traffic, DSP WORKING
or a position fix. Private archive inspection emitted only allowlisted state
names; no key, address, firmware bytes or raw log is included here.

## First Missing Input

A source-proven **download-only L1 bootstrap context bound to the real gps0
owner**, including its profile selection, TX/RX rings and decoded-ACK producer.
The ROM metadata query alone does not construct that context. In particular:

- Native caller52f2b4..52f2c4 passes the retained record at71f1d0, via GOT6e65b8.
  Its complete constructor/lifetime is not proved for a download-only host.
- At4f2244 the profile byte7178b8+33e chooses secure/MVCD versus embedded-image
  sending. At4f2254..4f227c the byte717cb0 chooses command23 versus CW command24.
  Neither selection can be inferred just from ADIE6631 or a successful ioctl23.
- Sender554828 needs651e50(1), the L1 object in table6fef78+8, including the
  ring at object+8 and callbacks. Its missing-object branch is554930. A mapped
  associated DSO and an open fd supply no such runtime instance.
- Receive decoder509fc0..509fd0 /50a278..50a288 publishes the decoded L1 ACK
  through GOT6e66d0 to7178a0. A host-written marker cannot replace that producer.

This is the next input to close, not another driver registration task. No dummy
context, zero second configuration, fd-to-pointer cast or helper-offset API is
provided. The alternative native-wire adapter must first prove the complete
bootstrap request and matching receive grammar for this same profile.
The follow-up [WIRE.md](WIRE.md) pins the complete 106-byte layout and the
actual bootstrap/fragment ACK dispatch. The former 212-byte interpretation
was wrong: the serializer counts 16-bit units, not u32 words. Producer inputs
remain incomplete. `wire.c` frames an explicit106-byte payload; it does not
construct the native profile or obtain its clock/session inputs.
The next [BOOTSTRAP_FIELDS.md](BOOTSTRAP_FIELDS.md) block implements50 bytes
from real typed owner snapshots, including the private-record frequency decoder,
clock mode and board/feature branches. It preserves the other56 bytes and
does not substitute for complete context or ROM-session acquisition.
The distinct [BOOTSTRAP.md](BOOTSTRAP.md) implementation now constructs all106
payload bytes and the116-byte frame from those fields, actual same-session
typed ioctl23/24 output and exact selector snapshots. It also closes the
previously missed frequency-table producer for62..93. The embedded-image
branch is explicitly unsupported; actual input acquisition and bounded TX/RX
still require the real gps0 owner.

## Exact Inspected Boundary And Protocol

`mtk_gps_dsp_init`: ELF VA52f5ec, symbol size130 hex; self-PLT6e5520,
relocation6e9188 names that export. Observed machine ABI uses an x0 record
pointer and w0 OEM status. This is **not a complete public C prototype**.
Its52f6a8 ->55471c ->4f3634 ->4f0bdc chain selects firmware/profile, builds
bootstrap requests, obtains boot information, sends fragments and pumps ACKs.
It sets other library state and invokes51fec4/52fbb4 after its download path;
its return18 is not an independent kernel RAM-running acknowledgement.

| Stage | Pinned evidence | Required interpretation |
| --- | --- | --- |
| Boot info |4f2274..4f229c ->52e3dc ->ioctl PLT6e5200|Command23/24, five u32 fields; key is field+12, private to this ROM session. |
| Bootstrap request |4f2cd4..4f2ce4 ->554828|L1 command8, 0x35 halfwords =106 payload bytes,116 total; serializer emits AA/F0 framing and checksum into its owned ring. |
| Fragment |4f32bc..4f32d4|Command25/26, integer sequence argument formed from the native counter minus1; **not a payload pointer**. |
| Fragment ACK |4f3374..4f3434; dispatch4c4024 ->50a228|Pump receive parser554748; command0x32 clears bit5 and publishes sequence. Command0x33 clears bit14 and is not this fragment ACK. |
| RAM running |Kernel gps_dl_hal.c MCUB bit0 ->RAM_CODE_READY; gps_dsp_fsm.c RESET_DONE ->WORKING|Reject DEAD/BEEF diagnostics. ioctl25=0, send completion, fragment count and OEM18 cannot replace this event. |

The kernel driver owns secure-monitor calls; no userspace SMC route is proposed.
The stock downloader consumes/logs the key field at4f229c/4f230c/4f2318, without
first rejecting failed ioctl output. Its554a84..554aa8 ring-drain loop has no
deadline, and its4f34f0 ->4f0d94 retry path masks earlier failures. Consequently
calling this export as-is violates first-fault, bounded lifetime and redaction
requirements even after the missing context is supplied. A future adapter must
refuse the first error, retain live resources, and never publish keys/ciphertext.

## Firmware And Pins

mnld SHA256:285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83.
libmnl SHA256:3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90.
Driver source:Nothing B4.1 modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835.

The declared package input `connsys_gnss_mt6878_mt6631.bin` is present,523368
bytes, and matches APKBUILD SHA512:
94312789dbbb30bff98814fa441e05394e84beee1277cd3bc63d8b5cf35bae93fe844aae8f18d9acb93dc0d36a04df05db180328065a3db095424ec2d20b56cf.
Packaging installs it at/usr/lib/firmware and aliases connsys_gnss(.bin).
The inspected MVCD path obtains metadata through the driver and asks the driver
to submit numbered fragments. No proof maps this complete packaged container to
a native DSP payload slice; do not write the whole file to gps0 or infer byte
length from code_size42505. The embedded-image branch is a separate selection.

## Static Verification And Recovery

Run `test_source.py PINNED_MNLD PINNED_LIBMNL PACKAGED_GNSS_FIRMWARE`, with
PYTHONDONTWRITEBYTECODE=1 and the existing Capstone5.0.6 directory on PYTHONPATH.
It checks hashes, disassembly, source ABI/fragment ownership, real running-event
conditions and the package declaration. It does not load a DSO, emit wire data,
read keys, compile native code or execute instructions. No hardware adapter/CI run or
phone test is included. Run `test_wire_source.py PINNED_MNLD PINNED_LIBMNL`
for the layout, serializer, dispatch and unresolved-input assertions. These
checks decode immutable instructions only. Parent owns any physical firmware test; whole-phone
fresh boot remains the recovery rule unless DMA close is independently verified.
`clock.c/h` closes the L1 synthesis arithmetic independently of an opaque DSO
context. [CLOCK.md](CLOCK.md) identifies its real constructor/query inputs.
`bootstrap_fields.c/h` implements the override decoder and profile field branches;
their live input acquisition and profile choices remain gated. Wire inputs stay
explicit. `test_clock_source.py PINNED_MNLD PINNED_LIBMNL` checks those producers.
`test_bootstrap_fields_source.py PINNED_MNLD PINNED_LIBMNL` checks the new block.
`test_bootstrap_source.py PINNED_MNLD PINNED_LIBMNL` checks complete assembly.
`sh run-ci.sh` compiles/runs synthetic wire, clock, field and complete bootstrap
C fixtures only inside GitHub Actions.
It has not been run locally or dispatched here; parent owns CI integration.
`TETRIS_MODULES_TREE` overrides the default outer vendor checkout. The override
must contain the exact B4.1 git commit object; source is read with `git show`
at e96f60dc081ae3525ef43d4bcf0ee5ee97e53835, not from a mutable working tree.
