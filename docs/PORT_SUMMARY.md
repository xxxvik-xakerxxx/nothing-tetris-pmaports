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
| U-Boot | Experimental `cd96ef3cb114b345ee773c89f3f0d43c2ae11417`, slot `lk_a` |
| U-Boot image SHA256 | `4e64ee87d9310e2120ad03852142356b8de49234ca212a0abc0e8c94764e9001` |
| Sensor backend | `iio-sensor-proxy-tetris 3.9-r2`, installed afterward from CI |
| Root filesystem | 104.5 GiB, expanded and writable |

The bounds/report fix is in U-Boot master `60cd9ade5b999732304f3b755c7dbe3d34307c13`.
[CI 38039293102](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38039293102)
passed native fault fixtures, ARM objects and full BROM/SCP image construction.
It validates LMB/DRAM bounds before refreshing DT length and preserves the
80-byte report ABI plus separate preflight/publication errors. The verified
3,306,096-byte image, SHA256
`8a8cde5d3fb4467090f3dd3793ed40d8b5cc3fef162b407c3feba1c33f7815f3`,
was written to `lk_a`; U-Boot then fully powered off the phone. After the
user's cold power-on and USB reconnect, the first readback matches both
`u-boot,version` and the installed image prefix hash. Board stage 15 reports
failure `-71` (`-EPROTO`), report-fetch `-22` (`-EINVAL`), invocation marker 1
and publication error 0. All loaded/hardware fields remain zero: the loaded
owner was never entered. This does not establish a physical BROM attempt.
The selector used `blk_get_by_device` on a BLK child instead of reading its
own descriptor; correction `c2e998bcbf5b53f7d1779522aa6462515f80721a` is
published in the user's [U-Boot master](https://github.com/xxxvik-xakerxxx/u-boot)
with a production-source regression fixture.
[CI 38066945059](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38066945059)
passed all native/ARM image gates. It was installed only in `lk_a`, fully
powered off and cold-started. Installed prefix hash and `u-boot,version` match;
the first readback still reports `-EPROTO`/`-EINVAL`, board stage 15 and no
loaded owner. USB, SCP and 24-entry/mask-31 sensor inventory recover.
Standard read-only UFS sysfs identifies the next rejection: boot LUs use
enable 1 with boot IDs 1/2, while the non-boot user LU legitimately uses
enable 2 (HPB). The matching Nothing source confirms this state. Our UFS
identity reader previously accepted only enable 1. Correction `7012ed17a2`
and actual-producer regression fixtures are in the user's U-Boot master;
[CI 38068197075](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38068197075)
passed all native/ARM image gates. The image was installed only in `lk_a`,
fully powered off and cold-started; version and installed prefix hash match.
The first report now passes storage/profile selection and reaches the loaded
owner: result `-16` (`-EBUSY`), report-fetch 0, loaded stage 2 (cold-OFF), board
stage 15 and publication error 0. The cold-OFF check refuses before firmware
reservation/copy or SMEM writes; bootstrap/hardware fields remain unobserved.
The current 80-byte record omits the loaded owner's sampled failing register.
Reporting-only correction `cd96ef3cb114b345ee773c89f3f0d43c2ae11417` is in
the user's U-Boot master; [CI 38069046288](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38069046288)
passed native/libfdt fault fixtures, actual ARM objects and the complete image.
Independent review found no P1/P2 issues. The verified 3,306,496-byte image was
installed only in `lk_a`; installed prefix hash and version match.
Its new independent BE fields preserve the v1 ABI and expose the already
sampled loaded-owner register without extra hardware access. The first report
still has loaded stage 2 / `-EBUSY`, report-fetch 0 and publication error 0;
valid loaded observation is address `0x1c001e00`, value `0x4200000d`.
`PWR_ON` is set, ACK30 is set and ACK31 is clear. This is not strict OFF and
does not establish authenticated firmware load or modem startup.
After `board:poweroff`, Preloader briefly appeared and pmOS returned; the
first report was preserved, but this boot is not claimed as a confirmed cold
start. A physical power-off with USB disconnected, ten-second wait and normal
power-on is pending. No Linux MMIO probe, guard bypass or modem retry occurred.
MD-specific ACK correction `5824646fa8cd4e138acb35da23da5c2da0c1ea14` passed
[CI 38073407645](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38073407645):
21 actual-helper sanitizer cases and complete ARM64 image construction.
The pinned Nothing `ee2be53` MD_OPS driver and matching audited LK poll ACK30
only; generic-domain ACK31 must not be required for MD completion. Loaded-owner
OFF and bootstrap ON/OFF now share that predicate. The observed ON/ACK30 value
still refuses; this is not a fix for inherited ON state or proof of BROM boot.
Image SHA256 `4943e596b022b471adf54cc54ba1678b773bde7d369d70dc0e440be4f21f5b84`
is verified and downloaded, not installed.
The shared MT6878-Mainline repository is not updated. No modem reset/retry was issued.

