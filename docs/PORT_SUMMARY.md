# Port summary, 2026-10-11

Native postmarketOS port for Nothing CMF Phone 1 (`nothing-tetris`, MT6878).
Experimental, not a fully functional daily-driver phone.
Current development is in [pmOS main](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports)
and the maintainer's [U-Boot master](https://github.com/xxxvik-xakerxxx/u-boot).
The shared MT6878-Mainline U-Boot repository has not been updated by this work.

## Latest installed checkpoint: r181

Clean installation used [CI 38117727546](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38117727546),
source `e0c67c561ff7c1a0472da851edfafd5a0abb6cec`.
Archive SHA256: `5989d07b77971280b7c2d1f5a88ea5244ed883557f8a54341520ccbbb2ce63bd`.
All image hashes and 7,691 sparse chunks were verified before installation.
`super` and all 17 userdata transfers completed successfully. The installed
FIT matches CI SHA256 `91d7f77a7d8b177fe6320d7bdce267dc88ec26ed146feff9227b5564513d55c1`.

| Installed component | Identity |
| --- | --- |
| Kernel | `7.2.1-r181`, Linux `6.18.0 #182` |
| Device package | `8-r17` |
| Running U-Boot / `lk_a` | Experimental `cdd806438d73e2e163fcc9aded557b029816011e` |
| Loader image SHA256 | `1dd571bf3965851c2d79a9417482ec172f62b56fbf9c84f429d70f8b09bf187d` |
| Sensor backend | `iio-sensor-proxy-tetris 3.9-r2`, included in the image |
| Root filesystem | Writable; first boot remains about 2.4 GiB, expansion unresolved |

The latest loader passed [CI 38113985169](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38113985169).
Its image was synchronously written only to `lk_a` and prefix-readback verified.
Stock `lk_b`, NV and calibration remain unchanged. The ordinary minimum loader
`dcb20ce` in the pmOS manifest is a recovery baseline, not this diagnostic profile.
See [installation and risk disclaimer](INSTALL.md) before flashing.

### First r181 observation: warm boot

Boot `2e9cfc97-4d08-4641-bb6c-b16b65713b79`, structured report at uptime134.32s:

- USB/NCM and SSH work. The installed GPS v051 module reports the expected ABI;
  it has not been started or tested for navigation.
- BROM completed with all errors zero, all four secure flags and verified EMI
  slot43/step20. The sole `/modem` remains disabled with AP6878/MD6299 identity.
- Linux received a fresh v2 descriptor: 3,972 used bytes, 21 tags, error/flag/MD
  error0; the separate 64 KiB reservation matches, is aligned and no-map, with
  no compatible/reusable owner. This is the first physical descriptor handoff,
  not yet the AP-only module import or runtime modem READY.
- SCP preparation returns `-EBUSY` on inherited TCM, with no secure-state fields.
  The sensor service fails rather than retrying. Boot-time sensor opt-in is now
  enabled for the requested physical cold start; r181 visual/cold checks remain.
- Initramfs's `resize2fs` asks for forced `e2fsck` despite the preceding quick
  clean check. Root is still about 2.4 GiB on the full userdata partition. No
  repair was attempted on the mounted root; cold behavior and image sealing need
  verification. r179 recovery images are retained.
- Post-install loader hashes match the pre-install values; neither LK slot,
  stock NV nor calibration was modified.

### Prior validated cold observation: r179

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

That r179 DT lacked a `mediatek,mddriver` consumer, so no descriptor was published.
r181 supplies the disabled anchor and now receives it. BROM/descriptor completion
is **not** runtime modem READY, SIM detection or a working call.

Warm reboot still fails SCP preparation on inherited TCM with `-EBUSY`.
Cold startup success does not resolve warm reboot or suspend/resume.

## Hardware summary

Basic functions below refer to the tested handset. Full lifecycle and other
firmware/SKU coverage are not implied; earlier evidence is identified explicitly.

| Subsystem | Status | Demonstrated / remaining |
| --- | --- | --- |
| Boot / UFS | Works for basic boot | Clean r181 boots and reads/writes root; firmware/SKU portability unverified. |
| Root expansion | Partial | r179 reached full capacity; r181 first-boot offline resize asks for forced fsck and remains image-sized. |
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

## Integrated r181 Changes

Kernel package r181 passed all preliminary jobs in
[CI 38117468070](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38117468070)
at `e0c67c561ff7c1a0472da851edfafd5a0abb6cec`: complete patch application,
actual ARM64 candidate objects, all four compiled/validated packaged DTBs,
GPS read/DMA fixtures, camera worker, GPUEB parser, sealed GNSS loader and
Bionic adapter. The downloaded four DTBs match the CI manifest hashes.
The root-property ordering error, stale CI-integration template and GPS fixture
buffer type are corrected; compiler warnings and contract checks remain strict.

The full kernel/package/image build passed at the **same source** in
[CI 38117727546](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38117727546).
Its isolated AP-only util module linked against real kernel exports, and all
kernel-evidence hashes matched after download. The image is now installed;
physical metadata import and new GPS read behavior remain untested.

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
  Actual-source fixtures passed both IRQ and polling branches under ASan/UBSan;
  removing each fix was detected. Real hardware behavior remains untested.

Next physical boundary: repeat the observed descriptor/21-tag handoff on a clean
cold boot, then test only the exact-ABI AP-only importer. Do not load the
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
