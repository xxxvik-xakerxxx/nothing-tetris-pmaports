# Frozen B4.1 MIPC Closure Contract

This bundle is review-ready source/evidence, not GNSS readiness. Parent owns
adapter/mocks/linkage integration and shared CI. No integration patch is included.

## Identity And Scope

- Release: Tetris_B4.1-260415-1709.
- Actual library: vendor/lib64/libmipc.so, 93696 bytes.
- SHA256: aecc344486ef18905eaf7b6ef4f8dcaf266e58b2e87a355cd8d2d7b27ae09d56.
- mnld SHA256: 285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83.
- libMNL SHA256: 3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90.
- mnld DT_NEEDED literal is libmipc.so; no RPATH/RUNPATH/directory prefix.
- libMNL has no direct MIPC dependency.

Frozen owned files, in bundle-hash order:

1. b41_mipc_checked_tag.c
2. b41_mipc_checked_tag.h
3. test_b41_mipc_checked_tag.c
4. run_mipc_checked_tag_ci.sh
5. b41_mipc_elf_audit.py
6. test_b41_mipc_elf_audit.py
7. b41_mipc_exact_contract.py
8. test_b41_mipc_exact_contract.py
9. b41_mipc_accessor_oracle.py
10. test_b41_mipc_accessor_oracle.py
11. MIPC_B41_CLOSURE_CONTRACT.md

Existing adapter/first-config/capability/association headers are parent-owned
dependencies, not additional new untracked files in this bundle. Python modules
import one another from this directory. No generated pycache is included.

## Required Adapter Integration

Original tag_word's get_val_ptr(response, tag, NULL) followed by memcpy4 was unsafe
for short tags. Parent now reports integration of b41_mipc_checked_tag_word into
adapter/test/runner and full Bionic CI linkage, plus16 short-tag vectors
(fault11..26). Parent owns these production/shared changes. The separate
checked-tag fixture intentionally allocates exact short extents for ASAN coverage.
No integration patch is included and none should be applied over parent's work.

The actual accessor at f200 masks tag to15 bits, retrieves node value at+0x20,
returns TLV+4, and writes uint16 length through argument3 at f260 (read f24c).
It returns nonnull even for lengths0..3. Therefore require nonnull AND length>=4
before copying a word. No uint32_t/size_t length-output substitution is valid.

The hashmap allocation contains copied header4+payload (e678..e6ec); borrowed
pointer use requires exclusive response ownership with no mutation/deinit.
Message deinit frees the hashmap nodes and message (eda0..edcc/e0f0..e198).
sync_timeout_with_cause transfers response to its nonnull output pointer at10610;
with NULL output it deinitializes that response at10618.

The regular wire TLV has u16 tag/+0 and length/+2, four-byte header, and stride
(length+11)&~7 after the16-byte message header. Zero length is a special12-byte
record, not an empty scalar. The deserializer reads zero-length record+12 atf6dc
before the full payload check atf70c/710. This helper cannot repair that earlier
vendor parser bounds gap; the bundle makes no full parser-safety claim.

CREATE_THREAD detaches atda98. DELETE_THREAD atdb00 only frees its descriptor.
mipc_deinit calls it at107ac, without a pthread_join acknowledgement. Use the
sole-owner dedicated child and bounded parent exit/reap lifecycle. Do not treat
deinit return as permission to unload, reuse, reinitialize, or replace its RX
owner while the child is alive. Accessor success is not engine startup success.

## Stock Extraction Dependency Targets

Reuse the existing vendor extraction stage/artifact rather than redownloading
vendor archives for each dependency. These three basenames are actual DT_NEEDED:

| Primary selected-asset target | Alternate discovery target |
| --- | --- |
| vendor/lib64/libmtkrillog.so | vendor/lib64/mt6878/libmtkrillog.so |
| vendor/lib64/libtrm.so | vendor/lib64/mt6878/libtrm.so |
| vendor/lib64/libmtkproperty.so | vendor/lib64/mt6878/libmtkproperty.so |

