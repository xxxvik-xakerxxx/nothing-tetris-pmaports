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

## Audit of experimental patch 0034

`0034-arm64-dts-mt6878-tetris-camera-inventory.patch` is safe to retain as a
disabled inventory patch:

- every new child has `status = "disabled"`;
- it adds no regulators, GPIOs, clocks, resets, endpoints, power domains, or
  automatic module loading;
- it does not enable I2C4, I2C7, or I2C8;
- its addresses and candidate names match the Nothing OS 4.1 Tetris DTS;
- it applies without fuzz and passes strict `checkpatch.pl`;
- the target DTB compiles, and the warning set is identical to the baseline
  DTB (53 existing warnings, 53 with the inventory patch).

The vendor-only compatibles (`mediatek,imgsensor`,
`mediatek,camera_eeprom`, and `mediatek,pd9302a`) have no binding or driver in
the current mainline tree. Therefore this patch is documentation in DT form;
it is not a camera foundation that should be advertised as functional.

## Missing dependency chain

Do not enable any inventory node until all owners below have a validated
probe-off and stream-off path:

1. MT6878 camera clocks and CAMSYS power domains, including runtime PM and
   IOMMU ownership.
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
7. CCU/remoteproc firmware and ABI, plus the userspace V4L2/libcamera pipeline.
   A media node alone does not establish preview or capture support.
8. LM3644 thermal/current limits and V4L2 flash integration as a separate
   gate.

The full vendor `mtkcam` stack also contains Android-specific ISP, imgsys,
CMDQ, AIE, scheduling, and firmware interfaces. It must not be blanket-built
or autoloaded as the first experiment.

## Next static gate

Prepare a build-only patch set in this order, with no DT status changes:

1. compile the three sensor variant pairs against the exact CI kernel;
2. compile read-only cam_cal and PD9302A independently;
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

Only after that gate passes may the next experiment enable one adapter and one
driver with all camera children still disabled. The rollback is a clean reboot
to the previous CI artifact; any USB/SSH loss, firmware assert, remoteproc
reset, IOMMU fault, regulator imbalance, or stuck clock ends the experiment.
