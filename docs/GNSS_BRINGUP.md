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

## Next gate

The next implementation must provide a maintainable userspace bridge for the
MediaTek MNL protocol or replace the vendor ABI with a Linux GNSS subsystem
driver. Its first live test must open only `gpsdl0`, preserve the first firmware
or protocol error, close the link cleanly, and verify USB, Wi-Fi and Bluetooth
before any position claim. Promotion requires time-to-fix and accuracy evidence,
three cold starts, restart, coexistence and suspend/resume testing.
