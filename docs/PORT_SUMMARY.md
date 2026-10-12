# Port summary, 2026-10-12

Native postmarketOS port for Nothing CMF Phone 1 (`nothing-tetris`, MT6878).
Experimental, not a fully functional daily-driver phone.
Current development is in [pmOS main](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports)
and the maintainer's [U-Boot master](https://github.com/xxxvik-xakerxxx/u-boot).
The shared MT6878-Mainline U-Boot repository has not been updated by this work.

## Latest installed checkpoint: r182

Clean installation used [CI38248220709](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38248220709),
source `75a510f072239825b9de7e620205a513568cce6e`. ZIP SHA256:
`1ca7f7ca96d7a7290bdec94b19caeb5917b97508d640c49fa136617c4b130a3e`.
All image hashes and 7,690 sparse chunks passed verification. `super` and all
17 userdata transfers completed. First boot `6e6171cf-c626-4081-afd4-6c1f95335f2b`
runs Linux `6.18.0 #183`, kernel package `7.2.1-r182`, device `8-r18` and
SensorProxy `3.9-r2`. Root expanded automatically to 104.5 GiB on this FIRST
installation boot. FIT readback matches CI:
`a4e5cad84cc5815113c76ff1e96009bb556a005a30e00aeda3270845b45ee144`.

U-Boot `8d2ccc12` and stock `lk_b` are unchanged; both readback hashes match
the prior checkpoint. USB/NCM and SSH work, and DRM reports the display
connected. The warm installation boot lacks prepared SCP handoff, so sensors
fail explicitly rather than retrying. A physical power-off/on and visual check
remain required. No new SIM/call, GPS fix, accelerated rendering or camera frame
is demonstrated by installing this image. The r182 config and kernel export
tables are byte-identical to the original r181 ABI used below.

After commanded poweroff, the phone booted again as
`19e13ae5-995e-40a0-afda-daa2061bc524`: SCP state3/error0, BROM/EMI/import
errors0, valid 21-tag descriptor, all three sensor/SSH services active and no
failed units. The service reports 24 inventory entries and physical mask31.
This was an automatic boot with USB attached, not a confirmed physical cold
cycle. The user subsequently confirmed normal screen, touch, rotation and
auto-brightness. One explicit packaged GNSS transport start
at uptime907.39s created both gpsdl nodes and preserved those services/USB;
no link was opened, engine started or position fix attempted. The installed
arch11.8 CSF firmware's decompressed hash matches the expected public payload:
`98ef32f43f05d03711580fb78f44a5b24dcd1f8a2f3ab09a25410fb3d39d7e1d`.

### Previous installed checkpoint: r181

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
| Running U-Boot / `lk_a` | Experimental `8d2ccc12e7861c5726e9c37a07f62c4ae18db7b5` |
| Loader image SHA256 | `adaefa00f662bcd126ecc9b3ee2b0c5352a8168130c4ce7d6a18c4a53a65573f` |
| Sensor backend | `iio-sensor-proxy-tetris 3.9-r2`, included in the image |
| Root filesystem | Writable; expanded to 104.5 GiB on the next boot; first-install issue recorded below |

The latest installed modem/SCP loader passed [CI 38235543158](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38235543158).
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
protected SMEM access was performed.
The preceding warm start refused SCP with EBUSY; after commanded poweroff the
phone booted again with automatic sensor initialization. This is not proof of
a physical cold start or a fix for warm/poweroff lifecycle behavior.

