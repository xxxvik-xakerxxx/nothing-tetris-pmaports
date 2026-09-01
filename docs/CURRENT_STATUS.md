# Nothing Tetris current port status

Updated: 2026-09-01.

## Exact software state

| Role | Revision | Device state |
| --- | --- | --- |
| Installed pmaports image | `f607513` | Kernel `6.18.0 #123`; clean-install and warm-reboot baseline. |
| Stable pmaports source | `main` at `ee994e4236d69c9f3eb18e81614dd0dff9e60266` | Rollback source of truth. |
| Previous pmaports CI candidate | `codex/next-hardware` at `0600a13ceba889d294f6bc1be289e273a75eca00` | `pkgrel=126`; CI run `33495661863` applied the patch series and completed the main kernel build, then failed before the IMX882 object check because a disabled Kconfig symbol was absent rather than serialized as `# ... is not set`. No image was produced or installed. |
| Active pmaports CI candidate | `codex/next-hardware` at `fdeeda042144e5ff1d2159f1590dbc5fb6b9392c` | `pkgrel=127` fixes the Kconfig guard to reject only built-in/module enablement, removes ignored stale DTS text from the camera patch, and adds a compile-only S6E8FC3X02 object gate. CI run `33502390335` passed overlay, full kernel/device packages, install-image construction and artifact upload. No image has been installed or hardware-tested yet. |
| Installed U-Boot | `8aa048f93bb7569e4107ef85aa994c630f85de48` | Current bootloader baseline. |
| U-Boot candidate | `b76e47e774304ab550a6354f3286860b7caffb3a` | CI passed; not flashed yet. |

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

`Works` means the end-user function was physically demonstrated. `Partial`
means useful behavior works but lifecycle, integration or portability gates are
still open. A compile-only patch does not improve the end-user status.

## Hardware matrix

| Subsystem | Current status | Confirmed evidence | Candidate / next gate |
| --- | --- | --- | --- |
| Boot and root filesystem | Works | Clean flash boots pmOS; root is writable and expanded. | Recheck after every candidate installation. |
| USB debug / NCM SSH | Partial | Automatic `usb0`, SSH and exact 32 MiB transfers passed on clean and warm boots. | Require reconnect, repeated reboot and suspend/resume on the exact `fdeeda0` candidate artifacts. |
| Wi-Fi | Partial | Scan, association and routed traffic passed alongside Bluetooth. | Three cold boots, reconnect and suspend/resume. |
| Bluetooth | Partial | Native BlueZ `hci0`, scan/UI and coexistence with Wi-Fi passed. | Pair/reconnect and audio/data profiles across suspend. |
| Touch and keys | Works | Touch plus balanced power/volume press and release events passed. | Regression check after native display work. |
| Haptics | Partial | Bounded RT6010 effects work and stop correctly. | Cold-boot repetition and suspend/resume. |
| Audio | Partial | Earpiece, lower speaker and built-in microphone paths have physical evidence. | Recheck stream lifecycle, calls and suspend/resume. |
| Thermal | Partial | All 24 MT6878 zones return plausible polling-mode values without USB loss. | IRQ/trip routing and sustained load remain disabled/unverified. |
| Charging | Partial | MT6375/charger telemetry works. AICR/ICHG were 500000 uA and the gauge measured +284424 uA net battery current with the system active. TCPM simultaneously reported Type-C default mode and `CURRENT_MAX=0`, so the conservative fallback is correct. Native BC1.2 SDP/CDP/DCP classification is absent. | Observe a USB 2.0 host, known Rp 1.5 A source and known 5 V BC1.2 DCP. Validate USB2 PHY DP/DM ownership before implementing only the MT6375 BC1.2 boundary. Keep PD/PPS and OTG disabled and never force 2 A on an unclassified source. |
| Idle battery drain | Broken | Roughly half the battery was reported lost during an uncontrolled overnight period. Existing captures retained `usb0`, kept MTU3 runtime-active with `power/control=on`, and sometimes charged, so they cannot identify an unplugged cause. Wi-Fi runtime PM is unsupported and its wake/IRQ counters make it the first A/B candidate, not a proven fault. | Run local, physically unplugged, screen-off intervals on separate clean boots with Wi-Fi associated and disabled. Record start/end coulomb counter, monotonic time, suspend result and wake/IRQ deltas; reconnect USB only after each interval. |
| GNSS | Broken | Manual vendor module probe created `/dev/gpsdl0` and `/dev/gpsdl1`; missing EMI handoff and LNA pinctrl blocked a valid link test. No position fix exists yet. | `11befa5` adds exact LNA pinctrl; U-Boot `b76e47e` adds validated EMI handoff. Install separately, then test firmware, DSP open and a position fix while USB/Wi-Fi/BT remain healthy. |
| Modem / SIM | Broken | No ModemManager modem, CCCI/DPMAIF/WWAN device or SIM state. U-Boot validates the LK CCCI payload; kernel CCCI core remains compile-only. An isolated patch converts `from_timer()` to `timer_container_of()` and non-sync `del_timer()` to `timer_delete()`; both timer errors are gone and `ccci_hif_ccif.o` now fails first at unowned `MTK_SIP_KERNEL_CCCI_CONTROL`. | Prove the exact installed trusted-firmware CCCI secure ABI and return semantics, then compile/link CCIF without producing or shipping a module. DPMAIF, DT and runtime remain later gates. |
| Sensors | Broken | SCP/mailbox/IPI/HF/sensorhub sources compile and fail closed; no accelerometer, gyro, proximity or light sensor is exposed. A host-only parser against U-Boot `b76e47e` now validates unique 64-bit shared/loader carveouts, DRAM containment, size and non-overlap without changing the FDT. It does not validate SCP firmware or TCM. | Establish authoritative active `scp1`/`scp2` authentication/selection and TCM region-info ABI. Only then integrate an observation-only U-Boot path; publication, disabled DVFS nodes and live probes remain separate later gates. |
| GPU | Broken | Panthor is configured, but no Mali platform device or render node exists. | `c8f02ca` inventories VSRAM/VGPU provider support without enabling it. MFG0 power domain, DT consumer, CSF firmware and protected memory are still required. |
| Rear/front cameras | Broken | No camera media pipeline or preview/capture. Torch channels work independently. | Corrected PD9302A init and an IMX882 raw-ID object remain compile-only in active `pkgrel=127`; no camera DT client or module is shipped/autoloaded. Sensor live identity, SENINF/ISP and the media graph remain. |
| Display | Partial | Bootloader framebuffer through simpledrm gives a usable fixed image. `pkgrel=127` prepares a compile-only S6E8FC3X02 object gate; shipped config remains off and no module/DT client is packaged. It has never run on the phone. | Pass full CI, then implement MT6878 DDP/mutex/CMDQ/DSC/DSI/PHY and test a separate opt-in DTB while retaining framebuffer rollback. |
| microSD | Untested | Controller probes, but no physical card I/O test was recorded. | Insert/remove, read/write and remount test. |

## Current installation test

The next install is deliberately a regression candidate, not a claim that all
new hardware works. It must first prove:

1. Boot to userspace with the same root filesystem behavior.
2. Automatic USB NCM/SSH and an exact 32 MiB transfer.
3. Wi-Fi association/routed traffic, Bluetooth, audio, touch and haptics.
4. Thermal and charger telemetry with no new warning, IRQ or power regression.
5. A clean warm reboot with USB returning automatically.

Only after those checks will the GNSS candidate be exercised manually. Modem,
GPU, sensorhub, camera pipeline and native display stay disabled in that boot.
