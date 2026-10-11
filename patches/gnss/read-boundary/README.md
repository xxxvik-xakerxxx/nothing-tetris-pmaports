# GPS data-link read boundary

Production patch: `1008-vendor-gnss-bound-data-link-read.patch.vendor` in the
kernel package. It changes three real functions: device read, link read and
DMA get. APKBUILD applies 1008 after 1007 with fuzz=0 and records its revised
checksum.
`STAGING.json` records the pinned input, digest, limitations and integration
requirements. Actual-source native fixtures passed
[CI 38117468070](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38117468070)
at `e0c67c561ff7c1a0472da851edfafd5a0abb6cec`, with both IRQ/polling branches,
ASan/UBSan and six detected negative controls per branch. No native compilation
ran locally. Physical behavior remains untested. The corrected r181 candidate
is in [full image CI 38117727546](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38117727546)
at the same validated source; its real v051 module build remains pending.

## Source Trace

All source references below are Git blobs at NothingOSS connectivity commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`, not the local vendor checkout's HEAD.
Paths are relative to `connectivity/gps/data_link/`.

| Source | Evidence |
| --- | --- |
| `plat/v051/Kbuild` | Links the Linux device read, each-link read, DMA buffer library and link waitable implementation into the v051 driver. |
| `linux/gps_each_device.c:23` | `gps_each_device_read` uses shared `private_data`, passes size_t count to unsigned-int link reader, then copies returned bytes from `dev->i_buf`. Blocking read was unconditional. |
| `linux/inc/gps_each_device.h:33` and `:57` | `GPS_DATA_PATH_BUF_MAX` is 2048; `i_buf` is an inline array. `sizeof(dev->i_buf)` is its actual storage size. Header provides no read mutex. |
| `gps_each_link.c:657` | Blocking wrapper uses `GPS_DL_RW_NO_TIMEOUT`, defined as -1 in `lib/inc/gps_dl_time_tick.h:9`. |
| `gps_each_link.c:662` | Reader calls `gdl_dma_buf_get` first. On success, handles pending RX under the link DMA spinlock and returns data length. Invalid link returns -EINVAL; other DMA errors return -EFAULT. |
| `gps_each_link.c:695` | NODATA previously entered polling HAL waits or the IRQ waitable regardless of zero timeout. New guard returns -EAGAIN before logging/waits for both configurations. |
| `link/gps_dl_link_sync.c:38` | IRQ path uses `wait_event_interruptible`, without a timeout argument. Signal maps to -ERESTARTSYS; unsupported wait maps to -EFAULT. Positive timeout values still do not establish an IRQ deadline. |
| `lib/gps_dl_dma_buf.c:237` | Real DMA get acquires a data entry, copies it, consumes it and releases `reader_working` before the outer `copy_to_user`. |
| `lib/gps_dl_dma_buf.c:313` and `:356` | Entry acquisition tests `reader_working` and emptiness under the DMA spinlock. Empty acquisition clears reader_working before NODATA. Busy maps to -EFAULT at the link layer. |
| `lib/gps_dl_dma_buf.c:372` and `:405` | Entry completion updates ring ownership under the DMA lock. Its NULL branch at :380 only clears reader_working and returns, without ring/entry consumption. Failed DMA copies now call this API before returning their first error. This does not lock the shared device buffer until userspace copy finishes. |
| `lib/gps_dl_dma_buf.c:593` | Copy helper rejects data_len > buf_len, handles contiguous/wrapped entries and returns bounded data_len on success. The new get failure branch releases acquired ownership with NULL rollback. |
| `linux/gps_data_link_devices.c:221` | Normal Linux RX transfer limit is `GPS_LIBMNL_READ_MAX` (512), but this is not a proof that arbitrary small userspace reads work or every malformed/reset state is safe. |
| `plat/v051/inc/gps_dl_config.h:48` | Production v051 uses IRQ (`GPS_DL_NO_USE_IRQ=0`). The fixture also covers the existing polling branch (`=1`). |
| package `APKBUILD:31`, `:170`, `:271` | Pins this vendor commit, lists 1000-1007 and applies connectivity 1001-1007 to `_connmods_dir`; generator/application tests use that input and order. |

## Concurrency And Errors

The clamp prevents a single read from writing beyond the actual input array and
prevents truncation of very large counts before the bound is applied. Zero read
does not consume DMA data or start a wait. Nonblocking empty reads return
-EAGAIN without consuming waitable state or invoking polling HAL handlers.

There is no proven existing lock covering the complete device-read transaction.
Open's `is_open` check is not such a lock; one open file may be shared between
threads or duplicated. The DMA spinlock protects ring bookkeeping, while
reader_working protects acquisition/copy/completion of one DMA entry. Another
reader can overwrite shared i_buf after entry completion but before the first
copy_to_user finishes. This patch preserves that behavior and adds no mutex.
The disabled `gps_each_device_data_submit` block does not prove an active lock.

Small requests below an entry's length still return -EFAULT, but now release the
acquired reader and preserve all queued entry/ring data for a larger retry.
Oversized entries above 2048 fail safely and release ownership too. Device reads
remain clamped; such an entry needs a sufficiently large direct DMA API buffer
to succeed. This fixes the actual stuck-busy failure without changing error
mappings or inventing partial-entry reads. `gdl_dma_buf_get` retains its original
copy error even if cleanup reports an ownership mismatch. Acquisition failures
(BUSY, NODATA, NOENTRY, assertions) do not invoke rollback: BUSY must not release
another reader's ownership. Failed userspace copies still retain -EFAULT and may
lose data already consumed. No finite IRQ timeout, poll ABI, startup support or
working GNSS navigation is claimed.

Between successful acquisition and rollback, reader_working normally prevents
another reader from acquiring the same DMA entry. The existing completion API
takes the actual DMA spinlock, clears that flag for NULL, and returns before
touching read_index, entry_r or entry contents. Thus a retry may acquire the same
queued data after the lock is released. This adds no ring write, MMIO or wait.
However, `gps_dma_buf_reset` at `lib/gps_dl_dma_buf.c:21` also clears reader_working
under that lock; close/reset paths call it from `link/gps_dl_link_event_proc.c`.
The boolean carries no ownership/session token across an unlocked copy. If a
reset invalidates ownership and a new reader acquires before old completion,
NULL rollback cannot distinguish that newer owner. Existing non-NULL completion
has the same missing-generation boundary. This patch does not establish reset
quiescence or resolve that lifecycle race. The fixture simulates invalidation
without a new owner to check preservation of the first error, not race safety.

## Validation

Local, static only (from repository root):

```sh
python3 -B patches/gnss/read-boundary/run.py --vendor /path/to/vendor-git-tree
python3 -B patches/gnss/read-boundary/generate.py --vendor /path/to/vendor-git-tree
```

`--vendor PATH` overrides `TETRIS_MODULES_TREE`. Without either, the default is
this repository's `upstream/connectivity-modules` if present, then the sibling
local vendor repository. The checkout need not be at the pin: all inputs come
from `git show PIN:path`. The pin must exist in its object database.

CI entry point for main's `kernel_smoke_only` gate, from repository root:

```sh
CI=true GITHUB_ACTIONS=true TETRIS_MODULES_TREE="$PWD/upstream/connectivity-modules" \
  python3 -B patches/gnss/read-boundary/run.py --ci-native
