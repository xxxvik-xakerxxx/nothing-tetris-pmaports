# B4.1 XML global backend

Status: partial startup, concrete global-write implementation. Unpublished sidecar;
frozen runtime/first-config/adapter/worker and global CI are unchanged.
No C compilation, device access or native engine calls performed locally.

## Exact Profile And Ownership

Input library SHA256:
`3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`.
Input XML SHA256:
`7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31`.
The frozen GET decoder enforces that XML digest for every request.

SET consumer `4fd870` writes through GOT `6e6660`, whose file-backed value is
`7178b8`. This is a separate engine-global object, NOT either startup config.
DCB obtains actual library chip identity through GOT `6e6610` -> `6f2dac`.
These are ELF-relative virtual addresses, not physical device addresses.

`b41_xml_global_owner_bind` checks the complete associated ELF digest and both
relocated GOT pointers. The legitimate Bionic loader must supply/retain that
mapped library and file, its readable GOT/writable global spans, and exclusive
pre-engine ownership. The API is not a loader; supplying an address/extent alone
does not establish memory permissions, file-to-mapping identity or Bionic ABI.
Do not pass a musl dlopen object or manufacture a mapped object in production.
The native fixture uses synthetic storage ONLY to test byte writes and faults.

`owner_apply` performs exact XML GET, complete per-feature planning, then writes
only marked bytes into the owned library globals. It preserves unrelated fields
and does not invent initial values. First application failure latches quarantine;
correcting XML/GOT/chip afterward cannot revive it. Exposure is irreversible and
must occur before registration/init; no subsequent writes or unloading are
provided. This is single-controller storage, not a concurrent setter API.

`owner_apply_stock` preflights all19 features in exact XML document order into
temporary storage, composes the15 enabled consumers, and skips the4 disabled
ones. It snapshots/rechecks the actual mapped chip, both GOTs and original global
bytes before committing only the combined write mask. Failure leaves globals
and receipt untouched and latches quarantine. Success returns enabled/disabled
feature masks and byte provenance; another stock/per-feature setter is refused.
This is a complete producer for the supported global-byte portion, not an atomic
CPU-wide transaction or authorization to call native init. Exclusive ownership
remains required. DCB reads actual library state, never a fabricated property.

## Recovered Consumers

All offsets below are relative to global `7178b8`:

| Feature | Stores | Consumer evidence |
| --- | --- | --- |
| CoTMS | c,d bytes; 10,12,14,16 u16 | 4fd9c4..4fda3c; version threshold at a660 is 4.4 |
| SwitchTIA | e byte | 4fda40..4fda64 |
| GLP | 45 byte; flags8 OR1 | 4fdc98..4fdcc8 |
| GnssMode | 358 byte; flags8 OR4 | 4fe6b4..4fe6e8 |
| IFB | 1e0..248, fourteen binary64 values | 4fe8f4..4fe980 |
| GGTO | 300..318, four binary64 values | 4ff184..4ff1d0, version1 |
| L1Only | 2ac byte when converted setting nonzero | 4fe9cc..4fe9f8 |
| DisableSignal | 324 byte, version1/range0..31 | 4ff200..4ff240 |
| MDTime | 2c0 version; 2cb option; 2cc interval; 2ce window; 2d0 sync; flags8 OR40 | 4feb38..4febb8 |
| Time_Source | 2d4 RAT,2d5 SIB,2d6 packed SIB/RAT | 4fed64..4feda0 |
| Bluesky | 2b6 byte | 4feda4..4fedcc |
| GNSSPower | 348..354, four binary32 values | 4ff500..4ff55c, version1 |
| SignalConfig | 35c..370, six u32 values | 4fec70..4fecd4 |
| OSNMA | 374 version binary32,378 option | 4ff56c..4ff5b4, stock optional-row early exit |
| DCB | 198,1a8,1b8,1c8 first row; 1a0,1b0,1c0 second row | 4fe8bc..4fe8f0,4fe9fc,4fea48,4fecec..4fed60 |

MDTime uses max(interval,1) and limits window to half that interval before u16
storage. CoTMS count3 includes the proven GET-zero fourth slot, not an unresolved
default. SignalConfig count1 similarly has five GET-zero slots; the planner
rejects nonzero extras. OSNMA's stock single setting does NOT install optional
keys/config arrays: the actual branch writes version/option then skips that loop.
Binary32 conversion requires the usual nearest rounding mode. Nonfinite or
unsafe integer conversions are refused rather than guessed ARM FCVT saturation.