On the same boot, SCP reports `secure-handoff-prepared`, error zero; the hub
reports firmware ready, 24 entries and physical mask 31. All three sensor/SSH
services are active and no system units failed. First report and full kernel
journal were preserved before further changes. The user confirmed normal
display, touch, both rotations and automatic brightness for `60cd`; the
corresponding visual check for the latest loader remains pending. The rootfs remains
r179; r180 is downloaded but not installed, and runtime CCCI stays disabled.

New candidates, not hardware support: [SMEM transaction](../patches/modem/drafts/runtime-smem/README.md)
validates real NC/cache rows, builds CCCI/CCB tables and implements private WC
mapping with reverse rollback and retained published lifetime. The complete
source stack and independent review pass;
[CI 38068292750](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38068292750)
passed all 70 native cases at both 4 KiB and 64 KiB page geometry and compiled
66 real ARM64 objects, including the private SMEM transaction and argument
importer. Their required defined symbols and source review digest match.
This does not link a shipping driver or enable a production caller, physical
mapping, modem READY or SIM support.
[GNSS XML policy](../patches/gnss-navigation-audit/xml-policy-draft/XML_READ_PROFILE.md)
models the actual vendor/data-file arbitration and provides a bounded SET-text
serializer. [CI 38067494972](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38067494972)
passed native XML/ADC and SET sanitizer fixtures, 16 exact SET recipe/message
comparisons and 18 actual selector/scanner cases. All 12 policy code/dependency
hashes match published inputs. These are bounded ARM64 instruction oracles with
mocked libc/output, not Bionic execution, GPS engine initialization or a fix.
A separate sealed XML snapshot now extends the existing private loader root:
the fixed independently pinned 5,087-byte vendor XML is transferred as the thirteenth descriptor,
copied to `/vendor/etc/MNL_Config.xml`, then covered by the read-only remount.
Original 10-provider/12-FD executable admission remains unchanged. Actual Linux
sealing and native mount/copy/failure/reap cases are wired into the existing
`gnss-sealed-load.yml` CI after its unchanged Bionic load-only stage; execution
is pending. This does not admit INIT or provide missing CCCI/property/RX services.

Installation wrote `super`, `userdata` and the required loader to `lk_a`.
Stock `lk_b`, factory/NV and calibration partitions were preserved.
See [installation guide and disclaimer](INSTALL.md) before flashing.

The clean installation originally used validated loader `dcb20ce` (image
`71b474fe0c4cfbdfa33fb9ddef51b835b1bf2c367afc84f5ee4a6d85061a6967`),
which remains the recovery baseline. The earlier `d385921` checkpoint comes
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

