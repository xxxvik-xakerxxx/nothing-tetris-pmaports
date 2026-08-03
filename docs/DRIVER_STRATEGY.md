# Driver integration strategy

The port has two goals that must remain separate:

1. provide a usable Tetris build while hardware is being reverse engineered;
2. replace vendor compatibility modules with native Linux drivers over time.

## Package boundaries

| Package | Ownership |
| --- | --- |
| `linux-postmarketos-mediatek-mt6878` | Kernel, DT, native patches, and ABI-matched MT6369 calibration, NothingOSS connectivity, and MT6878 audio modules. |
| `firmware-nothing-tetris` | Proprietary MT6631 Wi-Fi, Bluetooth and GNSS firmware with the names requested by the drivers. |
| `device-nothing-tetris` | Device metadata, boot layout, UCM/UI configuration, udev rules and temporary module loading policy. |

External modules are built together with the kernel and depend on its exact
package release. Linux has no stable in-kernel module ABI, so a module built for
another release must never be reused.

## Vendor compatibility rules

- Pin immutable NothingOSS commits and use real archive checksums.
- Keep compatibility changes as patches, never source-editing commands in
  `APKBUILD`.
- Do not suppress implicit declarations, incompatible pointers, integer
  conversions or invalid return types.
- Keep every vendor group independently packageable under `extra/mediatek-*`.
- Package modules before enabling their DT consumers.
- Do not autoload experimental display, GPU, camera, modem or sensorhub stacks.
- Preserve the inherited framebuffer until native KMS is proven on hardware.
- Keep GNSS manual until position data, repeated power cycles and suspend/resume
  pass while Wi-Fi, Bluetooth and USB remain healthy.

## Migration classes

### Native first

- PMIC MFD/IRQ, regulators, keys and power supply;
- pinctrl, clocks and power domains;
- Type-C/TCPM, touchscreen and haptics;
- flashlight through LED/V4L2 flash;
- direct I2C/SPI sensors through IIO;
- SD/MMC and USB.

### Vendor bridge, then native

- MT6631 conninfra, Wi-Fi, Bluetooth and GNSS;
- MT6878 AFE, MT6369 codec and AW88261 routing;
- Samsung S6E8FC3X02 with the complete MT6878 DRM path.

### Inventory only until dependencies exist

Loading these Android stacks prematurely can corrupt memory or reboot the
device. Keep their DT nodes disabled and use NothingOSS as a hardware reference:

- Mali GPU and MediaTek GED/GPUEB;
- camera ISP, sensors, VCM/OIS and calibration;
- modem/CCCI and SIM;
- SCP sensorhub and audio DSP.

## Hardware dependency map

| Function | Confirmed hardware/path | Integration |
| --- | --- | --- |
| SD card | MT6878 MSDC1, GPIO14 card detect, MT6369 VMCH/VMC | Native `mtk-sd`, patch `0014`. |
| Audio calibration | MT6369 AUXADC plus PMIC efuse | Vendor providers in the kernel package, patch `0013`. |
| Rear flash | Dual-channel LM3644 at I2C6 address `0x63`, enable GPIO155 | Small native LED/V4L2 driver; do not import Android flashlight-core. |
| Fingerprint | Goodix SPI1, IRQ GPIO18, reset GPIO73, MT6369 VFP | Experimental vendor bridge also requires the TEE userspace contract. |
| Rotation/ALS/proximity | MediaTek SCP sensorhub | Requires SCP firmware, SCP core, HF manager and sensorhub as one group. |
| Cameras | IMX882, GC16B3C and SC202CS through MT6878 seninf/ISP | Experimental camera group after clocks, power domains and IOMMU. |
| Modem/SIM | CCCI/DPMAIF, SIM detect GPIO46/GPIO47 | Experimental modem group plus userspace daemon and firmware. |
| SoC thermal | MT6878 LVTS, 24 sensors in MCU/AP/GPU domains, four efuse cells | Port the official B4.1 calibration/controller data to Linux thermal; start with read-only zones and conservative critical trips. |
| USB-C data role | MT6375 TCPM graph plus MTU3 dual-role controller and MT6375 OTG VBUS regulator | Preserve peripheral/NCM as the default; enable host role only after the VBUS regulator and role-switch ownership are complete. |
| Display | Samsung S6E8FC3X02 through MT6878 DSI/DSC | Keep inherited framebuffer until native DRM survives suspend/resume. |

The live hardware audits confirmed a 108 GiB root partition with about 97 GiB
free and all eight CPUs. `lscpu` correctly decodes four Cortex-A55 and four
Cortex-A78 cores. The blank processor row in GNOME 50.3 is a userspace parser
limitation, not missing kernel topology. The running kernel has no thermal
class, so thermal support remains a blocker before sustained GPU/modem/camera
loads.

## Promotion gate

A hardware block moves from experimental to default only after:

1. module dependency and symbol validation succeeds;
2. probe succeeds without warnings, lockups or unexpected reboots;
3. suspend/resume is tested;
4. the standard Linux userspace interface appears;
5. firmware and userspace configuration are packaged;
6. the feature table records the tested kernel release.
