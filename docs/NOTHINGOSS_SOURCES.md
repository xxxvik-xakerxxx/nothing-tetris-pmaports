# NothingOSS source map for Tetris

This port should prefer official NothingOSS Tetris module sources over local
driver rewrites during hardware bring-up. Local kernel patches should mostly
provide the postmarketOS glue: pinned source commits, module build wiring,
small Linux API shims, devicetree nodes, MFD cells, firmware packaging and
UCM/userspace integration.

## Authoritative Tetris repositories

| Repository | Use |
| --- | --- |
| `NothingOSS/android_kernel_6.1_nothing_mt6878` | Android kernel source and device tree reference for CMF Phone 1. Use it to verify registers, DT nodes, clocks, resets, pinctrl, panel/audio/camera topology and vendor driver expectations. |
| `NothingOSS/android_kernel_modules_nothing_mt6878` | Vendor module tree for connectivity and large out-of-tree blocks. For Tetris use the pinned `mt6878/Tetris/16b` commit. |
| `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878` | Vendor device-module tree for PMIC, sound, media, LEDs, IIO, power, USB, thermal, haptics and other peripheral drivers. For Tetris use the pinned `mt6878/Tetris/16b` commit. |
| `NothingOSS/android_kernel_build_nothing_mt6878` | Build metadata reference. Use it to identify which vendor modules Nothing intended to build together and the config symbols they expect. |

Other NothingOSS repositories target different SoCs or devices. They are useful
only as style/reference material, not as direct Tetris module sources.

## Current pinned Tetris 16b sources

| APKBUILD variable | Repository | Commit |
| --- | --- | --- |
| `_connmods_commit` | `android_kernel_modules_nothing_mt6878` | `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` |
| `_devmods_commit` | `android_kernel_device_modules_6.1_nothing_mt6878` | `ee2be53cb75670b548948636a0db1d1ff112bf12` |

Pin commits, not branch names. NothingOSS branch heads can move; pmaports
builds must be reproducible.

## Module-first bring-up queue

| Block | Source | Expected approach | Notes |
| --- | --- | --- | --- |
| Wi-Fi / Bluetooth | `android_kernel_modules_nothing_mt6878/connectivity` | Already staged as vendor modules. Keep fixing Linux 6.18 API fallout and firmware/service loading. | Includes `conninfra`, `connfem`, WMT, WLAN and BT pieces. |
| GNSS / FM | `android_kernel_modules_nothing_mt6878/connectivity/gps`, `fmradio` | Add after Wi-Fi/BT base is stable because they share connsys infrastructure. | Needs userspace integration later. |
| Speaker / microphones | `android_kernel_device_modules_6.1_nothing_mt6878/sound/soc` | Stage official MT6878 AFE, MT6369 codec and MT6878-MT6369 machine driver modules. Add board DT and UCM. | Current r78 work wires the first pass. |
| PMIC ADC / efuse | `android_kernel_device_modules_6.1_nothing_mt6878/drivers/iio`, `drivers/nvmem` | Stage vendor PMIC ADC/efuse modules or port the small parts natively. | Needed to remove temporary optional audio calibration fallback. |
| Flashlight / LEDs | `android_kernel_device_modules_6.1_nothing_mt6878/drivers/leds` | Prefer vendor modules first, then expose LED/V4L2 flash class cleanly. | Likely a better near-term target than full camera. |
| Thermal / hwinfo | `android_kernel_device_modules_6.1_nothing_mt6878/drivers/thermal`, `drivers/chino-e` | Stage small modules where dependencies are limited. | Useful for status page and device diagnostics. |
| Camera | `android_kernel_modules_nothing_mt6878/mtkcam` plus `device_modules/drivers/media` and camera misc drivers | Treat as a large staged stack, not one giant patch. Start with sensor inventory, cam_cal, VCM/OIS/flash, then ISP/media graph. | Kernel probe alone will not make a usable camera without DT, media pipeline and userspace stack. |
| GPU | `android_kernel_modules_nothing_mt6878/gpu` and `device_modules/drivers/gpu` | Large staged stack. Requires power domains, clocks, firmware/userspace and careful ABI work. | Do after core phone features unless CI capacity is available. |

## Maintenance rule

Do not copy entire vendor subsystems into the mainline kernel patch series as
one monolithic patch. Add one postmarketOS-maintainable hardware block at a
time:

1. pin official NothingOSS source commit;
2. build only the needed `M=...` module directories;
3. add minimal API shims in `prepare()`;
4. install the resulting `.ko` files under `extra/mediatek-*`;
5. add only the DT/MFD/UCM glue needed for probe and testing;
6. validate on hardware before enabling the next block.