The pure Linux decoder and actual U-Boot producer/decoder round-trip passed
[CI 38218370472](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38218370472),
including sanitizer rejection cases and actual ARM64 objects. The isolated
module now connects that decoder to init and retains an optional validated
snapshot bound to the same reservations and plan.
[CI 38222681473](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38222681473)
passed native integration/failure cases at 4/64 KiB, actual ARM64 compilation and
strict linkage against r181 exports. Module SHA256:
`3d0143789a7b60d19569c8cec480a81c6ac259d24805be5ad4d94250bede71b9`.
On fresh boot `65cc4f77-fd27-419c-8a13-e5a13fc0461d`, one insmod at uptime110.04s
returned0 and logged retained boot evidence plus the plan/import results. The
actual C decoder ran on the handset; USB/sensors/SSH stayed active with no new
kernel faults or failed units. The user confirmed normal display, touch, rotation
and auto-brightness. A completed 32 MiB USB transfer matched SHA256
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`.
The module is left loaded, not installed/autoloaded. Warm SCP
EBUSY recurred before that test; commanded poweroff again led to a prepared boot,
not a user-confirmed cold cycle. Neither the boot record nor its decoder grants
Linux NS memory access or proves modem READY.

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
That CI run was not installed; the later r182 installation above validates
first-boot expansion. SIM/calls, navigation, GPU acceleration and camera capture
are not demonstrated by these image checks.

Later full CI38227409738 compiled the kernel and packages, then failed our image
check with `gzip: invalid magic`. Upstream mkinitfs2.12.0 now defaults to zstd;
the device has no compression override and the kernel supports RD_ZSTD. Our
check now uses libarchive to read compressed CPIO and verifies the actual NCM
module entry plus exact deviceinfo value. Five gzip/zstd/raw/corruption/missing
entry fixtures pass locally, as does checking the original r181 initramfs.
The FIT still passes the ramdisk unchanged (`compression=none`); no archive
conversion or device behavior change is introduced. Full r182 CI subsequently
passed, and the verified images booted as recorded above.

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
SMEM mapping/publication functions are omitted from the default candidate's source;
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
The new opt-in resource-only profile retains the real unpublished planner,
evidence and extents together and claims only the planned page-rounded Linux
iomem ranges. It excludes CONSYS and unused bank tails, unwinds conflicts and
pins successful ownership until reboot. It performs no physical access,
secure-monitor call, mapping, publication or modem START. It is not installed
or autoloaded; the first physical resource result is recorded below.
Both profiles and init-level resource fault cases passed
[CI 38233900132](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38233900132).
The first handset resource attempt on boot `ae496989-7fc8-4759-af93-a5e61e3125c1`
failed with EBUSY, with no retained module/claims or USB/sensor regression.
The live iomem tree showed a busy `reserved` child covering both NC/cache banks.
U-Boot `8d2ccc12e7` removes only their duplicate FDT header reservations while
keeping LMB ownership and plain NOMAP nodes.
That fix passed [U-Boot CI 38235543158](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38235543158)
and the same resource module then passed on boot `6902543e-e25b-48ce-9dae-84f4dbd07b57`
at uptime200.56s: init returned0, two exact iomem children appeared, and the
module reference count was1. CONSYS and bank tails remained unclaimed.
USB/sensors/SSH stayed active; the user confirmed display, touch, rotation and
auto-brightness. This is one resource-ownership test, not modem READY or a
completed cold/warm/suspend lifecycle.

The separate initial-read profile passed
[CI 38240582807](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38240582807):
actual producer/import/init fixtures at both page sizes, post-claim geometry and
policy failures, wrong EL, map failure, default-profile boundary traps, and a
strict ARM64 module link against the original r181 configuration/exports.
Module SHA256: `a9e32ac8720c64119ca492c1a5f2c47629c00141574166232839c48cfaa26f30`.
On fresh boot `71cf27cd-4289-49f1-b79d-e65eb131fef8`, with the restored 8d2ccc12
loader, one insmod completed at uptime806.70s. It checked retained ownership,
the copied NC extents, boot range/policy and actual EL1, mapped the first NC page,
read one 32-bit word, and immediately unmapped it. The kernel logged
`initial NC read completed; zero`. Both iomem claims remain held with module
reference1; USB/sensors/SSH stayed active without a reboot or new abort/Oops.
No writes, cache/NV reads, modem START or transport activation occurred.
Zero does not exclude hardware zero-on-deny behavior, certify immutable secure
policy, prove modem communication or supply a fresh NS certificate. It is one
completed bounded initial read, not successful SIM detection or registration.
The next [private mapped profile](../patches/modem/drafts/runtime-metadata/MAP_ONLY.md)
reuses the existing WC transaction and mapped-unpublished table export. It
revalidates both banks and held claims, excludes CONSYS, copies into private
consumer storage, then retains mappings/ownership until reboot. Native fault
tests and exact-r181 ARM64 linkage passed
[CI38245658821](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38245658821).
Module SHA256: `cdb2841bfd0bfb0baf0933ae6e0c189ad8d75abcd393f77f9334b43392711eb2`.
One physical init on fresh boot `7d4b87cb-bd4e-412e-a7ea-b54eb9729c34` passed
at uptime229.86s, retaining both claims/mappings and module reference1 without
new kernel faults or USB/sensor failures. No memory reads/writes, legacy global
publication or transport START is enabled; this profile is not automatically
installed or loaded. Actual CCCI consumer integration and lifecycle remain.
The next [private CCCI consumer](../patches/modem/drafts/runtime-smem-consumer/README.md)
binds to a real GPL provider export, copies the mapped tables into the fresh
native modem structure and balances its separate module reference on abort.
It bypasses legacy void SMEM initialization and leaves ROM unmapped. Fifteen
source checks, independent review, native sanitized fault fixtures, 64 consistent
consumer objects and strict r181 provider/copy-module linkage passed
[CI38251600849](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38251600849)
at `d0336ee085585c56d80e17e8cbb12bd641219774`.
On fresh boot `2b17cde3-1cce-4b85-bb2a-d920cc7c685e`, one provider init and one
actual-kernel private-copy test returned0 at uptime143.34s. The real patched
`ccci_modem` received the checked tables, then its private copy/reference was
released. The provider retains both original claims/mappings and reference2:
one boot pin plus the normal loaded test-module dependency, not a leaked copy
lease. Provider SHA256 `726a606154aa8aa7351aa49cd809b804faab135990d9fcf5714ae420b323d9d7`;
copy module SHA256 `4e84e01bb1d13893f949460993da874b9dc9ce69ccc6ade304628cd8fc5d8a28`.
A subsequent 32MiB USB transfer matched
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`;
USB/sensors/SSH remained active without failed units or new kernel faults.
This establishes the real provider/copy ABI boundary, not FSM/HIF preparation,
post-bind publication, START or radio operation. The next
[complete-module link](../patches/modem/drafts/runtime-link-closure/README.md)
supplies the actual packaged first-start backend's missing exports and rebuilds
all eight vendor modules against genuine r181/provider exports. Strict ARM64
link/modpost, genuine dependency census and all ten module hashes passed
[CI38255895881](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38255895881)
at `5379657`. The downloaded ZIP matches GitHub's digest
`8a7e3cde7d1f6d47ecda031d2230b7ab5ec29cec96f62d1b3eeae41150ea0e0e`.
The provider matches the already tested module; core SHA256 is
`2f9280e0467c093ff5cfaf0f5c9385126b61af21b563d85eaf52358374e6140e`.
These complete modules are not installed/loaded and do not authorize activating
linked hardware operations. Resource-only HIF binding and actual private
preparation are next; transport publication, START and radio remain denied.
The optional resource profile now validates direct GIC descriptor capacity,
inherited address-cell bounds, trigger-independent IRQ identity and exclusive
resource overlap before private acquisition. Its native fault fixture and
separate strict full-module build are wired into CI; no shipping DT activation
or radio readiness is inferred.
The resource fixture passed ASAN/UBSAN in the completed producer job of
[CI38265540133](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38265540133)
at `5e2c0b1`. Its artifact ZIP SHA256 is
`a5194043fae4a27129b4ae2db00d07dd38802066e22e861ca32010d08ef96cb5`;
reviewed overlay hash `8567e75c09cdb485ba19f52b65c67e2aaedf899ed21a843a98027e3699b5202f`.
Both jobs of that CI passed, including the baseline and separate resource-only
strict ARM64 links plus both camera supplier object configurations. Resource
artifact ZIP SHA256:
`966c311f22e17e724479b69808075c6ae4770a2a21b81bb15f4bfcd6b10df009`.
All ten module hashes, actual constructor symbols/source identity and bounded
constructor disassembly were checked. Resource-profile core SHA256:
`ed11c9f274df533798af96ca86b546fa252c818431f2d8ab272e93452144e91e`.

