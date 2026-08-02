# NothingOSS 4.1 source map for Tetris

This port uses official Nothing OS 4.1 Tetris module sources as a temporary bridge
for complex hardware and as a register/topology reference for native drivers.
Package boundaries, compatibility rules and promotion gates are documented in
`docs/DRIVER_STRATEGY.md`.

## Authoritative Tetris repositories

| Repository | Use |
| --- | --- |
| `NothingOSS/android_kernel_6.1_nothing_mt6878` | Android kernel source and device tree reference for CMF Phone 1. Use it to verify registers, DT nodes, clocks, resets, pinctrl, panel/audio/camera topology and vendor driver expectations. |
| `NothingOSS/android_kernel_modules_nothing_mt6878` | Vendor module tree for connectivity and large out-of-tree blocks. Use the pinned Nothing OS 4.1 commit below. |
| `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878` | Vendor device-module tree for PMIC, sound, media, LEDs, IIO, power, USB, thermal, haptics and other peripheral drivers. Use the pinned Nothing OS 4.1 commit below. |
| `NothingOSS/android_kernel_build_nothing_mt6878` | Build metadata reference. Use it to identify which vendor modules Nothing intended to build together and the config symbols they expect. |

Other NothingOSS repositories target different SoCs or devices. They are useful
only as style/reference material, not as direct Tetris module sources.

## Current pinned Nothing OS 4.1 sources

| APKBUILD variable | Repository | Commit |
| --- | --- | --- |
| `_connmods_commit` | `android_kernel_modules_nothing_mt6878` | `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` |
| `_devmods_commit` | `android_kernel_device_modules_6.1_nothing_mt6878` | `ee2be53cb75670b548948636a0db1d1ff112bf12` |

Both commits are the official `Tetris-B4.1-260415-1709` source drop. The
`mt6878/Tetris/16b` branch name is not a version-selection rule: only commits
identified as Nothing OS 4.1 or newer are accepted. Older Tetris drops may be
used for historical comparison, but never as build inputs or hardware truth.

Pin commits, not branch names. NothingOSS branch heads can move; pmaports
builds must be reproducible.

Fenrir's `bin/tetris.bin` is a stock LK container from
`B4.1-260615-1652`. It is useful for reverse engineering the bootloader-to-
Linux handoff, secure connsys memory layout and firmware-loading contract. It
does not contain reusable Linux drivers and is not shipped by this repository.

## Module-first bring-up queue

| Block | Source | Expected approach | Notes |
| --- | --- | --- | --- |
| Wi-Fi / Bluetooth | `android_kernel_modules_nothing_mt6878/connectivity` | Staged as B4.1 vendor modules with native cfg80211/HCI integration and reproducible boot services. | Includes `conninfra`, `connfem`, WMT, WLAN and BT pieces; per-device calibration/address data is read-only extracted from `nvdata`. |
| GNSS / FM | `android_kernel_modules_nothing_mt6878/connectivity/gps`, `fmradio` | MT6878 GNSS v050 is staged after live boot, probe, IRQ and power-cycle validation; FM remains inventory-only. | GNSS still needs position-data, suspend and standard userspace integration. |
| Speaker / microphones | `android_kernel_device_modules_6.1_nothing_mt6878/sound/soc` | Stage official MT6878 AFE, MT6369 codec and MT6878-MT6369 machine driver modules. Add board DT and UCM. | Current r78 work wires the first pass. |
| PMIC ADC / efuse | `android_kernel_device_modules_6.1_nothing_mt6878/drivers/iio`, `drivers/nvmem` | Stage vendor PMIC ADC/efuse modules or port the small parts natively. | Needed to remove temporary optional audio calibration fallback. |
| Flashlight / LEDs | `android_kernel_device_modules_6.1_nothing_mt6878/drivers/leds` | Prefer vendor modules first, then expose LED/V4L2 flash class cleanly. | Likely a better near-term target than full camera. |
| Thermal / hwinfo | `android_kernel_device_modules_6.1_nothing_mt6878/drivers/thermal`, `drivers/chino-e` | Stage small modules where dependencies are limited. | Useful for status page and device diagnostics. |
| Native display | `android_kernel_device_modules_6.1_nothing_mt6878/drivers/gpu/drm` | Keep the working framebuffer path in the stable build. Test the official DRM v2 stack as a separate experiment. | Tetris uses `samsung,s6e8fc3x02`; Nothing builds `panel-samsung-s6e8fc3x02.ko` together with `mediatek_v2/mediatek-drm.ko` and helper modules. |
| Camera | `android_kernel_modules_nothing_mt6878/mtkcam` plus `device_modules/drivers/media` and camera misc drivers | Treat as a large staged stack, not one giant patch. Start with sensor inventory, cam_cal, VCM/OIS/flash, then ISP/media graph. | Kernel probe alone will not make a usable camera without DT, media pipeline and userspace stack. |
| GPU | `android_kernel_modules_nothing_mt6878/gpu` and `device_modules/drivers/gpu` | Large staged stack. Requires power domains, clocks, firmware/userspace and careful ABI work. | Do after core phone features unless CI capacity is available. |

## Official Tetris 4.1 module inventory

Nothing's `mgk_64_k61.bzl` confirms these hardware groups are intended to be
built for this MT6878 family:

- connectivity: `conninfra`, `connfem`, WMT/common, Wi-Fi, Bluetooth, GNSS and
  FM radio;
- input: PMIC keys, FocalTech/Goodix/Novatek touch modules and Goodix
  fingerprint support;
- power and PMIC support: MT6375/MT6379 MFD, charger/supply, IIO ADC,
  SPMI-PMIC ADC and NVMEM/efuse support;
- multimedia: MT6878 AFE, MT6369 codec, AW88261 speaker path, JPEG/VDEC/VENC,
  camera calibration, sensors, ISP, VCM/OIS and flash modules;
- display/GPU: MediaTek DRM v2, `panel-samsung-s6e8fc3x02`, MML, display
  notifier/security/AOD helpers, Mali GPU modules and MediaTek GED/GPUEB/QoS;
- platform diagnostics: thermal, hwinfo/board-id, EMI/MMQoS, USB/Type-C,
  haptics, LEDs, flashlight and logging/debug helpers.

The stable port should not enable this whole list at once. Keep already working
local patches for framebuffer display, touchscreen and the currently proven
PMIC/peripheral glue. For hardware that is still broken or missing, prefer the
official module implementation, added in small package-level groups with one
clear owner per patch.

## Display finding

The official native display implementation exists, but it is not only a panel
driver. The Tetris device tree uses `compatible = "samsung,s6e8fc3x02"`, and
Nothing builds `drivers/gpu/drm/panel/panel-samsung-s6e8fc3x02.ko`. That panel
depends on MediaTek DRM v2 helpers such as `mtk_panel_ext`, DDP/DSI, MML and
display notifier modules. Because the framebuffer handoff is currently the
known-good display path, native DRM should be developed as a separate patch set
or branch and only merged into the stable build after it shows a real userspace
KMS framebuffer on hardware.

## Maintenance rule

Do not copy entire vendor subsystems into the mainline kernel patch series as
one monolithic patch. Add one postmarketOS-maintainable hardware block at a
time:

1. pin official NothingOSS source commit;
2. build only the needed `M=...` module directories;
3. carry Linux API compatibility as explicit vendor patch files;
4. install the resulting `.ko` files under `extra/mediatek-*`;
5. add only the DT/MFD/UCM glue needed for probe and testing;
6. validate on hardware before enabling the next block.
