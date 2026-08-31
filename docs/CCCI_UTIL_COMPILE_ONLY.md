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
composite `ccci_util_lib.o` with Clang/LLVM. The build uses hard errors for
implicit declarations, incompatible pointer types and integer conversions.
Only existing missing-prototype warnings remain.

`APKBUILD` now applies the patch only to the vendor source tree and runs a
dedicated compile-only external-module gate after the exact Linux 6.18 kernel
and its top-level `Module.symvers` have been built. The gate requires clean
modpost, emits `ccci_util_lib.ko` only inside the temporary vendor build tree,
and validates its module name, GPL license, description and exact kernel
release prefix in `vermagic`. CI separately rejects the module if it appears in
the packaged rootfs.

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

## Evidence state

The earlier isolated object build established the source/API boundary. The
next full package build must prove clean modpost against the exact generated
`Module.symvers` and record `modinfo` from the emitted validation-only module.
Until that CI result exists, final `.ko`, `vermagic` and symbol-version evidence
remain pending.

This gate does not install, package or autoload `ccci_util_lib.ko`. It does not
enable a kernel config symbol in the shipped `.config`, add a DT node, supply
firmware, invoke an SMC, or control modem power/reset. `mddriver`, DPMAIF and
CCMNI remain outside this boundary, so runtime modem behavior is unchanged.