On r182 boot `19e13ae5`, actual DT/platform inventory showed only the disabled
metadata anchor, no matching devices, overlays or prior CCCI modules. One
guarded load at uptime5588.17-5588.25s inserted RPS, CCMNI, AUXADC, real backend,
mapped provider, core with `private_prepare=0`, CCIF and DPMAIF. All returned0;
the parameter remained `N`, provider references4 and core references2. Both
optional CLDMA/SCP modules remain unloaded. The only new kernel records were
retained mappings/import with transport disabled; no new fault or failed unit.
USB and sensor services stayed active, and a completed 32 MiB transfer matched
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`.
These temporary modules remain loaded until reboot, not packaged/autoloaded.
No resource probe or private preparation occurred because targets are absent;
this closes actual default-off full-core load/dependency linkage, not SIM/calls.
The subsequent source correction removes an artificial pericfg prerequisite:
pinned B4.1 uses that register only in the <=6297 clock-off branch; MT6878's
6299 uses infracfg and its DT intentionally lacks the pericfg phandle. Missing
pericfg is now accepted for resource-only acquisition, while supplied malformed
relationships still fail. Native fixtures and both strict ARM64 profiles passed
[CI38277279422](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38277279422)
at `c317404`. Its artifact ZIP matches SHA256
`77ec2beb77c7b21c9b1896eac5173cf93cd13424746ceb032716cddeada3016a`;
all ten module hashes and every changed header/source match the reviewed overlay
`f561be18dbbc10e649a8aa834c68240e0d970a063c687261b25eac2bd666f727`.
New CCIF SHA256:
`5979b19c4387f86dc9881ed7b47d52521cb8b87b96cf53ceb01420536039a537`.
This is not the already loaded CCIF above; no module replacement or unload was
attempted. The artifact inspector now rejects a different header/overlay profile,
even when constructor source happens to match.
See [modem research](MODEM_SIM_EVIDENCE_PLAN.md).

**GPU.** Panthor, GPUEB ingress and source-backed power/reset candidates exist.
An earlier physical transform-only test authenticated 156,064 bytes, reported
UNKNOWN segment format and erased the buffer without starting GPUEB. Matching
LK copies 258,744 bytes from the same destination; the extra 102,680 bytes have
no proven initialization/firmware producer. Do not substitute guessed padding,
BSS or debug xfile bytes. Complete SRAM layout, persistent authenticated
handoff, power/reset/IRQ ownership and boot readiness remain.
The pinned B4.1 storage callbacks and selected ATF cipher callback now have
explicit byte-bound traces: block reads and cipher DMA retain the original
count, and cache maintenance supplies no RAM contents. The unresolved source
interval is payload-relative `[0x261a0, 0x3f2b8)`. Source checks also confirm
our U-Boot authentication/transform path does not decrypt twice. No GPU loader
behavior was changed or accelerated rendering claimed by this offline audit.
See [GPU research](GPU_BRINGUP.md) and [exact LK copy boundary](../patches/gpu/uboot-segments/README.md).

The ordinary-DRAM analysis consumer now validates the exact plain no-map node,
gap-free NOMAP resources and every retained PFN, then claims the entire allocation
exclusively before the signed-digest snapshot. Success retains claim/snapshot
until reboot; failures unwind. The r182 package carries that fix.
[CI 38236228444](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38236228444)
linked its GPL module against the exact original r181 source/config/exports:
SHA256 `b32aa610d34464f87bab19afe005d127af8cd690f8cfa26297edf80cf83d4095`.
That module is staged on the handset; the original is retained for rollback.
The unchanged initramfs contains no GPUEB reader. Complete startup-layout and
upload analysis remain pending; no SRAM upload or GPU start is implied.
The first physical capture on boot `39116740-88af-499a-993b-7e02682918ab`
succeeded using the separate retention profile from
[U-Boot CI 38234399917](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38234399917).
The exact-r181 consumer claimed the full ordinary-RAM allocation, retained
module reference1 and produced a 156064-byte root-only snapshot whose SHA256
matches the signed plaintext `9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7`.
USB/sensors/SSH stayed active. The private snapshot is not committed or uploaded.
Offline inspection identifies a RISC-V entry and a BSS-clear loop wholly inside
the signed span; it does not yet authorize LK's excess copy or a GPU start.
The [bounded startup audit](../patches/gpu/rv33-startup/README.md) passes 16
static tests against those exact private inputs. It verifies branch targets,
cold caller dominance with explicitly conditional callee returns, BSS/stack
fill bounds and the alternate full-SRAM reader. Vendor instructions remain
opaque; the source-tail producer and whole-startup memory coverage are unresolved.
The [LK tail audit](../patches/gpu/lk-tail/README.md) now passes 21 source tests
and adds a bounded allocator-name leaf contract to the pinned instruction census.
Its 37-instruction leaf writes at most the passed 127 bytes; staging aliasing
remains unresolved, with 73 unexpanded calls. It establishes the exact extra-copy bounds,
excludes cache maintenance as a zero-fill producer and resolves the mapper's
branch tables. Its strict closure check still refuses activation: transitive
writer/callee coverage is incomplete. No excess upload or zero-padding is enabled.

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
The new default-off [CAMISP DMA supplier](../patches/camera-camisp/SOURCE-CONTRACT.md)
connects logical CQI/WDMA ports to real larb13/14, common16/19/31 and the existing
display-common0/IOMMU providers. It adds source-backed clock/translation restore,
busy-preserving suspend and CAMSV runtime-PM ordering. Forty-two source-only
checks, the exact B4.1 topology trace and zero-fuzz isolated staging pass.
[CI 38225925800](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38225925800)
at `b41ea66b5a94de59f93bf1dd0d02e76ebd7baac1` passed actual ARM64 CAMISP,
SMI and IOMMU objects with KUnit enabled and disabled. No KUnit execution,
linked-driver test, DT activation, installation or frame capture occurred.
Forced supplier withdrawal and lifecycle remain unproven.
The new isolated [resource candidate](../patches/camera-camisp/resources/README.md)
adds native MRAW/CAM_VCORE gates and the disabled logical/physical CAMISP topology.
Pinned generation and 31 source tests pass. Actual ARM64 objects passed with
KUnit enabled and disabled in [CI 38236217805](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38236217805).
Native power/VMM ownership and frame capture remain unproven. No shipping DT
include or activation is added.
The [native power candidate](../patches/camera-camisp/power/README.md) adds actual
Linux CAM_MAIN/CAM_VCORE descriptors, checked sequential ACK transactions and
MT6878 VMM isolation operations. Thirteen static negative-test groups and pinned
source/patch checks pass; its object is now included in both ARM64 config
variants, with actual ARM64 compilation passed in CI38245658821. Shared VMM ownership/voltage policy and
complete callback wiring remain missing; no provider or board node is enabled.
The new [shared VMM supplier](../patches/camera-camisp/power/SHARED-SUPPLIER.md)
uses native genpd child accounting and an exclusive regulator handle, checks
isolation synchronously, preserves the first error and guards cached-ON child
transitions. Ten new source mutation groups and exact pinned source checks pass.
Its two source objects are now included once in the isolated ARM64 CI, with both
KUnit configs; CI38254821266 exposed a missing cross-directory header include
in the object harness before full CCCI linkage. The explicit compiler include
closure is corrected with a regression test. Both actual ARM64 KUnit variants
passed CI38255895881; supplier object SHA256 with KUnit disabled is
`54e9271c4630bb63db1a4a36a70b0d8f69469cb7588eb6af8778ee17df57f157`.
A complete provider/link, verified
voltage/rate policy, quiescent handoff and all-user migration are still required.
No camera bus access or capture is enabled by the object-only candidate.
The supplier now also owns the CAM_MAIN/CAM_VCORE control phase under its lock,
validates shared rail/isolation before entry and latches the original leaf
failure before genpd parent unwind. Sixteen supplier source tests pass. This
new addition passed fresh ARM64 compilation in both KUnit configurations of
CI38265540133 at 5e2c0b1. The manifest matches changed source SHA256
`23c4cdea6559703fffd09b8591d213b207d8a7fd1ac19afb5f435f99bb798f8b`.
Complete callback/provider wiring and physical power/frame checks remain;
the prior object hashes do not validate the changed code.

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
Our startup controller now rejects a failed/completed host worker before
registration and again before engine entry, preserving the dispatch failure and
completion acknowledgement for cleanup. Native disconnected-socket regression,
source rejection checks, Bionic ARM64 adapter and sealed-loader tests passed
[CI 38223225507](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38223225507)
at `9e68c3bd5d12d09c1629564fc468da6d8887aaea`. This closes an error-propagation
defect, not configuration/AGPS admission or a physical position fix.
The B4.1 AGPS endpoint producer now opens the actual filesystem/abstract Unix
datagram route, validates connected ownership and unwinds once on failure.
Five pinned-ELF source tests pass. Native sanitizer fixtures passed CI38236217805,
and the actual ARM64 Bionic closure including this producer passed
[CI 38237141944](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38237141944).
The legitimate receiver and complete startup configuration are still missing;
endpoint connection does not establish engine INIT or a position fix.
The [receiver-policy producer](../patches/gnss-navigation-audit/RECEIVER_POLICY_OWNER.md)
now acquires the two exact build properties and reuses the existing constructor
for five proven second-config bytes. Its actual native sanitizer fixture and
ARM64 Bionic link passed CI38245663571. The property
service is an Android/Bionic boundary, not a new mandatory pmOS daemon; complete
native policy inputs and startup configuration still need integration.
The next pure [native quiet-policy builder](../patches/gnss-navigation-audit/b41_receiver_inputs.md)
selects the proven host/NMEA path without an Android property service. Its
1,024-vector native sanitizer fixture and ARM64 Bionic target link passed the
prerequisite jobs in CI38248220709; its full images passed and r182 is installed. It
preserves all remaining receiver/stop/MPE/AGPS gates. A new
[native satellite configuration](../patches/gnss-navigation-audit/native-config-completion/TRACE.md)
implements the exact twelve-option AGPS mask and normal-start selector, replacing
three incorrect constant-zero receipts in the first block. Seven pinned binary
source checks pass; the 4,096-vector native sanitizer fixture, related constructor/
runtime/bundle regressions and ARM64 Bionic target link passed mandatory checks in
[CI38254829662](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38254829662).
The new [native reverse AGPS receiver](../patches/gnss-navigation-audit/native-agps-receiver/TRACE.md)
binds the exact abstract endpoint, authenticates peer credentials, bounds nine
source-proven message types and delivers through the same associated engine
image. Pre-INIT preparation parks the worker; dispatch requires the actual
engine record after successful INIT. Eight static tests pass (seven pinned);
the AArch64 Bionic link passed CI38265545233. Its host compiler caught an ignored
terminal acknowledgement write; error handling is corrected and fortified
native sanitizer CI was repeated successfully in
[CI38274644174](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38274644174)
at `140e85c`: all validation jobs passed, including 15 real-Linux-IPC receiver
fixtures under ASAN/UBSAN and the AArch64 Bionic link. The forward assistance consumer
and full session/control protocol remain missing; no receiver gate is cleared
and no GPS fix is claimed.
The [LNA startup trace](../patches/gnss-navigation-audit/lna-start-contract/TRACE.md)
closes the actual OEM producer and MT6878 consumer: failed ioctl16 retains its
initialized zero, which the engine serializes. This is not a validated GPIO or
proof of RF interpretation. The existing typed LNA-plan wrapper already
propagates this origin through runtime/bundle consumers; production functions
were not changed. Seven static groups and 1,108 window-byte mutation checks pass.
A dedicated native CI fixture now exercises the complete dataflow while retaining
other INIT gates and distinguishing OEM EFAULT from the port's ENODATA profile.
Real startup caller integration remains missing.
The common first constructor now keeps these three bytes unresolved until the
explicit producers run; runtime/bundle fixtures preserve that gate. These are
native configuration producers, not an AGPS receiver or successful INIT.
On r181 boot7d4b87cb the explicit GPS transport
probe returned0 at uptime427.85s and created gpsdl0/1 beside the retained SMEM
owner; USB/sensors/SSH remained active. Neither link was opened and no navigation
or position fix was attempted.
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
