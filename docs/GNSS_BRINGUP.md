# Nothing Tetris GNSS bring-up

## Current boundary

The currently verified kernel package `6.18-r155` uses the stock-derived Tetris
v051 data-link module from Nothing OS 4.1 commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. Patch `0020` publishes its DT
platform device. The firmware package installs the exact
MT6878/MT6631 GNSS payload as
`connsys_gnss_mt6878_mt6631.bin`.

Clean r155 validation on 2026-09-12 flashed the CI 34589225716 super and
userdata artifacts and repeated the supervised BINFO/download/stop sequence on
three separate boots. All three runs completed DOWNLOAD_COMPLETE,
STOP_WRITTEN and CLOSED, published OFF -> ON -> RST -> WORK -> RST -> OFF, left
no gpsdl owner and preserved the exact 32 MiB USB hash. This proves the manual
transport/download/shutdown repeat gate for the r155 package. It is still not
a position fix: no navigation command, NMEA output, GeoClue/gpsd bridge,
autostart, restart stress, coexistence or suspend/resume has passed.

The image manifest still declares U-Boot 60bcf22 as required. The live repeat
kept the installed c931695 bootloader to preserve the known-good baseline, so
bootchain portability remains an explicit open gate. The first clean r155 boot
also logged `emi_mng_get_gps_emi failed to find gps node`; the later supervised
cycle passed, but the DT/EMI warning still needs source-level cleanup.

Pre-experiment read-only runtime check: boot ID
`3c9afcd9-04a0-4bed-8333-1f7c5ab4a7f5`, runtime `6.18.0 #154`, device
package `8-r9`. Package versions were read directly from the installed APK
database. The GNSS transport service was inactive and `/proc/modules`
contained neither `gps_drv_dl_v051` nor modem drivers. Connectivity, WLAN
and Bluetooth drivers were present. This is a baseline, not a new GPS test.

SSH initially timed out while the host route selected Wi-Fi. USB inspection
still identified the postmarketOS phone; its `en4` interface subsequently
had `172.16.42.2/24`, and SSH to `172.16.42.1` succeeded without changing
network configuration or rebooting. Do not record that timeout as a kernel
crash. Repository DNS lookups failed during package inspection; future
baseline checks should use the installed database without network access.

The B4.1 userspace analysis now identifies the normal MT6878 startup path:
all three chipset capability records select driver-assisted MVCD. The
kernel supplies boot metadata through secure operation `0x1f` and submits
only a DSP selector and fragment number through operation `0x20`; the
latter carries no userspace firmware buffer. Consequently the packaged
firmware's existence does not prove secure firmware loading. Conversely,
the historical successful v051 ioctl-23 test below already proves this
metadata boundary on that earlier boot and must not be discarded as
untested. Repeat on the current build from a controlled clean baseline
before advancing to the newly decoded FE08/BINFO and FE31/FE32 ACK exchange.
No new secure calls, link opens or fragment submissions were performed in
that baseline check.

A subsequent single transport-only service start on this same boot
succeeded at kernel time 1655.72. Both devices appeared, both links stayed
CLOSED, and a root ownership check found no users. USB stayed UP; a 32 MiB
zero-stream transfer retained SHA256 `83ee4724...`. Wi-Fi scanning also
succeeded, but routed Wi-Fi and Bluetooth functionality were not tested.
At this stage the module remained loaded; it was not unloaded or reloaded. Source triage
confirmed that mapped TIA2 takes precedence over the absent TIA1 resource.
The empty default pinctrl node explains its warning, while a live debugfs
read confirmed all six required L1/L5 control states. Raw evidence is in
`local/gnss-r153-live/TEST.md` and `transport-dmesg.txt`. This is transport
registration evidence only.

The subsequent single bounded readonly-helper invocation on r153 returned
status 0 and fragment count 106 (code_size field 42505, units unresolved).
The log identifies A-die 6631 and shows link0 OPENING -> OPENED -> CLOSING
-> CLOSED, with DSP reset readiness followed by OFF on close. No owner
remained; USB and the repeated 32 MiB hash check passed. The key was
redacted, and no fragments or device data reads/writes were submitted.
See `boot-info.txt` and `boot-info-dmesg.txt` in the same local evidence
directory. This confirms current-build metadata access, not a firmware
download, satellite fix, cold-repeat or full coexistence result.

### BINFO result and recovery (2026-09-11)

One bounded BINFO-only probe subsequently wrote a single FE08/BINFO frame
and received a checksum-valid FE31 index-zero acknowledgement. Probe SHA256:
`dac1ef53afb64abd7f5d0c312f1229ee981494027a778449f5d25f0598fad76b`.
The metadata-only close result above does not describe this later test:
after the write, shutdown exhausted 200 off-done polls, reported
need_dump_for_reset_done=1 and forced A-die off. Userspace exit 0 did not
prove clean teardown. No fragment submissions or navigation commands ran.
Evidence: `local/gnss-r153-live/binfo-only-kernel.log` and the test plan in
that directory. The phone was cleanly rebooted, not subjected to a module
unload/reload retry.