The combined native PM/capture camera closure, packaged GPU analysis consumer,
modem owner objects and GPS Bionic/native adapters passed
[CI 38029177349](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38029177349):
all 33 ARM64 objects compiled. Camera failed-start KUnit objects were compiled,
not executed. This is not an installed image or proof of working hardware.
The default-off owned modem BROM profile linked as a complete U-Boot image in
[CI 38028430903](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38028430903)
at `24e7c183c4`; its subsequent flash and pending checks are recorded above.
Its runtime CCCI drivers stay disabled. Actual UFS/storage, atomic handoff
publication and owned-loader fault checks passed
[CI 38029702595](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38029702595).
Hardware providers in these fixtures are mocked; they are not physical BROM
completion or executing-preloader attestation.
The subsequent native RAW/meta video owner and sole-parent GPU reset provider
also passed
[CI 38032210668](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38032210668):
all 37 actual ARM64 objects plus both video KUnit configurations compiled.
No kernel fixture execution, runtime registration, physical frame or GPU
acceleration is implied. The matching full kernel/image build failed in
[CI 38030432132](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38030432132)
after compiling the kernel: the overlay staging script omitted the SensorProxy
D-Bus `.service` source. Staging now includes it and an offline test compares
every local package source with the staged copy before a full build. No install
image was produced; the new video/reset sources remain isolated.
The corrected full install-image build is
[CI 38038376683](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38038376683);
it passed all jobs at `a3268afc0a3c41a13ff0a5e69de01faf58a78c47` and produced
the r180 installation archive, SHA256
`88d70c7f0ecc5361358fde8097959e3e204046aea9924261111be808c78cd93a`.
The archive and all three image hashes were independently verified; all 7,678
root sparse chunks passed size/CRC/extent checks (2,783,969,280 expanded bytes).
Installation remains pending; the phone still uses r179. This
image includes SensorProxy r2 but retains baseline loader `dcb20ce`; it must not
silently replace the separately installed BROM-only diagnostic loader.
Additional source-only candidates do not enable hardware in that image.

The current combined candidate check is
[CI 38050988309](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38050988309),
fully passed at `d6c3a6b7b445bdd555c712dfe82cbc6e23b63b26`.
Downloaded manifests independently confirm 47 real camera/GPU/owner ARM64
objects and 64 real ECCCI/CCMNI/util objects. Video, CAM_MAIN and all four joint
camera objects, both repeat-capture objects and their native/platform consumers
also compile with KUnit disabled. Native modem callbacks, GPU
power fault fixtures, GNSS mount/control-launch/timeout/reap fixtures and
API28 Bionic builds passed. This is object/native-fixture evidence, not module
linkage, kernel KUnit execution or physical subsystem support.
This includes the camera selected-clock/shared-VCORE and lock/lifetime
corrections, plus genuine GNSS mid-copy fault fixtures. Subsequent source
changes require their own check; no physical subsystem is enabled by this run.

- **Modem:** authenticated firmware/layout and CCIF/DPMAIF groundwork exist.
  Actual boot-LUN/GFH identity, private authenticated snapshot metadata and
  the bounded boot-stage EMI/remap/power/BROM caller are now connected in the
  opt-in U-Boot profile. Physical BROM completion and runtime CCCI handoff
  remain unverified before SIM detection, network registration,
  calls, SMS or data can work. File signatures are not RAM attestation or READY.
  Isolated [runtime preparation](../patches/modem/drafts/runtime-prepare/README.md)
  now checks FSM/all-port preparation and separates private resource-only probe
  from explicit registration after a real device bind. Physical monitor ioctls
  remain denied even after registration. Failed publication retains bound devres
  rather than just `md_hw`. Both overlays apply to the complete packaged vendor
  adaptation/owner stack; strict native fault fixtures and static checks passed
  [CI 38038500256](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38038500256).
  The [actual runtime-object helper](../patches/modem/drafts/runtime-object-ci/README.md)
  stages all 27 shipping vendor adaptations before owner/port/prepare overlays
  and compiles 64 real ECCCI/CCMNI/util translation units with production
  Kbuild/includes. Actual complete-stack ARM64 compilation passed the current
  combined check; operational linkage and hardware startup remain pending.
  The new [metadata importer](../patches/modem/drafts/runtime-metadata/README.md)
  validates the real U-Boot tag chain, full memory layouts and retained no-map
  reservations before private argument publication. Its isolated
  `modem-metadata.yml` workflow tests public-stock producer/import round trips
  under ASan/UBSan and compiles the same 64 real driver objects with that overlay.
  Both stages passed [CI 38052285012](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38052285012)
  at `190ea15`: 59 producer/import cases and all 64 real ARM64 objects, including
  the actual metadata import/validation symbols. It maps only the admitted AP tag buffer, not modem firmware or SMEM,
  and neither grants protected-memory access nor enables modem registration.
  They are not packaged, automatically called or enabled on the
  phone; physical start, callback/DMA drain and forced removal remain unresolved.
  See [modem research](MODEM_SIM_EVIDENCE_PLAN.md).
