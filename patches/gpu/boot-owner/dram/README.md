# DRAM Candidate, Not Boot Activation

These new files leave the parent owner-join batch untouched. Nothing here is
installed or called by a shipping driver. The C allocator and candidate-word
loan are concrete native preparation; hardware GPR publication remains absent.

## Source Refinement

Exact NOS B4.1 trees contain host GPUEB/RV33 users, not the GPUEB firmware
compiler's instruction definitions. Searches did not identify authoritative
definitions for 0x08c66633 at 0xfe9a or 0x67458633 at 0xfec2. The pinned official
Chromium/MediaTek SCP cache header uses COP(rs1) = (rs1 <<15) |0x400f. That is a
different opcode family and a different target, not authority for either
GPUEB OP-0x33 word. The external comparison hash/URL is in SOURCE-PINS.json.

The actual primary identifies the first check with the diagnostic
"size ... is not 4KB aligned". The second word occurs in a PA split/recombine
sequence (low <<12, high >>20), before mapping. Neither observation establishes
an input-data read or cache flush/invalidate. Exact vendor semantics remain
unproved; do not label the entire operation opaque input-table consumption.

0x100b8 reads GPR6, and 0x100c4 passes PA>>12, upper argument zero, 4MiB and zero
to 0xfe94 (`gpumpu_init_page_table`). The successful branch maps through 0xa44e;
0xff02 calls 0x7a3e with its returned address, value zero and length 4MiB. That
callee has alignment-selected, end-tested fill-shaped loops with four further
undecoded vendor words. This narrows the initialization question to an actual
zero-fill candidate. It proves neither the store semantics nor the absence of
earlier workspace reads. No initial table data requirement is established.

The staging prefix and the signed primary's six-word header are different:

- LK maps a 1MiB allocation, supplies mapped base+24 to 0x74da0, selects the
  ordinary MTK member at partition offset+512 and reads it into that destination
  at 0x75030. It later writes allocation PA, not PA+24, into GPR0.
- No prefix producer is established in the inspected caller/reader. Their
  security callees are not assumed incapable of side effects. Prefix contents
  are not authenticated input and are not constructed as invented zero words.
- The primary's own signed [0,24) header is `(0x0ac0006f,0,0,0,0,0)`. The early
  helper at 0x1df8 reads its +4 remap field. The copy helper uses header base+4,
  reading destination at +8, source at +12, count at +16. Count zero prevents
  source-copy iterations on this cold path. This is not a staging-prefix read
  or a whole-firmware GPR0/warm-save contract.

## Native Preparation

`mt6878_gpueb_dram_create(parent, &result)` allocates actual contiguous CMA pages for 6MiB,
pins its parent, checks 64KiB alignment and the complete physical span in the
selected stock low-memory interval [1GiB,2GiB), and rejects unsuitable results.
No assumed DMA/IOMMU bus address, caller PA, input data or initialization image
is accepted. It saves the real CMA area for release, independent of subsequent
device selector changes. No loop retries different allocations.

An exclusive opaque loan prevents destruction. The candidate GPR6 word is
derived from those actual owned pages, with PA drift detection, using >>12.
Failed release retains the object/pages/device reference and latches its actual
error. The result pointer must start NULL. On release failure during rejected
construction, create returns -EIO AND returns the retained, faulted owner in
that pointer. This preserves an accessible cleanup handle rather than losing
the allocation. Loans reject the first fault before allocating metadata; a
failed destruction cannot reopen candidate access. Private cleanup may only
release the actual original CMA pages. It makes no hardware-retirement claim.

The six-MiB buddy allocator alternative needs order11; the packaged 4KiB kernel
uses CONFIG_ARCH_FORCE_MAX_ORDER=10. CMA avoids that closure error. Pinned
cma_alloc/cma_release have no module exports: this is a built-in candidate,
not a linkable out-of-tree module. CI partial linking does not validate vmlinux
linking or secure access.

No DRAM bytes are arbitrarily initialized, no GPR is written, and no MMIO,
reset release, IRQ activation, power transition or secure call is introduced.
The source is not a complete native GPR handoff. Before publication, the same
real reset/SRAM owner must retain the loan, resolve exact initialization/cache
semantics and region12 secure visibility. No loan release proves physical OFF
or DMA retirement. GPR0 layout/lifetime and the independent Linux shared-memory
size mismatch remain separate. There is no claim of GPU acceleration.

## Checks

Local static/source checks only:

```sh
python3 -B patches/gpu/boot-owner/dram/ci_dram.py --check
python3 -B patches/gpu/boot-owner/dram/test_dram.py -v
sh -n patches/gpu/boot-owner/dram/run-ci.sh
```

`test_dram.py` and `trace.py` additionally accept the same six authenticated
input/source arguments as `../test_boot.py`. Tests check exact instruction
windows, header bases, mutations and pinned Linux allocator blobs. There is
no RV execution, guessed instruction emulator or generated firmware.

CI only, after the successful research-owner baseline:

```sh
sh patches/gpu/boot-owner/dram/run-ci.sh
```

This uses a separate source/O= copy, real kernel headers and the complete
canonical flat-consumer/reset/SRAM dependency. It compiles one additional
built-in DRAM object, checks internal partial-link symbols, and runs the actual
C allocator/loan fixture under ASan/UBSan with mocked CMA history. The mock
covers allocation/metadata failures, PA bounds/alignment, parent mismatch,
exclusive leases, PA drift and retained failed destruction. Neither ARM64
compilation nor C fault execution has been performed locally.
