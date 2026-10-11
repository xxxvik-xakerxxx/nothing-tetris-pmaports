# GPS data-link read boundary

Production patch: `1008-vendor-gnss-bound-data-link-read.patch.vendor` in the
kernel package. It changes two real functions, with 13 insertions and one
deletion. APKBUILD applies it after 1007 with fuzz=0; required main CI validates it.
`STAGING.json` records the pinned input, digest, limitations and integration
requirements. Native compilation and physical behavior remain pending CI and
hardware testing. It is included in the corrected r181 candidate.

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
| `lib/gps_dl_dma_buf.c:372` and `:405` | Entry completion updates ring ownership and clears reader_working under the DMA lock. This does not lock the shared device buffer until userspace copy finishes. |
| `lib/gps_dl_dma_buf.c:593` | Copy helper rejects data_len > buf_len, handles contiguous/wrapped entries and returns bounded data_len on success. A failed copy exits `gdl_dma_buf_get` without rolling back reader_working. |
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

Small requests below an entry's length retain -EFAULT and the existing stuck-busy
failure. Oversized entries above 2048 now fail safely at the bound, with the same
vendor error-state limitation. Failed userspace copies retain -EFAULT and may
lose data already consumed. These are recorded residual issues, not claimed
fixes. The native fixture characterizes them explicitly. No finite IRQ timeout,
poll ABI, startup support or working GNSS navigation is claimed.

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
CI=true TETRIS_MODULES_TREE="$PWD/upstream/connectivity-modules" \
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
invalid link, busy/no-entry, copy fault, short-buffer residual errors, blocking
retries, signals/unsupported IRQ waits and polling timeout errors. Negative
controls use original source and separately remove each fix; each must fail.
The mocks do not validate real kernel locking, hardware races or elapsed time.

## Next Integration Requirements

1. Main CI now runs the fixture with the pinned connectivity checkout before
   image construction. The early object job also compiles the four real DTBs.
2. Require the real-source fixtures to pass both configurations and all negative
   controls before the full image. Package application and checksum are wired;
   no automatic GNSS activation is supplied by this fix.
4. Once DT and native fixtures pass, main dispatches the full image at the same
   SHA. Compile the touched v051 driver with the package's kernel config/compiler,
   check modpost and module ABI, and include it in traceable CI artifacts.
5. Hardware validation remains untested: authorized clean artifact boots must
   retain USB/SSH, exercise empty/data/blocking/error behavior without module
   reloads, then pass the skill's cold-repeat, lifecycle and variant gates.

Existing untracked work is outside these new files and is preserved.
