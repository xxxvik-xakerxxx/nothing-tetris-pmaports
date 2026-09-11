# Mandatory slots3/4 and second-config producer

Status: callback machine ABI and bounded producer slices verified offline;
complete startup configuration and native operation remain Partial/Untested.
Scope excludes Epicurus's Bionic runtime closure, lifecycle and packaging.

## Pins

Same exact B4.1 ELF inputs as STARTUP_HOST_ABI.md:

- libmnl.so: `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`
- mnld: `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`

Inputs are read from `/probe/gnss-b41` in existing `mt6878-probe-build`.
All addresses are ELF VAs. No vendor binary is added to git. The tests execute
bounded instructions with synthetic globals and intercepted external calls,
not a native library or any hardware operation.

## Slots3/4 are frame-sync requests

Registration `52fa0c..52fa28` stores table slot3 through GOT `6e6d30`, slot4
through `6e6d28`. These stores are now asserted in the registration test for
all missing-slot cases. mnld table targets are `7ba50` and `7bbc0` respectively.

| Slot | Actual mnld use | libmnl veneer | Observed AArch64 contract |
| --- | --- | --- | --- |
| 3 | frame_sync_enable_sleep_mode | 509054..509060 | w0 input, only low byte consumed; w0 return |
| 4 | frame_sync_meas_req_by_network | 50903c..509048 | no inputs consumed; w0 return |

Names come from mnld literals `1cc53` and `1ebbe`, not nearest-symbol labels.
Slot4's veneer overwrites x0 with the callback target itself before branching:
it cannot be a data-pointer callback. Slot3's veneer preserves w0. Both veneer
paths propagate a synthetic -2 result in the bounded test.

Examples of actual callers: slot3 gets 1 at `54bdc8`, 0 at `54be50`, and the
validated byte [message+0xa] at `6b8924..6b8934` (values above 1 rejected before
the call). Slot4 is called at `54d0f8`, `54d958`, `6b8224`; the first two test
its returned w0 with cbz. These are assistance/frame-sync paths, not a license
to drop their side effects or substitute a successful no-op.

The complete bounded mnld callback bodies show:

- Slot3 masks w0 with 255, formats `PMTK738,%d` via literal `12105`.
- Slot4 ignores incoming registers, formats `PMTK736,0,0` via `20743`.
- Both XOR the body bytes and format `$%s*%02X\r\n` (literal `1385e`).
- Both copy strlen-1 bytes to another stack buffer and terminate it: only LF
  is removed, leaving CR. They call AGPS dispatcher `5fa80` with w0=0,
  w1=length, x2=borrowed buffer. Neither NUL nor LF is included in that length.
- Both return zero even when that dispatcher returns -1 (tested). This return
  is NOT successful IPC delivery or a completed network measurement.

The dispatcher is the previously traced AGPS Unix-datagram path, not gpsdl.
The receiving service and eventual frame-sync result are still dependencies.

`b41_frame_sync.h` declares the observed machine-ABI function-pointer shapes
and implements a pure bounded encoder. Its slot3 parameter is uint32 with
explicit low-byte semantics; this is not a claim about the vendor C typedef.
The encoder's status reports local encoding only. It is deliberately NOT a
registered adapter: no guessed IPC endpoint, fake measurement, or success stub.

## Second block: initialization and producer

mnld uses base `0xde590`. At `62b74..62ba8`, memset receives (base,0,0x444).
The adjacent first block is `0xde520`, size0x70. libmnl entry `52b638..52b6a0`
copies that first block separately and memcpy-copies exactly 0x444 bytes from
unchanged x1 to storage through GOT `6e69d0`. Both copies are now executed in
the test, which stops at `52b6a4` BEFORE initialization or device access.

The caller does not merely pass zeros. Recovered inline string fields:

| Offset | mnld source | Copy count / field bytes |
| --- | --- | --- |
| 0xd4 | literal a82b: /data/vendor/gps/mtkgps.dat | 29 / 30 |
| 0xf2 | literal 1d904: /data/vendor/gps/mtkgps_ofl.dat | 29 / 30 |
| 0x190 | global 88a80 | 29 / 30 |
| 0x1ae | conditional 62d1c..62d80: literal14431 or global88aa0 | 29 / 30 |
| 0x1cc | global88ac0: default UseCallback | 29 / 30 |
| 0x1ea | global88a60: default /dev/ttygserial | 29 / 30 |
| 0x208 | global88ae0: default /data/vendor/gps/ | 29 / 30 |
| 0x406, 0x424 | globals88b78,88b98 | 29 / 30 |
| 0x110 | global88e41: default GPS_HOST log path | 127 / 128 |
| 0x226,0x256,0x286,0x2b6 | globals88b00,88b1e,88b3c,88b5a: EPO paths | 47 / 48 |
| 0x2e6..0x3d6, stride0x30 | six literal assistance paths | 47 / 48 |
| 0x46 | literal2014e: MTK_MNLD_14_1.00 | 29 / 30 |

