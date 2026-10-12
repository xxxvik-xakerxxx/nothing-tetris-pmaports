# Native satellite mask and normal-start completion

Status: Partial candidate. Static checks, the 4,096-vector native sanitizer
fixture and ARM64 Bionic target link passed parent CI38254829662 at d7b6f9e.
Source preparation used no engine, emulator, local compiler or phone. Parent
integration also corrected the common first constructor's provenance and its
related fixtures. No engine INIT or position fix is established.

## New result

The earlier first constructor marked `first+58..5a` as CONSTANT zero. These are
not final constants. Parent integration now leaves them UNKNOWN, with fixtures
checking that runtime configuration and the startup bundle preserve that gate.
Two independent mnld startup producers overwrite them.
This candidate implements the twelve-option AGPS satellite-mask producer and
the normal-start selector, repairing three incorrect provenance receipts.
This is a configuration correction, not an AGPS receiver or permission to INIT.

The quiet receiver builder in `../b41_receiver_inputs.md` changes second-block
logging/build policy. It cannot produce these first-block fields. This addition
composes with it without a property service, stock globals, or property receipts.

## Exact private inputs

Outer workspace: `/Users/vlysko/Documents/Nothing CMF Phone 1`.
Both binaries reside in
`worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/` there:

| File | SHA256 |
| --- | --- |
| mnld | `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83` |
| libmnl.so | `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90` |

Repository baseline observed: `d0336ee085585c56d80e17e8cbb12bd641219774`.
All addresses below are ELF virtual addresses, not file offsets or live ASLR
addresses. Tests validate hashes before decoding. No extracted firmware bytes
are copied into the repository. Small ABI tables below are recovered constants.

## Producer trace

`mnld51760..51784` copies exactly fourteen request bytes to `9a925`, using
overlapping eight-byte copies at offsets0 and6. `52074..52098` repeats this
producer. The input is not a twelve-bit integer and not an Android property.

| Request byte | Native option | Destination bit |
| --- | --- | --- |
| 1 | GPS | 0 |
| 2 | GLONASS | 1 |
| 3 | BeiDou | 2 |
| 4 | Galileo | 3 |
| 5 | assisted GLONASS | 4 |
| 6 | assisted GPS | 5 |
| 7 | assisted BeiDou | 6 |
| 8 | assisted Galileo | 7 |
| 10 | extension10, meaning unconfirmed | 9 |
| 11 | extension11, meaning unconfirmed | 8 |
| 12 | extension12, meaning unconfirmed | 11 |
| 13 | extension13, meaning unconfirmed | 10 |

The logging format at135ac names bytes0..9; byte0 is SIB8/16 enable and byte9
LPPE enable. Neither belongs to this mask, and neither is silently represented
as a completed native service. The additional fields published atddd94/ddd98
remain separate from this candidate.

Exact reduction:

- 51788 loads bytes10..13;517a0 widens;517b0 masks each lane to bit0;
  517bc shifts by the four little-endian halfwords at22ab8:9,8,11,10.
- 5178c loads bytes4..7;517a8 widens;517b8 shifts by22b50:3,4,5,6;
  517c8 masks with22b88:8,16,32,64. Thus only each input's low bit survives.
- 517c0 shifts byte8 bit0 to7;517ec/517f4 place bytes2/3 bit0 at1/2;
  5181c extracts byte1 bit0. The OR tree ends at51830.
- 5183c stores the halfword atddd90. The second handler repeats these
  instructions at addresses plus914, ending at52150.
- 63640/63650 load that halfword;63658 stores it tode578. First block starts
  atde520 (62b64 and63c34), so the final field is first+58.

Native settings require canonical booleans0/1; unlike stock, invalid bytes2..255
are rejected instead of silently truncated. No default satellite availability
or assistance capability is inferred. In particular extension settings are
explicit inputs with opaque names; this audit does not identify their systems.

