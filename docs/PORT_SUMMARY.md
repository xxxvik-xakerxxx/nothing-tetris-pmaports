# Port summary, 2026-10-11

Native postmarketOS port for Nothing CMF Phone 1 (`nothing-tetris`, MT6878).
Experimental, not a fully functional daily-driver phone.
Current development is in [pmOS main](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports)
and the maintainer's [U-Boot master](https://github.com/xxxvik-xakerxxx/u-boot).
The shared MT6878-Mainline U-Boot repository has not been updated by this work.

## Latest installed checkpoint: r179

Clean installation used [CI 37949322510](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37949322510),
source `0b904d61731624418b70201e4d615c945eacbb4d`.
Archive SHA256: `de5dd350fe8519ebcf986757446ea3dae69b809ff19e8c10b69e02ae44cd9c2c`.
All image hashes and 7,665 sparse chunks were verified before installation.

| Installed component | Identity |
| --- | --- |
| Kernel | `7.2.1-r179`, Linux `6.18.0 #180` |
| Device package | `8-r17` |
| Running U-Boot / `lk_a` | Experimental `cdd806438d73e2e163fcc9aded557b029816011e` |
| Loader image SHA256 | `1dd571bf3965851c2d79a9417482ec172f62b56fbf9c84f429d70f8b09bf187d` |
| Sensor backend | `iio-sensor-proxy-tetris 3.9-r2`, installed afterward from CI |
| Root filesystem | 104.5 GiB, expanded and writable |

The latest loader passed [CI 38113985169](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38113985169).
Its image was synchronously written only to `lk_a` and prefix-readback verified.
Stock `lk_b`, NV and calibration remain unchanged. The ordinary minimum loader
`dcb20ce` in the pmOS manifest is a recovery baseline, not this diagnostic profile.
See [installation and risk disclaimer](INSTALL.md) before flashing.

### Latest cold observation

User-confirmed physical power-off, ten-second wait and power-on produced boot
`82a5ef34-9a64-498b-820a-2770b02a004e`; the first structured report was saved at
90.14 seconds, together with the complete kernel journal.

- Modem BROM: loader/report errors0, loaded stage11 COMPLETE, hardware stage15
  COMPLETE, board stage16/status1, publication error0 and no cleanup failure.
  Secure response x2=x3=`0x100000001` satisfies all four source-defined flags.
  Final EMI slot43 is VERIFIED/step20/error0.
- SCP: `secure-handoff-prepared`, prepare error0, secure state3/error0.
  Sensorhub reports firmware ready, 24 inventory entries and physical mask31.
- Sensor, SensorProxy and SSH services started automatically after the existing
  sensor opt-in. No failed system units; USB/NCM and SSH stayed healthy.
- The user confirmed normal display, touch, both rotations and automatic brightness.
- No new kernel Oops, BUG, SError, panic or WARNING was found. Existing null SCP
  resource diagnostics, filesystem mount warning and Wi-Fi/SCP notification
  timeouts remain unresolved.

Installed r179 has no `mediatek,mddriver` consumer. The strict final metadata
publisher refuses this DT: there is no CCCI descriptor or AP tag reservation.
BROM completion is **not** runtime modem READY, SIM detection or a working call.

Warm reboot still fails SCP preparation on inherited TCM with `-EBUSY`.
Cold startup success does not resolve warm reboot or suspend/resume.

## Hardware summary

Basic functions below refer to the tested handset. Full lifecycle and other
firmware/SKU coverage are not implied; earlier evidence is identified explicitly.

| Subsystem | Status | Demonstrated / remaining |
| --- | --- | --- |
| Boot, UFS/root expansion | Works for tested setup | Clean r179 boots with writable expanded root; other firmware/SKUs unverified. |
| Native display | Partial | Route and frame-end updates are in main; no visible stripes/flicker. Fixed 60 Hz and software rendering; 120 Hz and power lifecycle remain. |
| Touch and keys | Works for basic input | Touch and power/volume keys tested; full suspend/wake coverage remains. |
| Sensors | Partial | Five physical classes emit data; rotation, auto-brightness and local-call proximity tested. Automatic cold startup observed; calibration, warm reboot, suspend and smooth brightness remain. |
| USB/NCM/SSH | Partial | Clean boots and transfers pass; reconnect/suspend lifecycle remains. |
| Wi-Fi / Bluetooth | Partial | Earlier association/traffic and discovery demonstrated; profiles, coexistence and suspend remain. |
| Audio | Partial | Earlier speaker paths and microphone capture demonstrated; cellular audio and full route coverage remain. |
| Haptics / torch | Partial | Earlier bounded physical effects tested; lifecycle and camera strobe remain. |
| Battery, charging, thermal | Partial | Telemetry and charging observations exist; sustained safety and idle power remain. |
| GNSS | Partial, transport only | No position fix or operational GeoClue navigation stack. |
| SIM, calls, SMS, mobile data | Broken | BROM completes; runtime CCCI, SIM/registration and calls are unavailable. Proximity testing used a local dummy call, not GSM. |
| GPU acceleration | Broken | No render node or accelerated compositor. |
| Cameras | Broken | No preview/capture or operational video/media node. |
| microSD | Partial | Controller probes; card insertion and real I/O untested. |
| NFC | Not present | No NFC hardware on this model. |

## Next Combined Image