Last verified post-recovery boot:
`3334a5ab-4658-4310-b07e-77b6fcaf0fa1`, unchanged r153 / kernel #154,
GNSS service inactive and no gpsdl nodes; USB/SSH available. Revalidate this
baseline before the next experiment. A staged full-fragment native probe
passes 29 mocked-I/O scenarios, including 1/106/256-fragment ACK chains and
fail-closed framing/index/error cases. It has not been installed or run.
The kernel's off-done check precedes USRT/hardware power-off; the vendor
userspace cleanup traced so far does not establish a DSP stop contract.
Do not run the staged probe merely because its fragment exchange compiles:
RAM-code readiness and safe shutdown must first be resolved. GPS remains
Partial at the transport/protocol boundary, with no satellite fix.

## Historical Evidence

The following dated tests describe earlier installed images. They are not
claims that the current boot has passed those gates.

The module exposes two vendor character devices, `/dev/gpsdl0` and
`/dev/gpsdl1`. Their read/write/ioctl ABI is consumed by MediaTek MNL userspace;
it is not a standard NMEA stream and cannot be passed directly to `gpsd`.
Opening a device starts the associated GNSS link, so transport staging and
position testing must remain separate experiments.

The installed pmaports image includes the exact Tetris LNA pinctrl states.
Fastboot proved the executable loader was initially old `8aa048f`, despite
earlier documentation claiming `b76e47e` in the wrong `boot_a/b` partitions.
After the hash-verified LK image was installed in the actual `lk_a/b`
partitions, fastboot reported `gb76e47e77430` and live DT exposed the exact
eight-byte `emi-addr = 0x86a00000` plus `emi-size = 0x100000`. v051 consumes
that handoff and initializes its reserved DMA buffers. No position fix is
claimed.

`nothing-tetris-gnss-transport.service` remains intentionally static and
manual. It requires the proven connectivity service, checks the packaged
firmware, loads `gps_drv_dl_v051`, and verifies both character
devices. It never opens either device, never loads modem modules, and does not
unload the shared connectivity stack on stop.

## Live transport test

Capture the boot ID, USB/Wi-Fi state and kernel log before starting. Then run:

```sh
sudo systemctl start nothing-tetris-gnss-transport.service
systemctl status nothing-tetris-gnss-transport.service --no-pager
test -d /sys/module/gps_drv_dl_v051
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
v051/v061 instead. The generic public Kleaf build compiles every GNSS variant,
so it was insufficient by itself to identify the product profile; the
stock-derived product configuration below resolves that ambiguity. Mixing
backend objects between profiles remains unjustified. Evidence is in
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

On 2026-09-04, the first clean #130 probe under old executable U-Boot `8aa048f`
created both devices but logged a zero GPS EMI handoff, so neither link was
opened. After installing `b76e47e` in `lk_a/b`, boot
`845c9536-699f-4b87-8c27-23a3605314a1` repeated transport with the exact
reserved-memory values and no fallback errors. A separate clean boot
`9c99400e-9678-4e58-92b7-7948a5998cc8` opened only link0, issued read-only
ioctl 23 with its exact 20-byte result structure, and returned successfully.
The fd close drove `OPENED -> CLOSING -> CLOSED`; no process owner or modem
module remained. Wi-Fi stayed associated at `192.168.22.64`, Bluetooth stayed
powered/non-discovering, and the exact 32 MiB USB transfer retained SHA-256
`83ee4724...` after both gates.

The v051 compile/package candidate is now installed. Run `33532308762` reached
the v051 ATF objects and proved that mainline's SiP header lacks
`MTK_SIP_KERNEL_GPS_CONTROL`; the exact B4.1 header defines it as
`MTK_SIP_SMC_CMD(0x537)`. The compatibility patch carries that identifier
behind `#ifndef`, which is compile evidence rather than proof that installed
trusted firmware implements every operation. The installed handoff and
boot-info call now prove this boundary on the phone. A maintainable MediaTek
MNL bridge or Linux GNSS subsystem driver
can implement MVCD and expose standard position data. Do not interpret raw
reads from `gpsdl0` as NMEA, load v051 over the current v050 session, or graft
its ATF objects into v050. Promotion requires a timed and accurate fix, three
cold starts, restart, coexistence and suspend/resume tests.

The `pkgrel=150` compile candidate adds ABI-only patch `1003` for commands 13,
23 and 28. Device package `8-r8` adds the unconfigured
`/usr/libexec/nothing-tetris-gnss-readonly` diagnostic. It is not a bridge or
daemon: explicit `--probe-link0` is required, it has an eight-second deadline,
performs no device read/write, and redacts the returned cipher-key field. See
`GNSS_USERSPACE_BRIDGE_AUDIT.md` for source evidence, the live gate and the
remaining protocol blockers.
