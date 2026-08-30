# Nothing Tetris camera bring-up

Status: inventory only. No camera rail, clock, reset, SENINF, CAMSYS, CCU,
sensor, EEPROM, actuator, or flash node is approved for automatic probing.

## Authoritative source baseline

The board inventory is derived from the matching Nothing OS 4.1 source set:

- device modules: `ee2be53cb75670b548948636a0db1d1ff112bf12`
  (`Tetris-B4.1-260415-1709`);
- camera modules: `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`
  (`Tetris-B4.1-260415-1709`).

The device tree source is
`arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi`, included by
`k6878v1_64_tetris.dts`. The matching sensor implementations are under
`mtkcam/imgsensor/src-v4l2/common/` in the camera-modules repository.

## Confirmed inventory

| Role | Bus/address | Candidate IDs | Vendor CSI port | Additional device |
| --- | --- | --- | --- | --- |
| Main | I2C8, `0x1a` | IMX882 `0x8202`, IMX882TXD `0x8203` | 1 | PD9302A VCM at `0x0c`, EEPROM at `0x50` |
| Front | I2C4, `0x10` | GC16B3C `0x16b3`, GC16B3CTXD `0x16b4` | 0 | EEPROM at `0x50` |
| Auxiliary | I2C7, `0x36` | SC202CS `0xeb52`, SC202CSSJ `0xeb53` | 2A | no EEPROM node in the Tetris DTS |

The names and addresses above are source inventory, not detected hardware
identity. The alternate IDs show that module-vendor selection is required and
must not be hard-coded from one handset. EEPROM contents and calibration are
per-device data and must never be committed.

The vendor DTS also describes a dual LM3644 flash controller on I2C6 at
`0x63`. Flash bring-up remains a separate bounded power experiment; it is not a
prerequisite for identifying the three camera modules.

PD9302A is the only actuator referenced by the Tetris board DTS. The generic
vendor source tree contains OIS drivers, but the Nothing OS 4.1 Tetris camera
DTS does not instantiate an OIS device; those drivers are not board evidence.
The PD9302A driver uses a 10-bit `V4L2_CID_FOCUS_ABSOLUTE` range, obtains `vin`
and `vdd` supplies, optionally selects `vcamaf_on`/`vcamaf_off`, and parks the
lens toward position 512 before power-off.

## Audit of experimental patch 0034

`0034-arm64-dts-mt6878-tetris-camera-inventory.patch` is safe to retain as a
disabled inventory patch:

- every new child has `status = "disabled"`;
- it adds no regulators, GPIOs, clocks, resets, endpoints, power domains, or
  automatic module loading;
- it does not change adapter status or bus frequency. I2C4, I2C7, and I2C8
  already have no `status` property in `mt6878.dtsi` and are therefore active;
  disabled children are required to prevent client creation and I2C traffic;
- its addresses and candidate names match the Nothing OS 4.1 Tetris DTS;
- it applies without fuzz; strict `checkpatch.pl` reports no errors and only
  the expected missing-binding warnings for the disabled vendor compatibles;
- the target DTB rebuild and warning-set comparison must be repeated after
  removal of the earlier I2C frequency changes.

The vendor-only compatibles (`mediatek,imgsensor`,
`mediatek,camera_eeprom`, and `mediatek,pd9302a`) have no binding or driver in
the current mainline tree. Therefore this patch is documentation in DT form;
it is not a camera foundation that should be advertised as functional.

The earlier draft set the active adapters to the vendor frequencies (1 MHz on
I2C4/I2C8 and 400 kHz on I2C7). That was removed: an inventory patch must not
alter a live controller even when every newly described client is disabled.

## Board power and CSI trace

The Nothing OS 4.1 board source assigns CSI0 to front, CSI1 to main and CSI2A
to auxiliary. CSI receiver tuning is not interchangeable: front has D-PHY
settle delay 17, while main and auxiliary have HS-trail `0x20`; each port also
uses its own `csi_efuse0/1/2` NVMEM cell. The auxiliary path additionally
records a 312 MHz AOV CSI clock requirement.

All three sensors share a GPIO23-backed 1.8 V DOVDD rail. The main actuator
uses the GPIO1-backed 2.8 V AFVDD rail. Sensor-specific evidence is:

| Role | MCLK/reset | Switched analog/core rails | Camera gate |
| --- | --- | --- | --- |
| Main | GPIO93 CMMCLK1 / GPIO25 | AVDD GPIO22, DVDD GPIO21 | CAMTG2 |
| Front | GPIO96 CMMCLK4 / GPIO24 | DVDD GPIO20, AVDD GPIO19 | CAMTG5 |
| Auxiliary | GPIO94 CMMCLK2 / GPIO26 | AVDD GPIO28 | CAMTG3 |

Each sensor node offers 6, 12, 13, 19.2, 24, 26 and 52 MHz source clocks in
the vendor implementation. These GPIO numbers, rates and delays are
source-trace evidence, not permission to express switched rails as raw GPIOs
or to toggle them on a device. A mainline model needs regulators with complete
consumer ownership and a proven reverse-order shutdown path.

## Capture pipeline trace

The sensor inventory is only the edge of a much larger pipeline:

- SENINF owns CAM_MAIN and CSI_RX power domains, 12 receivers, 13 muxes, 43
  camera muxes, CSI analog registers, CAM/SENINF/CAMTG clocks, DVFS and the
  three per-port CSI efuses.
- CAMSV instances 0, 1 and 4 use CAM_MAIN, CAMSYS_MAIN clocks, SMI larbs,
  MMQoS interconnects and display-IOMMU ports.
- MRAW0 uses CAM_MAIN, CAMSYS_MAIN plus CAMSYS_MRAW clocks, larb25 and three
  display-IOMMU ports.
