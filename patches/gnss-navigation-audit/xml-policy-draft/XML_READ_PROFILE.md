# B4.1 actual XML reader placement and arbitration

This separate draft profiles the real reader called after the global clear at
`4fc22c BL 4fd044; 4fc230 BL 4fd20c`. Pre-initialization feature-global writes
are not an XML ingestion route: that clear erases them. The reapply path at
`4fcaf8/4fcafc` has the same clear/read ordering. No published sources changed.

## Exact placement, not another property default

Pinned `mnld` owns these second-config directory producers:

| Second-config field | Source address | Stock bytes |
| --- | --- | --- |
| `+0x406` primary | `0x88b78` | `/vendor/etc/` |
| `+0x424` preferred | `0x88b98` | `/data/vendor/gps/` |
| `+0x208` fallback for empty preferred | `0x88ae0` | `/data/vendor/gps/` |

`4fd20c` appends the literal `MNL_Config.xml` (`181e2`), using 50-byte paths.
Empty primary falls back to the actual `/vendor/etc/` literal (`4c3df4`).
Empty preferred copies the configured `+0x208` directory. No property lookup
chooses these default filenames in this bounded source path. Modified config
directories require their actual producer, not a caller boolean.

Expose independently pinned, immutable XML at **`/vendor/etc/MNL_Config.xml`**
in the owned private reader root, sourced from sealed bytes, without reopening
untrusted source paths or overwriting vendor storage. Pin:
`7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31`.
This document does not implement the mount/loader integration or authorize INIT.

The existence and content of **`/data/vendor/gps/MNL_Config.xml`** must come
from that actual owned root. Its absence in a selected CI artifact is NOT
evidence that a device's data file is absent. A deliberately fresh private
read-only root can establish absence by construction; this draft does not
silently assume it. If present, preserve legitimate per-device contents and
derive selection from their bytes rather than overwriting them to win priority.

## Actual scanner and policy

`4fd544/4fd554` call the real scanner `500910` for both files. It uses `fopen(r)`
and `fgets(1024)`, searches the lexical `<mnl_config version=` and `type=`
markers, extracts the version text, and tokenizes with `.` (`ca73`). It is NOT
an XML DOM or schema validator. The actual version arbitration uses `atof`
of **token 0 only**: pinned `21111601.6.00.00` compares as `21111601.0`.
Token 1 and remaining revision components do not break a tie. Token 2's first
two bytes classify the root using `00/0O/0L/0S/0H/0V/AB` -> statuses 1..7.
That classification is not a `type="gps"` attribute interpretation.

At `4fd558..4fd5f0`:

- Preferred fopen failure (status 0): select primary; policy becomes 7.
- Both statuses nonzero and primary numeric token greater: primary; policy 7.
- Otherwise retain preferred; policy stays 3, including ties and missing primary.
- Missing root marker, empty file or unsupported root code returns status 8,
  which is NONZERO and can still participate in selection. Never promote it
  to valid XML/engine readiness. Both absent select primary, whose reader open
  then fails; both empty retain preferred, which is not a valid configuration.

The original preferred path remains the WRITE destination even when the
selected READ path becomes vendor. `4fd600` calls `4ff868` with the policy,
selected read descriptor, original data-write descriptor, and feature scratch.
For policy 7 the reader tries `fopen(data,w)` at `4ff938`. Failure executes
`policy &= ~4` at `4ff958..4ff960` and continues parsing the selected read file.
Thus a read-only/absent data target is source-supported for READ/SET; it does
not require pretending that writing succeeded. SET bit 0 stays enabled.
Optional `.dat/.dbg` logging has its separate source branch at `4fd440` and
is not declared disabled in the production profile.

## Bundle and exact CI commands

Four new files, plus existing published `../test_b41_startup.py` for the oracle:

- `b41_xml_read_profile.py`: validates whole ELF/XML pins, 15 exact slices and
  eight exact call targets including both clear/read pairs,
  generates JSON, implements bounded lexical scanner and source arbitration.
- `test_b41_xml_read_profile.py`: offline pin/selection/fault/AST fixtures.
- `test_b41_xml_read_profile_oracle.py`: Linux CI-only actual selector + actual
  version scanner, memory-only stdio/libc mocks and finite instruction budget.
- `XML_READ_PROFILE.md`: this contract.

With `D=.../patches/gnss-navigation-audit/xml-policy-draft`, `V` the independently
pinned selected vendor artifact root (not a new OTA or stale inferred asset):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 "$D/b41_xml_read_profile.py" \
  "$V/lib64/mt6878/libmnl.so" "$V/bin/mnld" "$V/etc/MNL_Config.xml"
PYTHONDONTWRITEBYTECODE=1 python3 "$D/test_b41_xml_read_profile.py" \
  "$V/lib64/mt6878/libmnl.so" "$V/bin/mnld" "$V/etc/MNL_Config.xml"
CI=true PYTHONDONTWRITEBYTECODE=1 timeout 120s python3 \
  "$D/test_b41_xml_read_profile_oracle.py" \
  "$V/lib64/mt6878/libmnl.so" "$V/bin/mnld" "$V/etc/MNL_Config.xml"
```

Offline dependency: pyelftools. Oracle additionally needs the existing CI's
working Unicorn package; no Capstone needed. It executes 17 selection vectors
and one empty-directory fallback with bounded emulator lifetime. It executes
the actual scanner (not canned status/version returns), retains its 0/8
distinction and root table, checks all fclose lifetimes, and stops **before
the instruction at `4fd600`**. No XML reader/SET/host/engine/native ELF executes.
Optional logging is off in the fixture ONLY. No native C build is involved.
Local Mac Unicorn must not be retried (prior dependency mismatch caused SIGILL).

The pure scanner refuses unsafe root layouts, NUL/chunk/counter ambiguity,
unsupported numeric-prefix/NaN/overflow grammar, and long tokens outside its
proven subset rather than misclassifying them as fopen failure. These refusals
are not claims about OEM error behavior. Profile generation is fully pinned;
untrusted alternate versions exist only in explicit selector test vectors.

## Remaining gates

First unresolved runtime branch: actual preferred-file open/status/version in
the owned execution root. Next code integration is XML placement from sealed
assets plus legitimate second-config directory producers, after CI validates
this selector oracle. The profile does not resolve runtime libxml2/OpenSSL,
all real first/second-config inputs, CCCI/property admission or engine RX stop.
No hardware success, native reader success or INIT readiness claimed.
