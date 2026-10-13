# Matched Native START Image Candidate

New image scope only. Published real-boot/native-start/native-link helpers, workflow
and shipping packages are unchanged. This composes an independent package COPY,
not an overlay of previously compiled modules onto the running r189 image.

## Concrete Missing Plumbing

The frozen AP-only util `ccci_util_init()` skips the stock runtime initializers.
Prepared registration actually calls `tetris_sysfs_register()` after FSM/port
commit. `ccci_sysfs_add_modem()` rejects `!ccci_sys_info` with
`-CCCI_ERR_SYSFS_NOT_READY`. Calling the legacy initializer unchecked is unsafe:
`inject_md_status_event()` dereferences `s_bc_ctl_tbl[i]`, pin injection dereferences
`pin_event`, and the logger/event reader requires real buffers and initialized locks.

The new generated vendor delta wires checked constructors into the actual util
module init. It allocates the NOS log/dump/event buffers and broadcast/pin objects,
initializes their actual lists/locks/waitqueues, then calls the genuine common
sysfs constructor before the SMEM mapper's boot-lifetime module pin. There is no
new fallible AP initializer after that ownership transition. Every constructor failure returns an error with
unpublished-resource cleanup. There are no ready flags, test callbacks or proof
cookies. Dependent module references protect these resources once used. Native
sysfs omits boot/reset/PIN controls; legacy broadcast character devices, proc dump
controls and SIB hardware initialization are not installed. Existing received
events still own modem state; no status or handshake is synthesized.

The shipping `/modem` is only a metadata anchor. B4.1's actual
`md_cd_get_modem_hw_info()` rejects absent `mediatek,cldma-capability`, and missing
WDT IRQ yields zero/failure. The candidate DT now supplies the genuine MT6878
capability 14, HIF mask 6, EPON layout 0x64/6, boot-status configuration, L2 SRAM
resource and WDT SPI491 inventory. The sequencer resource comes from the actual
NOS getter's 0x1c803000 fallback, now expressed as a checked DT resource rather
than an unclaimed hardcoded mapping. The new branch in that real caller validates
native supplier readbacks, uses `platform_get_irq()` and checked
`devm_ioremap_resource()` claims, propagating their errors. It does not infer secure
NS access from mapping or Linux ownership.

`power-domains = <&md_spm 0>` supplies the actual platform/genpd input required by
`mt6878_md_adopt_binding(..., true)`. Without it that function returns `-EINVAL`.
TOP/infracfg and the three rail phandles retain their actual providers. Consumer,
CCIF/DPMAIF/CCIF4/CCIF5 and rails remain disabled. Disabled rail admission would
return `-ENODEV`; absent operational HIF providers prevent prepared commit. The
f25 loader deliberately publishes a disabled modem, not authority to enable one.
No activation option or automatic caller of `ccci_tetris_native_first_start()` is
added. Its real post-bind API and existing FSM START call chain remain installed
code awaiting loader/secure/controller admission.

Sources: exact device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`,
`arch/arm64/boot/dts/mediatek/mt6878.dts`, ECCCI `md_sys1_platform.c` and util
main/sys/private-log/broadcast/pin sources; companion modules
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`; Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`. No untracked input is adopted.

## Parent Call

On Linux GitHub CI, use a fresh COPY of the reviewed shipping pmaports packages,
not the already staged r188/r189 session tree. Require the completed native-link
gate before publishing an image; its pending result is not assumed here.

```sh
python3 -B patches/modem/md-pm-integration/native-link/image/stage.py \
  --pmaports /tmp/tetris-native-start-image/pmaports \
  --vendor /tmp/tetris-kernel-smoke/vendor-git-source \
  --pristine-kernel /tmp/tetris-native-start-pristine \
  --report /tmp/tetris-native-start-image/pmaports/native-start-image.json \
  --candidate-pkgrel 190 --include-native-start-image
```

The revision is explicit and must exceed r189; the example is not a published
package or reservation. Build boot/FIT/kernel/modules/rootfs together through the
existing parent image route, preserving the exact f25 loader
`f25c01444a642c6fca857bd9678ef438ec371988` and stock recovery slot. No loader is
downloaded, selected or flashed by this helper. GNSS exact1009, SCP, conninfra,
USB and display source inputs remain unchanged. It does not include session1010.

The generated APKBUILD prepares fresh source-only native vendor copies and uses
the original util/ECCCI/HIF/CCMNI/RPS Kbuilds. It links the sole mapped util plus
eight native composites against this package's real kernel and original shipping
SCP/rpmsg/tinysys exports. Shipping ThinLTO, CFI, signatures, architecture and
MODVERSIONS settings are unchanged. Strict modpost and actual ELF/export-owner,
namespace, dependency, CRC/config/vermagic checks must pass before installation.
Alpine build dependencies use `py3-elftools` and `dtc`. All local source checks
are non-compiling; the new image-specific C delta is not covered by the earlier
seven-unit native-start compiler result.

Compiled DT validation compares the whole inherited board, allowing only the
explicit disabled-consumer resource delta and HIF status changes; SCP/USB/display/
conninfra typed references remain identical. The nine modules install once into
`extra/mediatek-native-modem`, with blacklist plus install-denial policy, no init
service, autostart or activation script. Module/DT reports are installed with them.
Checksums are computed for every generated source and changed config/device input;
the parent must still run normal pmbootstrap checksum/package/image gates.

Local checks from this directory:

```sh
python3 -B -m unittest -v test_static.py
python3 -B stage.py --source-check --vendor <exact-vendor-git> --pristine-kernel <pristine-d84>
```

Trusted final loader descriptor/lifetime and secure NS access, genuine IRQ/DMA/
clock ownership, calibration owners when requested, controlled first START and
HS1/HS2, forced removal/STOP/restart/exception/suspend safety remain unresolved.
Package composition or POWER0 does not prove READY, SIM or cellular service.
Only selected modules, reports, symbol tables and logs are artifact candidates,
not vendor/kernel build trees. No local native build, phone, remote or slot change.
