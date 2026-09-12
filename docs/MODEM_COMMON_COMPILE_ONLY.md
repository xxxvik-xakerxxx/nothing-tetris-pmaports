# CCCI modem common Linux 6.18 compile-only evidence

## Boundary

This gate builds exactly three translation units from
`NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878` commit
`ee2be53cb75670b548948636a0db1d1ff112bf12` (Nothing OS 4.1, Tetris B4.1)
against `MT6878-mainline/linux` commit
`d84b264a54a37611f2f46bc19363cb9b41606205` (Linux 6.18):

- `drivers/misc/mediatek/eccci/ccci_modem.o`
- `drivers/misc/mediatek/eccci/hif/ccci_hif.o`
- `drivers/misc/mediatek/eccci/fsm/ap_md_mem.o`

It advances the compile boundary only. It does not link or install a module,
change Kconfig, add or enable DT, add an autoload rule, map modem memory,
request an IRQ, start DMA, or issue an SMC. Modem, SIM, calls, SMS and mobile
data therefore remain `Broken`.

## Source adaptation

Patch `0089-vendor-eccci-modem-common-compile-only.patch.vendor` adds the
explicit `<linux/sched/clock.h>` include required for `local_clock()` on Linux
6.18. Its SHA-512 is
`6ed67c1975e76cdf9f11cca3974e5620f94f4bd46d160ad6afbea6513d11dc7f1e7018422616b7a8077ada9e8d8aa868c9c10c26a57c20db2aa4d592d806d8b1`.
No function body or runtime path changes.

The patch must be applied after the existing CCCI util, core and CCIF
compatibility patches. `scripts/validate-pmaports-overlay.sh` checks this
ordering and rejects additions to this patch that introduce SMC, DMA, module
registration, device matching or an enabled DT status.

## Reproducible package gate

The kernel package's `_build_ccci_modem_common_compile_only()` runs after the
fully built LLVM 21 kernel and directly requests only the three object targets:

```sh
make -C "$builddir" M="$_devmods_dir/drivers/misc/mediatek/eccci" \
	ARCH=arm64 LLVM=1 \
	KERNEL_SRC="$builddir" KERNEL_OUT="$builddir" \
	DEVICE_MODULES_PATH="$_devmods_dir" \
	CONFIG_ARM64=y CONFIG_MTK_ECCCI_DRIVER=m \
	CONFIG_MTK_SECURITY_SW_SUPPORT=n \
	CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n CONFIG_MTK_AEE_IPANIC=n \
	KCFLAGS='-Werror=implicit-function-declaration \
	-Werror=incompatible-pointer-types -Werror=int-conversion \
	-DCONFIG_MTK_COMBO_CHIP_CONSYS_6878=1 \
	-Wno-error=format -Wno-error=format-extra-args \
	-Wno-error=missing-prototypes' \
	ccci_modem.o hif/ccci_hif.o fsm/ap_md_mem.o
```

The gate requires all objects to be non-empty, checks representative defined
symbols with `llvm-nm`, and fails if any `.ko` exists below the ECCCI source
directory. The package function never copies these objects into `$pkgdir`.
The CI rootfs check independently rejects every `ccci*.ko*` artifact.

Run the static package/overlay checks from the repository root with:

```sh
sh -n scripts/validate-pmaports-overlay.sh
./scripts/validate-pmaports-overlay.sh
```

## Local result

The exact-source rerun used Alpine Clang/LLVM 21.1.8. All three targets built
successfully and the object checks passed:

| Object | Size | SHA-256 |
| --- | ---: | --- |
| `ccci_modem.o` | 338132 | `dd3e6589f37fd7f6e410b3693652e0a524763e529ede51d0f8dc2708dc0df8d1` |
| `hif/ccci_hif.o` | 379176 | `ded0f1e0db705323a5f65aa199b5110db7c1f7e5602da66929254794d1f679a0` |
| `fsm/ap_md_mem.o` | 33608 | `c486149c5149fb2680666d33b239a8d58ef2abb5bf4a8c9da7444bb9faf9890c` |

`llvm-nm` found `ccci_get_per_md_data`, `ccci_hif_register` and
`ap_md_mem_init`; the ECCCI tree contained zero `.ko` files. The only compiler
diagnostics were existing missing-prototype warnings for
`get_smem_by_user_id()` and `ccci_md_clear_smem()`. They remain visible because
changing linkage without the later cross-object audit would alter the vendor
ABI rather than improve this compile boundary.

The unresolved-symbol inventory includes `modem_sys`, `sched_clock`, CCCI
debug/HIF registration helpers, `get_md_resv_mem_info()` and the
`mtk_ccci_get_md_*_smem_inf()` family. This is expected evidence that the
objects are not independently loadable.

## Remaining risks

These objects retain unresolved cross-object and kernel references by design.
They do not establish a link-complete ECCCI stack. In particular,
`ap_md_mem.o` describes writable AP/MD shared-memory setup, and the later FSM
and HIF owners can reach modem power, secure-call, IRQ and DMA paths once
linked and probed.

Patch `0095` now compile-checks the vendor FSM, port and non-page-pool DPMAIF
groups separately. It does not resolve this runtime boundary or make the
earlier common objects loadable.

Before any link, package or runtime step, separately validate the complete
undefined-symbol closure, bootloader handoff and reserved-memory bounds,
trusted-firmware CCCI command semantics, power/reset/clock ownership, IRQ and
DMA isolation, firmware identity and teardown behavior. USB NCM/SSH and Wi-Fi
remain hard stop conditions for every later live experiment.
