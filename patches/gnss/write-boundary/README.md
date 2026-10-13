# Staged GNSS Nonblocking TX Boundary

Status: **Untested on hardware; staged only.** Local static suite: 14 passed,
one GNU-patch check skipped because GNU patch is unavailable on this host.
The actual-source native harness passed GNU-patch application, IRQ/polling
ASan/UBSan fixtures and all applicable regression controls in
[CI38335304033](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38335304033)
at `e8ad596`. Parent main wires it into the GNSS workflow and adds genuine ARM64
v051 object compilation to research CI. The real ARM64 translation units passed
[CI38336059980](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38336059980)
at `9f4b4b2`. No complete module link, package or shipping activation,
phone write or physical TX test is claimed. Existing untracked drafts are preserved.

## Production Change

`1009-vendor-gnss-nonblocking-data-link-write.patch.vendor` is generated against
Git blobs at `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` from
`NothingOSS/android_kernel_modules_nothing_mt6878`, after the exact packaged
1001..1008 vendor stack. SHA-512 identities of the patch, prerequisites, and
resulting source files are recorded in `STAGING.json`. Stack/source drift stops
generation. The local vendor checkout is read through `git show`; its worktree
is never patched. Disposable application fixtures stay inside this directory.

Only three vendor files change:

- `linux/gps_each_device.c`: zero count returns before private-data access,
  logging, recording, user copy, or link lookup. Clamp count to
  `sizeof(dev->o_buf)` before narrowing, recording, or copying. Existing short
  writes remain at most 2048 bytes. `O_NONBLOCK` selects the new per-call API;
  blocking writes retain the existing entry. The oversize warning is replaced
  by recording the bounded accepted request size.
- `gps_each_link.c`: add `gps_each_link_write_with_options(..., wait_tx_done,
  nonblocking)`. The existing `gps_each_link_write_with_opt` delegates with
  `nonblocking=false`, retaining its capacity retry and polling completion
  behavior for either `wait_tx_done` value. `gps_each_link_write` is unchanged.
- `inc/gps_each_link.h`: declare the new entry and its per-call wait policy.

For nonblocking calls, a successful `gdl_dma_buf_put` sends the existing write
event exactly once, then returns 0 before polling completion, even when
`wait_tx_done=true`. NOSPACE, BUSY, and NOENTRY return `-EAGAIN` after one put
attempt and before capacity waiting or diagnostic buffer dumps. Invalid link,
oversize direct-link length, closed link, and other DMA failures keep existing
`-EINVAL`, `-EBUSY`, and `-EFAULT` mappings. The new nonblocking link entry returns
0 for an empty request before lookup; legacy direct-link empty-write behavior
is retained. No global flags or new poll/readiness semantics are introduced.

## Local Static Checks

From the repository root:

```sh
python3 -B patches/gnss/write-boundary/generate.py
python3 -B patches/gnss/write-boundary/run.py
```

`--vendor PATH` overrides `TETRIS_MODULES_TREE`; an explicit missing tree fails
without falling back. The local default is the adjacent
`android_kernel_modules_nothing_mt6878` checkout. CI's existing
`upstream/connectivity-modules` checkout is supported.

`generate.py --write` regenerates only the staged patch inside this directory.
The manifest patch hash is a separately reviewed identity; generation does not
silently update it. Balanced C spans and exact unique anchors are borrowed from
the existing read-boundary generator, imported read-only. Tests prove the
legacy implementation is recovered byte-for-byte by removing the new option
guards and wrapper, and unchanged content outside the permitted spans matches.

Application tests populate all prerequisite inputs from the exact source pin,
apply 1001..1008 with fuzz zero, then test the new patch using `git apply` and
the host patch engine, rejecting offsets/fuzz/skips for the new patch. They
compare every resulting file, reverse the patch, and reject double application.
The existing package clock CRLF cleanup is reproduced before 1005. Existing
1002 uses counts accepted by the package patch engine but rejected by Git;
the prerequisites are left intact. GNU patch fuzz-zero validation is mandatory
in native CI and explicitly skipped locally when unavailable.

## Parent CI Integration

Parent owns the required workflow step and packaging review. Suggested required
step, using the already pinned vendor checkout:

```sh
python3 -B patches/gnss/write-boundary/run.py --ci-native \
  --vendor upstream/connectivity-modules
```

The runner rejects native mode before source checks or compiler invocation
unless both `CI=true` and `GITHUB_ACTIONS=true` are present. Do not set those
variables locally. The parent must provide a 64-bit Linux host, GNU patch, and
an ASan/UBSan-capable C compiler. Failures must block integration; do not mark
the step optional or continue on error.

The fixture extracts actual stacked device write, both existing link entries,
the new link helper, DMA put, free-entry acquire/complete functions, and the
ring-copy function. Original vendor declarations and constants are extracted
as well. Kernel user-copy, locking, recording, link-state, event, and HAL
boundaries are mocked. Test cases cover zero effects, large size_t counts,
copy errors, queue-once behavior, busy/no-space/no-entry, copy-stage rollback,
wrapped payloads, word padding, invalid links/states, signal interruption,
blocking retries, and both legacy completion choices.

ASan/UBSan builds run for `GPS_DL_NO_USE_IRQ=0` and `=1`. The unmodified stacked
baseline and eight mutations supply negative controls. Both builds reject
missing device/link zero guards, count bound, nonblocking dispatch/capacity
guard, and a legacy wrapper incorrectly made nonblocking. The polling build
also rejects a missing completion guard and a wrapper forcing completion;
these two controls have no behavioral effect in the IRQ build and are excluded
there. Total: seven negative controls for IRQ, nine for polling, plus one fixed
fixture per build. Missing guards fail bounded assertions rather than hanging.

## Remaining Gates And Limits

The implementation bounds shared `o_buf` access by size; it does not serialize
concurrent writes through a duplicated descriptor or multiple threads. Existing
DMA ownership/reset races, full-ring and alignment edge behavior, ignored
non-signal wait errors, and event transport behavior remain vendor contracts.
User copy, logging, existing locks, and event dispatch are still executed;
this is not a wall-clock deadline guarantee.

Native mocks do not prove real kernel locking, asynchronous progress, timing,
or hardware behavior. Parent must run required native CI, review the final
integration, and compile the touched v051 driver under the package kernel
config/compiler before activation. No shipping activation before CI. The outer
porting skill's clean-artifact, USB/SSH, cold-repeat, lifecycle, GNSS function,
coexistence, and portability gates still apply to any later hardware testing.
