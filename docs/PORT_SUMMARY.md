# Port summary, 2026-10-13

Native postmarketOS port for Nothing CMF Phone 1 (`nothing-tetris`, MT6878).
Experimental, not a fully functional daily-driver phone.
Current development is in [pmOS main](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports)
and the maintainer's [U-Boot master](https://github.com/xxxvik-xakerxxx/u-boot).
The shared MT6878-Mainline U-Boot repository has not been updated by this work.

## Latest installed checkpoint: r188

Full image [CI38377639691](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38377639691)
at `e19e691ee25f2edfd3e958111e08345162115d46` passed all five jobs, including
the complete kernel/rootfs build. Artifact `nothing-tetris-native-md-gnss-tx-images`
ZIP SHA256 `94438e53dc36a176bbed489b708391749e0b47165884554e62aa18cb76f646d7`
and every image digest were verified. The sparse image parsed all 7634 chunks,
expanding to 2785017856 bytes. Both `super` and `userdata` were cleanly flashed;
neither LK slot nor factory calibration/firmware partitions were written.
Kernel `7.2.1-r188`, Linux `6.18.0 #189`, device `8-r20`; its first boot used
the paired `322cf227` loader, SHA256
`0a16ba1da3a40b8da43b9d5b322fc496c65636ab5f516a5c152b7639e973073b`.
Stock `lk_b` remains SHA256
`812873696e06a972eb5d67f5035687b91b1b48e4df0d25efc15d52fbf09b2518`.
Installed FIT SHA256, read back after boot:
`ef731b4f4d2058eec19fa61dfdb9241b6b0a0f29b15afaabbf6b1bd7e61327a9`.

Cold boot `c4d22767-3308-42b5-9aa0-feff51527846` retained USB/SSH and completed
native MD first-OFF with CTL `0x02000009`, isolation `0x3`, IFR9 `0xfbfb03b8`,
IFR11 `0xcffcd932`, NEMI `0xc1`. This is physical OFF evidence, **not modem
restart, SIM detection or calls**. Connectivity initialized automatically;
an actual Wi-Fi scan returned 63 access points. Association/routed traffic
were not tested. The previous conninfra NULL wake-lock fault is absent from
the captured first-boot journal. The user confirmed normal display and touch.