Normal/factory is independent:5c598/5c59c/5c5b8 setde4a4=1 in the handler
identified by the literal `factory_mnld_gps_start` atb44b;5c660/5c664 clear it.
Startup63530 reads it,63544 compares to1,6354c forms `!=1`, and63564 stores
the byte atde57a = first+5a. The native NORMAL_START choice emits1. FACTORY_START
is refused because the factory handler's other side effects are not implemented.
This choice is not a hot/cold restart command or a statement about a live global.

## Library evidence

The public run entry52e2bc branches to52b638. At52b680/52b688 the first block's
50..6f range, including all three fields, is copied to library-owned storage.
The lower initialization routine52e580 separately copies its x2 configuration
at52e728/52e734 and loads the mask at52e86c. Its BICS/CSET sequence tests whether
both bits in each pair are present:

| Pair | Instructions | Interpretation justified by producer names |
| --- | --- | --- |
| 21 | 52e91c/52e924/52e92c | GPS plus assisted GPS |
| 12 | 52e944/52e94c | GLONASS plus assisted GLONASS |
| 44 | 52e95c/52e964 | BeiDou plus assisted BeiDou |
| 88 | 52e984/52e98c | Galileo plus assisted Galileo |
| 500 | 52e9ac/52e9b4 | extension pair, system not identified |
| a00 | 52e9c4/52e9cc | extension pair, system not identified |

These are static copy/consumer observations, not a claim that the entire
runtime call route to52e580 was exercised or that assisted positioning works.

## Parent integration

Add `b41_native_satellite_config.c` to the native candidate sources. The header
uses the existing first-config structure through a relative include; no other
object is needed by this pure producer. Provenance81 is local to this candidate
(existing LNA producer uses80); reserve or renumber it during parent integration.

After first-config construction, apply explicitly populated settings:

```c
status = b41_native_satellite_config_apply(&first, &native_settings, &first);
if (status < 0) return status;
status = b41_native_start_config_apply(&first, B41_NATIVE_NORMAL_START, &first);
if (status < 0) return status;
```

Pass that `first` into startup_bundle_build. Runtime config currently preserves
58..5a; do not reconstruct first afterward. The two producers can be ordered
either way. Use the native configuration decision for every option, not bytes
read from mnld and not a guessed all-enabled mask. An ordinary unassisted
configuration must explicitly disable assisted options; selecting constellation
bits alone does not demonstrate chip capability or a fix.

Both producers support in-place application, copy into a local result before
publication, retain no pointers and own no live resource. Apply only before
registration under the parent's single configuration owner. Concurrent writes
or mutation of an active engine are outside this API. Unknown bytes may be
replaced; an existing conflicting nonconstant receipt returnsESTALE. Only the
old zero CONSTANT receipts are specially repaired. Satellite-only application
revokes the stale5a CONSTANT receipt until the start producer resolves it.
Missing-input masks (including unknown bits), XML and all lifetime gates survive.
Return1 means partial even if unresolved_bytes becomes0.

Native fixtures for parent-owned CI (not run locally):

```sh
CI=true sh patches/gnss-navigation-audit/native-config-completion/run_ci.sh
CI=true BIONIC_CC=/path/to/aarch64-linux-android28-clang \
  sh patches/gnss-navigation-audit/native-config-completion/run_ci.sh \
  --bionic-compile /path/to/output-fixture
```

The default CI route uses ASan/UBSan and synthetic inputs only. The Bionic route
compiles without running. The CI-passed fixtures cover4096 settings, every invalid byte for
every setting, aliasing/idempotence, conflict rejection, unchanged failure
output, normal/factory policy and preservation of unrelated fields and gates.
No vendor object is linked.

Static validation from the outer workspace:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 \
python3 upstream/nothing-tetris-pmaports/patches/gnss-navigation-audit/native-config-completion/test_static.py \
  worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/mnld \
  worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/libmnl.so
```

Seven static tests pass, including both producer traces, complete Boolean
algebra, hash rejection and consumer pairs; shell syntax passes. Static Python
checks do not themselves execute the C candidate. Parent CI executed the native
fixture and compiled the target independently. Actual AGPS reception, remaining config
producers and the existing owner/XML/stop gates still require parent work.
No real INIT, fix, portability or lifecycle result is claimed.
