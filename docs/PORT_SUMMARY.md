# Port summary, 2026-10-12

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
| Running U-Boot / `lk_a` | Experimental `e2929baa549f54ce5518b2dd84952318ba857fda` |
| Loader image SHA256 | `26a9dea98387803ddbcd4097610f4d7f0e12a084c0113d8f69f985c10e25d984` |
| Sensor backend | `iio-sensor-proxy-tetris 3.9-r2`, included in the image |
| Root filesystem | Writable; expanded to 104.5 GiB on the next boot; first-install issue recorded below |

The latest loader passed [CI 38217024964](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38217024964).
Its image was synchronously written only to `lk_a` and prefix-readback verified.
Stock `lk_b`, NV and calibration remain unchanged. The ordinary minimum loader
`dcb20ce` in the pmOS manifest is a recovery baseline, not this diagnostic profile.
See [installation and risk disclaimer](INSTALL.md) before flashing.

### Current loader handoff

The new loader publishes a 336-byte v1 SMEM boot-evidence record, scoped to
historical BL33 readbacks, alongside the existing v2 AP descriptor. Linux field
inspection confirms NC/cache reservations, ranges, slots42/43, enables and the
pinned preloader profile. Endpoint marker bit43 is absent on this hardware and
is handled symmetrically; no other readback bits are masked.

On boot `0b955ce0-a0d9-4442-b362-ac980d0d83fc`, the existing exact-r181 isolated
module `ab2e570c5a7fdaa6e16e1f0742efb9bf1b5ea0e5f019703a6d7a67646e740426`
passed one import/plan at uptime299.77s. USB, sensors, SensorProxy and SSH stayed
active with no new kernel faults. No module unload/reload, firmware START or
protected SMEM access was performed. Fresh visual confirmation remains pending.
The preceding warm start refused SCP with EBUSY; after commanded poweroff the
phone booted again with automatic sensor initialization. This is not proof of
a physical cold start or a fix for warm/poweroff lifecycle behavior.

The pure Linux decoder and actual U-Boot producer/decoder round-trip passed
[CI 38218370472](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38218370472),
including sanitizer rejection cases and actual ARM64 objects. The isolated
module candidate now connects that decoder to init and retains an optional
validated snapshot bound to the same reservations and plan. This additional
consumer still needs its own linked-module CI and hardware test. Neither the
boot record nor its decoder grants Linux NS memory access or proves modem READY.

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

### Image expansion fix: CI candidate

