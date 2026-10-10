# Port summary, 2026-10-10

Native postmarketOS port for Nothing CMF Phone 1 (nothing-tetris, MT6878).
This is an experimental port, not a fully functional daily-driver phone.
Default repositories: [pmOS main](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports)
and [U-Boot master](https://github.com/xxxvik-xakerxxx/u-boot).

## Latest installed checkpoint: r179

Clean installation used [CI 37949322510](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37949322510),
source `0b904d61731624418b70201e4d615c945eacbb4d`.
Archive SHA256:
`de5dd350fe8519ebcf986757446ea3dae69b809ff19e8c10b69e02ae44cd9c2c`;
all image digests and 7,665 sparse chunks were verified before installation.

| Installed component | Identity |
| --- | --- |
| Kernel | `7.2.1-r179`, Linux `6.18.0 #180` |
| Device package | `8-r17` |
| U-Boot | Experimental `d385921124b9e48a00d5e078d11b07dcdf311270`, slot `lk_a` |
| U-Boot image SHA256 | `ab95c709d8579daf89fe3d8eeb8b04e1782e53605a509a18f97c12bb08382365` |
| Sensor backend | `iio-sensor-proxy-tetris 3.9-r2`, installed afterward from CI |
| Root filesystem | 104.5 GiB, expanded and writable |

Installation wrote `super`, `userdata` and the required loader to `lk_a`.
Stock `lk_b`, factory/NV and calibration partitions were preserved.
See [installation guide and disclaimer](INSTALL.md) before flashing.

The clean installation originally used validated loader `dcb20ce` (image
`71b474fe0c4cfbdfa33fb9ddef51b835b1bf2c367afc84f5ee4a6d85061a6967`),
which remains the recovery baseline. The current experimental loader comes
from [CI 37990994952](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37990994952);
download hashes and installed `lk_a` readback match. Stock `lk_b` digest remains
`812873696e06a972eb5d67f5035687b91b1b48e4df0d25efc15d52fbf09b2518`.
Warm boot reached r179 and restored USB/SSH, but SCP again rejected inherited
TCM with `-EBUSY`; sensors did not start. After full poweroff and user-confirmed
cold power-on, boot `eb3d9a5e-43b2-4bc8-8447-286a5de4f441` reports prepared SCP,
error zero, automatically active sensor services, 24 inventory entries and mask
31. USB/SSH remain functional and no system units failed. The user confirmed
display, touch, both rotations and automatic brightness. GPUEB reports
`verified-erased`, error zero, 156,064 authenticated bytes and segment format
UNKNOWN (zero count/span/entry): neither ELF nor MTK PT. No GPU power/start
writes occur; the LK copy-span mismatch remains unresolved.

The clean image lacked the SensorProxy D-Bus activation descriptor, so sensors
initially required a standard service start. Package `3.9-r2` fixes activation
through the existing standard systemd/D-Bus service, not a second daemon or
boot polling script. [Package CI 37970239648](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37970239648)
passed at `d941aa6`; APK SHA256:
`ba8ce7185648dcc7d745c516a158fd4de9ff02a9722ace8e483c842f5b0d792c`.

The verified APK owns the activation descriptor; its triggers regenerated
initramfs/FIT without changing the kernel. Automatic activation passed the
cold boot above without manual service or module startup. A fresh image
containing r2, repeat boots and full lifecycle remain unverified. Warm sensor
recovery still fails at SCP preflight, separately from D-Bus activation.

## Hardware summary

Works below means demonstrated basic function on the tested handset, not every
lifecycle or SKU. Earlier subsystem evidence is identified explicitly.

| Subsystem | Status | Demonstrated / remaining |
| --- | --- | --- |
| Boot, UFS/root expansion | Works for tested setup | Clean r179 reaches userspace with writable expanded root; other firmware/SKUs remain unverified. |
| Native display | Partial | Route and frame-end updates are in main; user confirms no stripes/flicker. Fixed 60 Hz/software rendering; 120 Hz and full power lifecycle remain. |
| Touch and keys | Works for basic input | Touch and power/volume keys tested; full suspend/wake coverage remains. |
| Sensors | Partial | Five physical classes emit real data; rotation, automatic brightness and local-call proximity tested. Automatic startup passed one cold boot with r2; repeats, calibration, warm boot, suspend and smooth brightness remain. |
| USB/NCM/SSH | Partial | Clean boots and transfer gates pass; reconnect/suspend lifecycle remains. |
| Wi-Fi / Bluetooth | Partial | Earlier association/traffic and Bluetooth discovery demonstrated; profiles, coexistence and suspend remain. |
| Audio | Partial | Earlier speaker paths and microphone capture demonstrated; cellular audio and full route/lifecycle coverage remain. |
| Haptics / torch | Partial | Earlier bounded physical effects tested; lifecycle and camera strobe remain. |
| Battery, charging, thermal | Partial | Telemetry and charging observations exist; classification, sustained safety and idle power remain. |
| GNSS | Partial, transport only | No verified position fix or operational GeoClue navigation stack. |
| SIM, calls, SMS, mobile data | Broken | No operational modem; proximity testing used a local dummy call, not GSM. |
| GPU acceleration | Broken | No render node or accelerated compositor. |
| Cameras | Broken | No working preview/capture or video/media node. |
| microSD | Partial | Controller probes; card insertion and real I/O remain untested. |
| NFC | Not present | No NFC hardware on this device. |

## Remaining hardware work

- **Modem:** authenticated firmware/layout and CCIF/DPMAIF groundwork exist.
  The actual boot-stage EMI/remap, physical power/BROM completion and complete
  kernel handoff must be connected before SIM detection, network registration,
  calls, SMS or data can work. File signatures are not RAM attestation or READY.
  See [modem research](MODEM_SIM_EVIDENCE_PLAN.md).
- **GPU:** Panthor and GPUEB groundwork exists. Transform-only firmware inspection
  succeeded on the preceding loader, then erased the buffer without starting
  GPUEB. The verified 156,064-byte interval does not explain LK's 258,744-byte
  SRAM copy. Authenticated upload layout, power/IRQ ownership and firmware boot
  remain unresolved. See [GPU research](GPU_BRINGUP.md).
- **Camera:** IMX882 V4L2 tables, SENINF and CAMSV/CQ candidates exist. Native CQ
  generation is available; power/reset, sensor-to-receiver stream, IRQ/DMA stop
  and a real capture controller remain. No Android HAL or proprietary composer
  is running. See [camera research](CAMERA_BRINGUP.md).
- **GNSS:** matching stock engine/config and transport contracts are retained.
  Actual engine init/run, host services, exclusive RX ownership and bounded
  shutdown remain incomplete. Library loading is not a fix.
  See [GNSS research](GNSS_USERSPACE_BRIDGE_AUDIT.md).

## Source and CI boundary

[Native CI 37968660008](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37968660008)
passed the actual kernel ASN.1/modem certificate and PSS32 fixtures, GPUEB
bounded MMIO logic, GNSS argument and existing camera/CSF checks.

[ARM64 CI 37991879173](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37991879173)
passed validation, Bionic compilation and all 20 isolated kernel translation
units, including direct-camera and platform consumers. Production source bytes and object identities
are recorded in the CI artifact. The generated CAMSV patch matches the
macro-safe barrier calls. KUnit object compilation is not KUnit execution.

These research candidates are not shipping DT activation, linked operational
drivers or hardware support. No full image was built by the object-only run.
Future image builds must retain display/touch/sensors/USB behavior and include
actual runtime integration, not merely additional compile-only candidates.

The signed modem input caller reuses the existing ROM/DSP layout and retains
the firmware API's verified bytes without another full allocation, bundle scan
or rehash during placement. Independent manufacturer-signed B4.1 input
[CI 37988706465](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37988706465)
passed the actual public 90,214,400-byte `modem.img`, real crypto and sanitizer
lifetime/fault fixtures. This caller does not establish physical EMI/power/BROM
ownership; its ARM64 integration and hardware startup remain pending.

The direct camera candidate builds coherent CQ memory in the kernel and uses
native vb2 RAW/meta buffers. Its restricted single-frame path needs no CCD
daemon, new userspace ioctl or RPMSG transport. DONE observation is separate
from controller-side IRQ drain/stop and buffer completion.
A platform IRQ/lifetime consumer is now present, but complete power/route/stop
providers and hardware capture remain pending. Compilation is not camera
support. See [direct path](../patches/camera-direct/DIRECT-CONTRACT.md).

GNSS output now uses the existing callback worker, with separate application
and raw/NMEA sinks for standard consumers. Frame requests keep the same AGPS
path; no second receiver reader or navigation parser was added. Native stream
fault tests and AArch64 Bionic builds passed
[CI 37990623007](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37990623007).
Engine initialization, firmware readiness and a position fix remain
unverified. See [integration](../patches/gnss-navigation-audit/NAVIGATION_HOST_INTEGRATION.md).

The modem boot-stage candidate now implements concrete EMI/remap/lock,
source-derived NS BL33 clock/isolation/power/bus ordering and four-word BROM
completion. First-error reporting and finite stock-order failure shutdown are
separate. [CI 37991128306](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37991128306)
passed all 37 native sanitizer fault cases plus the actual signed stock input.
Active EMI row production and physical startup remain incomplete;
[U-Boot CI 37992519175](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37992519175)
passed real ARM64 bootstrap/secure objects and the full image at `a52243d8d5`.
Those objects have no active caller. The installed loader remains `d385921`.
The bootstrap is not enabled
by a board hook and does not expose SIM/calls. See
[boot transaction](../patches/modem/drafts/boot-stage/README.md).

The camera platform consumer adds four source-derived IRQ handlers, native
media-pipeline ownership, runtime-PM/clock references and controller-context
stop. IRQ drain occurs outside the vb2 mutex. CAM_MAIN/SMI reset, calibrated
SENINF/CAMMUX and TG/VF shutdown providers are still required; no video node
is activated. Its two additional ARM64 objects passed the combined CI above. See
[platform contract](../patches/camera-direct-platform/SOURCE-CONTRACT.md).

## Project rules

Use Linux media/vb2, remoteproc, DRM/Panthor and the standard desktop sensor
interface where applicable. Optimize our code, not unrelated vendor/upstream
sources. Preserve per-device calibration, derive resources from DT and never
replace missing hardware state with guessed constants or successful stubs.

SCP remains cold-handoff dependent. No secure-boot bypass, universal NOS 4.0
support, calibrated sensor certification or completed suspend lifecycle is
claimed. The unsolicited on-screen keyboard issue remains deferred.

Older installation diaries are in Git history; detailed source/evidence belongs
in [subsystem research](README.md), not duplicated here. Retired branch tips are
under `archive/2026-09-22/*`; archived does not mean merged or hardware-verified.
Local research drafts/worktrees are intentionally untouched.

Next: [completion plan](PORT_COMPLETION_PLAN.md).