The strings except conditional0x1ae are exercised in producer slices
`6352c..6365c` and `63694..638a0`, with bounded strncpy mocks. Offset0x1cc
is copied at `635c8` with x22=base+0x18; explicit terminator is written at
`635e0`. Replacing the source global with CustomOutput changes the destination
in the test: UseCallback is an ELF default, not a forced startup constant.
Earlier overrides of the global configuration are not comprehensively traced.

Selected scalar/block producers:

| Offset | Write provenance | Coverage |
| --- | --- | --- |
| 0x4 | 636d8, global88e40 with conditional bit0 clear | executed |
| 0xc | 6370c/63954, global88c18 | executed first write; second static |
| 0x10/0x14 | 63afc/63b14, globals88798/8879c; secondary conditional on56ce0 | both branches tested |
| 0x1c/0x20 | 63898, bounded log sizes from dfff4/dfff8 | executed, not exhaustive range tests |
| 0x24 | 63ba4, global88a5c u32 | static |
| 0x28 | 638c0, formatted float globalde4bc | static; formatter not executed |
| 0x64/0x68 | 63940, globalde21c and value+0x50000 | static |
| 0x6c | 639f4, boolean(globalde228) AND helper56c70 result | executed with mock |
| 0x70..0xb3 | 639e8..63a04, 68 bytes from de4d4 | executed |
| 0xb4/0xb8 | 63b9c/63ba0, globals88c58 and88c68 | static |
| 0xc4 | 63a84, low byte of helper56c90 result | static |
| 0xc8 | 636c4, helper628e0 result (Android property policy) | sentinel result tested; helper not executed |
| 0xcc..0xd3 | 639b8, literal22b08: u16 ce,6,aa55,102 | tested |

These are a producer map, NOT a supported complete struct initializer. In
particular the source globals, optional branches, paths, and numeric field
semantics cannot be replaced wholesale with defaults. The config needs real
policy/transport ownership; an opaque copy or correct marker alone is insufficient.

## Validation and first failure

The expanded `test_b41_startup.py` passes all earlier tests plus complete mnld
callback bodies (format helper mocked for ONLY the three pinned formats),
library veneers, registration stores, producer slices and entry copy boundaries.
The copy/strlen/IPC endpoints are mocked; no libc compatibility is claimed.

262 callback vectors cover all256 low-byte values, truncation256/257/UINT32_MAX,
and three different ignored inputs to slot4. C encoder vectors match exactly:
SHA256 of newline-joined lowercase hex vectors, without final newline:
`3ca6ab96e43f0dd4c7dca7ae8797f4e60ba92d944b39d0265a6d97f1f7d51468`.
C tests also check exact capacity, insufficient capacity, invalid slot/pointers
and untouched output on rejection; compiled with ASan/UBSan and warnings-as-errors.

First new failure: config test line273 expected both neighboring guard bytes to
remain a5; the low guard was zero. Source instruction `62ba4` stores xzr at
first-block+0x68 (de588..de58f), immediately before the second block. Corrected
the expectation for this legitimate adjacent write, retaining the high guard
and exact 0x444 zero-content checks. No vendor instruction was skipped to pass.

Commands from this worktree:

```sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined patches/gnss-navigation-audit/test_b41_frame_sync.c -o /tmp/camera-agent-frame-test
/tmp/camera-agent-frame-test
docker exec -i mt6878-probe-build python3 - /probe/gnss-b41/libmnl.so /probe/gnss-b41/mnld < patches/gnss-navigation-audit/test_b41_startup.py
```

## Handoff boundary

Runtime work can use the two callback shapes and exact borrowed dispatcher
payload contract; it must not install the encoder itself as a callback or
interpret zero as completion. Next callback-side prerequisite is tracing the
AGPS receiver's handlers for PMTK736/738 and the return/result path, then building
a typed adapter to a real bounded service interface. Next config-side prerequisite
is resolving the remaining policy producers and single fd owner, not inventing
a 0x444-byte all-zero initializer. No phone startup is justified by this change.