DCB requires a real chip snapshot from the owned library and accepts only the
explicit XML profiles6637/6686: rows0/1 or3/4 selected by matching selector row2/5.
Unknown/uninitialized chip values fail; OEM unmatched-chip fallback is NOT
promoted to universal calibration. This is vendor profile data, not handset
calibration. No vendor assets are added to this repository.

Disabled L5Test/CAIC/Blanking/PSO return EACCES. Unknown features, versions, DCB
profiles, extra OSNMA policy, or unsupported setting layouts fail explicitly.
The stock batch skips disabled entries instead of calling their planners.
OEM reader500198/5001a0 likewise skips config0;5001a4/5001a8 additionally gates
SET on bit0 of the actual reader-policy object, reaching SET at500378. That
reader-policy provenance/ordering is not supplied by the global-only receipt.

## Evidence And CI

The new bounded oracle executes `4fd870..4ff864` but stops at `4fe320` BEFORE
serialization, output dispatch, file logging, or transport. It intercepts only
allocation/memset/strncmp/strlen. Its code hook rejects unreviewed execution.
Exact GET output is used as input. Values AND the actual global-store byte mask
are captured. All15 enabled stock features, both DCB profiles, and root-selector
inputs0/1/ff are exercised. No callback/engine routine is loaded natively.

Native fixtures check exact-profile bind, stale GOT, first-error retention,
post-exposure refusal, unknown chip/no fallback, disabled feature, nonfinite
conversion, and unsupported nonzero unused settings. C has NOT been compiled
locally. Native and emulation are separate CI steps so oracle failure cannot
prevent running native fixtures.
The native fixture also checks full-stock byte/mask composition for both DCB
profiles, untouched receipt/globals on failed preflight, disabled feature masks,
preservation of unrelated bytes, first-error retention and repeat/exposure gates.

CI dependencies: compiler, pkg-config, libxml2/libcrypto development packages,
libm; Python pyelftools and Unicorn for the separate oracle. No Capstone needed.
Keep ASAN/UBSAN and assertions enabled. From the audit directory, with the exact
stock-asset paths assigned to LIB and XML:

```sh
CI=true sh run_xml_globals_ci.sh "$LIB" "$XML" "$RUNNER_TEMP/gps-xml-global-ci"
PYTHONDONTWRITEBYTECODE=1 python3 test_b41_xml_set_consumers.py \
  "$LIB" "$XML" "$RUNNER_TEMP/gps-xml-global-ci/test_xml_globals"
```

The third runner argument must be a NEW directory. It retains the compiled
fixture plus2048-byte value/mask outputs for the separate oracle step. Without
that argument it uses/removes a temporary directory and runs native tests only.
It now refuses non-CI execution and bounds compiler/fixture processes. No
command-line _GNU_SOURCE override is passed: the published decoder defines it.
The aggregate native+Bionic entrypoint and complete staging closure are in
[XML_ADC_CI.md](XML_ADC_CI.md). Bionic XML requires genuine target-built libxml2
and OpenSSL headers/libraries; the NDK alone is insufficient. No stub substitutes.

## Gates Not Cleared

This does NOT clear first.xml_policy_missing. Global byte writes are now mapped,
but full SET continues at4fe320 with serialization, category5 output dispatch,
and optional log/counter effects. File selection (/data vs/vendor), placement
relative to native init/global resets, and those host services need integration
proof. BD_PRIORITY remains an independent missing-feature GET/retained-policy
contract; it is not GnssMode and does not imply a GPIO pin.

No callback/transport/AGPS receiver/stop gates are cleared. Native register/init
and stop remain forbidden until active mandatory services and retained-thread
ownership are proven. uninit=RET is not safe teardown.

RX source boundary, independently read with git show at module pin
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835:
gps_mcudl/linux/gps_mcudl_each_device.c read does NOT inspect O_NONBLOCK;
gps_mcudl/xlink/gps_mcudl_each_link.c calls read_with_timeout with
GPS_DL_RW_NO_TIMEOUT and can wait after poll. A nonblocking fd or successful poll
is not proof of bounded read/stop. The real RX owner needs isolated read-worker
ownership and control-thread deadline/quarantine; no live RX implementation is
claimed by this XML delivery.

Next gate: native ASAN/UBSAN byte/mask comparison, then audited Bionic loader
association and XML application ordering/host dispatch. No phone probe in this
chunk and no claim of GNSS fix or hardware readiness.
