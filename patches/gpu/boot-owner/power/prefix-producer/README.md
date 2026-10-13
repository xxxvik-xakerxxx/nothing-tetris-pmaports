# MFG0 Entry-State Producer Boundary

New isolated research delta. Cold-deps, power, root and DRAM batches are frozen.
No installed runtime change, GPU activation, local compilation, firmware
execution, phone access, secure calls, workflow edits or publication.

## Source Trace

Authenticated B4.1 LK payload SHA256:
`431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a`.

The full 1681136-byte aligned payload was searched for direct calls, literal
addresses, wide-immediate address seeds and locally constant memory addresses.
This also finds diagnostic reads via **0x1c001410 + 0xaa4** at `0x1e194` and
`0x1e42c`. The ACK helper `0x1eb74`, loader reads `0x1ebc8`/`0x1ebd8` and timeout
read `0x1efa8` are readers. No locally resolved store to **0x1c001eb4** or exact
physical/virtual address literal was found. Other SPM stores are recorded, not
borrowed as MFG0 producers.

This is **not an exhaustive absence proof**: the payload contains data as well
as instructions, branch joins lose local constants, indirect/table/dynamic
addresses and transitive secure/firmware effects remain unresolved. The scanner
does not execute instructions, emulate the CPU or construct a successful state.

Actual preceding route:

- LK `0xfa58 -> 0xea10` installs the `0xea64` io-task callback. On the selected
  non-mode2 route, `0xec04 -> 0x331e4` loads SPM firmware through `0x74da0`.
- `0x33438 -> 0x188dc` issues the concrete SMC: x0=**0x82000410**,
  x1=**0xda065731**, x2=1, x3=SPM firmware allocation, x4=0x10000.
  Failure from the load hook diverts before GPUEB; preceding callees are not
  declared free of power side effects.
- GPUEB's immediate `0xed58 -> 0x16eb0` hook is a zero-return stub.
  `0xed94 -> 0x1eb88` reaches the actual ACK/12/13 admission before allocation
  or GPUEB secure loading. ACK[31:30]=3, bit12=0, **bit13=1** remains required.
- LK entry saves incoming x0..x3 at `0x40`/`0x44`; those argument captures do
  not expose the earlier preloader/EL3 MMIO sequence or certify inherited state.

The independently **hash-pinned**, not certificate-authenticated here, matching
ATF payload `05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`
provides a narrower secure boundary:

- Record `0x58a80` names MTK_SIP_BL_LPM_CONTROL and selects `0x1994c`.
- Registration code `0x2033c -> 0x1f530` selects group6 callback `0x1f560`.
  The actual registration running is not asserted by static inspection.
- UID0x5731/action1 reaches `0x1f594 -> 0x30fd4`, which stores the firmware
  pointer/count, calls `0x3195c` and continues at `0x31048`.
- The concrete platform initializer `0x30bac -> 0x29f04` installs table
  `0x5a808` at `0xf6040`. Its +0x18 callback at `0x3108c` resolves to
  `0x19f00`, a read of SPM0x1c001194. The +0x28 PCM preparation callback at
  `0x311cc` resolves to `0x30eb4`; +0x30 at `0x310f0` resolves to `0x30f00`.
- The control callback conditionally calls `0x30f54 -> 0x39cc`, whose
  `0x39d8` stores1 to **SPM_CPU_WAKEUP_EVENT0x1c0010b0**. That is an actual
  secure SPM event store, not a MFG0 control write or proof the branch ran.
  Mutable table state and control/status branch selection were not observed.

Exact NOS `ee2be53cb75670b548948636a0db1d1ff112bf12` register definitions at
`spm_reg.h:2879` name bit9 **MFG0_SRAM_SLEEP_B**, bit12 **PDN_ACK**, and bit13
**SRAM_SLEEP_B_ACK**. Bit13 is an ACK status, not a permission bit to write or
a proof cookie. The descriptor's missing bit9 transition is not repaired by
copying another domain, adding fake regulator/clock handles or guessing an SMC.

**Result:** actual bit13 state producer is still not selected between this
secure/SPM initialization chain and earlier inherited cold-boot state. A
firmware-only producer is not proven. **First causal unresolved dependency:**
the loaded SPM program/control effects after this conditional PCM preparation
and event, versus earlier preloader/EL3 MFG0 control writers. Those must be
resolved before any new Linux control transition. There is no invented poll
or MFG0 writer here, and the secure SPM event is not imported into U-Boot.

## Concrete Read-Only Loader Delta

