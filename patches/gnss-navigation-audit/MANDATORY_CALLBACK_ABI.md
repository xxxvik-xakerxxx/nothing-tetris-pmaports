# Mandatory B4.1 callback machine ABI

Same pinned ELF hashes as `STARTUP_HOST_ABI.md`; no recovered vendor typedefs
are claimed. mnld registration caller61444 passes table88cb8. ELF RELATIVE
relocations establish the producer addresses below independently of symbols.

| Slot | Producer | Arguments / result | Executable adapter behavior |
| --- | --- | --- | --- |
| 0 | 5de00 | w0 event; w0 status | Genuine vendor no-action selectors return0; active0/3/7/13 refused |
| 1 | 7b240 | x0 borrowed bytes, w1 length; w0 status | Separate copied app-diagnostic event, not duplicate GPS fix publication |
| 2 | 7b3f0 | x0 borrowed bytes, w1 length | Copied raw-output event, no validity claim |
| 3 | 7ba50 | low byte w0; w0 status | PMTK738 sleep request, CR without LF |
| 4 | 7bbc0 | no input; w0 status | PMTK736,0,0 network request, CR without LF |
| 5 | 7b850 | signed32 w0; w0 status | PMTK736,1,value measurement request, retains CRLF |
| 6 | 5fa80 | w0 selector, w1 parameter, x2 pointer; w0 status | Copies selector0 data only; refuses other selectors without dereferencing |
| 7 | 5d910 | preserved w0; result unchanged | Exact input pass-through; not guessed successful service |
| 8 | 5d920 -> 84c6c | x0 source, x1 destination, w2 length; returns length | Byte rotate-right2 then XOR63 |
| 9 | 5d930 -> 84d7c | x0 destination, x1 source, w2 length; returns length | XOR63 then rotate-left2 |

## Important Differences

Slot5 consumes all32 bits with signed `%d`, unlike slot3's low-byte masking.
Its complete body copies strlen bytes, so LF is retained. Seven producer
vectors including INT32_MIN/UINT32_MAX verify this; AGPS failure is masked by
stock's zero return. Adapter zero means queued only, not measurement completion.

Slots8/9 are reversible log obfuscation, **not security or encryption**. Their
full scalar and SIMD bodies execute in44 length/direction/overlap vectors.
Asymmetric pointer order matters. Zero length returns0 before pointer access.
The adapter uses the same forward overlap behavior and caps wrapper work at
the explicit1024-byte host limit, recording errors rather than silently
truncating. Direct capacity-aware `b41_byte_codec` is reusable independently.
No active libmnl8/9 invocation was found in this bounded audit; registration
still requires both. This absence is not a license to infer future call sizes.

Slot7 producer is exactly RET. libmnl veneer509064 preserves x0, and its caller
542008 converts a double to signed32 w0 before the call and ignores the return.
Pass-through is source-backed, not an invented no-op for unknown behavior.

Slot0's14-entry table routes only0/3/7/13 into active handlers; other selectors
and unsigned values above13 return0. Those active branches obtain engine
information, persist data and communicate with Android-dependent services.
Their implementation remains blocked explicitly by HOST_SERVICES. Tests stop
before entering them: no mocked persistence is passed off as completed support.

Slot6 is **not universally `(type,payload_length,payload)`**. libmnl5329e0
calls type15 with parameter1 and NULL; other types carry structured/control
contracts. Only selector0 data is copied. Unsupported types return a sticky
error rather than interpreting the parameter as a length and crashing.
With the explicitly disabled receiver flag88bf4, stock selectors0/1/7 return-1;
tests exercise that dependency instead of declaring delivery from a queue.

Slot1 uses pointer/length at libmnl524ab8/524c98. Stock condition89264 gates
diagnostic logging; it is not navigation output delivery. Its disabled branch
is emulated with an explicit zero flag. First test failure retained: the ELF
default enabled diagnostics and reached unreviewed85800; fixed the test input
to the intended disabled state, without widening execution or hiding a call.

## Maximum Safe Executable Path

Construct validated config fragments, bind typed known callbacks once, exercise
pure codecs and callback queues, consume copied data, and inspect sticky errors.
No vendor registration/engine call is allowed yet. The mandatory ABI-shape bit
is removed from readiness; mask0x7b still records first configuration, second
policy, transport ownership, AGPS receiver, stop and real host services.
Conditional optional slots10..23 are not fabricated; their activation must be
covered by complete configuration audit before constructing a vendor table.
Native CI must build/run six isolated adapter scenarios with ASan/UBSan.