The r181 build log confirms pmbootstrap unmounted both install images and
detached their loops before export. The quick clean check at first boot is
not a full fsck after the build-time mount: upstream
[resize2fs 1.47.4](https://github.com/tytso/e2fsprogs/blob/v1.47.4/resize/main.c)
rejects an offline filesystem whose last full check precedes its last mount.
Read-only decoding of the original hash/CRC-verified r181 sparse artifact
confirms clean state1, last-check1791705001 and last-mount1791705002:
the exact refusal condition is present in the shipped image. No inspection
copy was flashed and no mounted-root repair was performed.

Our CI now checks detached regular images with forced offline `e2fsck -p`,
accepting only statuses 0/1, then requires a read-only full check and an
unforced `resize2fs` check before sparse conversion and final hashes.
A separate native fixture must reproduce the refusal, seal ext2/ext4 images,
round-trip Android sparse format and grow to a larger simulated partition
without a force flag. Diagnostic DTBs are retained before full pmbootstrap
shutdown; no driver, bootloader, partition table or handset calibration is
changed by this candidate.

[CI 38149660135](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38149660135)
at `4dcbab6e60b56c60f83ea6f8ae958f2014b56446` passed every job, including actual
ARM64 objects, the sealed GNSS loader, Bionic adapter and full install images.
All ten image-gate tests ran, including
real ext2/ext4 refusal, sparse round-trip and growth from 16,384 to 32,768 4KiB
blocks without force; the Ubuntu fixture used e2fsprogs1.47.0. The full build
used e2fsprogs1.47.3: detached root/boot images passed forced fsck, both read-only
checks and unforced resize checks, retaining exact extents 2,783,969,280 and
536,870,912 bytes. Both fsck statuses were 0. The sealing log is retained in
the CI build-log artifact. New image archive SHA256:
`2ecd345b25ab89f0723ff8fd1dd8d3308453b41d5e9652ee9f2190de1f2db842`.
Clean-install expansion remains unverified until the new artifacts are tested.
The installed phone is still the original r181; SIM/calls, navigation, GPU
acceleration and camera capture are not newly demonstrated by these CI tests.

### r181 restart and first AP-only import

After the user's restart, boot `8d332faa-c0ef-4968-bc21-58571eb2dfaf`
at uptime51.65s again received the valid 21-tag descriptor and zero-error BROM
report. SCP preparation was `secure-handoff-prepared`, state3/error0; the
sensor, SensorProxy and SSH services started automatically. The journal lists
all 24 sensor inventory entries. Physical cold-power procedure and current
visual behavior are not inferred from the word "restarted".

Initramfs recovered the journal and orphaned inodes before mounting root, then
expanded ext4 to 28,299,256 4KiB blocks. Root now reports 104.5 GiB, with
96.9 GiB available at the baseline. This subsequent-boot result does not
remove the original first-install defect or prove a clean shutdown.

At uptime231.28s the exact-ABI AP-only module from original CI38117727546
was loaded once with a 20-second deadline. Module SHA256:
`90106d01591ce111a020ad8526ac5344c4b25cbaff7cbe1d1704b9b52a05836f`.
`insmod` returned0, and the kernel emitted:
`Tetris CCCI: owned metadata imported; runtime transport disabled`.
Only this isolated util module was loaded; no legacy CCCI/DPMAIF or SMEM
mapping, firmware START, registration or radio device activation was attempted.

The same boot, USB/NCM and all three services remained active, with no failed
units or new Oops/BUG/SError/panic/WARNING. A fresh 32MiB SSH transfer matched
SHA256 `83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`.
No radio/GPS/video/media device or DRM render node appeared. The test module
is not installed/autoloaded and was left loaded, not repeatedly removed/retried.
This is physical metadata import, not modem READY, SIM detection or a call.

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

Earlier warm reboots failed SCP preparation on inherited TCM with `-EBUSY`.
The successful r181 restart above does not by itself resolve every warm-start
path or suspend/resume.

## Hardware summary

Basic functions below refer to the tested handset. Full lifecycle and other
firmware/SKU coverage are not implied; earlier evidence is identified explicitly.

| Subsystem | Status | Demonstrated / remaining |
| --- | --- | --- |
| Boot / UFS | Works for basic boot | Clean r181 boots and reads/writes root; firmware/SKU portability unverified. |
| Root expansion | Partial | r181 reaches 104.5 GiB on its next boot; fixed image sealing passed CI, but its first clean installation remains untested. |
| Native display | Partial | Route and frame-end updates are in main; no visible stripes/flicker. Fixed 60 Hz and software rendering; 120 Hz and power lifecycle remain. |
| Touch and keys | Works for basic input | Touch and power/volume keys tested; full suspend/wake coverage remains. |
| Sensors | Partial | Five physical classes emit data; rotation, auto-brightness and local-call proximity tested. Automatic cold startup observed; calibration, warm reboot, suspend and smooth brightness remain. |
| USB/NCM/SSH | Partial | Clean boots and transfers pass; reconnect/suspend lifecycle remains. |
| Wi-Fi / Bluetooth | Partial | Earlier association/traffic and discovery demonstrated; profiles, coexistence and suspend remain. |
| Audio | Partial | Earlier speaker paths and microphone capture demonstrated; cellular audio and full route coverage remain. |
| Haptics / torch | Partial | Earlier bounded physical effects tested; lifecycle and camera strobe remain. |
| Battery, charging, thermal | Partial | Telemetry and charging observations exist; sustained safety and idle power remain. |
| GNSS | Partial, transport only | No position fix or operational GeoClue navigation stack. |
| SIM, calls, SMS, mobile data | Broken | BROM and physical AP-only metadata import pass; runtime CCCI, SIM/registration and calls are unavailable. Proximity testing used a local dummy call, not GSM. |
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
kernel-evidence hashes matched after download. The image is installed and the
single physical AP-only import passed as recorded above. New GPS read behavior
remains untested on hardware.

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

Next operational boundary: immutable bank ownership, source-backed range/security
admission and transactional SMEM integration before CCCI transport/registration.
Do not load the legacy util module against the new descriptor or treat successful
tag import as permission to access firmware/SMEM. Runtime transport remains off.
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
The isolated AP-only util candidate now retains a private copy of the validated
bank reservations and feeds the existing pinned SMEM argument adapter during
serialized module initialization. It retains consumer-ready NC/cache tables
with NULL virtual addresses, then destroys the transient planner owner. Module
failure/exit clears the tables before freeing the argument storage. Physical
SMEM mapping/publication functions are omitted from this candidate's source;
it is not installed or autoloaded. [CI38179025105](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38179025105)
passed 59 native end-to-end producer/import/plan scenarios at both 4 KiB and
64 KiB geometry, actual ARM64 compilation and strict module linking against
the original r181 full-build exports. Kernel archive/patches, util adaptations,
LLVM21.1.8, the prepared configuration and kernel release match r181; no fake
symbol table or relaxed modpost was used. The resulting GPL module has no
external module dependencies, vermagic `6.18.0 SMP preempt mod_unload aarch64`,
and SHA256 `ab2e570c5a7fdaa6e16e1f0742efb9bf1b5ea0e5f019703a6d7a67646e740426`.
Independent review found no relevant correctness/safety bugs. The first physical
import/plan passed on boot `e73e5393-de6e-4525-afeb-3e47c2a1c3ff`: a single
insmod at uptime232.96s returned0 and logged NC1204224/cache39190528 bytes with
memory access and runtime transport disabled. USB, sensors, SensorProxy and SSH
stayed active, no failed units or new kernel faults appeared, and a complete
32 MiB USB stream matched SHA256
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`.
That module was left loaded until the later planned loader update; no unload/reload
or partition flashing occurred during the first import/plan experiment.
Visual regression confirmation is pending. The preceding warm boot refused SCP
preparation with EBUSY; one identity-guarded host USB reset restored networking.
After a commanded poweroff the phone booted again with successful SCP preparation
and automatic sensor services. That observation is not a user-confirmed physical
cold start and does not fix warm reboot or poweroff behavior. This single pure
SMEM-plan test is not evidence of SIM, modem READY or protected-memory access.
Runtime SMEM admission, CCIF/DPMAIF/FSM lifecycle,
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