- **GPU:** Panthor and GPUEB groundwork exists. Transform-only firmware inspection
  succeeded on the preceding loader, then erased the buffer without starting
  GPUEB. The verified 156,064-byte interval does not explain LK's 258,744-byte
  SRAM copy. Authenticated upload layout, power/IRQ ownership and firmware boot
  remain unresolved. A new isolated bound-parent transaction acquires native
  MFG0 runtime PM before registering the existing SRAM/reset owner. Power errors
  retain lifetime references but release the synchronous device mutex. Its two
  real ARM64 objects and native fault fixture are now CI inputs, not shipping
  activation. See [GPU research](GPU_BRINGUP.md).
- **Camera:** IMX882 V4L2 tables, SENINF and CAMSV/CQ candidates exist. Native CQ
  generation is available; power/reset, sensor-to-receiver stream, IRQ/DMA stop
  and a real capture controller remain. No Android HAL or proprietary composer
  is running. The new isolated one-shot first-frame path performs actual sensor
  OFF/IRQ drain/receiver disconnect, joint SMI/CAM_MAIN reset, then the existing
  calibrated ON/CQ/DMA path. Its four objects and staged sensor callback gate
  passed the combined 45-object CI check. The new isolated repeated-frame
  cycle keeps IRQ/MMIO/queue ownership stable, waits for actual DONE-triggered
  stop work, verifies DMA/PHY OFF, then allocates fresh CQ/transactions.
  Premature stop before DONE is rejected; timeout remains latched and blocks
  rearm. Its two objects and rebuilt consumers passed the 47-object CI check.
  Repeated capture and a physical frame remain unproven.
  See [camera research](CAMERA_BRINGUP.md).
- **GNSS:** matching stock engine/config and transport contracts are retained.
  The load-only adapter now stages ten pinned real providers plus the original
  probe/engine as sealed descriptors, with a private read-only loader root.
  The dedicated native parent and actual sealed Bionic load passed on ARM64 in
  [CI 38050310221](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38050310221)
  at `43b4a2d`. Downloaded logs confirm real control denials, `LOAD_OK`, terminal
  reap with status0 and empty containment. Parent log limits do not truncate
  provider copying, and the child restores its signal mask before setup.
  General validation/native fixtures/API28 builds also passed
  [CI 38050314277](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38050314277).
  Engine initialization and a physical fix remain separate gates.
  [Stock CI 38048111345](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38048111345)
  passed complete pinned system/APEX extraction and real ten-provider sealed
  closure checks. Downloaded provider bytes match the independent pins.
  The bounded copy reads sealed FDs into a private tmpfs and remounts the snapshot
  read-only before execution. Native isolation runs independently; full install
  images still require all jobs to pass. The ARM64 load-only service uses
  destructive CI-only failure containment, never runtime quarantine or a
  hardware-readiness claim.
  Actual engine init/run, host services, exclusive RX ownership and bounded
  shutdown remain incomplete. Library loading is not a fix.
  The [XML/ADC backend candidate](../patches/gnss-navigation-audit/XML_ADC_CI.md)
  preflights the complete stock XML global configuration before committing
  writes and sends sealed ADC snapshots as bounded atomic diagnostic packets.
  The isolated `gnss-xml-adc.yml` workflow executes only our native sanitizer
  fixtures against pinned stock bytes. Native sanitizer execution passed
  [CI 38052531292](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38052531292)
  at `0d7458d` (16 XML feature/profile executions plus the ADC fixture). Genuine
  Bionic libxml2/OpenSSL dependency builds, XML reader/SET ordering and actual
  ADC endpoint ownership remain required. It never calls vendor INIT or claims
  satellite acquisition.
  The separate [real Bionic dependency build](../patches/gnss-navigation-audit/BIONIC_XML_DEPS.md)
  now builds pinned official XML/crypto sources with the same NDK/API28 ARM64
  compiler, checks their real exports/dependency closure and links both full
  fixtures. [CI 38065279869](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38065279869)
  passed the real dependency builds and both full target links at `7963a02`.
  Target execution remains untested. It does not alter the sealed probe or
  insert unreviewed libraries into the shipping provider chain. The subsequent
  one-snapshot batch XML optimization passed native
  [CI 38065800131](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38065800131)
  and full target linkage
  [CI 38065806550](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38065806550)
  at `d86ce98`. There is no phone performance measurement or target execution.
  The OEM startup initializer clears the globals before reading XML; pre-init
  sidecar writes are not a runtime configuration solution. Source-backed reader
  ordering and real endpoint ownership remain unresolved.
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
ownership; its ARM64 integration passed, while hardware startup remains pending.

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

