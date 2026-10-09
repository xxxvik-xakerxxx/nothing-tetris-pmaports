# Post-freeze host service and typed second configuration

Status: source-recovered executable candidates, native CI pending. These new
files do not modify the frozen adapter, first builder or query-plan snapshots.
Same pinned B4.1 hashes as MANDATORY_CALLBACK_ABI.md. No phone/native local build.

## Actual AGPS transmit service

`b41_agps_host.c/.h` implement the complete bounded envelope behind mnld39490:
u32LE1, u32LE150, presence byte, then for a present string u32LE(length+1) and
the NUL-terminated string. NULL is a9-byte absent-string packet, distinct from
a14-byte present-empty packet. 39540 emits the8-byte u32LE1/u32LE152 envelope
for selector1. Its meaning is NOT navigation start/stop. Source helpers35410
and35630 prove the serialization. Oversize/embedded-NUL/overlap input rejects
instead of reproducing vendor truncation with a misleading advertised length.

An actual descriptor owner moves an exclusively owned connected Unix datagram
fd, validates exact supplied peer/type/inode, and sends one packet using
MSG_DONTWAIT|MSG_NOSIGNAL. No guessed namespace, endpoint, connect/bind or retry.
The caller supplies its audited peer and must end any previous owner's use
before moving the descriptor; fstat detects already-reused fd identities, not
arbitrary concurrent external close/reuse in violation of that ownership contract.
First transmit failure is sticky. Stop serializes behind transmit and closes
only the matching owned IPC descriptor, with no close retry/reinitialization.
This IPC stop is real, but is NOT an engine stop/receiver teardown contract.

Host workers can send frozen copied frame-sleep/network/measurement events via
this service. Raw app/NMEA and generic selector0-data events are refused:
selector0's parameter is only tested nonzero by the real dispatcher, not proven
to be strlen. Explicit bounded string API is available once the real source is
validated. No frozen callback registration/readiness logic changes.

`test_b41_agps_packets.py MNLD` passed five complete producer vectors and type152,
including NULL/empty/CR/CRLF and a mocked send failure. `run_agps_host_ci.sh`
builds actual socketpair delivery, fd move, reinit/close rejection, already-reused
fd avoidance, peer disappearance, backpressure, short-send fault and concurrent
send/stop tests. The short-send fault uses linker --wrap=send; all ordinary
delivery/backpressure/lifecycle calls are real CI-host syscalls. No device nodes
except CI /dev/null as a deliberately wrong replacement descriptor.

## Typed second-config constructor

`b41_second_config.c/.h` build a separate0x444 block with byte provenance, not
a blanket-zero resolved struct. Proven identity/output marker, explicit build
policy and bounded typed path fields reuse frozen helper logic. Receiver fd
snapshot+10 is primary; +14 is secondary if actual56ce0 bit0 is set, otherwise
producer-initialized0 (not a fabricated -1). Those are gpsdl descriptors,
NEVER the AGPS IPC fd; the constructor neither owns nor opens/closes them.

Actual68-byte de4d4 state is copied to+70..b3. +6c is the boolean request AND
the actual56c70 backend's bit0; neighboring padding stays unresolved. The copy
is synchronous with no retained pointer. It does not invent XML/calibration
state or claim the still-unknown MPE schema is validated. Missing state remains
unknown, not a default-off success. Receiver owner, engine stop and schema gates
stay missing even with all supplied inputs, so status remains partial1.

`test_b41_second_state_producers.py MNLD` passed four secondary-fd condition
vectors and fifteen full state-copy/backend combinations using pinned slices.
`run_second_config_ci.sh` builds constructor/provenance/lifetime and immutable
failure tests. Native compilation was not performed locally.

## Remaining Mandatory Host Contracts

- Slot0/event0: gps-control notification plus actual engine position/info,
  persistence and Android-facing publication paths; full state schema/owners
  unresolved. Do not acknowledge by returning0 from a queue-only replacement.
- Slot0/event3: owned ADC fd/global88790; reads0x50000 bytes, persists ADC.txt
  and invokes5d770. Read-length/format/lifecycle/backend still unresolved.
- Slot0/event7: literal MTK_GPS_MSG_FIX_PROHIBITED. Producer5df28 constructs
  u32LE3 and sends to literal mnld_gps_control_socket via36b40, then logs;
  this is a DIFFERENT control service, not the AGPS type150/152 peer. Actual
  endpoint transport/result contract must be recovered before implementing it.
- Slot0/event13: literal MTK_GPS_MSG_NEED_RESTART invokes55220; supervisor
  restart ownership and safety are unresolved, not an unconditional reset.
- Slot6: selector0 typed string IPC and selector1 envelope now implemented
  independently; remaining structured/control selectors, AGPS service receiver
  and result routing remain unresolved. No fake backend for selector15 LPP stop.
- Slots3/4/5: request encoding and real transmit boundary are implemented;
  assistance/frame-sync receiver and result publication remain required.
- Slots1/2 retain their bounded copy boundary. Slots7/8/9 remain proven pure
  pass-through/codecs; they are not missing runtime services.

First-config27 bytes/XML and complete second scalar/profile policy are still
unresolved. Neither host code nor source-copy provenance removes engine gates.
Next executable gate: run both new native fixtures under Ubuntu ASAN/UBSAN and
main's standalone AArch64 Bionic runner (AGPS fixture needs --wrap=send and
pthread). Then audit slot0 control-socket receiver/position schema and complete
receiver-fd/engine-stop lifecycle before connecting any native engine.
