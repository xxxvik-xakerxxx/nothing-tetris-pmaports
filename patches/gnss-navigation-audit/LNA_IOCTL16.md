# Read-Only LNA Metadata Query

Candidate `0002-gps-mcudl-query-owned-lna-metadata.patch` implements mcudl
ioctl16 as a u32 SoC pin-index metadata query. It adds no GPIO, pinctrl-state,
rail, register or firmware writes. Successful metadata is not RF operation,
navigation startup or a GNSS fix.

## Authoritative Chain

Modules pin: `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`.
Device-modules pin: `ee2be53cb75670b548948636a0db1d1ff112bf12`.

The disabled mcudl branch calls mtk_wmt_get_gps_lna_pin_num, which calls
wmt_lib_get_gps_lna_pin_num, then mtk_consys_get_gps_lna_pin_num. The legacy
producer in common_main/platform/mtk_wcn_consys_hw.c:468..480 obtains a DT
pinmux and returns `(pinmux >> 8) & 0xff`. Thus the ABI is a SoC pin index,
not a dynamic Linux GPIO number. That legacy producer has unchecked reads and
a 0xffffffff initial sentinel; neither is copied into the new implementation.

Current ownership belongs to gps_dl_probe and its GPS-node pinctrl context,
not the old consys pinctrl-1 positional assumption. gps_dl_lna_pin_ctrl already
uses the named gps_l1_lna_dsp_ctrl state. MT6878's binding defines seven valid
L1 DSP alternatives: pin/function 18/6, 20/4, 33/3, 143/2, 154/3, 181/3, 186/2.
These form a validation set, never a fallback or board-specific selection.

Important: the entire reference GPS LNA block in k6878v1_64.dts is inside
`#if 0`. k6878v1_64_tetris.dts includes that file but supplies no LNA override.
Therefore GPIO143 is NOT proven enabled Tetris wiring by those source records.
No DT patch enabling that block is included. Existing local pmOS DT records may
satisfy the query but their board/SKU provenance remains main's validation gate.

## Query Contract

At probe, read metadata only after the existing pinctrl initialization. Require:

- Available GPS owner with mediatek,mt6878-gps compatibility and resolved L1 DSP state.
- Named pinctrl state with exactly one phandle, not a guessed numeric slot.
- Available state under the mediatek,mt6878-pinctrl controller.
- Exactly one available child, one pinmux cell, and a binding-valid L1 DSP function.

The optional metadata read does not alter the pre-existing probe result. Missing
metadata reports ENODATA or ENODEV at query time; malformed/ambiguous records
report EINVAL, unsupported SoC reports EOPNOTSUPP. No 0/143/0xffffffff fallback.
The cache is protected by a mutex. A second distinct owner latches a global
EBUSY error immediately, because the pre-existing singleton driver globals can
now refer to a different device. All later queries fail closed and leave the
user buffer untouched. Neither owner-removal order nor re-probing either owner
can revive cached metadata. The latch clears only after driver-wide
platform_driver_unregister has synchronously removed every bound device (or
fresh module/boot state), not after individual removal. A clean new probe must
then supply metadata again. Without conflict, owner removal invalidates the
cache normally. This deliberately conservative barrier avoids needing an
unbounded owner registry and also covers additional ambiguous probes.
Successful copy returns zero; bad user buffer returns EFAULT. Compat pointers
are translated under CONFIG_COMPAT. No new exported inter-module symbol needed.

Scope intentionally covers mcudl ioctl16 and L1 only. It neither enables the
disabled old data_link ioctl branch nor invents L5 selection from a device index.

## Validation And Integration

Seven source tests passed locally, including exact pristine patch application without
fuzz/offset, decoder equality to every pinned GPS_L1_ELNA_EN binding alternative,
absence of added control APIs and owner/compat/error contracts. Shell syntax
passed. No C/kernel builds or phone operations were run locally.

CI checkout paths are injectable through `TETRIS_MODULES_TREE` and
`TETRIS_DEVICE_MODULES_TREE`; local workspace paths are defaults only. An
explicit invalid override fails rather than falling back. Main supplies the
exact fetched checkout paths; names such as android-kernel-modules are not
assumed. Both repositories must contain the pinned commits used by git show.

The source check also applies the entire package 1002/1003/1004/1005 stack to
disposable pinned inputs before the candidate. Pre-1005 clock CRLF normalization
matches APKBUILD. Every application uses fuzz=0; line offsets from earlier
patches are allowed in this stacked check. The final metadata parser/cache must
equal the pristine candidate code, while Linux-6.18 remove and clock-error
changes remain present. Native parser fixtures now use this stacked output.

Main CI: `sh patches/gnss-navigation-audit/run_lna_metadata_ci.sh` on Ubuntu.
It retains ASan/UBSan and runs two native fixtures:

- The actual decoder across 65536 mux values, invalid upper bits and null output.
- The actual patched parser/cache extracted into a disposable include, with
  synthetic OF APIs, twelve invalid-record cases, reference balance, missing
  pinctrl, first-valid/second-probe query rejection, both removal orders,
  repeated-init rejection while conflicted and driver-wide lifecycle reset.

The parser fixture does not validate real OF lifetime or kernel mutex behavior.
Main must compile the touched GPS module against its kernel/config and apply
the patch after the existing compatibility patch stack. The patch includes its
header; the separate identical header is the native fixture input. No APKBUILD,
global CI or frozen first-config/query/adapter files changed here.

Next runtime gate: on a clean main-owned CI boot, confirm the actual live GPS
node/state/controller/mux matches authoritative board data, then query ioctl16
through the existing sole GNSS descriptor owner. Record exactly four returned
bytes and ioctl status; absent records must fail, invalid user pointer must
return EFAULT. Keep the established USB/SSH and controlled GNSS-close checks.
Do not start libMNL until first/second policy, XML/calibration, stop/transport,
mandatory host services and assistance routing are complete. Kernel metadata
support removes the disabled-ioctl obstacle only when actual valid DT exists.