Kernel package r181 is being corrected after
[CI 38115566997](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38115566997)
from `2e983241000633a6e572f0e1558bc36ebfdce2b8` failed during DTB compilation:
the new metadata subnode preceded root properties. Its corrected placement
follows those properties. The early object gate now compiles and validates all
four real packaged DTBs before the full image build.
Source/patch validation, isolated ARM64 objects, the sealed GNSS loader and
the Bionic adapter passed the failed run; the corrected DTBs and full
kernel/package/image remain pending new CI.
The first short retry stopped on an obsolete CI-integration template after the
`dtc` dependency was added; that template is corrected without relaxing its
forward/reverse or duplicate-helper checks.

The candidate includes:

- A sole **disabled** CCCI metadata anchor matching B4.1 AP6878/MD6299, with no
  physical resources or inherited descriptor. A compiled-DTB check enforces it.
- An isolated AP-tag-only `ccci_util_lib.ko` build against actual kernel exports.
  It validates/copies the retained 64 KiB AP tag buffer, never maps MD firmware
  or SMEM, and is neither installed nor autoloaded.
- CI checks of the actual camera worker mapping/retirement code and the actual
  U-Boot GPUEB parser, rather than separate review mirrors.
- SensorProxy r2 with standard systemd/D-Bus activation.
- The real GPS data-link reader now bounds requests to its buffer, returns zero
  without channel access for an empty request and honors nonblocking empty reads.
  Failed DMA copies release reader ownership without consuming the queued entry,
  so a correctly sized later read can recover instead of returning permanent BUSY.
  Native fixtures cover both IRQ and polling branches; CI execution remains pending.

Next physical boundary: verify the retained descriptor and 21-tag handoff on a
clean cold boot, then test only the exact-ABI AP-only importer. Do not load the
legacy util module against the new descriptor. Runtime transport remains off.
This candidate is not a promise of functioning SIM, camera, GPU or navigation.

r180 from [CI 38038376683](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38038376683)
was downloaded and verified but not installed; it is superseded by this candidate.
Historical failed builds and installation diaries are retained in Git history.

## Remaining Integration

**Modem.** Authenticated placement, initial power ownership, EMI/remap readback
and physical BROM completion are connected in the opt-in U-Boot profile.
[Metadata import](../patches/modem/drafts/runtime-metadata/README.md) has passed
59 native producer/import cases and 64 real ARM64 driver objects in
[CI 38052285012](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38052285012).
[SMEM transactions](../patches/modem/drafts/runtime-smem/README.md) passed 70
native cases at both 4 KiB and 64 KiB geometry and actual ARM64 compilation in
[CI 38068292750](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38068292750).
Neither result proves protected-memory access or runtime registration.
Immutable bank ownership, runtime SMEM admission, CCIF/DPMAIF/FSM lifecycle,
SIM/registration and the userspace radio/audio path remain.
See [modem research](MODEM_SIM_EVIDENCE_PLAN.md).

**GPU.** Panthor, GPUEB ingress and source-backed power/reset candidates exist.
An earlier physical transform-only test authenticated 156,064 bytes, reported
UNKNOWN segment format and erased the buffer without starting GPUEB. Matching
LK copies 258,744 bytes from the same destination; the extra 102,680 bytes have
no proven initialization/firmware producer. Do not substitute guessed padding,
BSS or debug xfile bytes. Complete SRAM layout, persistent authenticated
handoff, power/reset/IRQ ownership and boot readiness remain.
See [GPU research](GPU_BRINGUP.md) and [exact LK copy boundary](../patches/gpu/uboot-segments/README.md).

**Cameras.** IMX882 V4L2 tables, SENINF/CAMSV, coherent CQ, native vb2 RAW/meta
buffers, power/reset and repeated-frame ownership candidates exist. Actual
ARM64 compilation and synthetic fault fixtures pass; KUnit compilation is not
KUnit execution or a captured frame. The native worker now handles closed
sessions without losing first errors and releases mappings only after real
retirement acknowledgement. Complete route/provider activation, physical IRQ/DMA
completion, safe stop and actual capture remain. No Android HAL or proprietary
composer is running. See [camera research](CAMERA_BRINGUP.md),
[native direct path](../patches/camera-direct/DIRECT-CONTRACT.md) and
[worker lifetime](../patches/camera-ccd-bus/NATIVE-WORKER.md).

**GNSS.** Transport, pinned stock engine/config, native callbacks and bounded
host/loader ownership candidates exist. Genuine sealed ARM64 Bionic loading,
XML snapshot/control and terminal reap passed
[CI 38074800655](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38074800655).
Engine initialization and hardware readiness were explicitly false.
Real XML/crypto dependency builds and target links passed
[CI 38065279869](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38065279869);
target execution is not established. Firmware/startup, native configuration and
calibration/assistance services, exclusive RX, bounded shutdown and a position
fix remain. Library loading is not navigation.
See [transport](GNSS_BRINGUP.md) and [userspace research](GNSS_USERSPACE_BRIDGE_AUDIT.md).

## Development Boundaries

Use Linux media/vb2, remoteproc, DRM/Panthor and standard desktop sensor interfaces
where applicable. Optimize our code, not unrelated vendor/upstream sources.
Preserve per-device calibration; derive resources from DT and real firmware
identity, never current-handset addresses or successful stubs.

All native/kernel/bootloader compilation is in CI. Driver probe, object tests,
module linkage, clean installation and end-user operation are separate results.
Preserve display/touch/sensors and USB/SSH through each hardware experiment.

No secure-boot bypass, universal NOS 4.0 compatibility, calibrated sensor
certification or completed suspend lifecycle is claimed. The unsolicited
on-screen keyboard issue remains deferred. Retired branch tips are under
`archive/2026-09-22/*`; local drafts/worktrees are intentionally untouched.

Detailed source/evidence belongs in [subsystem research](README.md), not this
status page. Next: [completion plan](PORT_COMPLETION_PLAN.md).