The native receiver controller now retains the real loader association, gpsdl
descriptors, callback/output worker and supervised stop procedure together.
Report/restart/prohibition events wake a controller instead of invoking Android
FM or position publication. Stop requires actual native joins and parent reap;
a timeout is not successful teardown. Native sanitizer tests and the complete
AArch64 Bionic link passed
[CI 38025448174](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38025448174)
at `788d8fc`. First/second configuration, calibration and slot6 assistance remain
unresolved, so no engine initialization was attempted. See
[native resource integration](../patches/gnss-navigation-audit/NATIVE_ARGUMENTS_INTEGRATION.md).

The modem boot-stage candidate now implements concrete EMI/remap/lock,
source-derived NS BL33 clock/isolation/power/bus ordering and four-word BROM
completion. First-error reporting and finite stock-order failure shutdown are
separate. The complete EMI producer derives active rows32..43 from signed
metadata and distinct firmware/NC/cache/SIB allocations, including real slot40
padding and its exact preset policy. Full reservations cannot overlap.
[CI 38025322548](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38025322548)
passed the actual signed stock input, 37 bootstrap and 20 EMI sanitizer cases.
The initial EMI fixture failure was a wrong CONSYS field offset, corrected
without weakening the check. [U-Boot CI 38025178952](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38025178952)
passed actual ARM64 bootstrap/secure/EMI sources and the full image at `a0f6855512`.
The linked boot candidate now replaces the old EMI phase, derives metadata
before authenticated-source release, retains separate aligned NC/cache banks,
and verifies the stock remap readbacks before power/BROM completion.
[CI 38026075076](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38026075076)
passed 41 integrated-bootstrap and 17 allocation-lifetime sanitizer cases,
alongside the signed-input, 37 earlier bootstrap and 20 EMI cases. Integration
into the actual loader is now present in `24e7c183c4`, including the opt-in
one-attempt board caller. Runtime CCCI publication stays disabled in that
diagnostic profile; physical completion and SIM/calls remain unverified. See
[boot transaction](../patches/modem/drafts/boot-stage/README.md).

The camera platform consumer adds four source-derived IRQ handlers, native
media-pipeline ownership, runtime-PM/clock references and controller-context
stop. IRQ drain occurs outside the vb2 mutex. The source now includes native
SMI common31 reset leases, calibration from nvmem/held CSI clock, restricted
RAW/PDAF SENINF/CAMMUX routing and TG/VF shutdown. Combined native faults and
26 actual ARM64 objects passed
[CI 38026834337](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38026834337),
after fixing the route's PHY argument order; this is not hardware capture evidence.
MAC/PHY IRQ, TSREC, allocation and prepared-format lifetime integration remain
open; no video node is activated. The PHY shutdown helper now retains its
configured state after failed shutdown and refuses replay. See
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
