# LNA startup contract: existing wrapper propagation

Status: static producer/consumer proof and native integration fixture passed
CI38282916412 at 090c61b. Source checks and actual ASAN/UBSAN consumers passed;
the private engine was never loaded or called. The initial CI failed before
compilation because the old stock artifact expired. The shared public-input
cache was refreshed once and its selection/retention corrected.
No native INIT, RF interpretation, navigation fix, or runtime admission is claimed.

## Pinned private inputs

Whole-file SHA256s are enforced by the existing
`native-agps-receiver/private_evidence.py` loader before disassembly:

- mnld: `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`
- libmnl.so: `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`

Reviewed local inputs are under
`/private/tmp/tetris-b41-mipc-closure-ci38030808388/vendor/`:
`bin/mnld` and `lib64/mt6878/libmnl.so`. Capstone is exactly 5.0.6.
No private binaries, calibration data, or vendor code copies are added here.
`evidence.py` verifies nineteen half-open instruction windows by SHA256 and
decoded anchors, checks import relocations and real GOT/table values, and emits
the complete bounded disassembly as JSON. The tests mutate every window byte
and three whole-file positions per input; all mutations must be rejected.

## Actual branch and consumer

mnld `62b64` selects first base `de520`. `62bcc` initializes `sp+94` to zero
with `stp w9,wzr,[sp,#90]`. `6345c` calls the relocation-confirmed
`ioctl(fd,16,sp+94)`. `63460` tests the sign bit: a negative return logs at
`63480`, then rejoins `63484`. `6348c/63498` copy the output unconditionally
to `de574`, exactly first+54. Failure does not abort this producer.

Matching mcudl source `gps_mcudl_each_device.c` has case16 at lines423..428
inside the `#if 0` opened at337 and closed at429. Default499..505 returns
`-EFAULT` without copying to userspace. The source pin recorded by the existing
audit is `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`; no git operation or live
kernel measurement was performed here. The inspected whole source SHA256 is
`e86503641fed4316b87f1de1aee4f367926ab2aa5010b7d77d7c938174a5cd7d`;
the source test pins it and rejects changed case/default behavior. Source input
location can be set with `TETRIS_MODULES_TREE`, matching the existing audit.
libc exposes a negative return and
errno EFAULT; `b41_first_ioctl` normalizes that receipt to `-EFAULT`.
The reference DTS's disabled LNA records alone are not this proof.

libMNL copies first+50..6f at `52e728/52e734`. GOT `6e65b8` identifies the
stored first block `71f1d0`. Lookup `52ea3c..52ea80` matches chip first+30
against the real table at `6ee1a8`: its first row is `(5,ffff6878)`, and stores
family5 at `717cb6`. The DSP chain is `52f2bc -> mtk_gps_dsp_init52f5ec ->
55471c -> 4f3634 -> 4f0bdc`, which carries config in x26.
The config pointer is saved at `4f224c` to sp+a8 and restored at `4f259c`
before the consumer; both windows are pinned as well.

MT6878's dispatch arithmetic at `4f287c..4f288c` gives308, greater than22,
so it branches to `4f3000` and rejoins at `4f28b4`. In `4f29e0..4f2a48`,
MT6878 differs from6771 and6632 and family5 is not below4: `4f2a28` therefore
loads config+54. `4f2a40` stores its low byte at sp+712 and `4f2a48` stores
mode10 at sp+713. The older literal72 alternative is bypassed.
`4f2ce4` passes the payload at sp+6b0 to `554828`; `554a10` serializes its
6a bytes via `683b9c`. The LNA byte is payload offset62, within that extent.
This establishes consumption, not firmware's physical interpretation of zero.

## Integration finding

No production correction is necessary in the inspected consumers:

- `b41_first_config_from_lna_plan` already uses the strict raw builder and
  assigns provenance80 only for the reviewed negative-receipt/retained-zero
  branch. It clears only the LNA missing bit. A successful query remains
  separate and uses `B41_FIRST_LNA_RESULT`.
- `b41_runtime_config_apply` copies the entire first result, preserves its
  missing/XML flags, and recomputes unknown provenance without requiring the
  query-success bit or successful-query provenance at54.
- `b41_startup_bundle_build` uses that runtime result and copies its bytes to
  the ABI block. `b41_native_arguments_config_missing` checks remaining input,
  provenance and XML gates; it does not require LNA-query success.

The retained receipt must remain available alongside these configurations:
profile `B41_LNA_PINNED_MCUDL_DISABLED` with status `-EFAULT` is OEM evidence;
profile `B41_LNA_PINNED_METADATA_ABSENT` with `-ENODATA` is the separately
reviewed port extension. The latter is never an OEM kernel errno. The existing
wrapper uses the same retained-value origin enum for both, so origin or
first-byte provenance alone cannot distinguish them; preserve the snapshot's
profile AND `lna_query_status`. The first-config and startup-bundle types do
not themselves contain that receipt.

No GNSS function named `runtime_args` was found in the provided workspace or
the inspected extracted CI directories. A source search for wrapper calls
found only its dedicated fixture. Thus a live executor calling the wrapper
has not been established by these sources. The unchanged fail-first collector
`b41_first_queries_collect` still rejects a negative ioctl16, and
`b41_first_config_from_queries` still requires its successful-query bit.
Parent integration must route the identity-selected LNA-plan collector receipt
through its existing builder bridge before runtime/bundle construction and
retain the diagnostic receipt, rather than use that old fail-first path.
No executor or workflow was edited.

## Verification

Read-only local source/disassembly checks:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 \
  python3 patches/gnss-navigation-audit/lna-start-contract/test_static.py MNLD LIBMNL
```

For the complete bounded disassembly, use `evidence.py MNLD LIBMNL` with the
same environment. Both commands enforce whole input hashes.

CI host only, with libxml2/OpenSSL development libraries and the verified asset:

```sh
CI=true sh patches/gnss-navigation-audit/lna-start-contract/run_ci.sh MNL_Config.xml
```

The fixture calls the actual existing wrapper, runtime/bundle builders and
native configuration gate. It compares retained-zero results with successful
zero-query results everywhere outside LNA provenance; verifies original
errno/profile and absent query-success bit; rejects negative/nonzero, wrong
profile errno, positive status, missing receipt and falsely promoted receipt;
and keeps XML, unresolved first bytes, second policy, AGPS, transport, stop and
host-service gates. Queries are synthetic callbacks, with no device/native
engine execution. Native compilation and sanitizer execution remain CI gates.
