# GNSS v051 userspace bridge audit

## Scope and source identity

This audit used local sources only. The authoritative connectivity source is
Nothing OS 4.1 Tetris commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` from the local
`upstream/android_kernel_modules_nothing_mt6878` object store. The pmaports
baseline is `1f8aef10668c62284ac4824eb334a67a14f6c1df` on the isolated
`codex/gnss-userspace-bridge` branch.

The source exposes a private character-device ABI, not NMEA or the Linux GNSS
subsystem. Opening `/dev/gpsdl0` powers link0. Closing the final descriptor
drives its normal close sequence. The exact v051 source proves these bounded
userspace operations:

| Operation | Command/layout | Boundary |
| --- | --- | --- |
| Query status | integer ioctl `13`, argument `0` | Returns link state without requesting the reason `2`/`4` debug events. |
| Get DSP boot information | integer ioctl `23`, five 32-bit fields, 20 bytes | Calls the v051 ATF boot-info backend already exercised on the phone. |
| Get boot time | integer ioctl `28`, two signed 64-bit fields, 16 bytes | Copies boot-time and architectural-counter values to userspace. |

The kernel patch moves only those constants and layouts into a versioned UAPI
header. Kernel static assertions and a host C11 test lock every exported value,
size and offset. Assert/reset, suspend/resume, link1/CW-DSP, firmware control,
MVCD fragment submission and raw payload formats remain private.

## Manual diagnostic

`nothing-tetris-gnss-readonly` is a manual diagnostic, not a daemon or a
position provider. It accepts only `--probe-link0`, opens only
`/dev/gpsdl0` with `O_RDONLY | O_CLOEXEC | O_NOFOLLOW`, installs an eight-second
process deadline, executes the three allowlisted ioctls, validates the observed
fragment-count and clock bounds, redacts `cipher_key`, and closes the descriptor.
It contains no `read(2)` or `write(2)` call and has no service, preset, udev rule
or module-load entry.

Opening the node still changes GNSS power state. Therefore the diagnostic stays
manual until the complete lifecycle gate passes. On a clean boot with the
correct LK and current image:

```sh
sudo systemctl start nothing-tetris-gnss-transport.service
scripts/check-live-regression-gate.sh 172.16.42.1 user '<password>' baseline
sudo /usr/libexec/nothing-tetris-gnss-readonly --probe-link0
sudo find /proc/[0-9]*/fd -lname '/dev/gpsdl*' -print
nmcli dev wifi list --rescan yes
scripts/check-live-regression-gate.sh 172.16.42.1 user '<password>' transfer
```

The first live run must use one SSH control session and capture the boot ID,
kernel/package identities, pre/post `dmesg`, `/sys/module/gps_drv_dl_v051`, both
device nodes, Wi-Fi association/routing, Bluetooth power, and the exact USB
transfer hash. Stop after a timeout, firmware assert, remote-processor reset,
owner left on either node, Wi-Fi/BT regression, or USB/SSH loss. Recover by a
clean reboot; do not unload conninfra or retry in the same boot.

## Validation

`scripts/check-gnss-v051-readonly.sh` performs the local authoritative gate. It
archives the exact B4.1 GNSS tree, applies compatibility patch `1002` followed
by UAPI patch `1003`, compiles and runs the ABI test, compares the kernel and
device-package UAPI byte for byte, and host-compiles the manual diagnostic.
The gate also links the diagnostic into a mocked syscall harness with no route
to the real device node. Nineteen scenarios cover the valid path, zero
fragments, argument rejection, missing/non-character/symlink nodes,
open/ioctl/close failures, excessive fragment counts and invalid boot clocks.
After an alarm is armed, every exit path cancels it; on the successful path
the descriptor is closed before any diagnostic output is printed. The harness
also fails if the raw cipher-key value reaches stdout or stderr.

The repository validator additionally rejects extra UAPI commands, link1,
device reads/writes, write-capable opens, missing deadlines, service/preset
activation, and omission of the packaged diagnostic. The full kernel package
build remains the module compile/modpost gate, and image CI checks that the
manual executable and v051 module are present.

## Blockers to a position bridge

No local source defines the MediaTek MNL framing, MVCD payload-container
algorithm, DSP RAM-code download sequence, navigation output protocol, or a
mapping to standard GNSS/NMEA. Local stock-derived inventories name `mnld`,
GNSS HAL/services, `mtk_agpsd`, `libmnl.so`, init/VINTF files and SUPL profiles,
but the corresponding B4.1 binaries, ELF dependency closure, notices and
configuration are not present.

Consequently this change does not send fragments, read raw payloads, start
`gpsd`, expose GeoClue, autostart GNSS, or claim satellite acquisition or a
fix. The next safe input is either a complete, provenance-recorded local B4.1
vendor filesystem inventory or a bounded known-good Android trace that proves
the MVCD and navigation framing. Only then can a bridge implementation advance
beyond this read-only control-plane boundary.