```

When `TETRIS_MODULES_TREE` is already exported by CI, the equivalent explicit
CLI is:

```sh
python3 -B patches/gnss/read-boundary/run.py \
  --ci-native --vendor "$TETRIS_MODULES_TREE"
```

CI requires Python 3, Git, GNU patch and a native 64-bit Linux compiler/runtime
supporting AddressSanitizer and UndefinedBehaviorSanitizer. `CC` may select the
compiler; `TETRIS_GNU_PATCH` may select GNU patch. The runner fails on static
errors, missing GNU patch in CI, fixture build/runtime failure, or an undetected
negative control. Native compilation requires explicit `--ci-native`, CI=true
and GITHUB_ACTIONS=true; normal local runs never compile C. It does not invoke a kernel or
image build, dispatch another job, contact the phone, or load a module.

`generate.py` locates balanced function/branch/statement spans, masks comments
and quoted strings, verifies unique expected call sites and rejects source
drift/double application. It emits deterministic three-context-line hunks.
The local tests validate hunk counts, exact generation, raw and stacked Git
application/reversal, and GNU fuzz-zero application when available.

`native_harness.c` supplies kernel/HAL boundary mocks, but `real_source.c` and
`real_types.h` are extracted at run time from the pinned production source,
including its actual DMA get/copy/entry ownership functions and actual device
array declaration. There is no hand-written implementation of the read logic.
The patched extraction is checked against the staged patch by static generation
and application tests before compilation. Both IRQ and polling variants test
zero/one/bound/oversized/SIZE_MAX reads, empty/data/wrapped/pending-RX paths,
invalid link, busy/no-entry, copy fault, short-buffer and oversized-entry
rollback/retry, first-error preservation despite cleanup mismatch, blocking
retries, signals/unsupported IRQ waits and polling timeout errors. Negative
controls use original source and separately remove each fix, including rollback;
each must fail in both IRQ and polling configurations.
The mocks do not validate real kernel locking, hardware races or elapsed time.

## Next Integration Requirements

1. Main CI now runs the fixture with the pinned connectivity checkout before
   image construction. The early object job also compiles the four real DTBs.
2. The real-source fixtures passed both configurations and all negative controls
   before the full image. Package application and checksum match STAGING.json;
   no automatic GNSS activation is supplied by this fix.
3. DT/native fixtures passed; main dispatched the full image at the same SHA.
   Compile the touched v051 driver with the package's kernel config/compiler,
   check modpost and module ABI, and include it in traceable CI artifacts.
4. Hardware validation remains untested: authorized clean artifact boots must
   retain USB/SSH, exercise empty/data/blocking/error behavior without module
   reloads, then pass the skill's cold-repeat, lifecycle and variant gates.

Existing untracked work is outside these new files and is preserved.
