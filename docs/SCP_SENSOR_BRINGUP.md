# SCP and sensor architecture

Status: **Partial**. r167 plus the pinned U-Boot profile reaches SCP READY
and real data from five physical sensor classes. Opt-in service startup,
rotation, automatic brightness and proximity UI behavior were observed.
See [startup](SENSOR_INTEGRATION_PATCH.md),
[desktop integration](SENSOR_DESKTOP_INTEGRATION.md) and
[loader research](SCP_LOADER_TRACE.md).

## Hardware ownership

| Function | Firmware endpoint | Owner |
| --- | --- | --- |
| Accelerometer | icm4n607_acc | SCP |
| Gyroscope | icm4n607_gyro | SCP |
| Magnetometer | qmc6308 | SCP |
| Light | ltr569_als | SCP |
| Proximity | ltr569_ps | SCP |
| SAR | SAR-hx9031as | SCP; outside the five tested basic classes |

Nothing OS 4.1 device modules at
`ee2be53cb75670b548948636a0db1d1ff112bf12` and stock DTBO expose no
matching AP I2C/SPI children for these sensors. Do not add guessed direct
sensor drivers or a competing bus owner.

## Active chain

1. U-Boot authenticates the pinned slot-A firmware, reserves memory before
   initrd allocation, decrypts/prepares TCM and completes secure registration.
2. `mtk-mbox`, `mtk_rpmsg_mbox` and `mtk_tinysys_ipi` provide transport.
3. `scp` consumes validated handoff and shared infracfg regmap, registers its
   logger receive path before reset release, then completes READY.
4. `sensorhub` validates reply correlation and shared-memory inventory.
5. `hf_manager` publishes the packed HF ABI at `/dev/hf_manager`.
6. Native iio-sensor-proxy HF backend publishes standard desktop properties;
   Phosh/GNOME own screen behavior.

Modules are packaged under `extra/mediatek-sensors/`. They are not early
initramfs or unconditional modules-load inputs. The guarded startup service
is disabled by default. Mask bits 0..4 identify accelerometer, magnetometer,
gyroscope, light and proximity; ready Y, count 24 and mask 31 were observed.

## Diagnostics and remaining work

`scripts/check-live-sensor-samples.py` inventories or captures a bounded
stream without loading modules or writing calibration. Source ABI:
`drivers/misc/mediatek/sensor/2.0/core/hf_sensor_io.h` and `hf_manager.c`
at the pinned vendor commit. The vendor write callback returns zero on
success; do not resend it. On-change light/proximity are not periodic-rate
failures. Packed-layout, signed-sample and malformed-record tests are in CI.

The backend is not a kernel IIO driver and does not advertise an uncalibrated
compass. Gyro/magnetic accuracy was 0; calibration is not proven.
Remaining: clean packaged installation, repeated cold starts, safe warm
ownership, suspend, resource lifetime/idle power, stress and other variants.
Do not clear stale TCM, fake READY, reset/reload modules, or weaken firmware
checks to bypass these gates.
