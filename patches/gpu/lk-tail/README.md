# B4.1 LK Source-Tail Audit Candidate

Status: **incomplete producer proof**. No upload/start boundary is cleared.
The requested complete scratch/zero proof has not been established. This
candidate closes specific local alternatives and records the remaining calls,
stores, system effects and control-flow exits instead of declaring them safe.

Only new files in this directory are owned by this work. No firmware bytes,
private snapshot, native binary, packaging change or runtime code is included.
All analysis is static ARM64 disassembly with Capstone 5.0.6; there is no
emulation, native compilation, RV33 decoding, live operation, CI or push.

## Inputs

- LK payload SHA256:
  `431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a`.
  The tool parses the first 512-byte MTK header and pins the payload, not the
  whole container. It does not repeat certificate/signature authentication.
- Private signed-primary snapshot: 156064 bytes, SHA256
  `9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7`.
  Authentication provenance comes from the existing transform/snapshot work.
  This tool verifies identity only and does not decode its instructions.
- Sixteen complete contiguous LK windows are individually pinned. There are
  1937 decoded ARM64 instructions and 150 store/system-effect census entries.
  These are bounded windows, not the entire executable or a complete call tree.

## Checked Findings

1. At `0x1ed74`, LK retrieves the mapped reservation; `0x1ed8c` sets the source
   to mapping + `0x18`. The loader receives that pointer at `0x1ed90`. The
   copy at `0x1ee08..0x1ee18` reads 64686 words, or `0x3f2b8` bytes. Therefore
   the extra 102680 bytes are mapping-relative `[0x261b8, 0x3f2d0)`, copied to
   SRAM-relative `[0x261a0, 0x3f2b8)`. This interval is inside the 1 MiB
   reservation, but beyond the signed primary. Being in-bounds is not proof
   of initialized or authenticated content. Callee register preservation uses
   the normal AAPCS64 return convention; arbitrary callee effects are not proved.
2. The post-load full-reservation call at `0x1edbc -> 0x5e74` is exclusively
   an aligned `dc civac` loop followed by `dsb sy`. It can write back existing
   dirty cache bytes; it does not produce a zero-filled tail or expand firmware.
3. The complete selector at `0x16ec0` is two instructions / eight bytes:
   `mov w0, wzr; ret`. Consequently the branch at
   `0x1ec84` always selects `0x1ed30`, excluding the high-address allocation
   call at `0x1ecb0` in this B4.1 caller. The later low-address allocation at
   `0x1ed4c` remains in the caller graph.
4. With the selected RV33 name, the checked byte comparator and the three
   post-load name comparisons skip every `0x978a0`/`0x98a04` action block.
   Timestamp and stack-check callees remain obligations. This proves the
   local name-selection result, not arbitrary effects of every callback callee.
5. Both indirect branches in the architecture mapping routine resolve to
   four-entry signed-offset tables indexed by a checked two-bit field. Every
   target is inside the same fully decoded window. The page-table allocation
   and mapping callees still need alias/write contracts.
6. The mapping descriptor allocation is 88 bytes. The mapper's explicit zero
   call at `0x6c38` receives the buffer returned through `0x670ac`; the caller's
   `0x1edfc` clear receives SRAM. Neither is a checked full-staging clear.
   In particular, this census does not assert that the page-table buffer is
   disjoint from staging without the missing allocator/alias proof.

## What Remains

`evidence.json` includes every direct/indirect call in each window, all local
store/system-effect sites, all CFG exits, and the unexpanded reachable call
frontier. The graph includes possible callee returns even for error handlers;
it overapproximates caller reachability rather than silently assuming a call
cannot return. Only the checked constant selector and RV33 name branches are
pruned. Window presence is **not** a transitive side-effect proof.

The storage indirect dispatch at `0x67f08`, authentication/secure transform
paths, mapper allocators, logging/formatting callbacks, and earlier or
asynchronous writers are not closed here. Existing `audit_gpueb_b41.py`
contains useful storage/ATF bounds, but those selected-instruction checks are
not imported as a complete alias proof. No ATF input is silently assumed.
Thus neither "scratch" nor "zero" is a justified final tail classification.

Read-only U-Boot comparison: local `upstream/u-boot-mt6878` HEAD
`ddb4bcf7f9f08024a4477157dba781c0ab4f278b`;
`board/mediatek/mt6878/tetris_gpueb_flat.c` SHA256
`9a425bfa1a824459a6e0fd4c7fa31397a798aa91fdc7bcdff17907437b256d7f`.
That implementation explicitly erases its retained reservation before copying
the signed primary. Its zero tail is a U-Boot policy, not evidence of LK's
source contents. It must not be promoted to upload data using this report.

The concrete boundary still blocked is enlarging the signed `0x261a0`-byte
upload to stock's `0x3f2b8` span or substituting zero padding. Beyond the
producer proof, transitive RV33 startup requirements and actual
power/reset/OFF/IRQ ownership remain prerequisites to start. The previously
documented in-primary BSS fill does not establish this tail's producer.

## Reproduce

From the outer workspace, using only the supplied local inputs:

```sh
export PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012
python3 -B upstream/nothing-tetris-pmaports/patches/gpu/lk-tail/test_tail.py \
  --snapshot /private/tmp/tetris-gpueb-signed-39116740.bin \
  --lk worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img
python3 -B upstream/nothing-tetris-pmaports/patches/gpu/lk-tail/audit_tail.py \
  --snapshot /private/tmp/tetris-gpueb-signed-39116740.bin \
  --lk worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img \
  --output upstream/nothing-tetris-pmaports/patches/gpu/lk-tail/evidence.json \
  --require-closure
```

The strict audit intentionally exits **2** after publishing an incomplete
evidence report. Without `--require-closure`, exit 0 means only that inspection
and report generation succeeded. Invalid input exits 1 without replacing a
previous report; callers must check the exit code rather than reuse stale output.
No report field enables activation. Reports contain offsets, bounds, hashes
and results only and are atomically written with mode 0600. Inputs reject final
symlinks, nonregular files, oversize and nonprivate snapshots; output aliases
of either input are rejected. This assumes trusted local parent directories.

The 18 tests cover identities/framing, each window's mutation, independent
semantic mutations, branch and signed-table resolution, decode budgets,
unresolved indirect exits, tail arithmetic, private-input/alias rejection,
atomic output and mandatory failure of the strict closure gate.
