# IMX882 V4L2 Streaming Candidate

Status: **Untested on hardware**. This patch does not enable any board node,
request camera power on probe, or replace the identity driver's compatible.
It is a real sensor-side V4L2 implementation, not a working capture pipeline.

## Implemented

- Standard subdevice, source pad, format and frame-size negotiation.
- Exact vendor init and two 30 fps mode tables: 4000x3000 and 4096x2304.
- Exposure in lines, analogue gain in vendor 1024-base units, and VBLANK.
- Read-only HBLANK and upstream pixel-array PIXEL_RATE (878400000), frame
  interval reporting, and endpoint-derived C-PHY bus configuration.
- Group-held frame/exposure/gain writes with first-error preservation and an
  explicit release attempt after every possible hold-write failure.
- Explicit stream start/stop with sensor ID checked on each powered start;
  no retry, no speculative I2C scan, no state inherited from Android.
- Checked existing 24 MHz exclusive-clock and ordered supply/reset helpers.
- CSI-2 descriptors preserve both RAW10 (VC0/DT0x2b) and vendor PDAF
  (VC0/DT0x30). No register guessing to suppress the second packet type.
  Their maximum packed RAW10 lengths derive from the exact mode dimensions;
  PDAF is width x height/4, identified as a blob rather than Bayer image data.
- Short exposures only, 64-line margin and manual frame length; auto-extension
  is disabled using the vendor `set_shutter_frame_length(..., false)` path.
- A control transfer fault requires explicit stream-stop/power-down before
  restarting. An uncertain regulator teardown blocks further starts.
- Suspend rejects an active stream rather than silently dropping capture.

No long exposure shift, HDR, remosaic, flash, actuator, test-pattern mode
names, guessed link-frequency controls, or unit-specific calibration is added.
The vendor's no-QSC path writes 0x3206=0. This is not calibrated photography;
per-unit QSC and module supplier validation remain required before promotion.
The default Bayer code is the vendor's normal, binned RAW_4CELL_HW_BAYER_R
interpretation; actual colour order remains a frame-validation gate.

## Provenance

Nothing OS 4.1 modules:
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`,
`mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c`.
Register order is mechanically copied, not reconstructed from comments.
Gain base 0x400 is from that commit's `kd_imgsensor_define_v4l2.h`.
The upstream PIXEL_RATE control describes the pixel-array sampling clock:
using pclk 878400000 with line length 7500 preserves the frame-duration
contract. The vendor Android adapter instead exposes mipi_pixel_rate
700800000 and derives a different HBLANK; those two semantics must not be
mixed. No C-PHY LINK_FREQ is inferred from either number.
The matching device-modules commit is
`ee2be53cb75670b548948636a0db1d1ff112bf12`; this change does not import
older board power/pipeline descriptions or alter shared regulator/DT files.

Power helper source is existing patches 0049, 0050, 0106 and 0107, copied
mechanically by `generate.py`. Re-running the generator after helper changes
keeps the isolated streaming candidate consistent with the checked helpers.
Do not edit generated patch register arrays by hand.

## Integration For Main

1. Add `0112-media-i2c-imx882-v4l2-controls.patch` after 0107 in the kernel
   APKBUILD source list and checksums. Keep the board fixture disabled.
2. Add `CONFIG_VIDEO_IMX882_TETRIS=m` to the CI test config, and build
   `drivers/media/i2c/imx882-tetris-stream.ko` against the pinned kernel.
   Require patch/config/modpost checks; do not autoload it yet.
3. Run `sh patches/camera-imx882/run-core-tests.sh` in CI only. It compiles
   the same transaction header embedded in the kernel patch with ASan/UBSan.
4. Run the static check with the exact vendor modules and kernel tree:

```sh
python3 patches/camera-imx882/check.py \
  --vendor-repo ../android_kernel_modules_nothing_mt6878 \
  --kernel-tree ../linux-d84b264a54a37611f2f46bc19363cb9b41606205
```

No APKBUILD, global CI or shared status document is modified by this task.
Native tests and kernel compilation were deliberately not run locally.

## Precise Next Runtime Gate

Before replacing the disabled main camera fixture with the streaming
compatible, establish all of:

- Per-SKU IMX882 vs IMX882TXD module identity and owned per-device calibration.
- I2C adapter, active-low reset, four supply owners and 24 MHz clock/pinctrl
  without touching shared VCORE/VGPU/VMM through guessed GPIOs or voltages.
  Driver requires an explicit 24000000 clock-frequency claim and verifies
  the actual exclusive rate before applying power. Only the upstream C-PHY
  identity trio numbering [0, 1, 2] is accepted; sensor lane remapping has
  not been traced. This is a restriction, not proof of board routing.
- A bound MT6878 SENINF C-PHY receiver with three trios and an actual media
  link to this source pad, routing VC0/DT0x2b to DMA and handling or rejecting
  VC0/DT0x30 explicitly. No such bound capture receiver exists in the port.
- Receiver/RAW power domains, clocks, IOMMU, reserved memory, CCU/firmware
  ownership and a V4L2 capture queue with finite DMA buffers and shutdown.
- Accurate link clock/rate contract: vendor timing pclk is 878400000,
  line length 7500, frame length 3900; reported wire pixel rate is 700800000.
  Do not substitute timing pclk for a guessed C-PHY link frequency.

Then perform one bounded stream-on/capture/stream-off from cold boot while
preserving USB/SSH. A registered subdevice or successful register write alone
does not prove a received image, calibrated controls or lifecycle support.