`initial-report.patch` is generated against exact U-Boot
`f0f204bfdf6c3ce442db4f93ceb155a9306b5cba`. It changes only the existing
`board/mediatek/mt6878/mt6878_tetris.c` translation unit, not mappings,
configuration or authentication. It is **not applied to the U-Boot checkout**.

The staged `gpueb_initial_power_capture()` reads **0x1c001eb4 once** through the
existing 0..0x40000000 MT_DEVICE_NGNRNE identity mapping. The actual caller is
**board_late_init() during startup**, before the normal/fastboot early return.
Pinned common/board_r.c calls it after relocation/cache/DM/console setup and
before run_main_loop; the board defconfig selects that callback. It is **not**
the later board_prep_linux observation, a reset-entry sample, or a preloader
snapshot. Earlier U-Boot/firmware power changes are not excluded.

The raw read is retained in this boot's private loader state; stage1/error0 is
assigned only after readl returns. A synchronous MMIO fault cannot be caught by
this API: it can prevent reaching Linux. The metadata does not invent a secure
permission, successful firmware authentication or hardware ownership result.

During **board_prep_linux()**, after its existing bounded DT preparation and
before SCP/GPUEB loading, `gpueb_initial_report_publish()` uses the SAME checked
`tetris_linux_fdt_prepare()` clone helper used by the authenticated GPUEB final
publisher. The original DT allocation is retained. A private clone is committed
only after all checked property writes, full FDT validation and cache flush.
On failure the private clone is released; a bounded minimal actual-error report
is attempted on the caller's owned DT. The first error is returned, not masked.
If even that publication fails, no complete new report is promised.

The `/chosen` ABI uses the `nothing,gpueb-initial-` prefix:

- `report-version`: 1, written last, not an authority cookie.
- `report-stage`: 1 means the retained startup observation; 0 means no usable
  sample in this report. No GPU state/ownership meaning.
- `report-error`: actual signed error encoded as u32; -ENODATA if startup did
  not sample, or the first native clone/property/validation error on fallback.
- `spm-raw`, `spm-ack`, `spm-pdn-ack12`, `spm-sleep-b-ack13`: only for the
  complete stage1/error0 observation, all derived from the SAME retained word.

Imported stale namespace fields are removed, version first. Missing/error
reports never fill raw/ACK fields with zero. Later DT cloning preserves these
properties, making the startup word available from Linux without UART.

This exact cached loader has **no report_u32 helper**. The additive candidate
uses its real checked `fdt_setprop_u32()` API and bounded clone; it does not
invent an unavailable external helper or adopt untracked loader files. Parent
must supply a newer helper's exact git object/path if that source variant is
required, then regenerate/review against that preimage before integration.

Only existing GPU diagnostic guards select capture/publication; neither option
is enabled by this patch. There is no new peripheral mapping, MMIO write, poll,
reset, SMC or ready grant. RAM mappings/cache operations belong only to the
existing bounded DT clone owner. Authentication, erasure and unrelated error
paths are byte-for-byte preserved after subtracting the helper and its calls.

`read_initial.py --chosen /sys/firmware/devicetree/base/chosen` is a read-only
Linux metadata consumer for a later authorized matched-loader test. It rejects
missing/malformed/unknown/stale data and ACK fields inconsistent with the raw
word. An actual zero word is an observation, not missing-data filler or READY.
These loader diagnostic properties are not independently signed; even a
matching observation never authenticates power ownership or the cold producer.

Parent may compile/apply the matched-loader delta in CI and later arrange an
authorized diagnostic boot. No such compilation or boot occurred here. Do not
promote a matching snapshot to ownership, calibration, OFF or GPU-ready state.

## Reproduce Static Checks

Required external fixtures are explicit; missing files/objects fail, not skip.
`LK` is the authenticated container; `ATF` the matching declared-image file.

```sh
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 python3 -B patches/gpu/boot-owner/power/prefix-producer/test_producer.py --tree "$UBOOT" --lk "$LK" --atf "$ATF" --device-tree "$NOS" -v
python3 -B patches/gpu/boot-owner/power/prefix-producer/generate_report.py --tree "$UBOOT" --check
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 python3 -B patches/gpu/boot-owner/power/prefix-producer/audit_producer.py --lk "$LK" --atf "$ATF" --device-tree "$NOS" --check
```

The 22 tests authenticate LK, verify exact ATF/NOS/U-Boot identities, test
generated patch application/reversal in disposable source copies, check both
diagnostic selection branches, unchanged authentication/error/erase paths and
negative image/source/address cases, bounded clone/error/stale-data source
paths, and the Linux reader on synthetic property fixtures. No C compiler,
cpp, emulator or JIT is used. C/libfdt fault execution and actual loader object
compilation are CI-only and have not run for this new batch.
