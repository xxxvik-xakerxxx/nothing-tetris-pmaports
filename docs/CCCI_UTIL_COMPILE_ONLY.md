# CCCI util Linux 6.18 compile-only evidence

## Scope

- Vendor source: `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878`
  at `ee2be53cb75670b548948636a0db1d1ff112bf12` (Nothing OS 4.1,
  Tetris B4.1).
- Kernel source: `MT6878-mainline/linux` at
  `d84b264a54a37611f2f46bc19363cb9b41606205` (Linux 6.18).
- Only `drivers/misc/mediatek/ccci_util` was compiled.
- `CONFIG_MTK_ECCCI_DRIVER=m`; modem security and NVRAM anti-clone options
  were disabled for this first compatibility boundary.
- No DT, autoload, firmware, SMC, power, mddriver, DPMAIF, CCMNI, packaging or
  runtime changes are part of this work.

## Result

The unmodified B4.1 source stopped on two calls to the pre-6.4
`class_create(owner, name)` API. Patch
`0039-vendor-ccci-util-linux-6.18-api.patch.vendor` removes the obsolete owner
argument from the broadcast and SIM pin status classes.

After the patch, all 15 `ccci_util_lib` objects compiled and linked into the
composite `ccci_util_lib.o` with Clang/LLVM. The build used hard errors for
implicit declarations, incompatible pointer types and integer conversions.
Only existing missing-prototype warnings remained.

Final module modpost could not be completed because the prepared local Linux
tree has no top-level `Module.symvers`. Consequently modpost reported ordinary
kernel APIs such as `_printk`, `class_create`, `ioremap_prot` and
`of_find_compatible_node` as unresolved. This is a kernel build-output gap, not
evidence that these APIs need another modem module. No `.ko` was emitted, so
`modinfo` is also pending.

## Static dependency audit

The linked object has 60 undefined references. Every reference is a normal
Linux 6.18 kernel API or arm64 implementation symbol under this compile config;
there is no unresolved CCCI, mddriver, DPMAIF, CCMNI, SMC, firmware or power API.

The source requires the vendor public header
`drivers/misc/mediatek/include/mt-plat/mtk_ccci_common.h`. The optional
`mrdump_mini_add_extra_file` dependency is compiled only when
`CONFIG_MTK_AEE_IPANIC` is enabled; that option was disabled here and must be
audited separately before enabling it. The MASP security path was also disabled
and remains outside this first layer.

## Remaining gate

Repeat the same isolated module build against a fully built copy of the exact
Linux 6.18 kernel with its matching `Module.symvers`. Require clean modpost,
`ccci_util_lib.ko`, `modinfo`, and a reviewed symbol/version list. Do not add the
patch to `APKBUILD`, install or load the module as part of that compile gate.