Relative extraction NAMES are lib64/<basename> and lib64/mt6878/<basename>, matching
the existing extraction prefix loop. These are discovery paths, not a claim that
both or either path exists: DT_NEEDED alone does not encode vendor placement.
Record the actual extracted path/size/SHA in the existing manifest. Audit each
library's transitive DT_NEEDED; if both locations contain candidates, do not
silently select by guessed search order. Existing closure audit rejects ambiguity.

The four additional direct dependencies are libc++.so, libc.so, libm.so, libdl.so.
Supply the existing legitimate Bionic platform closure. Typical discovery paths
are system/lib64/<basename>; exact installed Bionic staging/namespace ownership
must come from parent's validated runtime, not the host's libraries or a guessed
Android system/APEX path. No additional platform asset hashes are invented here.

The selected local vendor asset directory currently lacks all seven dependency
files. File/name closure remains incomplete. Even a completed file/name audit
does not prove symbol versions, loader namespace policy, property service or
modem readiness. Real /dev/ttyCMIPC5 CCCI ownership and modem141 response are
runtime prerequisites; this bundle performs neither operation.

## Commands And Verification

From the audit directory, use PYTHONDONTWRITEBYTECODE=1 throughout.

```
python test_b41_mipc_elf_audit.py
TETRIS_B41_MIPC_SO="$LIBMIPC" python test_b41_mipc_exact_contract.py
TETRIS_B41_MIPC_SO="$LIBMIPC" TETRIS_MIPC_ACCESSOR_EMULATION=1 \
  python test_b41_mipc_accessor_oracle.py
python b41_mipc_elf_audit.py --mnld "$MNLD" --libmnl "$LIBMNL" \
  --libmipc "$LIBMIPC" --libmipc-sha256 "$MANIFEST_SHA"
python b41_mipc_exact_contract.py "$LIBMIPC" \
  --dependency-dir "$VENDOR_LIB64" --dependency-dir "$BIONIC_LIB64"
```

The exact contract/closure command returns2 if files/symbol names are missing;
do not suppress that exit code in a required closure gate. The structural ELF
audit can return0 while semantic gates remain unresolved: it is evidence only.
Neither script can authorize engine startup.

Native CI only:

```
sh run_mipc_checked_tag_ci.sh
```

Runner has CI guard and compile/test timeouts; native ASAN/UBSAN fixtures and
Bionic compilation must be parent-integrated. No C was compiled locally here.

Local interpreter used: /private/tmp/tetris-modem-auth-venv/bin/python with
PYTHONPATH=/opt/homebrew/lib/python3.14/site-packages. ELF/exact audits require
pyelftools/Capstone; getter emulation additionally requires Unicorn. It uses one
Uc, two coalesced mappings, explicit hook cleanup, an intercepted hashmap lookup
and no native loading/parser/transport/engine calls. Earlier agent runs passed
two accessor tests including72 vectors, five structural and five exact/closure
tests with the exact asset environment supplied.

Parent's latest local run passed ELF5 and exact4 with one environment skip, but
accessor export test printed '.' before the process exited132 (SIGILL) during
Mac emulation using the interpreter/PYTHONPATH combination above. That is NOT an
accessor oracle pass. A native Unicorn/runtime/architecture or sandbox mismatch
is possible, particularly with a venv plus Homebrew Python3.14 packages, but
root cause is unproven. Do not retry the local emulator or suppress the signal.
Require the actual72 vectors in Linux CI with its consistent interpreter/native
library environment. Read-only inventory does not require importing Unicorn.
Parent reports original native/Bionic CI38029177349 and exact instruction oracle
CI38029707052 succeeded; these are not claims that new checked-helper integration
or live GNSS has passed.

Freeze hashes are reported separately. Aggregate algorithm: SHA256 over each
filename UTF-8, one NUL, then its exact file bytes, in the11-file order above.
