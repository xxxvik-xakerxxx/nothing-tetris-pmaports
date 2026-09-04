# Nothing Tetris current port status

Updated: 2026-09-01.

## Exact software state

| Role | Revision | Device state |
| --- | --- | --- |
| Installed pmaports image | `fdeeda042144e5ff1d2159f1590dbc5fb6b9392c` | Kernel `6.18.0 #128`; CI run `33502390335`; clean install and warm reboot completed. |
| Previous rollback image | `f607513` | Kernel `6.18.0 #123`; preserved stable artifacts and prior clean/warm regression evidence. |
| Stable pmaports source | `main` at `ee994e4236d69c9f3eb18e81614dd0dff9e60266` | Rollback source of truth. |
| Previous pmaports CI candidate | `codex/next-hardware` at `0600a13ceba889d294f6bc1be289e273a75eca00` | `pkgrel=126`; CI run `33495661863` applied the patch series and completed the main kernel build, then failed before the IMX882 object check because a disabled Kconfig symbol was absent rather than serialized as `# ... is not set`. No image was produced or installed. |
| Active pmaports source | `codex/next-hardware` | Installed image code is exact commit `fdeeda0`. Audio candidate `384f155` built kernel and device packages in CI `33522638794`; image creation then hit a stale mono-remap assertion, now fixed. GNSS v051 candidate `adf8606` passed overlay validation in CI `33532308762` and exposed the missing B4.1 GPS SiP service ID. Candidate `fb93b54` carries guarded `MTK_SIP_SMC_CMD(0x537)` and CI `33540592686` then advanced to a Linux 6.18 `of_device_id` header blocker in `gps_dl_linux_clock_mng.c`; no image was produced and no runtime support is claimed. |
| Installed U-Boot | `b76e47e774304ab550a6354f3286860b7caffb3a` | Flashed to `boot_a` and `boot_b`; clean boot, warm boot and Linux-to-fastboot reboot pass. |
| Previous U-Boot rollback | `8aa048f93bb7569e4107ef85aa994c630f85de48` | Preserved rollback artifact. |

The downloaded `nothing-tetris-images` ZIP is SHA-256
`c47230ff07ebefe86faf54cf216bf7901279afbef482647389c91cd4a56bc996`.
Its manifest matches `fdeeda0` and requires U-Boot `b76e47e` with SHA-256
`869303227941e0f050d083c74eeffcfb9bf90bf80a59978780b915d22722b9c4`.
Streaming verification passed for `boot_image.itb` (`d4c97120...`), the 512 MiB
boot image (`edfb650a...`) and the root sparse image (`0fdcff2f...`). The CI
filenames are generic, but the package's `fastboot-bootpart` contract and the
validated installation path map `nothing-tetris-boot.img` to `super` and
`nothing-tetris-root.sparse.img` to `userdata`. `boot_image.itb` is retained as
the independently verifiable FIT payload; it is not a third fastboot partition.

The live partition inventory confirms separate per-device stores without
reading their contents: `nvcfg` 32 MiB, `nvdata` 80 MiB, `nvram` 64 MiB,
`persist` 48 MiB, `proinfo` 3 MiB and `protect1`/`protect2` 8 MiB each. A/B
firmware partitions also exist for modem, GNSS, Wi-Fi, Bluetooth, SCP, CCU and
GPUEB, plus `md_sec`. Wi-Fi/BT already use bounded records from `nvdata`; other
subsystems must validate their own calibration records rather than copying a
whole partition or one handset's data into the image.

`Works` means the end-user function was physically demonstrated. `Partial`
means useful behavior works but lifecycle, integration or portability gates are
still open. A compile-only patch does not improve the end-user status.

## Hardware matrix

