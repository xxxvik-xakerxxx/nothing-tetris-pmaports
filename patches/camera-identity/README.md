# IMX882 logical reset prerequisite

Status: Untested on hardware. Reset is packaged as `0050`; r169 adds shutdown
as `0106` and exclusive clock control as `0107`. Camera probing remains disabled.

## Exclusive clock control

`0107` uses `clk_set_rate_exclusive()` and verifies `clk_get_rate()` is exactly
24 MHz before enabling any supply. The reference is released after shutdown,
including power-on, rounded-rate and teardown errors. CI exercises 416 cases
and rejects mutants that omit the release or ignore rounding. These new tests
and the full patched driver's kernel ABI build are pending. Software rate
readback is not a physical frequency measurement or proof of board ownership.

## Shutdown candidate, 2026-10-07

`0002-imx882-identity-check-shutdown.patch` follows the logical reset fix.
It adds the vendor's missing 1 ms DOVDD settling delay before MCLK selection,
checks pinctrl and regulator shutdown results, attempts all owned rails in
reverse order even after an error, and returns the first teardown error.
The probe logs cleanup failure, rejects an otherwise successful identity
probe on failed cleanup, and preserves an earlier power/read error.

The CI runner now additionally exercises 384 combinations: success/eleven
power-on failures crossed with all 32 pinctrl/rail shutdown failure masks.
It checks that failed disables are not reported as successful, no later
cleanup is skipped, reset remains asserted, and DOVDD settles before MCLK.
Mutants removing the delay or swallowing the shutdown result must fail.
Native tests run only in CI. `check-reset.py --check-only` validates both
patch applications without local compilation and has passed. The shutdown
native tests passed CI run 37655704824. Full-driver kernel ABI validation of
the newly packaged shutdown/clock combination remains pending.

No camera node, rail, driver or service is enabled. Shared-rail ownership,
physical clock and shutdown behavior still require proof before a live probe.
The runner checks the packaged reset result matches the historical candidate
and the packaged shutdown patch is identical to its tested candidate, then
applies the packaged clock patch. Base 0049 and fixture 0055 remain hash-pinned.

## Missing prerequisite and source evidence

The identity driver must hold physical GPIO25 low while rails settle and
after shutdown, then release it high before reading the sensor. The fixture
already uses GPIO_ACTIVE_LOW, so gpiod logical 1 means physical low. The
baseline incorrectly acquires GPIOD_OUT_LOW, asserts logical 0 during power-up
and shutdown, and writes logical 1 just before reading. This reverses all
three physical states. The candidate corrects only these reset operations.

Nothing B4.1 device modules commit
ee2be53cb75670b548948636a0db1d1ff112bf12, read with git show:

- arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi: cam0 reset states
  explicitly drive GPIO25 output-low/output-high; main MCLK is GPIO93/CAMTG2.
- drivers/clk/mediatek/clk-mt6878.c: CAMTG2 parent index 1 is
  top_uvpll192m_d8 (univpll / 104). This is source evidence, not a measured
  24 MHz clock and not a reason to add another CAMSYS_MAIN provider.

Nothing B4.1 camera modules commit
e96f60dc081ae3525ef43d4bcf0ee5ee97e53835, also read with git show:

- mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c
  and common/imx882txd_mipi_raw/imx882txdmipiraw_Sensor.c: pw_seq sets RST 0
  before rails, RST 1 after MCLK drive/settling.
- mtkcam/imgsensor/src-v4l2/adaptor-hw.c: HW_ID_RST maps STATE_RST_LOW plus
  the supplied value to pinctrl; these vendor values are physical states,
  not Linux descriptor assertion values.

## Reproduce on host

Run from this worktree:

```sh
python3 patches/camera-identity/check-reset.py
```

The runner extracts the baseline driver into a temporary directory, checks
and applies the candidate, then compiles the actual power functions with
cc -std=c11 -Wall -Wextra -Werror against instrumented host mocks. It checks
the acquire flag against the active-low fixture, success, and failures at
each of the 11 fallible power-on operations (rate, four voltage requests,
four rail enables, pinctrl, clock enable). Every case checks physical reset,
clock balance and reverse-order removal of only successfully enabled rails.
The unmodified baseline must fail the same executable regression test.

This is not a kernel ABI build, GPIO electrical measurement, I2C test or
proof that power-off operations cannot fail. No complete kernel build is
needed for the original reset-only step. r169 integrates both subsequent fixes
into APKBUILD and its checksums. DT, I2C8 and kernel config remain untouched.

## Remaining blockers and next live gate

Before authorizing identity: verify complete shared DOVDD/AFVDD consumer
ownership and actual 24 MHz; validate the new clock ownership behavior on
hardware. Compile the complete driver
against the pinned kernel and review the final DT. This reset candidate
alone does not make the baseline identity probe ready for a phone.

The next minimal live gate is still observation-only on an approved clean
artifact: record hashes/slot/board/SKU, establish one USB NCM/SSH control
session and Wi-Fi baseline, map adapters from DT resources, confirm no camera
client or enabled camera supply and no new faults. Repeat on three cold
boots. No bus scans, raw reads, module loading or camera power transitions.

## Future bounded identity sequence

Only after the above prerequisites and separate rail/clock ownership and
shutdown live evidence, authorize one reviewed driver probe on main I2C8,
7-bit address 0x1a. Do not change the shared adapter or its rate.

1. Record artifact identity and pre-test USB/SSH/Wi-Fi, clocks, regulators
   and first kernel errors. Keep front/auxiliary, EEPROM, VCM, flash, SENINF,
   CAMSYS and CCU consumers inactive. Start from a clean boot, no retries.
2. Acquire reset asserted: logical 1, physical GPIO25 low. Configure and
   verify xclk at 24000000 Hz while output remains off.
3. Enable AFVDD 2.8 V; wait at least 1 ms. Enable AVDD 2.8 V, then DVDD
   1.2 V; wait at least 1 ms. Enable shared DOVDD 1.8 V through its owner;
   wait at least 1 ms. These are vendor source timings, pending live proof.
4. Select GPIO93 CMMCLK1 at 4 mA, enable CAMTG2, wait at least 5 ms.
   Release reset: logical 0, physical high; wait at least 1 ms.
5. Issue exactly two combined I2C transactions to 0x1a: write the two-byte
   register pointer 00 16 then repeated-start read one byte; repeat with
   00 17. Each i2c_transfer must return 2, else stop. No sensor register
   payload writes, initialization, streaming or EEPROM access. Expected
   physical ID is 0x8202 for either supplier; do not infer 0x8203/module ID.
6. On success or first failure: assert reset (logical 1/physical low),
   disable/unprepare xclk, select mclk-off, disable only rails acquired by
   this probe in order DOVDD, DVDD, AVDD, AFVDD. Check every teardown result.
7. Compare clock/regulator references and USB/SSH/Wi-Fi with baseline;
   retain bounded ID/error evidence only. Any fault, imbalance or transport
   regression ends the experiment; clean reboot to the prior artifact,
   no reload/rebind loop. An ID read proves silicon identity only.

Read-only here means no sensor configuration writes. Sensor power, reset
and the register-address phase still cause hardware transactions; this is
not the observation-only gate and has not been executed.