Sensors on that first boot failed closed: `/chosen/nothing,scp-prepare-stage` was missing.
SCP secure state 3 and plaintext region size 60 are present, but secure
operation/error and prepare stage/error are absent. This is not sufficient
proof of a complete handoff. The sensor service was not bypassed and hardware
owners were not reloaded. U-Boot's standard final DT step shrinks its tree
before late SCP setup. Personal U-Boot
[`688fb90f`](https://github.com/xxxvik-xakerxxx/u-boot/commit/688fb90f6677ef2421d2bc8b4f059536c6616718)
adds a bounded, independently reserved DT clone before SCP setup, rejecting
unproven allocator results before mapping. The matching SCP-secure/BROM-metadata
[CI38389560147](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38389560147)
at `f25c01444a642c6fca857bd9678ef438ec371988` passed, including actual libfdt
sanitizers and ARM64 compilation. The first CI attempt stopped in a new test
because it incorrectly expected zero rather than a nonnegative DT node offset;
the follow-up changes only that test. The verified LK image, 3317552 bytes,
SHA256 `30b5f535e5a2642bbd5d650a65637a123209af242c4246f7da9c2dd0fbefdc04`,
was successfully flashed to `lk_a` only and full poweroff was issued. The hash-pinned
[experimental mirror](https://github.com/xxxvik-xakerxxx/u-boot/releases/tag/native-md-startup-off-f25c0144)
is now selected for future native diagnostic images; the frozen r184 parent
remains unchanged. Existing r188 downloads still contain the original loader.

After the user-confirmed physical cold cycle, boot
`b09bc1f9-5096-442d-8546-5e1c92aa1bd2` read back that exact corrected LK hash;
FIT and stock `lk_b` remained unchanged. SCP now reports
`secure-handoff-prepared`, prepare error0, secure state3/error0, with operation
also present. Sensor transport and SensorProxy started automatically (24 entries,
physical mask31), with no failed systemd units. The user confirmed display,
touch, both rotations and auto-brightness. An actual Wi-Fi scan returned 68
access points. The complete captured first-boot journal has no new kernel
Oops/BUG/WARNING/SError/panic/refcount fault. Native MD first-OFF passed again
with the same recorded values. This is one corrected cold boot on one handset;
warm reboot, suspend and cross-firmware/SKU coverage remain unproven.

On this corrected boot a second bounded GNSS ROM cycle at uptime540.596-540.604s
returned status0/code_size42505/fragment_count106 and confirmed both DMA stops,
GPS OFF and CLOSED. Wi-Fi stayed powered; sensor/proxy/connectivity/SSH services
remained active. No new fault appeared in the cycle's journal. SensorProxy
advertises accelerometer and ambient light through its standard D-Bus interface.
These results close the observed wakeup-source and missing-report regressions,
not the missing end-user radio, navigation, GPU or camera functions.

Loader-selection integration at `b0aaef16c62cedfad424ba6e278d2cc808c80085`
passed [CI38391021694](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38391021694):
overlay validation, Bionic adapter and sealed-loader jobs succeeded. Kernel
object/full image jobs were intentionally skipped for this validation-only run;
the installed kernel/rootfs remain the fully built r188 artifacts above.

r188 packages exact GNSS TX patch1009 and all matching external modules in one
build. The packaged transport started without reload. One bounded read-only
link0 cycle at uptime1081.084-1081.093s passed actual power-on, ROM reset,
OPENED, status0 and metadata (code_size42505, fragment_count106), then confirmed
TX/RX DMA stop OKAY, GPS power-off and CLOSED. Wi-Fi remained powered and
USB/SSH survived without a new kernel fault in that cycle's journal. No
firmware fragments or navigation commands were sent; DSP WORKING, protocol
ACK, repeatability and a GPS fix remain unproven.
The same CI compiled the separate GPU flat-metadata candidate as a real
AArch64 object, source SHA256
`e0ac3e88c4a23faabf0cc80f406a52e7eda1ac44af0f9004df65de730a367204`, object SHA256
`49442839b12decedd4a3938e464458903cba910ed85f05239c84dacc0ccef91e`.
That candidate is not installed or proof of accelerated rendering. Camera
VMM admission and post-OFF modem TOP gating remain uninstalled sidecars.
SIM/calls, GPS navigation, GPU acceleration and camera capture remain unavailable.

### Combined bring-up candidate

The installed baseline remains r188 with U-Boot `f25c0144`; the changes below
are not installed hardware support. All target compilation stays in GitHub CI.

| Subsystem | Change | Remaining functional gate |
| --- | --- | --- |
| Modem | Native genpd ON callback after first-OFF, using real MT6363 voltage/sync, TOP, FLIGHT, isolation, ACK30 and bus release. | CCCI first-start integration, secure execution release, firmware handshake, SIM registration and calls. |
| GNSS | Native L1 firmware download and all matching ACKs passed on r188; the driver observed RAM_OKAY and WORK. | Retained session/clean stop, navigation initialization and position fix. |
| GPU | Package the retained-v1 metadata consumer directly; preserve exclusive RAM ownership and digest checks. | Matching retained loader, executable GPUEB SRAM/DRAM/mailbox contract, power lifecycle and rendering. |
| Camera | Package IMX882's documented 24 MHz mux/source acquisition before sensor power/reset. | Checked GPIO-rail ownership, sensor identity, streaming-clock integration and capture. |

On the same healthy boot, read-only conninfra queries returned chip `0x6878`
and GPS ADIE `0x6631`. The actual GPS NVM file is 54 physical bytes; its logical
profile selects 26 MHz, interval0 (stock fallback2000), mode255 and profile0.
Only these common fields were reported. Unique calibration, key material and
raw records are not published. GNSS ioctl11 returned33 and the bound MT6685
clock query returned0 (26 MHz); neither establishes firmware readiness.

The complete 107-patch package application, overlay checks and 58 smoke-helper
tests passed locally. These are source/orchestration checks, not target C
compilation or live execution of this candidate. Camera DT and shipping
identity probe remain disabled; no GPIO power sequence was activated.

The standalone GNSS build at `ca947b991b83851512083802f7ed14cdcaccb3b9`
passed [CI38403683556](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38403683556),
including actual C fixtures and static AArch64 musl compilation. Its 88704-byte
executable SHA256 is
`fea532a7178de6d751d14d781fcec4ab35855015b238e3c8cc078bcf3f328522`;
the same digest was verified on the phone before one exclusive fresh-fd test.
At uptime6907.18-6907.69 on boot `b09bc1f9`, bootstrap and every selected
fragment received matching ACKs. The kernel observed `RAM_OKAY -> WORK`.
The temporary private NVM copy was removed; no calibration/firmware partition
was modified. Sensor/proxy/connectivity/SSH services stayed active, with both
DMA stops OKAY and GPS CLOSED. No new kernel BUG/WARNING/Oops appeared.

The runner closed immediately after the final ACK, before queued RAM_OKAY was
handled. The resulting WORK -> FUNC_OFF transition has the vendor FSM's
`is_err=1`; this is not a clean navigation/session lifecycle pass. The next
owner must retain its descriptor through actual DSP readiness and source-backed
stop handling. No navigation commands, NMEA output or position fix were tested.

In [CI38402801113](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38402801113),
the normal seven-object/DT gate passed on `4bfe7d4`. The new IMX882 identity
object is AArch64 SHA256
`8c41c97d5c0a38cc40fa40d58e608f56b41b6ae7032a3d94184efc57815dc32e`;
the canonical GPU object is
`49442839b12decedd4a3938e464458903cba910ed85f05239c84dacc0ccef91e`.
The later modem-ON step failed before compilation because container checkout
had fallen back to a non-Git source download. This run is not globally green,
and neither object result proves camera capture or accelerated rendering.

The additive native CCCI first-start composition, camera GPIO-rail provider
and GPUEB reset-held SRAM installation are in main as disabled candidates.
The private GPUEB CMA allocator adds an owned six-MiB workspace, not GPR writes
or executable GPU startup. The full cellular link gate remains open.
U-Boot's bounded late GPUEB DT clone passed
[CI38415042958](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38415042958)
at `f0f204bfdf`; its retention profile has not been installed and remains separate
from the modem BROM profile. The phone still uses the verified `f25c01444a` loader.

The native GNSS session candidate adds read-only ioctl31 and keeps the actual
download descriptor through sampled WORK and source-backed stop. A failed
attempt enters a live recovery-hold rather than implicitly closing on exit.
The installed backend was identified read-only as `gps_drv_dl_v051.ko`; the new
ABI still requires a new matching kernel/supplier/module image before testing.
IMX882's actual streaming driver now has a staged 24-MHz source contract and
checked partial-power/reset lifecycle. Camera and cellular compile paths are
independent in CI; neither is activated by these object-only gates.
At `797e7d8c`, [CI38454201394](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38454201394)
passed the actual GNSS snapshot/session and retained-download C fixtures under
sanitizers, plus static AArch64 musl compilation. The new CLI is not compatible
with installed r188: r189 must supply matching ioctl31 modules first.
[CI38454186695](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38454186695)
passed joined GPUEB SRAM/reset and DRAM ARM64 compilation, internal symbol
resolution and native allocation/failure fixtures. No reset-held installation,
DRAM publication or accelerated rendering was tested on the phone.

In [CI38454175016](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38454175016),
the normal objects/DT, camera GPIO-rail provider and actual IMX882 streaming
driver compiled successfully. The modem step failed on a missing resource-only
revalidation helper. The correction preserves original physical ON validation
and separates immutable handoff/resource checks for post-OFF callers; its
source/application checks passed, but target recompilation is still required.
The additive full CCCI link gate builds the actual kernel exports and native
first-start callers with strict modpost. Its selected modules are not approved
for loading into r188. The r189 image composer adds exact session patch1010
after TX patch1009 without activating camera or GPU hardware.

### Previous regression: r184

Full image [CI38356364811](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38356364811)
at `91c7a1108149d3694fbb255cdf95c3f6ab62be19` passed all five jobs.
Archive SHA256 `214a67cb840f5ff477ae8ea31cbef3634265e8740ac3f4d52d1582932d023110`
and all four image hashes were verified before clean `super`/`userdata` installation.
The sparse image parsed completely: 2783969280 expanded bytes, 7677 chunks.
Kernel `7.2.1-r184`, Linux `6.18.0 #185`, device `8-r20`; paired startup-OFF
U-Boot `322cf227` remains in `lk_a`, with stock `lk_b` unchanged.
Installed FIT SHA256 is
`54b959868cc3548a7211b1ec525960ae19114f7c74cfd7d166e5cdd9c7403995`.

First boot `62d3d417-ea51-4e83-a228-f8253a921523` retained USB/SSH and completed
the actual native MD first-OFF transaction: CTL `0x02000009`, isolation `0x3`,
IFR9 `0xfbfb03b8`, IFR11 `0xcffcd932`, NEMI `0xc1`. This physically validates
the ACK30 correction and protected MTCMOS OFF, **not modem restart or SIM/calls**.
The modem consumer remains disabled. Warm SCP preparation failed and conninfra
reported completion timeouts; no module reload was attempted. Logs were saved
before full shutdown. The user subsequently reported a working Linux desktop
but no Wi-Fi or sensors, then entered fastboot. A cold journal was unavailable
because the host's external hub had lost its USB2 branch; reconnecting the hub
restored fastboot. This does not identify the causal hardware regression.

A control boot filesystem changes only the DT to the normal native DT compiled
in the **same r184 CI** (SHA256
`544b6fa716e1523b74bc9c081592cb0cdde8a489f047760cad90799ea3841398`).
Kernel/initramfs payloads and every other FIT property were compared unchanged;
boot filesystem contents differ only in FIT, and userdata/modules stay r184.
Control FIT SHA256 `d8be9d96a91f3ed251526f67803cffcfefc88a7a808eef2904d5c93f01a12411`;
boot image SHA256 `6a795b4348dfcb6e12bfb916f3c9143212d934427af50a411eb573b6578b2d11`.
This disables the first-OFF DT activation to isolate the reported failure; it
is a derived diagnostic repack, not a separately compiled or validated release.
The control boot filesystem was written to `super` successfully; userdata and
both LK slots were untouched. Control boot `0edff604-0759-41a2-be3f-b97c13ec3552`
confirmed that the failure persists with normal DT: SCP recovery succeeds,
but sensorhub returns `-ENOMEM` at wakeup-source registration. The first
conninfra fault is `osal_wake_lock_count`, before subsequent completion timeouts.
USB/SSH and the control FIT hash remain valid; no hardware owners were reloaded.

The actual r184 configuration disables PM_SLEEP. Pinned Linux
`include/linux/pm_wakeup.h` then makes `wakeup_source_register()` return NULL;
the matching sensor transceiver checks it and returns ENOMEM, while conninfra
dereferences the absent wake lock. This source/live match identifies the
configuration regression independently of MD first-OFF. Corrected r187/r188
image staging keeps SUSPEND/PM_SLEEP/PM_SLEEP_SMP and retains a static PM prepare
veto before the first modem write. A system-transition mutex trylock excludes
concurrent suspend/reboot without waiting behind a probe-dependent transition.
PM_SLEEP_SMP selects HOTPLUG_CPU in the pinned Linux Kconfig. Preserve that API
as well and hold the real boot-lifetime `cpu_hotplug_disable()` owner before MD
writes, requiring all present CPUs online. CPU idle, hibernation and kexec stay
compiled out; actual CPU up/down and system sleep are vetoed. The veto persists through
success/failure for this boot; this is not working suspend support. The complete
r188 build and physical connectivity recovery are recorded above; the separate
incomplete bootloader report was corrected and sensor cold recovery passed.
This diagnostic profile excludes idle/sleep/hotplug and is not a battery-optimized
shipping release. GNSS exact1009, camera frames and accelerated rendering are
not enabled by r184.

The opt-in CI `gnss_tx_image` path stages exact1009 in a matched r188 kernel,
with all genuine supplier/external modules rebuilt together and separately
named artifacts. Without GNSS TX the corrected first-OFF image is r187; frozen
r184 remains a reproducible historical parent. The installed r188 image combines
the causal wakeup-source correction and real GNSS TX package integration.
The new GPU v1 metadata admission preserves the existing RAM owner and actual
bootloader profile/digest fields; real ARM64 object compilation passed in CI38377639691,
not GPUEB upload/start. The camera VMM admission addition rejects independent
firmware voters before rail acquisition; post-OFF modem TOP gating remains an
uncalled, default-off staged primitive. None of these source changes establish
SIM, GPS fix, GPU rendering or camera capture.

### Current integration checkpoint

The 2026-10-13 joint source candidate adds a one-boot native MD MTCMOS first-OFF
transaction with direct error/readback retention, bounded GPUEB TX through the
existing RX/SRAM owner, and an isolated disabled CAM/ISP DT graph using the real
shared USID6 rail and ordered protection clocks. GNSS now has exact MVCD
bootstrap framing/ACK decoding and source-derived clock synthesis. The actual
board/profile/frequency inputs remain required; no synthetic bootstrap is sent.
These source changes have passed the joint native build gates, **not installed
hardware support**. The nonbootable camera fixture is excluded from FIT inputs.

Paired U-Boot source `322cf227f2ea26a7e319d20e3ce0321db8a38f15` adds the
paired fresh final first-OFF marker, without a new hardware operation. Its
[CI38314466282](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38314466282)
passed. The matching SCP-secure/BROM-metadata build
[CI38325598818](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38325598818)
was written and read back in `lk_a`: 3316288 bytes, SHA256
`4ff2fae500477380575b2c6f9cc1942f66720c944c5db8e8c94accb5598c07a0`.
Stock `lk_b` is unchanged. Warm boot `b8e13a10-19f6-4ab7-9f71-de0623e1d494`
returned r182 and USB/SSH; SCP reported handoff not prepared and sensors did
not start. After the user-confirmed physical cold cycle, boot
`52ab3b24-f0e5-4cbe-a40f-ac4422e98bdd` automatically initialized SCP and the
24-entry sensor transport (physical mask31); sensor/proxy/SSH services and
`usb0` were active, with no failed systemd units. This establishes recovery on
that cold boot, not warm-reboot support. The separate
first-OFF kernel profile excludes deep idle, sleep, hotplug and kexec for this
experiment; it is not a shipping battery-optimization policy. It does not
implement rail/TOP/FLIGHT shutdown, inhibited restart or SIM/call service.

All mandatory validation, Bionic and sealed-loader checks for the preceding
CI/configuration correction passed
[CI38310658085](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38310658085).
For the joint candidate `cbb777d`, all mandatory native validation, new GPU
mailbox fixtures, GNSS framing/clock fixtures, Bionic and sealed-loader jobs
passed [CI38315471685](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38315471685).
The exact pinned GNSS wire/clock/driver producer checks and native fixtures also
passed [CI38315481513](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38315481513).
The actual shared first-OFF modem/camera provider compiled and linked strict
ARM64 vmlinux with both KUNIT=y and KUNIT=n in the `native-provider-link` job of
[CI38315490334](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38315490334)
at `cbb777d`. The aggregate run failed only on the now-corrected DT comparison:
stock `hwid-node=<92>` is opaque scalar data, not a source-backed phandle.
The isolated repair [CI38317130122](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38317130122)
passed actual ARM64 driver builds, full/resource-only CCCI links and native
infrastructure clock linking. No hardware function is inferred from these tests.

The opt-in `native_modem_first_off` CI image profile freezes this verified
`cbb777d` provider while rebuilding the whole pmOS kernel package and its
external modules together as diagnostic `7.2.1-r183` / device `8-r19`.
It adds a separately checked board DT; only fresh successful U-Boot handoff may
enable supplier/domain0. Modem transport, camera and GPU remain disabled.
Shipping packages and default images are unchanged. This is an installation
candidate, not SIM/call support or a battery-optimized daily-driver image.
The first image attempt, CI38326117165, passed validation/isolated compilation
but stopped before kernel compilation because Alpine checkout had no Git
history. The corrected [CI38326786870](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38326786870)
failed on the nested native camera header's missing parent include path.
The diagnostic profile corrects that reference to the same actual shared
provider header used by native CI, explicitly builds/installs its selected DT,
and declares the sibling modem node in the power binding. A repeated uncorrected
attempt was cancelled. The corrected complete image is available as described
below; r183 was deliberately withheld and is superseded by r184.

The follow-up source revision retains a staged post-OFF TOP/rail owner and
first errno, but inhibited ON still stops before regulator acquisition or
hardware writes. GPU gains a sealed eleven-consumer dispatch lifetime, not IRQ
activation/RV33 startup. GNSS adds the source-derived constructor for 50 of 106
bootstrap bytes, including real private-record frequency semantics; the other
56 bytes are now implemented by the full 106-byte / 116-byte frame constructor,
including the immutable original-frequency profile block and exact MVCD/CW
ioctl selection. Same-session inputs and real ACK/WORKING evidence remain
required before navigation can work. New camera
supplier DT candidates preserve the native board or explicitly identify a
forbidden-to-boot ownership delta. These follow-ups require their own native
CI and do not replace the frozen `cbb777d` image inputs.
The 50-byte field constructor and updated GPU lifetime fixtures passed mandatory
validation [CI38327618654](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38327618654);
exact GNSS producer/native checks passed
[CI38327625537](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38327625537).
The full-frame constructor, exact pinned producers and native sanitizer fixtures
passed [CI38331513481](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38331513481)
at `789d002`. This does not establish live DSP download or a position fix.
The one-attempt secure L1 controller and actual Linux syscall adapter then passed
[CI38335304033](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38335304033)
at `e8ad596`, together with the exact pinned fragment sequence and actual-source
nonblocking TX fixtures for both IRQ/polling configurations. No fragment wire
trigger is invented: ioctl25/26 submits index0..N-1, matched ACK32 advances
sequence1..N. The new1009 TX patch remains staged, not present in r182/r183;
real ARM64 v051 translation-unit compilation passed with full/resource-only
CCCI, infrastructure clocks and the joint GPU/camera object stack in
[CI38336059980](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38336059980)
at `9f4b4b2`. Module linking/packaging and legitimate live
profile inputs, physical ACK traffic and independent kernel WORKING remain
required. Successful download-owner completion now detaches the borrowed
session; later result queries and adapter steps perform no session dereference,
clock query or syscall. Native sanitizer/source checks passed
[CI38338345488](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38338345488)
at `31cd56d`; no physical DSP transaction was performed.
[Download owner](../patches/gnss-navigation-audit/dsp-download/DOWNLOAD.md)
documents the limits, including synchronous SMC timing and sole-fd ownership.
The updated joint MD/camera provider passed strict ARM64 vmlinux linking with
KUNIT=y and KUNIT=n, both supplier DT candidates and full/resource-only CCCI
links in [CI38327631459](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38327631459)
at `5d507e5`. The camera candidates remain excluded from installation.

The running MT6363 provider exposes only VCN13/VRFIO18, not stock modem VBUCK2,
VSRAM_MODEM and VBUCK1. A standard native three-rail extension is staged under
`patches/modem/md-pmic-supplier`, preserving the existing connectivity source.
Selector/SET/CLR/mode operations retain real errors; unsupported shared-key,
SSHUB, hardware-voter and calibration controls stay denied. Actual ARM64 objects
with KUNIT=y and KUNIT=n, full/resource-only CCCI and infrastructure clocks passed
[CI38332592584](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38332592584)
at `37310ed`. KUnit cases were compiled, not run in a kernel. Disabled rail
metadata is not activated; no voltage measurement or SIM support is claimed.

The next diagnostic integration wires those three genuine supplies and TOP to
the disabled modem while preserving inherited voltage during registration.
It changes only the three native child availabilities when explicitly selected.
Twelve source/patch/full-tree tests and real ARM64 provider objects with KUNIT=y/n
passed [CI38363867364](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38363867364)
at `e44cccc`, including the registration correction. This is not included in
r184 or shipping images; compiled KUnit cases are not runtime electrical tests.

The corrected diagnostic image
[CI38331505196](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38331505196)
at `789d002` passed validation, the complete kernel/module package, selected-DT
validation and device/sensor packages. Image creation failed because the FIT
template still named the ordinary board while boot-deploy copied only the
selected diagnostic DT. Staging now updates both deviceinfo and the FIT incbin
reference, with positive and drift/duplicate regression checks. A container-registry quota failure was retried before
compilation; future jobs use a verified byte-identical Alpine manifest mirror.
The failed image was not installed. Corrected full
[CI38339848611](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38339848611)
at `bd74848b726b6c5b7e2fbea8db1c1618e6a72f5a` passed all five jobs and produced
artifact11789527090 (ZIP SHA256
`1d806baf12529de7434abc788e2cff4f8dc82538fb7ee514c0a51dbdd3c1f8cc`).
The ZIP and all four image hashes were verified locally; Android sparse parsing
passed (2783969280 expanded bytes, 7697 chunks). Installation was withheld after
the modem-only ACK defect below was identified. CI success does not establish a
physical OFF transition or radio service.
The diagnostic artifact is explicitly
named `nothing-tetris-native-md-first-off-images`, with the paired loader above;
ordinary shipping images do not activate this experiment.

The real cold r182 report identified an earlier causal failure: loader stage2
rejected inherited MD ON with `-EBUSY` (CTL `0x4200000d`), so no authenticated
final metadata or native supplier activation occurred. Corrected loader profile
[CI38350296947](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38350296947)
passed at the same `322cf227` source, enabling the existing initial LK OFF
transaction before RAM writes. Image SHA256
`0a16ba1da3a40b8da43b9d5b322fc496c65636ab5f516a5c152b7639e973073b`.
This profile was installed and read back in `lk_a` (3316976 bytes), preserving
stock `lk_b`. On warm boot `3bde0513-97f9-4932-93c8-51d1cdcd0b76` and the
user-confirmed physical cold boot `610323aa-8ba6-4b69-97e9-7a17e940d99e`, actual
loader stage11, bootstrap stage15 and board stage16 completed with zero errors,
no cleanup and four BROM flags equal to1. Real descriptor32/evidence336 and the
four NOMAP reservations were published; the modem consumer remained disabled.
Cold SCP/sensor/proxy initialization and USB/SSH passed without failed units.
Warm SCP recovery still failed; no warm sensor support is claimed.
The Linux modem-only ACK mask also required correction: pinned B4.1
`drivers/soc/mediatek/mtk-scpsys-mt6878.c` selects `MD_OPS | IS_PWR_CON_ON`, and
`scpsys_md_power_on/off()` use `scpsys_pwr_ack_is_on()` with BIT30, not the
generic second ACK31. The frozen native candidate incorrectly required both.
Diagnostic r184/device r20 adds an exact post-provider BIT30 correction and
pairs the corrected loader. Ten static staging/application checks pass;
complete kernel/image [CI38356364811](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38356364811)
at `91c7a11` passed validation, Bionic, sealed-loader, object smoke and full image
compilation. The installed first-OFF result is recorded above. r183 remains an uninstalled
CI checkpoint, not a working modem claim.

The full GNSS module gate builds actual kernel exports, connadp and conninfra,
then the complete v051 baseline and staged1009 candidate with strict modpost.
Its first [CI38356794383](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38356794383)
stopped before compilation on historical1000 patch context. The correction
matches packaged patch application and verifies both entire postimages contain
only the reviewed class_create API replacements; local real-source application
and54 static tests passed. Corrected
[CI38357565018](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38357565018)
at `f27228d` passed actual ARM64 kernel/supplier builds and both complete v051
module links. All118 strong imports resolve; candidate module SHA256
`ff929652ffde5ab1dc0d1ba44d92825351d316b8f7c0d92413484363c1972d79`.
LLVM21.1.2 differs from the installed kernel's21.1.8; this gate explicitly marks
phone ABI compatibility false. Matched image packaging and real DSP/position
tests remain pending; no replacement module is installed on the phone.

Personal U-Boot `bd8950d9bf6c10e6ee075e654e19ff43cc889841` adds explicit retained
GPUEB payload offsets/profile/version and signed-member/container provenance,
with a fresh plaintext digest check before failure-atomic DT publication.
[CI38356830921](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38356830921)
passed the real firmware/authentication tests, native retained-payload fixtures
and ARM64 loader build. This revision is not installed; the current modem/SCP
profile keeps GPUEB retention disabled. IRQ activation, GPR0/GPR6/EMI ownership,
RV33 execution and accelerated rendering remain unverified.

The older observation-only source `57f97dd` compiled all three actual native
objects in both KUNIT configurations in
[CI38309216336](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38309216336).
Its KUNIT=y vmlinux completed and the job entered the second configuration,
but the KUNIT=n build hit the one-hour job limit before completion. The aggregate
job is cancelled, not passed; this does not validate the newer first-OFF code.

- A separate [CCIF/DPMAIF DT](../patches/modem/drafts/runtime-hif-dt/README.md)
  supplies the actual B4.1 registers, IRQs and CCF references. CI repackages
  only this checked DT into the original r182 kernel/initramfs; the shipping
  disabled modem metadata anchor remains unchanged. DT compilation, complete
  delta checks and immutable FIT/boot-filesystem packaging passed the independent
  `hif-dt-image` job in [CI38299987535](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38299987535).
  The resource-binding test passed on the handset as recorded below, not
  firmware START or SIM service.
- [GPU mailbox dispatch](../patches/gpu/reset-owner-draft/MAILBOX-DISPATCH.md)
  connects the existing exclusive reset/SRAM owner to all eleven source-backed
  RX channels. IRQ activation, complete firmware upload and GPUFREQ admission
  remain disabled; no render node is claimed.
- [Native camera VMM integration](../patches/camera-camisp/native-integration/README.md)
  connects the shared supplier to the actual Linux genpd provider. CI must link
  the combined provider in genuine ARM64 vmlinux with KUNIT enabled and disabled;
  firmware/voltage ownership and board DT activation are still unverified.
- GNSS now embeds the reverse AGPS owner in the production startup controller,
  activates it only after a real successful engine-run result, and acknowledges
  quiescence before native teardown. Remaining assistance/configuration gates
  are preserved; no engine INIT or position fix is claimed. Exact B4.1 controller
  checks and native LNA dataflow passed [CI38300004525](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38300004525).
  All mandatory source/native, sealed-loader and Bionic checks passed
  [CI38301035398](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38301035398)
  at `247e714`, including the reviewed deliberate-IRQ-quiescence correction.
  The next forward configuration hook copies native selector7's exact 668-byte
  snapshot into the existing worker queue and sends stock message160, without
  retaining a callback pointer. Source checks pass; its new native delivery
  fixtures and Bionic regression build passed
  [CI38304276532](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38304276532);
  exact B4.1 producer checks passed
  [CI38304286142](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38304286142).
  Quiet logging does not
  remove the actual AGPS-agent initialization dependency; no startup gate is
  cleared by this change.

#### Actual r182 HIF DT test

CI source `f98d569808d9466748a116a389ea359634396b87`, artifact11770098745:
ZIP SHA256 `4f863bacc70085d29877b126496cb9ee8775369bc7c1cad915fcd6f0af5e4a1f`;
FIT SHA256 `832a340579e2f03bba897e4fcdc54a1f7c8bcefb85ec11c44814a8760b3af5a5`.
Kernel and initramfs payloads were independently compared against original r182
and are byte-identical. FIT was atomically replaced on mounted `/boot`; original
FIT remains `/boot/boot_image-r182-before-hif.itb`. No userdata or LK change.

After commanded poweroff, boot `bbc28d61-b267-4c48-9a23-ffa0ad62ed6c`
populated actual CCIF/DPMAIF platform devices. One guarded resource-only module
load at uptime176.35-176.54s bound `tetris_ccif_resources` and
`tetris_dpmaif_resources`; `/proc/iomem` confirms all eight primary/auxiliary
claims. Both completed probes imply actual six/three OF clock lookups and
retained IRQ descriptors. All thirteen CCF prepare/enable counts remain0.
Exact CI38287440390 modules use the unchanged r182 ABI; private preparation=N,
CLDMA/SCP companions absent, no transport publication, IRQ request, DMA or START
by these helpers. Owners remain loaded until reboot, not installed/autoloaded.

The full before/after kernel journals differ by only the two expected CCCI
metadata/retention messages; no new kernel fault or failed service. USB/SSH and
sensor services remain active. The user confirmed display, touch, rotation and
automatic brightness unchanged. Full local evidence archive SHA256:
`8c870e9094998644310f760355018893182bd0fc67e6305dcc0dad9cf0713b53`.
This boot automatically followed poweroff with USB attached, not a confirmed
physical cold cycle. Native MD ON adoption, actual HIF activation and end-user
radio functions remain separate pending steps.

#### Actual GNSS power and ROM-reset cycle

On the same r182 boot, one packaged `gnss-readonly --probe-link0` attempt at
uptime3175.908-3175.916s opened link0 through the actual driver. ADIE6631 was
detected, conninfra/GPS power-on succeeded, DSP changed OFF -> ON -> RST after
its real RST_DONE event, and the link became OPENED. Status ioctl returned0;
boot-info reported code_size42505 and fragment_count106. Cipher material is
redacted, not published. No userspace transport write/read or firmware fragment
download was performed.

Close confirmed TX/RX DMA stop0/OKAY, GPS power-off, DSP OFF and link CLOSED.
Wi-Fi/BT power states remained ON, USB and sensor services survived, and the
82-line kernel delta contains no Oops/BUG/WARNING/SError/panic/refcount fault.
Full local evidence archive SHA256:
`c49e67f80be192f09446623e50479c5401a15f093298939c3a00eaaad227d692`.
The missing pinctrl/LNA metadata diagnostic remains; stock MT6631 has no L5.
This proves one power/ROM-reset/open/close cycle, **not** working DSP firmware,
navigation INIT, calibrated RF reception, repeated lifecycle or a position fix.

[Modem power integration](../patches/modem/md-pm-integration/ON-ADOPTION.md)
must adopt the real ON state left by successful BROM. AID241 is the stock NS-CPU
identity; the loader's reported v2 cells encode RW for the declared service
ranges. An additional invented permission certificate is not required by an
ordinary trusted-loader handoff. These are boot-time observations, not a current
policy lock or coverage of reservation tails. Native shutdown/restart and Linux
activation remain outstanding.

The guarded supplier-only final producer is now in personal U-Boot master
`e2a916b716c593840291aad2e03de103bdb57e7d` and passed
[CI38302037174](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38302037174).
It is not installed. Ordinary input DTs remain unchanged; an explicit diagnostic
marker permits supplier/domain0 activation only after fresh successful metadata,
with the modem consumer still disabled. The Linux ON-adoption patch passes
12 static/application checks, but combined native compilation remains pending.
Its immutable-lifetime profile also requires a separate resolved diagnostic
configuration; the installed r182 kernel cannot run that adoption path.

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

At the r181 checkpoint, the modem/SCP loader passed [CI 38235543158](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38235543158).
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
| Boot / UFS | Works for basic boot | Clean r188 boots and reads/writes root; firmware/SKU portability unverified. |
| Root expansion | Works on tested clean install | r188 root reports 104.5 GiB after clean installation; wider lifecycle/SKU coverage remains. |
| Native display | Partial | Route and frame-end updates are in main; no visible stripes/flicker. Fixed 60 Hz and software rendering; 120 Hz and power lifecycle remain. |
| Touch and keys | Works for basic input | Touch and power/volume keys tested; full suspend/wake coverage remains. |
| Sensors | Partial | Corrected U-Boot on r188 restores automatic 24-entry transport and physical mask31; rotation and auto-brightness confirmed. Earlier local-call proximity passed; calibration, warm reboot and suspend remain. |
| USB/NCM/SSH | Partial | Clean boots and transfers pass; reconnect/suspend lifecycle remains. |
| Wi-Fi / Bluetooth | Partial | Earlier association/traffic and discovery demonstrated; profiles, coexistence and suspend remain. |
| Audio | Partial | Earlier speaker paths and microphone capture demonstrated; cellular audio and full route coverage remain. |
| Haptics / torch | Partial | Earlier bounded physical effects tested; lifecycle and camera strobe remain. |
| Battery, charging, thermal | Partial | Telemetry and charging observations exist; sustained safety and idle power remain. |
| GNSS | Partial | One real power/ROM-reset/open/DMA-stop/close cycle passes; DSP code download, navigation INIT, position fix and GeoClue remain. |
| SIM, calls, SMS, mobile data | Broken | BROM, metadata import and real CCIF/DPMAIF resource binding pass; runtime transport, SIM/registration and calls remain unavailable. Proximity testing used a local dummy call, not GSM. |
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

The next [native infrastructure CCF provider](../patches/modem/infra-clocks/README.md)
implements all thirteen B4.1 gates, including the nine CCIF/DPMAIF clocks missing
from d84's provider set. Exact IDs, five register banks and native factor/mux
names pass source checks; 33 isolated-staging checks preserve shipping Kbuild
and DT. Its ARM64 object and genuine r181/r182 module link are selected for the
modem workflow. Both jobs passed
[CI38287440390](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38287440390)
at `e73b77183101b74eb4af555cd3f7a7ab47293d44`. The downloaded ARM64 ZIP matches
GitHub SHA256 `d86e66ccf054288c947330bb1f72e642c8cc986b3efe68b62cbcca7b351bb9ec`.
The actual GPL AArch64 module, genuine imports/vermagic and source identity were
verified; module SHA256
`776edc6960618f7b0c1f65145be28833e92078a6729a5273ae0fd04c49931ef4`.
One guarded load on r182 boot `19e13ae5` at uptime12495.39-12498.74s bound the
existing `10001000.syscon` and registered all thirteen clocks. Every parent
resolved to the expected native factor; all prepare/enable counts remained0.
No enable was requested. Before/after kernel journals are identical; boot ID,
USB, SSH and sensor services are unchanged, with no failed units. The module
remains retained until reboot, not installed/autoloaded. The current IFR node
still lacks `#clock-cells`: real OF consumer references and cold initialization
require DT/package integration. This closes live registration, not physical
gate switching, modem power, transport activation or calls.

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

The [GPUEB resource owner](../patches/gpu/reset-owner-draft/RESOURCE-CONTRACT.md)
now validates all eight real memory windows before MFG0 resume and claims the
four mailbox control words outside the reset bank. Acquisition failures unwind
only completed claims, in reverse order; retained faults still refuse teardown.
Twenty-eight static checks pass, including the stored DTB comparison; one optional
private-LK check is skipped. The actual revised reset/control objects compiled
in CI38287440390; the reset object hash is
`5bc5cd2d426da177f637b46c5ca2518624ee18398172e1b5015a6cb9c729261f`.
These are AArch64 LLVM objects, not a complete linked/loaded GPU driver or
executed acquisition-fault fixture. No mailbox access,
larger firmware upload, IRQ enable, GPUEB start or rendering is added.

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

The supplier constructor now accepts the actual owning device's explicit
regulator supply ID instead of the nonexistent fixed `vmm` relationship. Pinned
B4.1 describes `cam-vcore`; the stored slot uses `cam-main`, but its release is
unverified. No alias guessing is added. Twenty supplier tests reject missing IDs,
fallbacks and lost errors; changed C/H hashes are recorded. Both actual ARM64
KUnit configurations passed CI38287440390; the KUnit-disabled supplier object
hash is `d1e45539cb23f2addf06b57bc9cc9ec4d2627cc836e68d59f4b05a592a0d575d`.
Complete linkage, provider/consumer wiring and physical integration remain.

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
It passed [CI38282916412](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38282916412)
at `090c61b`, with pinned source/binary checks and ASAN/UBSAN native consumers.
The initial run stopped before compilation because the old stock cache expired
after one day. Cache selection now resolves an available artifact rather than
a fixed run ID; retention is 14 days. One public-input refresh passed
[CI38281862668](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38281862668).
Real startup caller integration remains missing.
The common first constructor now keeps these three bytes unresolved until the
explicit producers run; runtime/bundle fixtures preserve that gate. These are
native configuration producers, not an AGPS receiver or successful INIT.
On r181 boot7d4b87cb the explicit GPS transport
probe returned0 at uptime427.85s and created gpsdl0/1 beside the retained SMEM
owner; USB/sensors/SSH remained active. Neither link was opened and no navigation
or position fix was attempted.
See [transport](GNSS_BRINGUP.md) and [userspace research](GNSS_USERSPACE_BRIDGE_AUDIT.md).

The separate production frame worker now retains terminal completion-write
errors instead of obscuring them as a later timeout. Failed publication never
creates an ACK or permits resource release; successful publication has no later
owner access. Nine source checks pass and four injected failure cases are
wired into fortified native CI and the AArch64 Bionic link. All validation jobs
passed [CI38287450780](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38287450780)
at `e73b771`, including actual ASAN/UBSAN failure fixtures, sealed lifecycle and
Bionic linkage. This is a lifecycle correction, not AGPS completeness or a GPS fix.

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
