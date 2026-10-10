# B4.1 slot0 ADC backend candidate

Owned new files: b41_slot0_adc.c/h, test_b41_slot0_adc.c,
test_b41_slot0_adc_producer.py, run_slot0_adc_ci.sh and this document.
No frozen output/identity/worker/adapter/CI files changed. No engine calls,
hardware operations, calibration writes or native local compilation.

## Exact producers

Pinned mnld SHA256:
285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83.

- Event3 at5dfd8 reads fd88790; -1 exits without capture. 5dfec/5e004 request
  0x50000 bytes. 5e030..5e064 writes the entire calloc buffer to ADC.txt, even
  after a short/failed read: the new capture API deliberately rejects that.
- 5d770..5d8f0 processes1280 rows, each256 bytes/64 little-endian words.
  Strings14653/22082/db2f are `$PMTKJAM3,%d,%d`, `,%08X`, `*%02X\r\n`.
  One-based row counter; total1280; upper-case eight-digit words.
- 7b820 XORs ALL bytes, including leading `$`. This is not a standard NMEA
  checksum. Do not normalize it or forward this diagnostic as navigation data.
- 7f090 emits u32LE260, u32LE2; 37450 adds strlen as u32LE then bytes WITHOUT
  NUL/presence byte. 37ef0 uses __write_chk, not AGPS sendto/150 framing.
  Its connection object at9a348+120 must be owned separately from gpsdl RX
  and the existing raw/app output streams. Do not reuse their fds by guess.

The packet constructor and finite1280-row synchronous delivery implement that
real service, preserving the first failed delivery without replay. No borrowed
samples/output pointers are retained. Sink failure halts before the next row.
The sink must perform real bounded/nonblocking accepted delivery, not merely
count notifications. The iteration bound cannot bound an arbitrary sink's work.

Capture reads an already-open exclusive owner's O_NONBLOCK FIFO once; it never
opens/closes/modifies hardware fds. Character devices and regular files are
rejected before read: pinned gps_mcudl read ignores O_NONBLOCK and can block.
On syscall/short-read error it wipes capture
storage. The caller must preserve raw capture to a newly owned diagnostic file
before delivery if OEM ADC.txt persistence is wanted. This is NOT NV calibration
and must never overwrite a calibration file or partition. No guessed fd lookup
or fabricated capture is installed into the frozen callback.

`snapshot_take` transfers only a real exact-size320KiB fully sealed regular-file
snapshot and a distinct already-open writable NONBLOCK diagnostic FIFO, requiring
PIPE_BUF >=640. It does not create/capture samples, authenticate their hardware
producer or impersonate the OEM connection. Validation failure transfers nothing.
`snapshot_step` checks retained inode/type/flags/seals, preads one256-byte row,
then makes one atomic packet write.1280 accepted packets complete the owner.
Actual complete delivery is counted even if subsequent signal-mask restoration
fails. Backpressure, changed descriptor identity, broken reader or signal errors
latch the first failure with no replay/reset and no FD release. Dedicated host
thread ownership is required; external close/flag mutation is forbidden, and
stat checks are fault detection, not synchronization against concurrent writers.
SIGPIPE is contained with a thread-local pthread mask, preserving preexisting
pending signals and process disposition. These owners remain leased until exit.

## Corrections and unresolved mandatory branches

The older event0 summary is incomplete: 5defc's imported85890 is
`mtk_gps_get_rtc_info`, NOT a position getter. It writes two doubles atsp28/sp30;
5e11c..5e198 compares these with actual88c0c runtime thresholds. The conditional
FM branch opens `/proc/fm` (12b55), checks byte0 == '2', then opens `dev/fm`
(138fd, notably relative in OEM) and invokes ioctl0xc008f520 with runtime values.
This cannot be replaced by guessed GNSS position publication or unconditional
success. At5e42c actual56c70/56c50 profile checks additionally gate the large
position/state publication branch. These effects are NOT yet implemented.

ADC fd88790 is initially -1; a relative relocation86760 points to it. A negative
text-reference search alone does NOT prove immutable/disabled lifetime. Need
actual fd producer and diagnostic connection9a468 owner before event3 binding.
Do not claim absent fd as a universal profile default.

Event13 calls55220: source includes611f0 condition,74e20/74fd0,36040 and tail
5d3d0; one branch reaches UDF552c4. It is not a safe generic restart callback.
Actual internal libMNL RX stop/join/timer fallback is still unresolved; retaining
fd/callback storage is mandatory if stop cannot be proven. No engine init/run
permission is inferred from the ADC backend or this metadata.

Further exact stop tracing: the join helper529e04 installs SIGRTMIN handler
5294b8 (GOT6e78c0), arms timer6ee180, then calls pthread_join529eb8. That
handler identifies join target6ee118 against17 thread handles and calls the
app-output callback at5296d4 while processing timeout. It is not a simple
pthread-exit/join acknowledgement, nor a proven finite stop primitive. Using
its timer expiry as a successful RX stop would be incorrect. Exported
mtk_gps_mnl_stop52e2c0 also performs queue/state operations and timeout paths;
its return alone cannot authorize closing a descriptor still read by RX.

## Integration commands

Pinned producer oracle (Python elftools+Unicorn; bounded/intercepted, not native):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT/test_b41_slot0_adc_producer.py" "$ASSETS/vendor/bin/mnld"
```

Native Ubuntu ASAN/UBSAN fixture (compiler and pthread required):

```sh
CI=true sh "$AUDIT/run_slot0_adc_ci.sh"
```

Bionic API28: compile b41_slot0_adc.c + test_b41_slot0_adc.c with existing
warnings policy and `-pthread`; it is build-only, not an ARM execution claim.
Native ASAN/UBSAN uses `-pthread` too. No libxml/libcrypto or frozen C dependency
is needed for ADC. Producer oracle reuses tracked test_b41_startup.py.
The fixture exercises actual sealed memfd/FIFO delivery,1280 rows, unsealed
rejection, sticky backpressure/EPIPE/flag faults and descriptor reuse. Its bytes
are synthetic fixture samples, never handset calibration or proof of capture.
The single sidecar entrypoint and staging closure are in
[XML_ADC_CI.md](XML_ADC_CI.md); physical device capture remains unimplemented.
Next runtime gate is a legitimate ADC/diagnostic owner and actual receiver
delivery, after engine-wide mandatory effects and internal RX stop are resolved.
Native/source fixture outcomes must be recorded separately from hardware success.