| Subsystem | Current status | Confirmed evidence | Candidate / next gate |
| --- | --- | --- | --- |
| Boot and root filesystem | Works | Clean flash boots pmOS; root is writable and expanded. | Recheck after every candidate installation. |
| USB debug / NCM SSH | Partial | Automatic `usb0`, SSH and exact 32 MiB transfers passed after clean install and warm reboot on #128. | Physical reconnect, repeated reboot and suspend/resume. |
| Wi-Fi | Partial | Clean #128 associates to `DistributedLabDev` at `192.168.2.98`; DHCP, default routing, DNS and HTTPS pass while USB and Bluetooth remain active. | Cold reconnect, suspend/resume, sustained transfer and second-unit checks. |
| Bluetooth | Partial | Clean #128 registers powered BlueZ `hci0`; an eight-second scan found more than 40 nearby devices while USB, Wi-Fi and HTTPS survived. The client exited but `Discovering` remained stuck until `bluetooth.service` alone was restarted; no radio module was unloaded. | Fix/repeat discovery teardown, then pair/reconnect and test audio/data profiles across suspend. |
| Touch and keys | Works | Touch plus balanced power/volume press and release events passed. | Regression check after native display work. |
| Haptics | Partial | The user physically confirmed the bounded RT6010 effect on clean #128; USB remained healthy. | Cold-boot repetition and suspend/resume. |
| Audio | Partial | Bounded speaker playback is physically confirmed and both sinks return to `SUSPENDED`. A five-second stereo capture contains two distinct active microphone channels with less than 0.002% clipping. Logs prove pre-login SSH user managers autostart PulseAudio without seat ACLs, producing ALSA, BlueZ and feedbackd ownership failures. | Build/install device r4, then require one PulseAudio/feedbackd owner across pre-login SSH, login, relogin and suspend; test system events and calls afterward. |
| Thermal | Partial | All 24 MT6878 zones return plausible polling-mode values without USB loss. | IRQ/trip routing and sustained load remain disabled/unverified. |
| Charging | Partial | Clean #128 reports AICR/ICHG 500000 uA and +195312 uA net battery current at 87%. TCPM still reports Type-C default mode and `CURRENT_MAX=0`, so the conservative fallback is correct. Native BC1.2 SDP/CDP/DCP classification is absent. | Observe a USB 2.0 host, known Rp 1.5 A source and known 5 V BC1.2 DCP. Validate USB2 PHY DP/DM ownership before implementing only the MT6375 BC1.2 boundary. Keep PD/PPS and OTG disabled. |
| Idle battery drain | Broken | Roughly half the battery was reported lost during an uncontrolled overnight period. Existing captures retained `usb0`, kept MTU3 runtime-active with `power/control=on`, and sometimes charged, so they cannot identify an unplugged cause. Wi-Fi runtime PM is unsupported and its wake/IRQ counters make it the first A/B candidate, not a proven fault. | Run local, physically unplugged, screen-off intervals on separate clean boots with Wi-Fi associated and disabled. Record start/end coulomb counter, monotonic time, suspend result and wake/IRQ deltas; reconnect USB only after each interval. |
| GNSS | Partial | On installed #128 with U-Boot `b76e47e`, v050 creates both `gpsdl` nodes and completes a bounded link0 open/close without connectivity regressions. Ioctl 23 returns `EFAULT` because v050 links a non-ATF stub. Stock-derived Tetris property and `vendor_dlkm` trees both select and load v051; source now packages only v051 as a manual candidate. | Pass patch/package CI, then clean-boot v051 transport/boot-info tests before MVCD/MNL, position and lifecycle work. |
| Modem / SIM | Broken | No ModemManager modem, CCCI/DPMAIF/WWAN device or SIM state. U-Boot validates the LK CCCI payload; kernel CCCI core remains compile-only. An isolated patch converts `from_timer()` to `timer_container_of()` and non-sync `del_timer()` to `timer_delete()`; both timer errors are gone and `ccci_hif_ccif.o` now fails first at unowned `MTK_SIP_KERNEL_CCCI_CONTROL`. | Prove the exact installed trusted-firmware CCCI secure ABI and return semantics, then compile/link CCIF without producing or shipping a module. DPMAIF, DT and runtime remain later gates. |
| Sensors | Broken | SCP/mailbox/IPI/HF/sensorhub sources compile and fail closed; no accelerometer, gyro, proximity or light sensor is exposed. A host-only parser against U-Boot `b76e47e` now validates unique 64-bit shared/loader carveouts, DRAM containment, size and non-overlap without changing the FDT. It does not validate SCP firmware or TCM. | Establish authoritative active `scp1`/`scp2` authentication/selection and TCM region-info ABI. Only then integrate an observation-only U-Boot path; publication, disabled DVFS nodes and live probes remain separate later gates. |
| GPU | Broken | Panthor is configured, but no Mali platform device or render node exists. | `c8f02ca` inventories VSRAM/VGPU provider support without enabling it. MFG0 power domain, DT consumer, CSF firmware and protected memory are still required. |
| Rear/front cameras | Broken | No camera media pipeline or preview/capture. Torch channels work independently. | Corrected PD9302A init and an IMX882 raw-ID object remain compile-only in active `pkgrel=127`; no camera DT client or module is shipped/autoloaded. Sensor live identity, SENINF/ISP and the media graph remain. |
| Display | Partial | Bootloader framebuffer through simpledrm gives a usable fixed image. `pkgrel=127` prepares a compile-only S6E8FC3X02 object gate; shipped config remains off and no module/DT client is packaged. It has never run on the phone. | Pass full CI, then implement MT6878 DDP/mutex/CMDQ/DSC/DSI/PHY and test a separate opt-in DTB while retaining framebuffer rollback. |
| microSD | Untested | Controller probes, but no physical card I/O test was recorded. | Insert/remove, read/write and remount test. |

## Current installation test

The installed image is a regression candidate, not a claim that all new
hardware works. Current gate state:

1. Boot/root expansion: passed on clean and warm boots.
2. Automatic USB NCM/SSH and exact 32 MiB transfer: passed after clean boot, warm reboot and the GNSS transport gate.
3. Bluetooth registration plus Wi-Fi association, DHCP, DNS and HTTPS: passed concurrently with USB.
4. Physical bounded speaker playback/haptics plus measured stereo microphone capture: passed; system-event ownership remains partial.
5. Warm reboot with automatic USB return: passed once.
6. Manual GNSS transport and bounded link0 open/close: passed without USB/Wi-Fi/BT regression; no position fix yet.

Modem, GPU, sensorhub, camera pipeline and native display stay disabled in this
boot. The next GNSS gate is a clean boot of the isolated v051 package and
read-only boot-info validation, then userspace protocol integration and a real
fix.
