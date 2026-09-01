# Nothing Tetris GNSS bring-up

## Current boundary

The kernel package builds and installs the Nothing OS 4.1 MT6878 v050 data-link
module from commit `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. Patch `0020`
publishes its DT platform device. The firmware package installs the exact
MT6878/MT6631 GNSS payload as
`connsys_gnss_mt6878_mt6631.bin`.

The module exposes two vendor character devices, `/dev/gpsdl0` and
`/dev/gpsdl1`. Their read/write/ioctl ABI is consumed by MediaTek MNL userspace;
it is not a standard NMEA stream and cannot be passed directly to `gpsd`.
Opening a device starts the associated GNSS link, so transport staging and
position testing must remain separate experiments.

The installed pmaports image includes the exact Tetris LNA pinctrl states and
installed U-Boot `b76e47e` writes the 64-bit GPS EMI address only after the
existing reserved-memory layout and secure EMI mappings validate. Their joint
transport and link-power behavior is now tested on the phone. No position fix
is claimed.

`nothing-tetris-gnss-transport.service` is intentionally static and manual. It
requires the proven connectivity service, checks the packaged firmware, loads
`gps_drv_dl_v050`, and verifies both character devices. It never opens either
device, never loads modem modules, and does not unload the shared connectivity
stack on stop.

## Live transport test

Capture the boot ID, USB/Wi-Fi state and kernel log before starting. Then run:

```sh
sudo systemctl start nothing-tetris-gnss-transport.service
systemctl status nothing-tetris-gnss-transport.service --no-pager
test -d /sys/module/gps_drv_dl_v050
test -c /dev/gpsdl0
test -c /dev/gpsdl1
```

Do not read from or write to the device nodes during this transport-only gate.
Confirm that no consumer opened them and that modem modules remain absent:

```sh
sudo find /proc/[0-9]*/fd -lname '/dev/gpsdl*' -print
lsmod | grep -E 'ccci|dpmaif|ccmni|modem'
```

An empty result is required for both commands. Finish with a Wi-Fi scan and the
32 MiB USB regression gate:

```sh
nmcli dev wifi list --rescan yes
scripts/check-live-regression-gate.sh 172.16.42.1 user '<password>' transfer
```

On 2026-08-31 this gate passed on kernel build `#120`, boot ID
`88d7d7b4-3449-43c8-8a98-7d31913f32b4`. Both devnodes appeared, no consumer or
modem module appeared, Wi-Fi scan remained functional, and the USB transfer
passed. This proves transport staging only, not satellite acquisition or a
position fix.

On 2026-09-01 the clean `fdeeda0` image, kernel `#128`, boot ID
`20e9eb59-7d0f-400e-84cf-2b6e0757af9e` and U-Boot `b76e47e` repeated the
transport gate. Firmware SHA-256 was `7ad6007c...`, both nodes appeared, no
consumer or modem module appeared, and the exact 32 MiB USB transfer retained
SHA-256 `83ee4724...` while routed Wi-Fi and powered Bluetooth remained active.

One separate bounded experiment then opened only `/dev/gpsdl0` for three
seconds and closed it normally. The operation returned success, left no owner,
and preserved USB, Wi-Fi/HTTPS and Bluetooth. This demonstrates the link0
power lifecycle and bootloader handoff boundary, not GNSS protocol operation or
a satellite fix. Raw evidence is under
`local/live-logs/20260901T161500Z-fdeeda0-clean1/`.

A second read-only experiment opened link0 and issued ioctl 23 for DSP boot
information with an eight-second process deadline. It returned `EFAULT` and
closed normally; USB, routed Wi-Fi, Bluetooth and HTTPS all survived. Source
tracing explains the result: the exact v050 Kbuild links
`hw/gps_dl_hw_gps.o`, whose boot-info implementation reports that ATF is not
supported and returns failure. The available ATF MVCD backend is linked by
v051/v061 instead, but the public Kleaf build compiles every GNSS variant and
does not identify which one the Tetris product loads. Switching profiles or
mixing backend objects is therefore not justified yet. Evidence is in
`gnss-mvcd-boot-info.txt` in the same directory.

Two stock-derived Tetris integration trees independently select v051: the
device property has specified `ro.vendor.gps.chrdev=gps_drv_dl_v051` since its
initial import, and its prebuilt `vendor_dlkm` contains and loads only
`gps_drv_dl_v051.ko`. The exact B4.1 `vendor_boot` archive does not carry late
`vendor_dlkm` modules, so this is strong corroborating evidence rather than a
byte-for-byte B4.1 load-list extraction. It is sufficient to prepare and
compile-check an isolated v051 candidate, but not to live-load v051 over the
currently active shared radio stack.

## Next gate

The next gate is an isolated v051 compile/package candidate, followed by a clean
boot that loads only that profile and repeats transport plus read-only boot-info
tests. Then a maintainable MediaTek MNL bridge or Linux GNSS subsystem driver
can implement MVCD and expose standard position data. Do not interpret raw
reads from `gpsdl0` as NMEA, load v051 over the current v050 session, or graft
its ATF objects into v050. Promotion requires a timed and accurate fix, three
cold starts, restart, coexistence and suspend/resume tests.
