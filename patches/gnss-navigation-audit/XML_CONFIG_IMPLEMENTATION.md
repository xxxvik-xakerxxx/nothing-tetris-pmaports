# Exact B4.1 XML GET host service

Inputs verified from CI37941089972:

- XML SHA256: `7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31`
- mnld: `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`
- libmnl: `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`

`b41_xml_config_get` is an actual decoder of the verified asset, not an opaque
blob constructor or fake vendor callback. It uses libxml2 and explicit C-locale
numeric conversion. Input digest is mandatory before parsing; no network,
entity expansion, device access, defaults, state mutation or retained pointers.
Alternate assets need separate reviewed profile selection, not disabling SHA.
This hash identifies a vendor profile, not handset calibration or SKU wiring.

## Recovered result ABI

Pinned `mtk_gps_get_MNL_Config_XML_param=51ac8c` delegates to `4ff868` in GET
mode2. Actual GET producer `5003ac..5003b8` copies precisely0xfc4 bytes.

| Offset | Representation | Proven producer |
| --- | --- | --- |
| 0x00..0x13 | Feature name, zero-filled | 4ffc08..4ffc60 |
| 0x14..0x1b | Unaligned binary64 version | 500064..500070 |
| 0x1c | Config enable byte | 4ffed0..4ffed8 |
| 0x1d..0x1f | Initial zero padding | 4ffc08..4ffc14 |
| 0x20..0x23 | Sum of settings values, LE32 | 4fffcc,500194..50019c |
| 0x24..0xfc3 | 20 rows of25 binary64 values | 4fffbc..4fffd0,500330..500338 |

Repeated DCB settings are separate rows, including chip selectors6637/6686;
they are not flattened or applied to a guessed current A-die. Formats are
descriptive text, not ABI fields. Disabled features still have settings decoded.
Root `type=gps` gives OEM return1; this is NOT engine-init success.
New API deliberately returns-ENOENT for a missing feature. OEM GET retains
the caller's initialized output on a miss, so callers must keep their explicit
policy rather than assume every nonzero OEM return indicates a found feature.

Locally executed pinned GET decoder, with in-memory fopen/fgets and intercepted
libc, matched all19 stock features byte-for-byte against this layout. It never
enters SET branch4fd870, transport, library init/run or hardware. The immutable
version-string GOT slot is restored from file-backed ELF, not synthetic globals.
Execution whitelist4ff868..500524 and budget300000 instructions per feature;
unreviewed branches/calls abort rather than returning fake success.

## Concrete stock policy

Recovered values include GnssMode6, L1Only1, SignalConfig128, enabled MDTime
`1,5000,1500,0`, and disabled L5Test/CAIC/PSO. These values are now decoded,
but their library-global/first/second-config consumers must be mapped separately.
No blanket XML-resolved bit clears the frozen first-config's27 unknown bytes.
In particular, helper62a20 requests `BD_PRIORITY`, absent from this XML;
it must not be confused with the present GnssMode feature.

## Main integration and tests

New files only:
`b41_xml_config.c/.h`, `test_b41_xml_config.c`, `test_b41_xml_native.py`,
`test_b41_xml_producer.py`, `run_xml_config_ci.sh`, this evidence file.
No frozen adapter/config/query/header, APKBUILD, CI or status file edited.

Run `sh run_xml_config_ci.sh /path/to/verified/MNL_Config.xml` in native CI.
Require pkg-config, libxml2 development files and libcrypto development files;
the script does not install anything or relax sanitizer settings. It builds
only the standalone decoder fixture and compares every native result to the
already-proven layout using standard Python. Faults cover missing/oversized
inputs, unsupported name, changed/truncated asset and immutable output.
Native C is not compiled locally. Runtime package integration needs real target
libxml2/libcrypto libraries; Ubuntu validation alone is not a Bionic link test.

Use the decoded0xfc4 results to replace the XML GET host boundary; do not invoke
the vendor SET helper as a substitute for recovering policy consumers.

## Stop investigation: concrete unsafe shortcut rejected

Pinned exported `mtk_gps_uninit=52f86c` is a single RET, not resource teardown.
`mtk_gps_mnl_stop=52e2c0` tests GOT6e6710's pointee+0x68, sets level-event10, transmits offload
selector1, waits via `508744(10,6,state)`, runs teardown helpers on result2,
clears a global flag, then always tails to52c524. Wait argument6 units are not
yet proven. Timeout/non2 still proceeds to the tail; do not close receiver fds
or free callbacks just because that wait returned. Uninit is not a safe stop
replacement. The52c524 tail actually stops timers, closes internal fds, destroys
event services and tears down assistance agents; these are not caller-owned
IPC resources. No engine call/stop success is fabricated in this chunk.

Next exact delivery gate: native19-feature/sanitizer comparison, then map actual
XML consumers into second-config with per-byte producer evidence. Engine stop
requires the52c524 tail and retained-thread teardown to be proven first.
