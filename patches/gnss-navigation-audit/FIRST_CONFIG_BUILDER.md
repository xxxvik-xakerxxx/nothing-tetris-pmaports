# B4.1 First Configuration: Review Snapshot

This chunk is separate from the frozen callback adapter. No native compilation,
phone operation, registration or engine startup has been performed here.

## Executable Boundary

`b41_first_config_build()` constructs a 112-byte little-endian first block from
typed semantic inputs. Every byte has a provenance tag: unknown, pinned constant,
explicit default-profile branch, clock result, LNA result, modem result,
same-unit calibration, or transport mode. Zero bytes with unknown provenance
are NOT defaults. Return 1 means partial, never permission to start libMNL.

The explicit default profile requires evidence of mnld's `de22c == 0` branch;
it is not inferred from the phone model. Calibration requires an actual complete
16-byte input. Alternate profiles are refused. Negative queries and nonzero
status returns for output-buffer queries are refused without changing output.
With all supported inputs present, 27 bytes and XML policy remain unresolved.

`b41_first_queries_collect()` borrows an already exclusively owned open GNSS fd,
including fd 0. The real `b41_first_ioctl()` boundary normalizes libc errno to
negative errno immediately. Collection queries 11, 30, 16, 21, stops at the first
failure, and retains earlier successful values as evidence only. It neither
opens nor closes, retries, resets, sets properties nor starts firmware/engine.

`b41_first_config_from_queries()` bridges a complete successful query snapshot
to the typed builder. It rejects partial snapshots, conflicting supplied query
inputs and failures without changing the output. It still returns only partial.
An ioctl30 result is retained separately for AGPS131, never written as Hz into
first+0x18. The collection order is our bounded preflight, not a claim that all
intervening mnld startup policy has been reproduced.

## Producer Evidence

Pinned mnld SHA256:
`285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`.
Pinned libMNL SHA256:
`3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`.
Kernel modules commit: `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`.

| Query | Exact mnld producer | Pinned kernel contract |
| --- | --- | --- |
| 11 | `62280..62544`, ioctl at `62298`, null third argument | return clock flag via `gps_dl_link_get_clock_flag()` |
| 30 | `632e0..6332c`, ioctl at `632f0`, null third argument; return stored sp+0x90 | enabled by GPS_DL_GET_PLATFORM_CLOCK_FREQ; return 0=26MHz, 1=52MHz, negative if regmap absent |
| 16 | ioctl `6345c`, sp+0x94 u32 output, copied at `63498` to first+0x54 even on failure | LNA case is inside `#if 0` in gps_mcudl_each_device.c; unsupported default is -EFAULT |
| 21 | helper `5dcc0..5ddc0`, ioctl at `5dcf8` with u32 output | reads DT-supplied b13_gps_status_addr and copies u32; absent address/copy failure is -EFAULT |

Clock helper marks first+0x13 FF for flags 0/2/3/16/32/48/64, FE otherwise;
low-byte flag81 additionally selects 52MHz at first+0x18. Stock masks negative
ioctl11 to a byte; this implementation refuses that unsafe continuation.
The helper also sets `vendor.gps.clock.type`; the native host-service equivalent
remains a gate, not an ignored side effect.

Query21's stock helper selects override88c74 when not -1, otherwise actual
ioctl output. Our builder tags the actual output but does not pretend that the
unresolved override policy has been reproduced. Query16's failed stock path
copies stale stack bytes; our path never promotes that value. Pinned source30
also ignores regmap_read's error: fixing that producer is a main-owned kernel
integration decision, outside this chunk.

## Required Assets And Policy

XML paths are `/data/vendor/gps/MNL_Config.xml`, then `/vendor/etc/MNL_Config.xml`.
The libMNL path producer and output structure size0xfc4 are recovered. Local
`local/stock-b41/evolution-device/proprietary-files.txt:2522` declares
`vendor/etc/MNL_Config.xml`; no matching extracted XML contents were found in
the inspected local asset trees. Presence of XML bytes is not parsed policy;
`xml_policy_missing` is always set. No XML values or fallback defaults guessed.

Legacy calibration producer `56d00..57184` reads 16 bytes from the same unit:
EL6N_000 at160 for chip strings 0x6735/0x0321/0x0335/0x0337; otherwise ML4A_000,
at64 for 0x6893/0x6855/0x6789 and160 otherwise. Both files are under
`/mnt/vendor/nvdata/md/NVRAM/CALIBRAT/`. Actual chip-string selection is required;
the SoC marketing name is not proof. Short reads retain stale bytes in stock
and are rejected here. Modern de3bc/property branch and profile overrides remain
unresolved. All test calibration is synthetic, not extracted unique data.

Unknown first-block ranges are 0x20..23, 0x28..3b, 0x50, 0x5b, 0x6c when all
supported inputs are supplied. XML policy, global88794, de304/de308/mode,
secondary receiver selection, profile overrides, MPE and feature policy remain
explicit gates. Full second0x444 policy, exclusive transport lifecycle/stop,
mandatory host services and assistance routing also still gate mnl_run.

## Main CI Integration

Run `sh patches/gnss-navigation-audit/run_first_config_ci.sh` in Ubuntu native
validation with ASan/UBSan unchanged. This compiles and runs two separate
fixtures: typed config (256 clock flags) and query/bridge ownership/error paths.
The runner has not been executed locally. Do not change the frozen adapter test
to add these fixtures before coordinating the aggregate snapshot.

For an additional Bionic standalone artifact, compile b41_first_config.c and
test_b41_first_config.c into one fixture; compile b41_first_config.c,
b41_first_queries.c and test_b41_first_queries.c into the other. Run those only
in the main-owned isolated artifact test environment. Query tests inject
synthetic responses, never invoke real ioctl. The production ioctl wrapper is
linked for ABI checking, not exercised against hardware. No libMNL link needed.

Offline checks passed: first-block early producer, XML path, clock helper,
host-fd acquisition, 18 calibration vectors, and 8 additional query30/21/16
vectors. The initial query21 test stopped at an undersized whitelist boundary;
after reviewing its epilogue and extending to5ddc0, all cases passed.
Shell syntax and Python parsing passed; native tests await CI.

Next runtime gate, owned by main: only after native CI and lifecycle review,
borrow the sole GNSS owner's fd and record fail-first query11/30/16/21 results.
On the unchanged pinned mcudl ioctl path, expect query16=-EFAULT; stop, preserve
earlier evidence, and do not call mnl_run. Resolve LNA via a justified actual
kernel/firmware contract, obtain the real XML asset and policy, complete other
startup/stop services, then review permission for engine initialization.
