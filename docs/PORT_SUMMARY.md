# Port summary, 2026-10-09

## Combined candidate: r177

Follow-on r179 packages the external-LNA control restriction after r178 metadata
and corrects the disabled camera fixture's context after GNSS pin removal.
The standalone GNSS query-plan distinguishes a successful query from the pinned
OEM untouched-zero error branch; the latter never becomes a successful ioctl or
physical wiring proof. Navigation startup remains blocked by missing config,
host-service and stop contracts. Native control/query fixtures are CI-only.

The follow-on transport suite validates actual CCIF/DPMAIF start functions,
GPUEB mailbox request/response ownership and firmware ingress, and CAMSV paired
DMA/CQ/composer completion. These source candidates are not in the kernel
package source list or shipping linkage. Native fixtures are not AArch64 kernel
compilation or end-user operation. Secure modem exclusivity, GPUEB transform/boot,
matching camera composer and DONE acknowledgment remain runtime blockers.
The manually dispatched stock-asset workflow extracts only named generic vendor
files from the [pinned B4.1 mirror](https://github.com/spike0en/nothing_archive/releases/tag/Tetris_B4.1-260415-1709).
It verifies both archive hashes and an independently pinned libMNL hash; this is
not OEM signature verification. No Android service or firmware is executed and
no handset NV/calibration is uploaded. The goal is the missing GPS XML, GPU CSF
image and matching camera composer inputs, not reinstalling Android.
Extraction [37941089972](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37941089972)
completed: all 15 selected files passed size/hash checks, including the independent
libMNL pin. The new XML decoder, owned AGPS datagram service, control notification
and typed second-config constructor are source candidates, not navigation support.
Matching libccd instructions now anchor a native bounded CQ encoder and its eight
frame-cookie commands; the full CAMSV frame recipe and hardware completion remain
incomplete. CSF format checks accept the actual B4.1 image, but GPU_ID, power,
clock/voltage ownership and runtime firmware startup remain unverified.

Follow-on r178 is on `main`; combined native validation
[37934849844](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37934849844)
at `063734b` passed, including source checks and ASan/UBSan fault fixtures:
dedicated CCCI first-start/runtime-PM and typed secure-call adapter, GPUEB-owned
whole-GPU power transaction, calibrated SENINF PHY/MAC register program,
and read-only GNSS LNA metadata. Hardware ownership/session validators and
transport/DMA integration remain incomplete; none is automatic hardware support.
All three new kernel backends are selected for compilation in an isolated output tree only;
shipping config and module packaging explicitly reject their activation.
Native fixture success does not establish kernel API compatibility or hardware
operation. The separate `kernel_smoke_only` workflow compiles the packaged
candidate AArch64 translation units using the image's Alpine/LLVM 21 toolchain,
after checksum verification and the ordered kernel patch stack. Historical
patches use package-default application rules; the new backends require zero
fuzz. Patch diagnostics remain in the CI log. It retains the
isolated config and manifest, never links/install modules or changes shipping DT.
Its independent concurrency group does not cancel a full image build.
The cheap validation job now applies all 104 packaged kernel patches to
disposable pinned source files before compilation. This catches cross-subsystem
context conflicts, including the camera fixture after GNSS pin removal.

The GNSS DT no longer supplies unproven GPIO143/144 LNA states. Pinned B4.1
sources and the cached stock base DT plus each of three stock DTBO choices
provide no matching GPS wiring records. A successful metadata query is not
physical wiring proof; without owned records it must fail, not return a default.
See [stock DT audit](../patches/gnss-navigation-audit/STOCK_LNA_DT_PROVENANCE.md).

Prepared together, not yet installed or advertised as working:

- Modem: dedicated power-domain sequencing with checked bus protection,
  isolation after shutdown acknowledgement, inherited-state rejection and
  first-error latching. No reset release or ready CCCI handoff is enabled.
  A separate opt-in five-register diagnostic exits before genpd registration
  and any power transition. Its shipping fixture remains unincluded.
- Camera: native IMX882 V4L2 stream candidate with exact B4.1 init/mode tables,
  exposure/gain/frame timing controls and checked start/stop. Runtime DT stays
  disabled. SENINF resource/media graph and partial analog/mux transactions
  are prepared; calibrated receiver register programming passes native fault
  fixtures, but capture DMA/composer ownership and runtime validation are missing.
- GPU: disabled VGPU/VSRAM inventory, disabled-child filtering and rejection
  of phase masks that reach unowned rails. A separately selected read-only
  diagnostic DT enables only the VGPU observer. Panthor remains inactive.
- GNSS: typed host configuration and callbacks with bounded copied-output
  queues. Missing engine/transport contracts still prevent navigation startup.
  AArch64 standalone first-config/query fixtures passed on the phone in a
  verified hardware-denying sandbox; these used synthetic inputs, not fixes.

The r177 CI [37930775277](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37930775277)
at `0f60b775fa3848057579296dddac5027f4c590ab` passed native validation and
AArch64 Bionic fixture builds and compiled the full kernel/install images.
Diagnostic repackaging then rejected compiler-renumbered DT references, so no
install image artifact was uploaded. The checker now compares typed references
by node path and unchanged arguments, preserving exact non-reference properties;
36 fault/delta tests pass. CI retains compiled diagnostic DTBs and publishes
verified normal install images even if the separate diagnostic stage fails;
the run still fails overall, and a failed diagnostic must never be flashed.
Combined transport/native validation
[37943848089](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37943848089)
passed for CCCI, GPUEB and CAMSV/composer. Isolated kernel-object compilation
stopped at a missing Bash build-tool dependency before compiling candidates;
the dependency is now explicit. No candidate AArch64 API compatibility is claimed.
Earlier fixture path, patch hunk count and isolated Media parent-config errors
were repaired without suppressing warnings or sanitizers. No r177 image has
been flashed. Native fault tests use Ubuntu with ASan/UBSan; the pmOS image
build stays on Alpine. The install manifest records the actually tested
U-Boot `dcb20ce71f`, not the older loader pin. Local checks do not replace
hardware qualification: SIM/calls, GPS fixes, accelerated rendering and
camera capture are still not available.

## Latest installed checkpoint: r175

Latest loader experiment: U-Boot `dcb20ce71f`, successful
[CI 37915946655](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37915946655),
is flashed only to `lk_a` for secure modem EMI observation. Warm and
user-confirmed cold boot both return complete, identical successful readbacks;
core/shared permissions match the independent pinned policy. On cold boot,
USB/SSH, sensors, display/touch, rotation and automatic brightness passed.
This does not release modem reset or establish SIM/calls. See
[experiment and first failure](MODEM_SIM_EVIDENCE_PLAN.md#secure-emi-observation-experiment).

Clean CI installation, 2026-10-09: full image run
[37894315052](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37894315052)
at `ba605b03d8bff2b0db15cc03198948f0f16f756e` passed. Archive digest, all
three image hashes and all 7,713 sparse chunks were verified before writing
only `super` and `userdata`. Factory/NV/calibration and both LK slots were
retained during this image installation.

First boot `aa136f81-1539-4455-a2f9-7eed5ffacc91` reports kernel
`7.2.1-r175`, Linux `6.18.0 #176`, device package `8-r17`, root 104.5 GiB.
Installed FIT matches CI. USB/SSH and a hash-verified 32 MiB transfer passed
after unlocking the Mac and reconnecting USB; before that, USB enumerated
but macOS registered no BSD network interface. No failed systemd units or
critical kernel crash signature was found; vendor warnings remain.
DSI is connected; the user confirmed normal display and touch on this image.

Retained U-Boot code `56de656803` from CI `37902382709` again reports
`service-initialization`, zero error, `ram-loaded-not-started`. Separate
512 MiB firmware and 39488 KiB service reservations are present. This is
authenticated modem RAM preparation, not modem execution or SIM/calls.
Sensor startup was disabled on the fresh image; previous opt-in was restored
for the next cold boot without starting/reloading modules on this warm boot.
User-confirmed cold power-on produced boot
`436b22a7-5886-4e19-b692-8ccd6e92b81d`: sensor firmware ready, 24 inventory
entries and physical mask 31 at 17.114 seconds, SensorProxy started at
17.488 seconds. All three D-Bus classes are present; a bounded 30-second
capture received real 134-135 lux light updates. No orientation/proximity
transition or brightness change was captured; desktop confirmation is pending.
USB/SSH, installed FIT hash and another 32 MiB transfer passed, with no
failed units or critical kernel crash signature. Modem RAM preparation again
reports zero error, not execution. This is one cold-start pass after opt-in;
repeat, lifecycle and portability checks remain open. GPU render nodes and camera
video/media nodes remain absent; GNSS navigation is not established.

Image SHA256:

- Boot: `af81b9bc5692d94d344ba6cd8de03b600754c912d0695901317625b3bce178ad`.
- Sparse root: `293d81906a30dc28c4d410fc8a0757e63216ad02537cfe787668f9e8e000322e`.
- FIT: `8e4bf94f2705a7630f30acd5cf817e7fd5da7bdc0d4c47896d1b2569e6d24295`.

Private evidence: `local/ci-run-37894315052/validation/` in the parent workspace.

## Previous installed checkpoint: r173

Live progress, 2026-10-09: the pinned B4.1 GNSS library loaded successfully
through Bionic on r173 in a read-only, unprivileged sandbox with devices,
ioctl and networking denied. CI `37898372984` passed, all staged hashes
matched, control returned zero failures and the single load returned
`LOAD_OK`, exit zero, 1.1 MiB peak memory. USB/SSH and the cold boot ID were
unchanged. This establishes loadability, not navigation or a GPS fix; see
[the runtime evidence](GNSS_USERSPACE_BRIDGE_AUDIT.md).

U-Boot `c9a2ee3e67f2ced75e3d7d2e9d8bbaa95e1dd790`, explicit SCP plus
RAM-only modem-load profile from successful
[CI 37896667322](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37896667322),
was flashed to `lk_a` after archive/image/header verification. Stock `lk_b`
was verified unchanged before the write and was not flashed. Reboot lost
the fastboot status response; the phone subsequently enumerated its pmOS
USB NCM interfaces. macOS initially did not register a BSD network interface.
Physical USB reconnect restored the network interface and SSH, boot
`efce2cb0-703d-490b-8dcb-ab527c42a8cd`, unchanged r173 kernel/rootfs.
The modem result is `service-layout`, `-ENOSPC`, `failed-not-started`:
authenticated ROM/DSP placement completed but service banks did not fit the
single window. Bounded container/header reads confirmed 480 MiB MD memory,
CONSYS `0xd80000`, NV cache `0x163780`, UDC disabled; offsets were derived
from the actual container, not copied from the OTA archive. U-Boot `56de656803`
allocates services separately without expanding the fixed modem-remap window.
CI `37902382709` passed; the verified image was flashed only to `lk_a` and
readback matched CI. On boot `d6ac0fdc-6f2e-47e5-b5c1-54c1fd8266cd`, the
result is `service-initialization`, zero error, `ram-loaded-not-started`.
DT contains the 512 MiB firmware reservation and separate `0x2690000`-byte
service reservation. A hash-verified 32 MiB USB transfer passed. No modem
execution is enabled; cold-start, protection/remap and CCCI handoff remain open.
Display connector remains connected; no critical kernel-fault signature was
found. The sensor service rejected the warm SCP handoff, requiring cold boot.
The previous SCP-enabled `fef0154b` CI image remains available for rollback.

Candidate status, 2026-10-09: r174 full kernel/image CI
[37886195992](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37886195992)
passed but was not installed. The combined r175 GPU/camera power-provider
bundle (`0110`, `0111`) and GNSS host-boundary checks passed native CI
[37894001985](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37894001985)
at `a5d72a1`: 16,384 mode/fault cases, 512 rail/reference cases, 32 shutdown
fault combinations and 262 pinned GNSS vectors, including negative mutants.
Full r175 image CI
[37894315052](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37894315052)
passed at `ba605b03d8bff2b0db15cc03198948f0f16f756e`; installation and first-boot
verification are recorded above. These changes do not enable
GPU/cameras, produce a GNSS fix or establish modem/SIM/calls. Installed state
below records the r173 rootfs/kernel checkpoint before the loader update above.

CI [37797116235](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37797116235),
source `37dc3d03734c2919b8d18c75ac1cf37b94b18694`, passed and was
clean-installed to `super` and `userdata`. The archive matched GitHub's
SHA256 digest; all three image hashes and all 7,661 sparse chunks passed
verification. Expanded root image size is 2,783,969,280 bytes.

First boot `1f027cdd-380e-4347-b8a8-149a79cf295c` reports
`7.2.1-r173`, Linux `6.18.0 #174`. USB/SSH, a hash-verified 32 MiB transfer,
root expansion to 104.5 GiB and the installed FIT hash passed. No systemd
units failed; no panic, Oops, lockup, refcount or use-after-free signature
was found in the captured kernel journal. Existing vendor warnings remain.
DSI is connected/enabled and touchscreen input is registered. After the
cold boot below, the user confirmed normal display, touch, rotation in both
directions and automatic brightness when covering/uncovering the sensor.

The installed SCP-enabled U-Boot `fef0154b0404210799a6851ac2c07dcbc9e9c736`
was retained. Neither LK slot nor factory/calibration partitions was written.
Sensor startup was disabled on the fresh image; its previous opt-in was
restored for the next cold boot without loading modules on this warm boot.

After user-confirmed physical power-on, cold boot
`a507d5d4-c1d4-4acf-9bba-c4724a6e1064` automatically reported firmware ready,
24 inventory entries and physical mask 31 at 17.134 seconds. SensorProxy
started at 17.527 seconds and advertised accelerometer, light and proximity.
A bounded 20-second root-authorized D-Bus capture received real light updates
of 4-5 lux. Orientation/proximity transitions and desktop brightness changes
were not exercised in this capture. No systemd units failed, no critical
kernel fault signature appeared in the captured journal, and a fresh
hash-verified 32 MiB USB transfer passed. This is one cold-start pass after
explicit opt-in, not zero-configuration startup or completed lifecycle testing.
The subsequent user check confirmed desktop rotation and automatic brightness;
proximity blanking during calls was not retested on this image.

r173 fixes the vendor CCCI shared-memory mapping span, including the real
`0x15fc0` cache padding gap, and rejects negative region IDs before indexing.
The actual patched vendor functions passed CI regression tests. This does
not enable modem DT, install/autoload the modem evidence modules or establish
SIM/calls. GNSS navigation, GPU acceleration and cameras remain unverified.

Image SHA256:

- Boot: `229e3817796e5eaf1f81ce1cd40a61121394e2ba2dafd50fc48f681686f2679f`.
- Sparse root: `81099c2756489746b6fb315568d1f17c331bbf719e1bc53935c74e7956ae589e`.
- FIT: `546ff8935cfee651f5a1dbabdf363d3baa5079519a323618fa95a30d6c582950`.

Private local evidence: `local/ci-run-37797116235/validation/` in the parent
workspace. Lifecycle and other-unit testing remain open.

## Previous installed checkpoint: r172

CI [37753866853](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37753866853),
attempt 2, source `17fbac0fbef455c1feb33526cf12eceee1e96e81`, passed and
was clean-installed to `super` and `userdata` on 2026-10-08. The archive
SHA256 matched GitHub's API digest; all image hashes and the complete sparse
structure passed verification. Expanded root image size was 2,783,969,280
bytes. Installed kernel is `7.2.1-r172`, Linux `6.18.0 #173`.

The first boot `ad734d5d-d70c-4fd6-9e5f-403a46db5abc` passed USB/SSH,
32 MiB USB transfer, root expansion to 104.5 GiB and installed FIT hash
verification. No systemd units were failed. DSI was connected/enabled;
the user confirmed normal display and touch. Wi-Fi and Bluetooth devices
enumerated; association and pairing were not tested. No critical kernel
fault was found in the captured log; vendor Wi-Fi scan warnings remain.
U-Boot `fef0154b0404210799a6851ac2c07dcbc9e9c736` in slot A was retained,
with slot B and factory/calibration partitions untouched. Fastboot lost USB
status during the reboot command; the subsequent successful Linux boot was
verified separately.

Sensor startup was disabled on the fresh image. Its previous opt-in was
restored for the next cold boot without loading modules on this warm boot.
After user-confirmed poweroff, 10 seconds off and physical power-on, boot
`4377a6ee-a2a3-48f5-bd41-f03dd9b12006` automatically reported firmware ready,
24 inventory entries and physical mask 31 at 17.187 seconds. SensorProxy
started at 17.571 seconds and advertised accelerometer, light and proximity.
A bounded root-authorized D-Bus capture received real light updates of
169-172 lux; the remote unprivileged claim was correctly denied by PolicyKit.
No orientation/proximity transition was exercised in this capture. No systemd
units failed, no critical kernel fault appeared in the captured log, and
another 32 MiB USB transfer passed. This is one cold-start pass after opt-in,
not zero-configuration startup or completed lifecycle testing.

The complete nine-module modem build/link gate now passes, but those modules
remain evidence artifacts, not installed/autoloaded runtime support. Modem
DT stays disabled. SIM/calls, GNSS navigation, GPU acceleration and cameras
are not established by this installation.

Image SHA256:

- Boot: `e5046b8c484b379e88e88cd2eb3b3a145a41ed9acb7e6b30bdcfb1b90b78f68d`.
- Sparse root: `d123990135f7a4543d278afcf406c15a7a7fec05743624f97e3104d96b90b0ff`.
- FIT: `cc05868c69d2595b8e89b79cb757a1cdf478d87a5d02e3861040ece037cbd7a3`.

Private local evidence: `local/ci-run-37753866853/validation/` in the parent
workspace. The r168 checkpoints below are historical baselines, superseded
by this installed version; subsystem research boundaries still apply.

## Previous r168 Baseline

- pmOS: `xxxvik-xakerxxx/nothing-tetris-pmaports`, branch `main`, integrated
  source `6576019` (before this documentation update).
- U-Boot: `xxxvik-xakerxxx/u-boot`, branch `master`, source
  `e0399e8a9d8552aebdb6ce9869dd7352d5506088` (temporary modem staging
  lifetime; CI `37655372236` passed, not installed). Installed loader remains
  `fef0154b04`: first warm reservation and one cold automatic sensor-start
  check passed; repeated cold starts, lifecycle and visual regression pending.
- Installed clean kernel: `7.2.1-r168`, Linux `6.18.0 #169`, CI
  `37614381947`, source `6576019bea1d31e7ff15e2c28870329a7bce6be4`.
- Installed loader: `fef0154b0404210799a6851ac2c07dcbc9e9c736`, explicit
  SCP + RAM-only modem diagnostic CI `37643162425`, slot A only; stock slot B
  retained. Previous sensor-validated loader `1d4cb6496b`, CI `37609012691`,
  is backed up locally for rollback. Image readback and first warm/cold RAM
  reservation checks passed. One cold automatic sensor startup passed with
  live light readings; greeter sensor behavior remains unresolved.
  Display/touch were confirmed on r168 before this loader change.
- The complete main CI image was clean-installed on 2026-10-07 to `super`
  and `userdata`; device package `8-r17` and SensorProxy `3.9-r1` came from
  the image, with no runtime implementation replacement. Root expanded to
  104.5 GiB. Display/touch were visually confirmed and a 32 MiB USB transfer
  passed. Sensor startup was disabled in the fresh image; its opt-in was
  restored without starting modules. One subsequent r168 cold start passed,
  including SensorProxy light readings and the 32 MiB USB transfer.
- On the previous r167 installation, all five physical sensor classes and SensorProxy light updates passed
  after one supervised service start and a subsequent automatic cold start
  after user-confirmed 10-second poweroff. Startup remains opt-in. See the exact
  [clean-install evidence](SENSOR_INTEGRATION_PATCH.md#clean-ci-installation-2026-10-07).
- CI at the previous r167 checkpoint: pmOS sensor package `35746976387` passed; full image
  `35746976417` passed (rechecked and installed 2026-10-07).
  U-Boot ordinary `35747798350` and explicit SCP
  profile `35747862279` both passed. At that clean-install checkpoint the
  existing loader was retained. The later slot-A update is recorded below;
  factory/calibration partitions remain unchanged.

## Hardware summary

Before the r168 clean install, SensorProxy `3.9-r1` from CI `37589615272`
was live-installed, with rotation and automatic brightness confirmed again.
It skips duplicate scalar callbacks, not hardware sampling or validation.
No measured battery/FPS gain is claimed. Kernel r168 is now installed from
successful CI `37614381947`. Run `37600980145`, source `fdf549c`, built the kernel package
but failed before image creation: abuild removed the build tree before the
evidence collector ran. CI now appends a package-local `CLEANUP=""` override
to the mirrored kernel APKBUILD, retaining results for the collector without
changing the shipped kernel. Twelve collector tests pass, including cleanup
reproduction and retention. The full rerun passed, including kernel evidence
upload and install-image creation. The preceding run
`37592121416` built the kernel package, then failed in our evidence collector
while recursively entering a chroot's mounted `/proc`. Discovery now visits
only `chroot_*/home/pmos/build/src/*/Module.symvers`, with mounted-tree exclusion
and ambiguous-kernel rejection tested. The candidate includes fixes for active GPU-rail
voltage readback and GNSS clock-read error propagation, not GPU acceleration
or navigation enablement. The first r168 validation run failed on an obsolete
literal blocker-string assertion; the assertion was updated without removing
the runtime activation boundary.
The new separate kernel-export artifact is for dependency analysis, not
runtime enablement. Current live modem handoff remains `no-fdt`; there is
no modem, render node or camera node. GNSS transport is inactive.

### r168 clean installation

Both `super` and `userdata` writes completed successfully. The complete
download matched GitHub's archive digest; all three image checksums passed.
Boot `0c1ef926-a8c5-4b90-9340-8e43981ecbcf` reports r168, active USB/SSH,
`wlan0`, `hci0`, connected/enabled DSI and the touchscreen input device.
The user confirmed normal display and touch. No system units were failed.
The installed `/boot/boot_image.itb` hash matches the CI artifact. The 32 MiB
USB transfer passed. These checks do not establish Wi-Fi association,
Bluetooth pairing, GPU acceleration, modem operation, GNSS fixes or cameras.

SHA256:

- Boot partition image: `a102a9ace52760ebbae866012ad642e061a7711eed54a69aea14ac422637ae4b`.
- Sparse root image: `cf61bd6adca5f086a032d2339a354ad4c99283bc1020f7ad34798b51582abc16`.
- FIT: `73a565bd4bd16b3c59afd5d45e591611679f5313e5a8b48b6dd82a02ec9e0a28`.

The packaged sensor service was disabled on the fresh rootfs. It was enabled
for the next boot, without a module load/reload on this warm boot, then the
phone was powered off. After the user's full poweroff/on, cold boot
`9cb06d3b-0b5c-4b65-ba95-e0763d448647` automatically reported firmware ready,
24 inventory entries and physical mask 31 at 16.760 seconds. SensorProxy
started at 17.128 seconds. Its standard D-Bus interface advertised accelerometer,
ambient light and proximity; a bounded 20-second capture received real light
updates (52-55 lux). Rotation and proximity transitions were not observed in
that capture. The user subsequently confirmed both desktop autorotation and
automatic brightness. No system units
were failed, no critical kernel fault was found in the captured journal, and
a fresh 32 MiB USB transfer passed after sensor startup. This is one cold-start
pass after explicit opt-in, not zero-configuration or lifecycle completion.
Local logs and SensorProxy observations are in
`local/ci-run-37614381947/` in the parent workspace. The LK slots and factory
partitions were not flashed; both loader hashes matched before installation.

### Loader prerequisites

U-Boot `7b45fdbc62` connects bounded container parsing, adjacent certificate
pairing, verification of all ROM/DRDI/DSP signatures and signed ROM layout
validation. It publishes offsets and the load plan only after all checks
pass; corrupt or incomplete input leaves output unchanged. This is not yet
a partition reader or RAM-copy/boot path. Independent device root trust,
slot/SKU/rollback and component-version policy, reset and complete memory
protection remain required. Local Python reference tests passed (7 executed,
5 native/optional tests skipped); native C and full ARM64 CI `37650077659`
passed. No phone change or new SIM capability is claimed.

U-Boot `7231449a30` adds the explicit-slot GPT/block reader: partition bounds
and staging capacity are checked before payload reads; reads use 64 KiB
chunks and short reads fail without retry. Only a complete snapshot reaches
bundle authentication. The selected names are `modem_a/b`, as established by
the B4.1 LK platform table (see `patches/modem-stock-audit/PRODUCER.md`) and
confirmed against this phone's GPT, not the generic `md1img` fallback.
Each observed partition is 200 MiB, larger than U-Boot's 32 MiB malloc arena;
an exclusive temporary LMB staging allocation is required before integration.
No boot caller, modem destination writes, SMC or activation is enabled.
Native reader tests for 512/4096-byte blocks, exact read addresses, short reads
and malformed geometry passed with full ARM64 CI `37651088677`.

U-Boot `e0399e8a9d` adds scoped LMB staging, sized from the validated partition
extent and aligned to 64 KiB. The diagnostic combines allocate, read,
authenticate and release without allocating the snapshot on the malloc heap.
Every successful acquisition gets one release attempt, including failure
paths; release failure suppresses success output. Only a pointer-free layout
is returned after cleanup, never references to freed firmware data. The
separate modem window and outgoing Linux DT are not changed. No boot caller,
slot inference or root pin is installed; execution and device policy gates
remain open. Local Python reference checks passed (7 executed, 8 skipped);
native lifetime tests and full ARM64 compilation passed in CI `37655372236`.

The next modem candidate, `0006-dpmaif-use-standard-allocation.patch.vendor`,
removes automatic selection of the incompatible vendor CMA pool while leaving
generic kernel page-pool support unchanged. CI `37641267429`, source `a88f8de`,
passed all overlay/candidate tests, including twelve actual Makefile selection
cases and rejection of a mutant restoring the unsafe default. The full image
job was deliberately skipped via `validation_only=true`; no new kernel/module
link or device installation is claimed. The candidate is outside APKBUILD.

The hash-verified r168 native DTB declares separate `mediatek,md_mem_usage`
fragments, not exclusive ownership of the complete 512 MiB remap window.
These inherited fragments cannot authorize the new loader's full-window
mapping. Contiguous reservation before firmware copy/remap and kernel memory
discovery remains necessary; no SMC was attempted on the running phone.

U-Boot `fef0154b04` adds an opt-in allocator for the complete window after
Linux image and existing SCP/conninfra placement. It uses free LMB memory,
checks single-bank containment, and publishes no-map plus memreserve entries
transactionally. Malformed/overlapping DT ranges, duplicate diagnostics and
publication failures leave the original DT unchanged. No handset address is
embedded, no firmware is copied and no modem SMC or startup is performed.
The ordinary build leaves this disabled. Explicit CI `37643162425` enables
`modem_reserve` and all three existing SCP inputs; compilation/native tests
passed. The image was flashed to slot A and its exact 3277248-byte readback
matches SHA256 `5597585ccb9f6eca23d0aa214b762eb062c04db0836653bc13746c6b9a1a55de`.
First warm boot `ab2d1b8f-c5a1-457a-b61e-a0e597400e3f` confirmed a 512 MiB
no-map region plus memreserve entry, excluded by Linux; USB/SSH returned and
stock slot B is unchanged. The observed base is not a board constant. No
kernel WARNING/BUG/Oops/panic was found in the boot journal. Sensors report
the known warm SCP handoff limitation. Subsequent cold boot
`2fd66df3-f3ac-47e5-8fcf-fe368b22f3f4` retained the reservation and started
sensors automatically at 15.52 seconds (24 records, physical mask 31), followed
by SensorProxy at 15.86 seconds. A bounded privileged subscription received
21-23 lux updates; USB/SSH remained available and no services failed. The
CHRE memory-reserve diagnostic also exists in the earlier r168 baseline.
Visual checks, repeated cold starts and lifecycle remain pending. Do not
flash the default SCP-disabled artifact over this loader. The reservation
consumes 512 MiB of Linux RAM without providing SIM functionality yet.

U-Boot `791756c966` adds a checked two-stage remap executor with injectable
transport, explicit consumed/failed state and verification of every owned
register field. Native tests and full ARM64 CI `37639979367` passed.
No production SMC adapter or boot caller is enabled. Full validation of
exclusive reservation, authenticated platform selection,
reset ownership, complete EMI policy and Linux handoff remain prerequisites.

U-Boot modem prerequisites now on `master`: `f7ed9f7f6b` accepts bounded
zero-tail 48-byte stock v3 descriptors; `b2917cce8f` verifies signed modem
headers/payloads (full CI `37597316422` passed). `bbbc3b06c5` adds a bounded
relative ROM/DSP layout planner for the observed v6/DRDI-mode-3 profile; native
full CI `37601037773` passed. `b510cbb875` adds the initial physical block-map
planner: region/DSP/padding flags, overflow-safe base arithmetic, full reservation
coverage and an atomic 32-block limit; full CI `37603138572` passed.
`b9d96e38da` adds full-window remap bounds and masked register expectations:
the audited ATF maps 512 MiB in 32 MiB pages, not only the ROM's 480 MiB
declaration. Full CI `37604538052` passed, including native bounds tests.
`1167c6c1d9` additionally encodes EMI range arguments and raw readbacks without
silent ATF address truncation; full CI `37608301896` passed. Offline execution
of the pinned ATF handler passes 64 emulated scenarios, including one-shot
slot rejection and permission-preset writes. This does not test physical
protection or activate a modem boot path.
These pure planners allocate no memory and execute no
protection SMC. The exact stock LK skips separate DRDI loading in mode 3,
but still marks DRDI memory windows. These are unactivated loader
prerequisites, not modem boot: device-root/rollback policy, physical reservations,
remapping, secure reset/protection and CCCI publication remain unresolved.
See the [U-Boot implementation notes](https://github.com/xxxvik-xakerxxx/u-boot/blob/1167c6c1d9/doc/board/mediatek/mt6878-tetris.rst)
and the [exact ATF/LK memory-contract trace](MODEM_SIM_EVIDENCE_PLAN.md#2026-10-07-remap-and-protection-contract).
The explicit SCP-profile build `37609012691` of `1d4cb6496b` was flashed to
`lk_a` on 2026-10-07 and retained for the r168 installation. Ordinary push builds have
SCP preparation disabled and were not substituted for the sensor-ready profile.
The 3,275,616-byte LK artifact passed manifest, checksum, aligned-payload and
partition-size checks. Readback from the phone matches SHA256
`b8baaba76c131c6a47ccfd8ed63a5cdda55337c4b76e5bc6c9e665748324f983`.
Stock `lk_b` retained SHA256
`812873696e06a972eb5d67f5035687b91b1b48e4df0d25efc15d52fbf09b2518`.

Warm boot `a4478ecb-7af2-41d2-bba7-553c739e7d17` reports the new U-Boot
version, unchanged r167 kernel and USB/SSH recovery. The native display
connector appeared after normal deferred initialization, not at the first
early probe. SCP stopped at the documented warm-reboot `preflight -16` gate;
the sensor service refused startup rather than reusing unprepared state.
After full poweroff, cold boot `88190cd5-a538-4a6c-9afc-ec73b95d5059`
reports SCP secure state 3 and error 0. The transport automatically reports
firmware ready, 24 entries and physical mask 31 at 17.005 seconds; SensorProxy
starts at 17.432 seconds. User login occurs only at 1245.907 seconds. The user
reports sensor-driven behavior working after login but not before it. Thus
hardware/service startup is not login-triggered; the greeter's sensor use is
an unresolved desktop integration issue, not a demonstrated loader failure.
USB/SSH recovered and both services remain active. This is one cold-start
pass, not completed regression/lifecycle coverage or visual display/touch
confirmation. No modem execution was enabled.

A 60-second USB-attached idle capture passed on the same boot
(`local/live-logs/20261007T074856Z-172.16.42.1-idle-delta`). CPU idle counters
advance, but the phone is charging: this is not a battery-discharge test.
Our display-unblank service took 11.034 seconds and connectivity 6.311
seconds on that boot. These durations alone do not identify CPU cost or
justify removing initialization waits.

Works below refers to the demonstrated basic function, not every lifecycle
or hardware variant. Partial does not mean production-ready.

| Subsystem | Status | Demonstrated / remaining |
| --- | --- | --- |
| Boot, UFS/root expansion | Works for tested setup | r167 clean flash reaches userspace; writable expanded root. Other firmware/SKUs remain unverified. |
| Native display | Partial | Route/startup and frame-end plane updates are in main (`aecf4f4`, packaged `0097-drm-mediatek-update-MT6878-planes-at-frame-end.patch`). User repeatedly confirmed no stripes/flicker, including r167. Fixed 60 Hz/software rendering; 120 Hz, acceleration and full power lifecycle remain. |
| Touch and keys | Works for basic input | Touch and power/volume keys tested; not a claim of completed suspend/wake coverage. |
| Sensors | Partial | All five physical classes emit real data; 24 firmware entries. Correct rotation, automatic brightness and proximity screen blank/restore confirmed. Brightness is stepped; calibration, warm boot, suspend, repeated cold starts and another unit remain. |
| USB/NCM/SSH | Partial | Repeated clean boots and 32 MiB transfer gates pass; full reconnect/suspend lifecycle remains. |
| Wi-Fi / Bluetooth | Partial | Initialization and earlier Wi-Fi association/traffic and Bluetooth discovery demonstrated; pairing/profiles/coexistence/suspend are not complete. |
| Audio | Partial | Both speaker paths and microphone capture demonstrated in earlier tests; full route/call/lifecycle coverage remains. |
| Haptics / torch | Partial | Bounded physical effects tested; full lifecycle and camera strobe remain. |
| Battery, charging, thermal | Partial | Telemetry, charging observations and thermal polling exist; charger classification, sustained charging/thermal safety validation and idle power remain. |
| GNSS | Partial, transport only | Supervised firmware/transport work exists; no verified position fix or complete GeoClue navigation stack. |
| SIM, calls, SMS, mobile data | Broken | No operational modem demonstrated. Sensor proximity used a local dummy call, not GSM. |
| GPU acceleration | Broken | No render node or accelerated compositor demonstrated; compile-only groundwork is not runtime support. |
| Cameras | Broken | No working preview/capture; clocks/topology/identity groundwork only. |
| microSD | Partial | Controller probes; card insertion and real I/O remain untested. |
| NFC | Not present | No NFC hardware on this device. |

SCP startup is opt-in. The exact slot-A ATF/SCP profile, authenticated firmware,
dynamic reserved memory, and zero-TCM preflight remain mandatory. Warm reboot
can leave SCP disabled deliberately. No secure-boot bypass or universal NOS
4.0 support is claimed. See [sensor evidence](SENSOR_DESKTOP_INTEGRATION.md),
[display audit](DISPLAY_FIRST_FRAME_AUDIT.md) and [status history](CURRENT_STATUS.md).
The unsolicited on-screen keyboard issue was observed but deferred, not fixed.

## Branch consolidation

Only `main` (pmOS) and `master` (U-Boot) are active remote branches after
cleanup. Former remote tips are retained as immutable-by-convention tags:
`archive/2026-09-22/<former-branch-name>` in the corresponding repository.
This preserves unique work without enabling unvalidated experiments in the
default image. Archived does NOT mean merged or hardware-verified. Local
worktrees and uncommitted research files are intentionally untouched.

See `git tag -l 'archive/2026-09-22/*'` or GitHub tags for exact retired
tips. Unmerged research remains recoverable there, including NOS 4.0
early-boot diagnostics; it is not declared compatible or enabled.

Next: [remaining work and test gates](PORT_COMPLETION_PLAN.md).
Research: [documentation index](README.md).
