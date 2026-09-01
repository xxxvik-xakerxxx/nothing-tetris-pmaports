# Nothing Tetris current port status

Updated: 2026-09-01.

## Exact software state

| Role | Revision | Device state |
| --- | --- | --- |
| Installed pmaports image | `f607513` | Kernel `6.18.0 #123`; clean-install and warm-reboot baseline. |
| Stable pmaports source | `main` at `ee994e4236d69c9f3eb18e81614dd0dff9e60266` | Rollback source of truth. |
| pmaports candidate | `codex/next-hardware` code at `f8df318` | `pkgrel=125`; integrated CI with U-Boot `b76e47e` not started yet; not installed. |
| Installed U-Boot | `8aa048f93bb7569e4107ef85aa994c630f85de48` | Current bootloader baseline. |
| U-Boot candidate | `b76e47e774304ab550a6354f3286860b7caffb3a` | CI passed; not flashed yet. |

`Works` means the end-user function was physically demonstrated. `Partial`
means useful behavior works but lifecycle, integration or portability gates are
still open. A compile-only patch does not improve the end-user status.

## Hardware matrix

| Subsystem | Current status | Confirmed evidence | Candidate / next gate |
| --- | --- | --- | --- |
| Boot and root filesystem | Works | Clean flash boots pmOS; root is writable and expanded. | Recheck after every candidate installation. |
| USB debug / NCM SSH | Partial | Automatic `usb0`, SSH and exact 32 MiB transfers passed on clean and warm boots. | Require reconnect, repeated reboot and suspend/resume on the `f8df318` candidate. |
| Wi-Fi | Partial | Scan, association and routed traffic passed alongside Bluetooth. | Three cold boots, reconnect and suspend/resume. |
| Bluetooth | Partial | Native BlueZ `hci0`, scan/UI and coexistence with Wi-Fi passed. | Pair/reconnect and audio/data profiles across suspend. |
| Touch and keys | Works | Touch plus balanced power/volume press and release events passed. | Regression check after native display work. |
| Haptics | Partial | Bounded RT6010 effects work and stop correctly. | Cold-boot repetition and suspend/resume. |
| Audio | Partial | Earpiece, lower speaker and built-in microphone paths have physical evidence. | Recheck stream lifecycle, calls and suspend/resume. |
| Thermal | Partial | All 24 MT6878 zones return plausible polling-mode values without USB loss. | IRQ/trip routing and sustained load remain disabled/unverified. |
| Charging | Partial | MT6375/charger telemetry works. On the current USB 2.0 default-current source the policy correctly limits input to 500 mA; about 284 mA net battery charge was observed with the system active. | Add proven USB 3, BC1.2, Type-C Rp and PD current detection; test real chargers. Do not force 2 A on an unclassified host. |
| Idle battery drain | Broken | Roughly half the battery was reported lost during an overnight idle period. CPU cluster-off works, but no controlled unplugged screen-off discharge run has isolated the cause. | Repeatable one-hour screen-off and suspend measurements with wakeup/IRQ deltas. |
| GNSS | Broken | Manual vendor module probe created `/dev/gpsdl0` and `/dev/gpsdl1`; missing EMI handoff and LNA pinctrl blocked a valid link test. No position fix exists yet. | `11befa5` adds exact LNA pinctrl; U-Boot `b76e47e` adds validated EMI handoff. Install separately, then test firmware, DSP open and a position fix while USB/Wi-Fi/BT remain healthy. |
| Modem / SIM | Broken | No ModemManager modem, CCCI/DPMAIF/WWAN device or SIM state. | U-Boot validates the LK CCCI payload; kernel CCCI core remains compile-only. Next: CCIF/DPMAIF dependencies, then a fail-closed manual boot before userspace integration. |
| Sensors | Broken | SCP/mailbox/IPI/HF/sensorhub sources compile and fail closed; no accelerometer, gyro, proximity or light sensor is exposed. | Complete SCP firmware/reserved-memory handoff, then expose standard IIO devices without automatic reset loops. |
| GPU | Broken | Panthor is configured, but no Mali platform device or render node exists. | `c8f02ca` inventories VSRAM/VGPU provider support without enabling it. MFG0 power domain, DT consumer, CSF firmware and protected memory are still required. |
| Rear/front cameras | Broken | No camera media pipeline or preview/capture. Torch channels work independently. | Corrected PD9302A init and a disabled IMX882 raw-ID probe are compile-only in `pkgrel=125`; no camera module is shipped or autoloaded. Sensor live identity, SENINF/ISP and the media graph remain. |
| Display | Partial | Bootloader framebuffer through simpledrm gives a usable fixed image. Native brightness, KMS page flips, 60/120 Hz switching and suspend are absent. | Compile S6E8FC3X02 independently, then test a separate opt-in native DSI/DSC DTB while retaining the framebuffer rollback. |
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