- RAW A and RAW B use CAM_SUBA and CAM_SUBB respectively, separate RAW/YUV
  clock domains, larbs 16/17 and 33/34, and distinct groups of DMA/IOMMU ports.
- CCU0/CCU1 use CAM_CCU_AO/CAM_CCU, CAM_MAIN handoff, larb30, multiple clocks,
  four IOMMU ports and a 1 MiB reserved-memory ABI. The matching vendor driver
  requests `lib3a.ccu`; the filename alone does not prove redistribution,
  firmware compatibility or a mainline remoteproc ABI.

The current mainline tree has no MT6878 SENINF, CAMSV, MRAW or RAW driver and
no matching DT bindings. Copying the vendor nodes would create unowned clocks,
power domains, DMA and firmware interfaces, so no pipeline node belongs in the
first camera patch set.

## Calibration trace

Main and front have explicit EEPROM clients at 7-bit address `0x50` (vendor
cam_cal tables encode the corresponding 8-bit address as `0xa0`). The tables
select different layouts for IMX882/IMX882TXD and GC16B3C/GC16B3CTXD and use
module identity to distinguish suppliers. The auxiliary DTS has no separate
EEPROM client, but both SC202CS variants still implement module-ID checking;
absence of a DTS EEPROM node must not be interpreted as absence of module
identity or calibration requirements.

Only bounded, read-only NVMEM access is acceptable for initial calibration
work. Per-device serials, module data, AWB/LSC/PDAF blobs and CSI efuses must
remain on the handset and must not be copied into patches, CI artifacts or
unredacted logs.

## Missing dependency chain

Do not enable any inventory node until all owners below have a validated
probe-off and stream-off path:

1. MT6878 CSI_RX, CAM_VCORE, CAM_MAIN, CAM_SUBA/B and CAM_CCU/AO power-domain
   support, complete camera clocks, runtime PM, SMI/MMQoS and IOMMU ownership.
2. MT6878 SENINF receiver and a complete media graph for CSI ports 0, 1, and
   2A.
3. Sensor drivers for both supplier variants of each camera, built against the
   pinned kernel ABI.
4. Board pinctrl and regulator sequencing. Vendor GPIO evidence is GPIO 93/25
   for main MCLK/reset, GPIO 96/24 for front, GPIO 94/26 for auxiliary,
   shared DOVDD on GPIO 23, main AFVDD on GPIO 1, and per-sensor AVDD/DVDD
   GPIOs. These numbers are evidence only, not an approved Linux power model.
5. EEPROM/cam_cal support with read-only, size-bounded access and variant
   selection. No calibration dump may enter artifacts or logs.
6. PD9302A V4L2 actuator support with a bounded park/power-down sequence.
7. CCU/remoteproc support, legal packaging of `lib3a.ccu`, firmware/secure
   handoff compatibility and ABI, plus the userspace V4L2/libcamera pipeline.
   A media node alone does not establish preview or capture support.
8. LM3644 thermal/current limits and V4L2 flash integration as a separate
   gate.

The full vendor `mtkcam` stack also contains Android-specific ISP, imgsys,
CMDQ, AIE, scheduling, and firmware interfaces. It must not be blanket-built
or autoloaded as the first experiment.

## Next static gate

Prepare a build-only patch set in this order, with no DT status changes and no
new module autoloading:

1. compile the three sensor variant pairs against the exact CI kernel;
2. replace vendor cam_cal access with bounded NVMEM layouts, then compile it
   and PD9302A independently;
3. inventory unresolved symbols and split kernel-subsystem dependencies from
   Android-only interfaces;
4. add DT bindings for any driver that survives that audit;
5. compile and validate the complete board DTB and inspect the resulting media
   graph before producing a CI image.

## First live gate

The first device experiment is observation-only.

- Record the exact CI artifact, bootloader, kernel, DTB, modules, boot slot,
  board/SKU identity, baseline `usb0`, SSH, I2C adapters, media devices, and
  first camera-related kernel errors.
- Verify that I2C4, I2C7, and I2C8 map to the expected MT6878 controllers from
  DT resources. Do not issue `i2cdetect`, raw I2C reads, regulator writes,
  GPIO changes, module loads, or remoteproc resets.
- Confirm that the disabled inventory creates no I2C clients and no new probe,
  power-domain, IOMMU, IRQ, thermal, or USB errors.
- Reboot normally and repeat three times. USB NCM/SSH and Wi-Fi must pass the
  existing regression gate after every boot.

## End-user gates

Camera support remains `Untested` until each gate passes in order:

1. Inventory: three clean boots create no camera clients and preserve USB
   NCM/SSH and Wi-Fi with no new kernel errors.
2. Identity: one sensor variant at a time is identified through a reviewed
   driver and complete regulator/clock/reset model; no raw bus scans are used.
3. Capture: the matching SENINF path produces a bounded test-pattern frame
   through one reviewed CAMSV/RAW route without IOMMU faults or leaked clocks.
4. Lifecycle: repeated open/capture/close, warm reboot and suspend/resume leave
   rails, clocks, CCU and actuator off and preserve USB/Wi-Fi.
5. User function: preview, still capture, video, orientation, autofocus and
   flash work through the shipped userspace without privileged setup.
6. Quality and portability: calibration is applied without exporting unique
   data, both supplier variants fail safely, and a second handset/SKU passes.

Only after the inventory gate may the next experiment instantiate one driver
while every power-producing camera component remains disabled. Enabling an I2C
adapter is not a useful gate here because these adapters are already active.
The rollback is a clean reboot to the previous CI artifact; any USB/SSH loss,
Wi-Fi regression, firmware assert, remoteproc reset, IOMMU fault, regulator
imbalance, stuck clock or unexplained battery drain ends the experiment.
