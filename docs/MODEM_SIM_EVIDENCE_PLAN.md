# MT6878 modem and SIM evidence plan

This document defines the smallest safe next step toward modem support on the
Nothing CMF Phone 1 (`nothing-tetris`). It does not promote modem support and
does not authorize loading a modem module or enabling a DT node.

## Source identity

- Canonical port branch: `main`; current hardware status is recorded in
  `docs/CURRENT_STATUS.md`.
- The original source audit was performed on historical branch
  `codex/scp-thermal` at `cd8fbdf`; its vendor-source conclusions remain the
  input to the current compile-only work.
- Mainline kernel package source: Linux 6.18 at the commit pinned by the
  package.
- Authoritative vendor device modules:
  `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878`, commit
  `ee2be53cb75670b548948636a0db1d1ff112bf12`.
- The vendor commit identifies the Nothing OS 4.1 Tetris B4.1 source drop.
- Exact vendor commit metadata: authored by `lio.chen <lio.chen@nothing.tech>`
  on `2026-05-30T09:30:11+08:00`, subject `Merge codes for CMF by Nothing
  Phone 1 Nothing OS 4.1 (Tetris-B4.1-260415-1709)`. It is contained by the
  official `mt6878/Tetris/16b` remote branch.
- Older branch heads and the `codex/radio-ci` pmaports branch are not modem
  inputs. The latter contains CPU-idle and Wi-Fi power work only.

## Boot-chain trace

This section preserves source-correlated observations needed for unresolved
modem handoff. Installed/candidate wording within each experiment refers to
that experiment, not today's r167 installation. Former U-Boot diagnostic
branches are archived as tags; they are not current deployment instructions.

### r153 handoff evidence

A fresh read-only check on the running r153 phone reports kernel
6.18.0 #154-postmarketos and U-Boot 2026.07-rc1-g60bcf22fdc0a. The published
/chosen/nothing,ccci-handoff-status values are failure=no-fdt,
observation-status=invalid, payload-status=not-checked. USB usb0 is UP before
and after collection. No SMC, modem module, NV access, reboot or power action
was performed. The phone SSH ED25519 fingerprint matched the previously
recorded r153 identity; a separate temporary known-host file was used rather
than changing the user's stale entry.

This is an earlier live failure than the descriptor/payload gates discussed
below. Do not interpret presence of the validator in U-Boot as a successful
handoff on this boot. At installed commit 60bcf22fdc0a94526424db59fc7640298ea8f0dd,
tetris_observe_ccci_handoff() starts with TETRIS_CCCI_NO_FDT. A failed
get_preserved_prev_bl_fdt() or map operation leaves that generic result;
tetris_ccci_read_descriptor() also uses it for a null/invalid FDT. Therefore
the current status cannot distinguish absent early input from a rejected or
damaged preserved copy. The exact errno and early preservation failure must
be surfaced before designing a handoff fix; neither register addresses nor
raw LK/calibration payloads need to be published for that diagnosis.

The installed arch/arm/lib/save_prev_bl_data.c keeps preserved_fdt_error for
console diagnostics but get_preserved_prev_bl_fdt() returns generic ENODATA
when the saved address/size are absent. It revalidates the copy on access.
The selection path prefers x2 only when its FDT contains devinfo, otherwise
tries x0. This is code to inspect, not proof that changing register preference
or relaxing range/FDT validation will fix the live failure.

### Source-diagnostic candidate

The local follow-up candidate is U-Boot commit 38192f202c on
codex/ccci-prev-fdt-diagnostic, based exactly on installed 60bcf22fdc0a.
Its working tree is ../uboot-ccci-prev-fdt. It records bounded x0/x2 FDT
validation errors during early preservation and publishes four diagnostics
alongside the existing sanitized CCCI status:

- source-error: access/revalidation/map result for the preserved source;
- preservation-error: saved early preservation result;
- x0-validation-error and x2-validation-error: bounded validation results for
  the original inputs, without their addresses or content.

These FDT cells encode signed 32-bit errno values in big-endian two's
complement. Absence means the diagnostic was not recorded, not success.
Zero means that specific check passed, never modem-runtime readiness. An
early preservation error distinguishes a failed copy from a later source
revalidation failure; valid inputs with preservation ENODATA direct the next
inspection toward source-selection rules. No range check, x2-devinfo selection
rule, firmware loader, memory handoff or power/SMC behavior is relaxed.

The existing CCCI host suite passes with five new diagnostic scenarios and
an omission/stale-property test. Checkpatch reports zero errors/warnings.
The three changed/relevant ARM64 objects compile in normal and initramfs-only
configurations with Clang 21.1.8. After the initial publication rejection,
the user explicitly approved this exact push. Commit
38192f202c8bc3009efbb1d357b97975768424af is now published on that branch in
xxxvik-xakerxxx/u-boot. CI run 34575135682 passed the full GCC build,
initramfs-only compilation, tests, boot-contract checks and LK packaging.
The downloaded u-boot.bin, u-boot-nodtb.bin and u-boot-tetris-lk.img all
match the artifact SHA256SUMS manifest. This is build/artifact evidence only:
these checks alone do not establish handset execution.

Subsequent controlled installation: on r153, USB/SSH and boot
3334a5ab-4658-4310-b07e-77b6fcaf0fa1 were verified before reboot-to-fastboot.
Fastboot confirmed executable 60bcf22, slot a, product nothing-tetris and
16 MiB LK partitions. The previously proven 60bcf22 recovery artifact was
downloaded and hash-checked; candidate and recovery preserve identical LK
header fields (except payload size) and non-fill template tails. The new
image SHA256 is 359ac6bf4022c3768ec0d794b8b0899282613cbdae248eabadac845d59aa3cf1.
Only lk_a was written, with send/write both OKAY; lk_b, rootfs, trusted
firmware and calibration were unchanged. Reboot lost its USB status reply.
The host subsequently enumerated the postmarketOS USB device, but no USB
network interface appeared while the macOS console was locked. The user
was asked to unlock the host; the outstanding SSH attempt was terminated.
At that stage running loader, boot ID, diagnostic values and healthy SSH
were unverified. Full local record: the artifact directory's LIVE-PLAN.md.

After the user unlocked macOS, one VID/PID/serial-guarded host USB reset
returned success; en4 appeared and SSH returned without another phone
reboot. Boot 6fca0ea2-9c15-4a05-8a9e-ee07fa8a76c6 reports exact U-Boot
2026.07-rc1-g38192f202c8b and unchanged kernel #154/r153. The signed cells
are source=-61, preservation=-61, x2=-61, x0=-74. Failure remains no-fdt,
observation invalid, payload not-checked. USB 32 MiB SHA256 is
83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302;
usb0 stays UP, DRM is connected, no failed units or matching kernel
Oops/panic/DRM timeout found. This is recovery evidence, not seamless
locked-host reconnection or modem functionality.

At this revision, x2 ENODATA means saved x2 is zero. x0 EBADMSG means
either fdt_check_header or fdt_check_full rejected its input; its header
address passed the normal-memory predicate and mapping. It does not
distinguish wrong-format input from a damaged FDT. Do not extend memory
ranges or change source preference on this result. Next establish the
previous-stage input format and validation stage without dumping addresses
or arbitrary memory. No modem SMC, firmware/power or DMA operation ran.

### Bounded tag-header follow-up (local, not installed)

The follow-up working tree on top of 38192f202c preserves x4/x5 at the
original ARM64 entry alongside x0/x2. The offline ATF argument-builder
evidence below motivates checking x0 == x4 and treating x5 as a candidate
byte count; neither relationship has yet been observed on the handset.
The observer rejects missing/mismatched inputs, lengths below eight bytes
or above 2 MiB, and ranges outside the existing normal-DRAM predicate.
It then reads only the first eight bytes, checks a little-endian byte length
within the supplied bound and a tag ID in the 0x8861 namespace. It neither
walks the tag list nor copies tag payloads, and does not alter FDT selection.

The additional signed errno cell `tag-header-error` reports this limited
classification. Zero means a plausible first header, NOT a validated list,
reserved-memory handoff, firmware load, secure-world state or working modem.
No input address, length, ID or payload is published. Existing CCCI status
remains authoritative about its separately checked FDT source.

Host tests extract and compile the actual observer: 17 cases cover early
rejection without mapping, mapping failure, eight-byte-only access,
unmapping, malformed lengths, namespace mismatch and boundary success,
including unchanged input bytes. The existing status suite now checks the
fifth diagnostic and its omission when unobserved; its runner includes the
new test for CI. The actual normal-memory predicate still passes its separate
17 boundary cases. ARM64 normal and initramfs-only object compilation passed
with Clang 21.1.8; disassembly saves x0/x2/x4/x5 and branches back without stack
access. These tests do not prove the live tag format or bootability of this
uninstalled follow-up. The installed device remains on 38192f202c/r153;
USB/SSH and no failed systemd units were rechecked on the same boot.

### Live tag-header result

Follow-up dd40c7d6420d25ecc9cd75ae608cd5b9d1a155d9 was published to
xxxvik-xakerxxx/u-boot/codex/ccci-prev-fdt-diagnostic. CI 34583094081
passed normal build, initramfs-only compilation, parser tests, boot
contract and LK packaging. Downloaded manifest checks passed. The LK
image is 3244336 bytes, SHA256
d82d190ed868f996735bda25b879cdb4fe5f078426e3b9438d48932d0e22da4f.
Exact embedded payload, unchanged header except length and preserved
non-fill tail were checked against the installed 38192f2 artifact.

Only lk_a was written after fastboot confirmed nothing-tetris, slot a and
16 MiB capacity; send/write both returned OKAY. Reboot lost its USB reply.
With the Mac unlocked, USB networking reattached without host reset and
SSH returned after initial service-startup connection refusal. New boot
043e6e88-b832-423c-a58d-50fdf3438684 reports exact dd40c7d6420d, unchanged
r153/kernel #154. The new tag-header-error is 0; FDT source/preservation/x2
remain -61, x0 -74, no-fdt/invalid/not-checked. Therefore the first bounded
MediaTek header is plausible. Full-list validity, tag meaning, producer
execution and modem readiness remain unproven.

Before/after USB 32 MiB SHA256 matched
83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302.
usb0 UP, Wi-Fi connected, Bluetooth powered, DRM connected, no failed
system units. No GNSS download, modem module, SMC, DMA, calibration or
rootfs write occurred. This is one boot, not complete lifecycle validation.
The detailed local procedure and recovery boundary are retained in
local/uboot-dd40c7d-ci34583094081/LIVE-PLAN.md.

### Bounded list diagnostic candidate

The next uninstalled diagnostic is c931695bb9 on the same U-Boot branch.
It walks at most 256 headers only after the existing whole-input normal
memory/header gate passes. Each read is four bytes, never a tag payload.
Sizes must be at least eight and fit the remaining input; a zero-size word
within the supplied bound is required for success. Unknown namespaces fail.
Only a successful walk publishes count and two bitmaps for header IDs
0x88610000..0x8861003f; other IDs in the namespace count but have no bitmap
bit. No addresses, payload sizes, calibration or modem readiness are exposed.
Failure clears summaries. No preservation/source selection rules change.

The byte-stride and zero-size conventions were checked by executing only
the pinned ATF parser 0xb234..0xb4c8 with synthetic inputs and stub consumers.
patches/modem/test-atf-tag-walk.py passes ten cases, including unknown IDs,
unaligned byte strides, payload pointer +8 and the ATF ten-consumer cap.
ATF accepts unknown namespaces and does not establish the boundedness needed
by U-Boot; those behaviors are not copied. The 256-header limit is a
defensive diagnostic policy, not an inferred firmware ABI maximum.

The actual new C walker passes 22 host cases with a fixture that rejects
payload access and checks input immutability, map/unmap balance, truncation,
mapping errors, missing terminator, masks and the 256/257 boundary.
Status tests check summary omission after failure/unobserved input and no
promotion of payload validity. Existing CCCI and 17 first-header tests pass.
The three relevant ARM64 objects compile in normal and initramfs-only
configurations with Clang 21.1.8; checkpatch has zero errors/warnings/checks.
This is static evidence only. Installed loader remains dd40c7d6420d;
complete live list structure and IDs have not yet been observed.

Subsequent live result: CI 34584756418 passed for exact
c931695bb963efaa0dfdf928ea475440581838b4. Manifest, embedded payload,
preserved non-fill tail and header checks passed; image size 3245472,
SHA256 71e26f9f38947e08450f2558fdd13137b52b768d57b26f416cf92f6bc1bcb88c.
After confirming dd40, nothing-tetris, slot a and 16 MiB capacity, only
lk_a was written. New boot 3bcabc1f-8d6e-4c0c-8d97-977eae5affc2 reports
exact c931695bb963. Header-list error=0, count=38,
low mask=0x3b0c7fff, high mask=0x0026ff3b. Popcount equals count, proving
38 distinct IDs within the bitmap range for this bounded observation.
FDT errors remain source/preservation/x2=-61, x0=-74 and
no-fdt/invalid/not-checked. No payload semantics or modem state established.

USB/SSH returned without a host reset despite initial SSH timeout. Mac
was unlocked and en4 active; three ICMP responses passed. Before/after
32 MiB USB SHA256 matched 83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302.
Wi-Fi connected, Bluetooth powered, DRM connected, no failed units or
matching Oops/panic/BUG/refcount/watchdog/DRM timeout log. No GNSS download,
modem operation, rootfs or calibration write. See local live plan.

### Earlier source-range audit

The exact installed base and diagnostic candidate call reserve_prev_bl_fdt
after dram_init/setup_dest_addr/reserve_malloc and before reserve_board,
reserve_global_data, reserve_fdt and stack reservation. The reservation
advances start_addr_sp below its copied FDT on success. Thus the source trace
does not support a simple claim that the copy was never reserved in the
normal enabled configuration.

arch/arm/mach-mediatek/mt6878/init.c caps the probed gd->ram_size at 2 GiB.
The previous-FDT predicate requires BOTH membership in that DRAM interval
and containment in one MT_NORMAL map entry. The board memory map extends
beyond the capped interval; membership in that wider map alone is not enough.
With a synthetic base of 0x40000000 and size 0x80000000, a 40-byte header
ending exactly at 0xc0000000 is accepted and one crossing that end is rejected.
An input beginning at 0xc0000000 is rejected despite a normal-memory mapping.
This is not evidence of the actual x0/x2 input addresses or the live failure.

`patches/modem/check-prev-fdt-range.py ../uboot-ccci-prev-fdt` extracts the
actual predicate and board map, compiles them with a host-only fixture, and
passes 17 boundary/overflow/zero-size/reserved-hole cases. The fixture uses
synthetic memory attribute encodings and never accesses physical memory.
It does not test FDT validity, copying, relocation, MMU behavior or LK inputs.
No memory limit/check was relaxed. An EFAULT diagnostic would still require
distinguishing a capped-range rejection from a reserved/non-normal range;
it would not authorize extending the accessible range by itself.

### Container-stage correction (2026-09-11)

The earlier statement that the complete stock LK necessarily executes
before replacement U-Boot is not established. The exact installed LK
container was walked sequentially using MediaTek header lengths and
16-byte alignment, not an unconstrained magic scan. Its first named `lk`
payload is the byte-verified U-Boot binary. Preserved later entries are
certificates, `bl2_ext`, `aee`, `lk_main_dtb` and `lk_dtbo`. Keeping these
entries is not proof that the replaced stock `lk` implementation's modem
loader or final kernel-FDT hooks have run.

The preserved `bl2_ext` is 711336 bytes, SHA256
170583094d4e4388d8e269cbcc8b14c17df0d4e248dcef57f1d112fba84c004b.
Its strings reference app_load_bl33, platform_load_device_tree, display
initialization, BL31 DTB preparation and PL2LK boot arguments. These are
leads for disassembly, not proof of argument layout, successful modem
authentication or the function reached on the live boot. Template firmware
release provenance must be established separately; no B4.1 label is inferred
from these strings. The upstream lplk utility edits multiple LK components
and is a different packaging path, not evidence that this U-Boot image
executes stock lk first:
https://github.com/MT6878-Mainline/lplk/blob/main/lplk.py

Next trace the actual bl2_ext-to-next-stage argument producer, and distinguish
header from full-FDT validation failure. Do not search arbitrary RAM or
weaken FDT/range checks to manufacture a descriptor. If the modem producer
belongs to replaced LK, native support needs that authenticated loading and
memory-ownership contract, not merely a parser for nonexistent inherited
tags. No production code or bootloader behavior was changed in this audit.

### Bounded bl2_ext disassembly follow-up

The pinned preserved binary was disassembled offline with Capstone 5.0.6;
`patches/modem/inspect-bl2-handoff.py` rejects other bl2_ext hashes, validates
container lengths and bounds requested disassembly to 8 KiB. Its string
xref search emits candidates only; register clobbers/control flow require
manual validation. All offsets below are within the file, not live addresses.

The load sequence around 0x8350 loads the named lk/BL33 image and later
looks up BL31-reserved at 0x8724. At 0x875c..0x8774 it passes the reserved
BL31 base, three saved values and the translated 0x8344 trampoline to
0xd648. The trampoline contains SMC #0. The final helper 0xd3e4 permutes
arguments, disables the EL1 MMU and branches to that trampoline. This
is a secure-monitor handoff, not evidence of a direct Linux-boot-protocol
call into U-Boot. The nearby direct-call helper at 0x8310 must not be
mistaken for the executed path solely because it clears x2/x3.

The entry sequence also stores four original registers at 0x98670 after
its early setup calls. The later load sequence reads a different saved
structure through the pointer slot at 0xad8d0. Their relationship, and
BL31's eventual BL33 register assignment, remain to be traced. Neither the
presence of a DTB loader nor these static calls proves that x0 is an FDT.
The live x0 EBADMSG remains the governing observation. Do not change
source selection or guess a boot-argument struct before closing this gap.

No binary was executed, no new U-Boot image was built, and no hardware
operation followed this disassembly. Template release provenance remains
separate from the measured hash and must not be labeled B4.1 without proof.

### Exact ATF input and parameter-builder trace

On boot 6fca0ea2-9c15-4a05-8a9e-ee07fa8a76c6, the active tee_a header
identifies an `atf` payload of 900240 bytes. Only its 512-byte header and
declared payload were read, not the remaining TEE partition. Local file
SHA256: ee71f42fe4fa6b3e671ead5ca9c57995ba0631ebdb7b32509d0df3cda7f08287;
payload SHA256: 05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e.
The binary remains ignored/local. USB stayed UP and SSH returned after the
read; no write, SMC or modem operation occurred. This is exact installed
firmware identity, not independently authenticated release provenance.

In bl2_ext, 0x8084 stores four incoming arguments into the structure used
by its later secure handoff. Consumers map its first pointer as a 4 KiB
`vm-bl-reserved` BL parameter region; one writes offset 0x10, another
offset 0x18. This is not the layout of a flattened device tree.

In the read-back ATF, 0x2761c builds a non-secure entry-point descriptor:
it copies parameter+0x10 to the entry PC, parameter+0 to argument 0 and
argument 4, and parameter+8 to argument 5. Getter results populate
arguments 3, 6 and 7. These offsets follow the descriptor's 0x18 start of
64-bit argument storage. The setup caller is at 0x276d0. A separate ATF
parser at 0xb234 dereferences parameter+0 as a list with byte length at
offset 0, tag ID at offset 4 and payload at offset 8, including
0x88610001..0x88610025 tags. Thus the static producer strongly supports
a tag-list interpretation of U-Boot x0, consistent with live EBADMSG;
the actual live tag header has not yet been observed.

Do not substitute x3 as FDT: its getter 0x118ac returns a value populated
by handler 0x193a8 for tag 0x88610025 (init_gz_plat), not a proven FDT
handoff. Next close the entry-descriptor-to-live-register trace and add
bounded tag-header/length validation before preserving any such input.
Do not copy a whole boot-argument area, publish addresses or infer CCCI
runtime readiness from the existence of non-modem platform tags.

`inspect-bl2-handoff.py --component atf` pins this payload hash for bounded
offline disassembly. No change to U-Boot source selection has been made.

`patches/modem/test-atf-bl33-args.py` now executes the actual 0x2761c builder
in ARM64 Unicorn with synthetic parameters. Six cases cover both selected
exception-level states, zero and wide values, the complete descriptor and
surrounding guards, unchanged input, preserved stack and exact getter-call
order. They confirm PC=parameter[2], arg0=arg4=parameter[0] and
arg5=parameter[1]. Arguments 1/2 are untouched by this builder, not actively
cleared; any zero-value claim also depends on descriptor initialization.
The three getter results map to args 3/6/7, with arg6 zero-extended from
32 bits. Unexpected execution stops the emulator. No SMC or firmware entry
executes, and no synthetic pointer is used on hardware.

U-Boot's ARM64 reset branches to save_boot_params before PIE relocation,
so retaining additional incoming registers is technically possible there.
The current implementation records only x0/x2. A follow-up diagnostic must
retain the producer's pointer/length pair, check agreement and normal-memory
bounds, and classify only bounded headers before any tag preservation or
parser integration. The emulator result does not validate the live list,
its length, tag meanings, lifetime, or modem firmware/memory ownership.

### Historical validator results

The installed boot path does not reproduce the Nothing OS modem handoff. A
newer installed U-Boot validates its structure but deliberately does not start
the modem:

1. MediaTek early boot stages precede U-Boot; execution of the complete stock
   LK is not proven and must not be assumed (see container correction above).
   Trusted firmware remains resident and may implement the
   MediaTek SiP ABI, but support for each CCCI request has not been measured.
2. Previous rollback U-Boot `8aa048f93bb7569e4107ef85aa994c630f85de48`
   preserves the prior LK/FDT and conninfra handoff work.
3. Installed U-Boot `b76e47e774304ab550a6354f3286860b7caffb3a`
   validates the bounded B4.1 descriptor, required payload tags, modem/check
   headers, image and shared-memory layouts. It publishes sanitized status and
   sizes only: no physical addresses, SMC call, power/reset, firmware load or
   `runtime-ready` claim. CI run `33492618726`, normal boot and Linux-to-fastboot
   reboot pass with this revision installed in both boot slots.
4. The postmarketOS FIT embeds its own `mt6878-nothing-tetris.dtb` and loads it
   at `0x47000000`. The FIT configuration selects that FDT explicitly. No code
   in the current boot path copies `ccci,modem_info_v2`,
   `ccci,modem_info`, or the referenced LK tag buffer into this DT.
5. Linux therefore still lacks an enabled modem consumer and a proven runtime
   memory/power/secure-world contract. Adding disabled inventory or parsing a
   valid descriptor does not make the modem usable.

The B4.1 kernel expects `ccci,modem_info_v2` on the `mediatek,mddriver` node.
That property points to a physical LK tag buffer containing at least the modem
header table, image location/size, memory layout, check header and shared-memory
layout. The parser consumes keys including `hdr_count`, `hdr_tbl_inf`,
`md_mem_layout`, `md1_chk`, `md1img`, `smem_layout`, `nc_smem_info_ext`, and
`md1_phy_cap`. A legacy `ccci,modem_info` property is the only alternate LK
format.

If neither LK property exists, `ccci_util` falls back to DT-calculated memory.
That path still requires a reserved-memory node compatible with
`mediatek,reserve-memory-ccci_md1` or a complete `mediatek,ccci_util_cfg`
contract. Draft `0031` supplies neither, so the correct result is modem
disabled.

The vendor FSM does not load the modem image from Linux. `md_cd_start()` says
`modem image ready, bypass load`; it validates a check header copied from the LK
tag buffer and uses the preloaded MD bank address. A `request_firmware()` based
loader is not present in this path. A maintainable pmOS port therefore needs
one of two explicitly designed owners:

- reproduce the complete authenticated LK loader/handoff in the boot chain; or
- implement a Linux firmware loader with a documented signed-container and
  secure-world protocol.

Silently depending on whatever stock LK left in RAM is not an acceptable cold
boot contract.

## Partition and calibration ownership

The live phone exposes 200 MiB `modem_a`/`modem_b` slot firmware partitions,
an 8 MiB `md_sec` partition, ext4 `nvdata`/`nvcfg`, and a separate raw `nvram`
device. The exact B4.1 modem image is 90214400 bytes, but Linux's vendor FSM
explicitly bypasses image loading and expects the authenticated LK handoff.
The owner and format of `md_sec` are not yet proven. CCCI also defines an
`SMEM_USER_MD_NVRAM_CACHE` region without identifying the userspace component
which fills it from persistent storage.

Never copy IMEI, SIM-lock/provisioning, radio calibration, anti-clone data,
whole NV partitions, `md_sec`, LK tag buffers or physical addresses between
handsets. Any future extractor must read a bounded, versioned record from the
same device and fail closed on absence or mismatch.

## Stock userspace contract

The stock-derived Tetris device tree confirms a dual-SIM DSDS configuration
with `ro.vendor.mtk_ril_mode=c6m_1rild`. Its proprietary manifest requires
`ccci_mdinit`, `ccci_rpcd`, `mtkfusionrild`, `libccci_util.so` and the MediaTek
RIL libraries. The product enables Android Radio AIDL v2 services for data,
messaging, modem, network, SIM and voice, plus MediaTek extension interfaces.
This is evidence for the expected control plane, not permission to copy the
Android blobs into pmOS.

The preferred maintainable path is a bounded native bridge from documented
CCCI control/port messages to a standard Linux telephony API. A compatibility
fallback could retain the matching Android `IRadio` service behind an
oFono/Binder adapter, but that imports a much larger proprietary Android ABI
and must be evaluated separately. ModemManager has no generic MediaTek CCCI
plugin; a CCMNI interface or `/dev/ccci*` node alone is not calls/SMS/SIM
support.

## Status of draft 0031

`0031-arm64-dts-mediatek-mt6878-modem-foundation-disabled.patch` is inventory,
not a modem implementation. It adds disabled DPMAIF, CCIF, MD1 and CCCI-SCP
nodes and disabled SIM hot-plug nodes. It omits clocks, power domains, syscons,
regulators, reserved memory and firmware ownership, so no node can probe.

The transport register windows and IRQs match the B4.1 vendor DT:

| Block | Vendor evidence |
| --- | --- |
| DPMAIF | `0x10014000`, `0x1022d000`, `0x1022c000`, `0x1022e000`; SPI 238 and 259; hardware v3 |
| CCIF | `0x10209000`, `0x1020a000`; SPI 228 and 229; SRAM size 512 |
| MD1 | `0x0d180000`; watchdog SPI 491; AP platform 6878; modem generation 6299 |
| CCCI-SCP | `0x1023c000`, `0x1023d000` |

The SIM interrupt conversion is not proven. The B4.1 board DT uses the vendor
EINT cells `<0 8>` and `<1 8>`. The MT6878 pinctrl table identifies GPIO46 and
GPIO47 alternate functions as UIM0/UIM1 hot-plug, which supports the draft
hypothesis, but it does not prove that the vendor EINT indices map directly to
mainline Linux IRQ specifiers 46 and 47. CCCI obtains the SIM data through its
RPC ABI (`port_rpc.c`), including `sockettype` and `src-pin`; these nodes must
remain disabled and must not be represented as `gpio-keys`.

Static checks performed on the current draft:

- `patch -p1 --dry-run`: both DT files apply without fuzz or offsets to the
  prepared post-stable-patch Linux tree.
- `scripts/checkpatch.pl --strict`: 0 errors and 7 warnings. One warning is the
  external vendor commit not existing in the mainline repository; six are the
  intentionally undocumented vendor compatible strings. The compatible
  warnings prevent treating this DT as upstream-ready.
- A fresh DTB rebuild could not be repeated in this audit: host GNU Make 3.81
  is too old, the project path contains spaces, and the Docker runtime stopped
  while its temporary Alpine filesystem was read-only. The patch was reversed
  after each attempt and no modem node remains in the prepared source tree.

Conclusion: keep `0031` untracked and out of `APKBUILD`. Before integration,
either remove the unproven SIM IRQ nodes or add a separately reviewed EINT
translation with binding and live evidence. Disabled vendor compatibles alone
do not provide a maintainable interface.

Enabling only `mddriver` is not a passive probe. The B4.1 probe path enables
runtime PM and immediately calls `pm_runtime_get_sync()` with the vendor comment
`match lk on`. First boot then performs CCCI SMC boot checks, power transitions,
PLL setup and `MD_KERNEL_BOOT_UP`. No node from `0031` may be changed to `okay`
until that inherited-LK behavior is removed or replaced with an explicit,
validated handoff.

## Exact dependency chain

The B4.1 ECCCI stack is not a single driver. Its minimum path is:

1. `ccci_util`: parses boot arguments, modem image metadata and reserved-memory
   contracts and enables modem image security checks.
2. ECCCI core/FSM plus CCIF and DPMAIF HIF modules.
3. CCMNI for packet data and the CCCI port/RPC ABI for control, SIM and userspace
   channels.
4. MT6878 infracfg/topckgen clocks, MD power domain, MT6363 modem regulators and
   DPMAIF reserved DMA memory.
5. SCP IPI/shared-memory synchronization for the CCCI-SCP path.
6. Trusted firmware support for `MTK_SIP_KERNEL_CCCI_CONTROL`. Vendor code uses
   this SMC for power configuration, boot release, flight mode, clock requests,
   boot status, SCP synchronization and debug operations.

7. A legitimate, version-matched modem firmware image and modem memory layout.
8. A Linux userspace integration that exposes standard WWAN/ModemManager
   behavior without depending silently on Android daemons or userdata.

The current port has only partial prerequisites. It has generic MT6878 scpsys
groundwork and PMIC register definitions, but does not have a validated MD power
domain sequence, the required infracfg modem clocks, the bootloader/ATF modem
handoff, modem reserved memory, firmware provenance, or a standard userspace
control path.

## Current compile boundary

The active LLVM 21 gates cover CCCI util, core, CCIF, modem common, and the
complete vendor FSM/port/non-page-pool-DPMAIF object groups from pinned Linux
`d84b264a` and Nothing OS 4.1 device modules `ee2be53c`. Patch `0095` adds the
last Linux 6.18 source compatibility needed for 39 new individual objects.
No ECCCI or DPMAIF module is linked, packaged, autoloaded or run.

The selected objects still leave 241 external references after internal
resolution. The numeric CCCI command fallback allows compilation against the
mainline SiP header but is not evidence that installed trusted firmware accepts
the command or implements its semantics. That firmware contract remains a hard
runtime blocker.

### Memory and isolation trace

There are three separate memory contracts:

| Memory | B4.1 owner | Required behavior |
| --- | --- | --- |
| MD ROM/RW plus AP-MD shared memory | LK tag buffer or `mediatek,reserve-memory-ccci_md1` fallback | Address and size must be reserved before normal memory allocation; layout must match the signed image header and MD view. |
| DPMAIF cacheable pool | Dynamic reserved-memory node, size `0x190000`, 4 KiB alignment | Vendor driver obtains the region by compatible, converts it with `phys_to_virt()`, maps it for DMA and clears it. |
| DPMAIF non-cacheable pool | Dynamic `no-map` reserved-memory node, size `0x50000`, 4 KiB alignment | Vendor driver maps it with `ioremap_wc()` and clears it before use. |

The B4.1 DPMAIF node has no `iommus` property. The transport uses the Linux DMA
API, but the source does not prove that a mainline IOMMU domain isolates its
transactions. Modem memory protection is instead coupled to MediaTek EMI
MPU/SMPU callbacks, MD/AP memory-view negotiation and secure firmware. Until
those protections are represented and validated, DPMAIF must not perform DMA.

The dynamic DPMAIF reserved-memory nodes are also not passive inventory: they
reserve about 1.9 MiB during early boot even if transport probing is deferred.
They should be added only with the DPMAIF driver patch and exact binding, not to
`0031`.

### SMC trace

The exact B4.1 call is `MTK_SIP_KERNEL_CCCI_CONTROL`, MediaTek SiP command
`0x505`. Its request IDs include:

| Request | Use in vendor stack | Risk if called without contract |
| --- | --- | --- |
| `MD_CLOCK_REQUEST` | AP/MD source-clock ownership and wake/sleep state | Clock leak, stalled transition or invalid secure state |
| `MD_POWER_CONFIG` | BROM checks, LK/kernel boot stage, boot release and PLL stages | MD power transition, reset or boot from invalid memory |
| `MD_FLIGHT_MODE_SET` | Secure flight-mode state | Radio/power state divergence |
| `CCIF_CLK_REQUEST/RELEASE` | Secure CCIF clock arbitration | CCIF hang or leaked clock |
| `SCP_INFO_TO_SAVE`, `SCP_CLK_SET_DONE` | SCP shared-memory and clock synchronization | SCP/CCCI ABI corruption |
| debug/remap requests | MD register remap and dumps | Unauthorized or invalid MMIO mapping |

The source defines request numbers but does not prove that the currently
resident trusted firmware implements the same ABI or return semantics. A raw
SMC probe is not observation-only and is forbidden before an authoritative ATF
source or non-mutating capability interface is identified.

## Minimal next patch

The next code patch should be a **compile-only Linux 6.18 compatibility patch
for `ccci_util`**, generated from the exact B4.1 commit. It must not contain DT,
Kconfig defaults, package autoload policy, firmware, reserved-memory addresses,
or changes to CCCI power/reset behavior.

Required procedure:

1. Archive only `drivers/misc/mediatek/ccci_util` and its exact required headers
   from commit `ee2be53...`; never build the moving vendor branch head.
2. Build only `M=drivers/misc/mediatek/ccci_util` against the exact prepared
   Linux 6.18 kernel/config used by CI. Record the first compiler failure.
3. Adapt only real Linux API changes. Do not suppress implicit declarations,
   incompatible pointer types, integer conversions, or modpost failures.
4. Require `checkpatch`, clean patch application, successful object/module
   build, `modinfo`, and a reviewed unresolved-symbol list.
5. Keep the result outside `APKBUILD`, the rootfs and module autoload lists.
   Building the module is the whole experiment; loading it is explicitly out of
   scope because its init path parses modem boot arguments and memory contracts.

Only after `ccci_util` is clean should separate compile-only patches address
CCMNI, ECCCI core/FSM, CCIF and DPMAIF. `conn_md` and `mddp` remain excluded.
This ordering keeps the first failure attributable and avoids a monolithic
vendor-stack port.

The later runtime patch must add an explicit fail-closed handoff gate before any
platform driver registration or runtime-PM call. At minimum it must reject:

- absent or malformed `ccci,modem_info_v2`/legacy handoff;
- an image header whose platform, generation or memory size does not match;
- overlapping, non-reserved or unit-specific physical regions;
- missing DMA isolation/MPU ownership;
- unsupported CCCI SMC ABI;
- missing MD power domain, regulator or clock suppliers.

Failure must leave MD, CCIF and DPMAIF unpowered, with no IRQ requested and no
DMA mapping. It must not retry, reset SCP, reboot the phone or degrade USB/Wi-Fi.

## Evidence required before any live modem probe

All of the following are stop/go gates:

- Prove the bootloader and trusted firmware implement the exact CCCI SMC ABI
  used by B4.1, including return-value semantics. Do not test this by issuing a
  modem power or boot SMC first.
- Derive every modem and shared-memory region from authoritative partition/FDT
  metadata. Do not copy a physical address observed on one handset.
- Identify the signed modem firmware container, version/SKU selector, loading
  path and legal packaging boundary. Preserve per-device radio identity and
  calibration; never commit IMEI or calibration data.
- Add bindings and clock IDs for the MT6878 DPMAIF/CCIF/MD resources before a DT
  consumer is enabled.
- Implement and validate the MD power domain and regulator sequence without
  relying on state inherited from stock LK.
- Prove the SCP transport and shared-memory ABI independently; do not reset SCP
  or load/unload its owners during modem experiments.
- Trace the userspace control path from CCCI ports to a standard WWAN or
  ModemManager-visible interface. A `/dev/ccci*` node alone is not success.
- Establish a clean-boot rollback artifact and verify USB NCM/SSH, Wi-Fi and
  Bluetooth immediately before the test.

## First permitted live experiment

The first live experiment is observation-only: boot a CI image with all modem
DT nodes disabled and no modem modules installed, then record the current FDT,
reserved-memory map, boot arguments, firmware/partition metadata visible through
documented read-only interfaces, and ATF capability evidence. It must not call a
CCCI SMC, request modem IRQs, enable a regulator or power domain, map modem
memory, or load `ccci_util`.

### Read-only live gate

Run this only on the current clean CI image with the modem draft absent from the
active patch series:

1. Record kernel release, boot ID, bootloader artifact hash, slot, rootfs image
   commit and DTB hash.
2. Pass the existing USB NCM/SSH regression gate, including the 32 MiB transfer.
3. Keep one SSH control session. Record Wi-Fi association, routed traffic and
   Bluetooth controller state before and after collection.
4. Copy the live FDT from `/sys/firmware/fdt` through SSH and decompile it on the
   host. Record only property names, region boundaries and hashes; do not commit
   unique identifiers or payloads.
5. Capture `/proc/cmdline`, `/proc/iomem`, `/proc/interrupts`, loaded modules,
   `/sys/kernel/iommu_groups`, power-domain state where exposed, and the absence
   or presence of `/dev/ccci*`, `/dev/wwan*` and `/dev/cdc-wdm*`.
6. Verify that the live FDT has no enabled `mediatek,mddriver`,
   `mediatek,ccci_ccif`, `mediatek,dpmaif` or `mediatek,ccci_md_scp` consumer.
7. Search the FDT for `ccci,modem_info_v2`, `ccci,modem_info`,
   `mediatek,reserve-memory-ccci_md1` and the two DPMAIF reserved-memory
   compatibles. Presence is evidence to inspect, not authorization to map it.
8. Repeat the USB transfer and routed Wi-Fi check. Stop if either regresses.

Prohibited during this gate: `/dev/mem`, debugfs register writes, raw SMC calls,
`modprobe`/`insmod`, regulator or clock writes, runtime-PM forcing, SCP reset,
suspend, and any modem partition write.

The gate passes when the evidence bundle is complete, hashes are recorded,
USB/Wi-Fi remain unchanged and no modem owner was activated. It does not change
the subsystem status from `Broken`/`Untested`.

The first later module-load experiment is allowed only after the compile-only
series and every prerequisite above pass. It must start with one persistent USB
SSH control session, a clean boot, complete baseline logs and a defined fastboot
rollback. Stop at the first error or any USB/Wi-Fi regression and recover by a
clean reboot; do not unload/reload modem, SCP or connectivity modules.

## Definition of modem progress

### 2026-09-11 network object continuation

Two offline candidates in `patches/modem/` now adapt CCMNI sysctl/GRO access
and RPS header ownership to Linux 6.18. Both ARM64 objects compile against
the prepared diagnostic tree. The exact-source host flush harness passes
48 cases and rejects a stale queue-count mutant. The first compile failures
and an initially unexported GRO helper dependency are recorded in that
directory's README; the final CCMNI object uses the public receive-list API.
This advances the previously missing CCMNI dependency, not modem boot or
the earlier 241-reference full-stack closure. No loadable modem module,
package activation or phone state change was made.

The read-only phone check found USB UP, ModemManager active, an empty WWAN
class, no CCCI/GPS device nodes and inactive GNSS transport service. A running
ModemManager daemon is not a detected modem. Installed r153 was preserved.

### 2026-09-11 combined object dependency audit

The earlier 241-reference partial count is superseded by the reproducible
64-object inventory in `patches/modem/object-symbol-audit.json`, not by a
module-link result. Additional core/CCIF/util objects and the unmodified
ADC/UDC wrappers compile with clang 21.1.8. Candidate 0003 conditionally
registers the MDSS crash dump only when the Android AEE provider is configured;
both enabled and absent-provider object variants were checked. No memory or
modem-power semantics changed. The final 242 references are classified in
`patches/modem/README.md`; configured exports, module boundaries and final LTO
remain unverified. No installed artifact, modem state or SIM result changed.

### 2026-09-11 composite code generation

The vendor Kbuild compositions now produce actual ELF64/AArch64 relocatable
objects for ccci_md_all, ccci_util_lib, ccci_ccif and ccci_dpmaif. The DPMAIF
gate passed with CONFIG_PAGE_POOL=n and, after candidate 0004, with y.
Candidate 0004 updates page-pool includes and sysctl registration only.
Separate composite inventories preserve hashes and dependencies for both
variants. Compile-time bad-copy references disappear during code generation.
This closes that intermediate question, not final module linkage or hardware
readiness. Clang 21.1.8 and LLD 22.1.8 were used; CI equivalence is unproven.

The exact r153 CI run has no saved Module.symvers/development-tree artifact.
Actual configured exports and modpost remain required. The vendor page-pool
CMA ownership, recycling and DMA lengths need runtime-oriented review before
activation. No .ko, CI rebuild, firmware write or live modem probe was made.

### 2026-10-07 remap and protection contract

Offline analysis uses the LK container SHA256
`29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f`
and the installed ATF payload SHA256
`05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
Offsets are relative to each payload, excluding the 512-byte container header.
The ATF container file hash `ee71f42f...` recorded above includes that header;
it is not a different ATF version. Neither input was executed on the phone.

Correction (2026-10-08): SIP registration at `0x23cb0` proves a `<QIIQQ>`
record: handler, SMC32 ID, SMC64 ID, name pointer, writable index pointer.
The previous `<IIQQQ>` parse started eight bytes late and selected the NEXT
handler. Entry `0x58bc0` binds LK_CCCI_CONTROL `0xc200040b` to `0xbe28`,
matching stock LK. KERNEL_CCCI_CONTROL `0xc2000505` instead binds to `0xbf2c`.
U-Boot's unenabled candidate again uses the correct LK ID. The earlier
claimed LK/ATF mismatch was an audit error, not a firmware incompatibility.
The LK dispatcher sends commands 1/2 to `0x1bbe0`
and `0x1bcf0`. They encode sixteen consecutive 32 MiB pages into six bank-0
remap registers, using ten bits per physical page. They check only whether
the base lies inside the reported DRAM, returning `-7` otherwise; a dispatcher
lock can return `-15`. This does not validate the entire 512 MiB window or
alignment. U-Boot `b9d96e38da` therefore bounds the complete reservation,
requires 32 MiB alignment and rejects truncation beyond the 35-bit aperture.
Its pure planner computes masked expectations, without SMC or MMIO access.
Command 2 returns a register readback in x0, not a zero-only success code;
LK's check for `-15` alone is insufficient for a new caller.

LK `0x8196c` stages 24-byte rows at `0x198678`: 64-bit base, 32-bit size,
flags, logical ID and hardware slot. `0x81804`, called from `0x253cc`, later
iterates twelve rows. It skips rows without flag bit 0 or with bit 7 set;
bit 1 selects the extra `0x7ee38` call. That wrapper issues `0x82000415`
command 6 with slot and logical ID. The common `0x7ef84` path forms the
start/end range; its platform-type-2 branch issues `0x82000415` command 0
with start/end shifted by 12 and the slot. The other platform branch writes
registers directly, but the pinned LK selector at `0x16ea0` returns constant
2: this image takes the SMC path. LK's loop does not check these helper return
values.

The pinned ATF's BL_EMIMPU_CONTROL `0x82000415` / `0xc2000415` maps through
entry `0x58e80` to `0x2f750`. The following command-2/6 results belong to this
bootloader interface. EMIDBG instead uses handler `0x2f6f8`; `0x308ac` is
TEE_EMI_MPU_CONTROL (`0x82000048`), not BL_EMIMPU. Command 0 reaches
`0x2f618`. The range helper at `0x10300` masks both page inputs to 24 bits,
checks ordering and subtracts the `0x40000000` origin. The writer `0x2d61c`
keeps only 23 relative page bits. Callers must reject truncation, not trust
successful return. The slot guard at `0x10380` consumes modem slots before
writing: repeat attempts return `-4`, while invalid bounds/slots return `-3`.
Exceptions 8/10/11/19 are not in the modem's 32..43 table. Command 2
subcommands 0/1/3 report start, raw end and enable state. The raw end getter
includes its register bit-31 marker shifted to result bit 43.

U-Boot `1167c6c1d9` encodes aligned, nonempty modem ranges and exact raw
readback expectations, rejecting unrepresentable endpoints before any SMC.
It follows LK's `start + size` endpoint convention; it does not establish
whether hardware treats that endpoint as inclusive or exclusive. No boot-time
caller, reservation or protection transaction is enabled.

Command 6 reaches `0x2f5c4`; `0x5aa8` allows only slot 40 with preset 0..3.
The table at `0x5a2b0` selects domain/value pairs: preset 0 is (35,2)/(47,2);
1 is (35,3)/(47,3)/(93,3); 2 is (35,3)/(47,2)/(93,2); 3 is
(35,2)/(47,3)/(93,3). `0x2d9c4` applies these through `0x4f28`, which
ORs the requested permission bits into the selected readback. It does not
replace an arbitrary prior policy. Domain labels and permission meanings are
not inferred from these numeric values. Fresh-state and permission readback
checks remain necessary before a hardware transaction.

`patches/modem/test-atf-emi-contract.py` now runs the pinned instructions with
Unicorn 2.1.4, synthetic stack/state and emulated register storage. All 64
scenarios pass: exact range writes, address endpoints, readbacks, one-shot
rejection, malformed requests, truncation and each allowed preset with zero
and preexisting permission bits. Unexpected execution/writes stop the test.
The prior emulator crash was resolved by permitting local JIT execution;
no C compilation or phone access was involved. Reproduce with:

```sh
python3 -B patches/modem/test-atf-emi-contract.py /path/to/atf-declared-image.bin
```

Dependencies are Unicorn 2.1.4 and the private, exact 900752-byte header/payload
snapshot identified above; its hash is checked before execution. No proprietary
image is committed or uploaded to CI. These tests cover an internal handler,
not SMC dispatch on real hardware. Native U-Boot compilation/tests run in CI.
U-Boot's `tools/tetris-sip-dispatch-contract.py` separately executes actual SIP
registration and outer routing, stopping before subsystem handlers. All 64
synthetic-state cases pass. With a non-secure caller and policy word
`0x5aea4 == 1`, state byte `0xf796a == 0` routes LK CCCI/BL EMI; state 1 routes
kernel CCCI/EMIDBG instead. Opposite-stage calls do not reach their handlers.
Policy word 0 reaches a rejection diagnostic. No hardware state was modified;
these payload-relative offsets do not establish the phone's current state.
Still required: hardware endpoint semantics,
initial permission state/readback, full table construction and reservation
ownership, shared memory and modem release. This remains `Untested` modem
bring-up infrastructure, not working SIM/calls.

U-Boot's transport-injected EMI transaction now requires an independently
established expected policy. It rejects enabled slots, compares all eight
packed policy words before the sole range write, verifies start/raw-end/enable,
then compares policy again. It stops on the first error without retry and
validates reservation bounds before any callback. Native fault injection
covers all 21 results, including missing outputs with zero/all-ones policies.
There is still no production SMC adapter or boot caller. Expected policy
values remain unresolved; never accept current readback as their replacement.

The pinned ATF exposes permission readback through operation 2, query 4:
arguments are `(2, 4, slot, group)`. Handler `0x2f464` selects 32 consecutive
domain indices, reads the slot's two-bit field and packs them into x0.
Groups 0..7 cover selectors 0..255; first selector occupies bits 1:0. Access
uses selector register `0x103519bc`, a `dsb sy`, then slot-dependent read word
`0x103519e4 + 4*((slot-1)/16)`. No permission commit is performed, but selector
access must be serialized. The emulator adds 96 independently varied cases
covering all modem slots/groups and checks that only selector writes occur.
This proves the readback ABI, not domain names, hardware policy correctness or
which selectors correspond to implemented domains. Full-width replies may be
all ones, so interface/stage admission cannot be inferred from that value.

Independent source cross-check: local Nothing device-module snapshot
`957dac185efe46cbf6336b0fff9516d84c8cd78f`,
`include/soc/mediatek/emi.h`, defines `MTK_EMIMPU_READ_AID` as 4.
`drivers/memory/mediatek/emi-mpu-test-v2.c` calls the selector an AID and
decodes each two-bit value as 0 = No, 1 = WO, 2 = RO, 3 = RW, with the first
AID in the low two bits. This corroborates the packed ABI and permission
labels, not the hardware identity behind each AID or the correct modem policy.
The driver obtains AID count and group size from DT; the 256-selector emulator
coverage must not be reported as a measured count of implemented domains.
U-Boot CI `37739687406` passed for policy verification commit `9bc8195573`;
no hardware protection transaction has been issued.

### Preloader policy recovered from boot LUN

Read-only acquisition on boot `2fd66df3-f3ac-47e5-8fcf-fe368b22f3f4`:
UFS boot LUN `/dev/sda`, 4194304 bytes, SHA256
`0be9c0df9c5d5db641744996630b95920f6e69dcb1ca340511f7d75886676f00`.
The GFH image begins at LUN offset `0x1000`, declares size `0xd0b9c` and
load address `0x02000f00`; its declared-image SHA256 is
`5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f`.
No partition or register was written. The private binary is not committed.
Reading this LUN does not independently prove the boot ROM selected it.

The table at image VA `0x020bf058` contains 64 rows of `0x410` bytes:
name pointer at +0, slot byte at +8, AID/permission byte pairs at +9 and
+0x209. Walkers `0x0207d3f0` and `0x0207d478` select these two pair lists.
`patches/modem/test-preloader-emi-policy.py` verifies the image hash and
executes both complete walkers, intercepting the writer before MMIO. Each
observed call must exactly match the independently parsed table.

| Slot | Stock label | First-list AID:permission | Second list |
| --- | --- | --- | --- |
| 32 | md_mem_mcu_rom | 35:RO, 47:RO | empty |
| 33 | md_mem_dsp_ro | 35:RO, 47:RO | empty |
| 34 | md_mem_dsp_rw | 35:RW, 47:RW | empty |
| 35 | md_mem_mcu_drdi | 35:RW, 47:RO | empty |
| 36 | md_mem_mcurw_hwrw | 35:RW, 47:RW, 93:RW | empty |
| 37 | md_mem_mcurw_hwro | 35:RW, 47:RO, 93:RO | empty |
| 38 | md_mem_mcuro_hwrw | 35:RO, 47:RW, 93:RW | empty |
| 39 | empty label | 47:RW, 240:RO, 241:RO | 240:RO, 241:RO |
| 40 | md_mem_mcu_padding | empty | empty |
| 41 | md_consys_smem | 35:RW, 37:RW, 47:RW, 241:RW | 240:RO, 241:RO |
| 42 | ap_md_nc_smem | 35/38/39/42/43/44/45/47/241:RW | 241:RW |
| 43 | ap_md_c_smem | 35:RW, 40:RW, 47:RW, 241:RW | 240:RW, 241:RW |

Writer `0x0207d310` reads the current selected policy, ORs the requested field,
commits, then clears staging words. Clearing staging does NOT clear the
committed policy. These lists therefore establish requested rights, not a
proof that all unlisted AIDs start denied. Caller `0x0207d594` chooses different
paths; do not concatenate the lists or call them universal cold/warm profiles.

The extended test executes that caller and the real predicate at `0x0207beb8`,
including the `aee_enable` comparisons at `0x0207bd40`. It passes 180 cases:
unset/mini/full/no/unknown configuration, six watchdog words, exception values
0/1/127 and diagnostic magic absent/present. The hardware exception read is
emulated at `0x1c00a024` (bits 10:4); watchdog input is synthetic state at
`0x020f6f30`. No phone MMIO is read. Hardware helpers and policy writes are
intercepted, with their order checked; unexpected code/writes fail the test.

`aee_enable=no` forces the first list. Otherwise, a nonzero exception field or
watchdog status outside {0, 2, 0x800} selects the second list, after the separate
helper at `0x020068c8`. The first list follows the reset/setup helpers and is
followed by commit/lock setup. These helper bodies are not validated by this
test. The diagnostic magic changes logging only. This establishes an AEE
normal/abnormal branch, not a cold/warm profile or known permission reset state.
An inverted branch in a synthetic image copy is rejected by the same test.
U-Boot commit `04b9a0c10d3c832f6d45043e4b494b5cc02a7216` contains the shared
policy planner and native fault-injection tests; CI `37771457999` passed.
No local C/U-Boot build was run and this loader is not installed.

U-Boot's `tetris_modem_plan_emi_policy()` produces a strict candidate for slots
32..38 and normal-path shared slots 41..43, gated by the exact declared-image
digest. Shared slots use the first list only; AID 240 remains denied.
Unlisted AIDs must read
as denied; that is an acceptance requirement, not an inferred reset default.
Its existing transaction checks all fields before and after the range write.
Unknown digests and slots 39/40 fail without changing output. Slot 40 requires
the separate ATF preset; shared memory still needs its phase/ownership chain.
No automatic selector or boot caller is enabled, and SIM status is unchanged.

On installed r172 boot `4377a6ee-a2a3-48f5-bd41-f03dd9b12006`, a read-only DT
check still reports `failure=no-fdt`, observation `invalid`, payload
`not-checked`. The diagnostic reservation exists but does not provide a valid
CCCI handoff. No modem module, SMC or register probe was executed; USB/SSH and
system services stayed healthy. The nine exact r172 CI module hashes passed
offline verification. Linking alone does not authorize loading this stack.

The source cross-check above also has `mt6878.dts` `nsmpu@10351000` with
`sr-cnt=63`, `aid-cnt=256`, `aid-num-per-set=32`, corroborating the shape of
the audited readback. This is source evidence, not a measurement on all SKUs.

### CCCI table producer

U-Boot `36ee5fcae52ebd7a68b80bd6e8e915e7c6793d50` adds bounded v2 tag
serialization, matching the pinned B4.1 `ccci_util_lib_fo.c` consumer's 64-byte
name and three little-endian 32-bit fields. The producer rejects duplicate or
unterminated names, empty payloads, oversized tables, pointer wrap and aliases
before changing output. It emits no native pointers or struct padding.
Native CI `37773917358` passed, including the ARM64 build; tests cover exact bytes, guards, boundaries
and a full synthetic payload passed through the real CCCI validator.

This does not publish `ccci,modem_info_v2`, mark firmware ready or start the
modem. The current `no-fdt` reports absence of a previous-stage FDT; it is not
the sole missing operation. Building a new handoff also requires the complete
validated shared-memory layout, applied/read-back protection, remapping and
reset ownership. Advertising tags before those gates would be false readiness.
The installed loader and r172 phone are unchanged by this source-only work.

### Shared-memory runtime table builder

The pinned LK container SHA256 is
`29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f`.
Payload helper `0x235c4..0x237f4` takes resolved 32-byte input rows and emits
40-byte runtime entries, matching B4.1 `rt_smem_region_lk_fmt`. The AP virtual
pointer and output alignment stay zero. AP physical address is allocated base
plus running offset; MD offset is a separate supplied base plus running offset.
When the next input offset is ahead, LK emits a padding row with that input's
ID, the gap size and flag 4, then emits the actual region. The output count
includes inserted padding; empty region rows are preserved. There is no row
for unused reservation tail.

`patches/modem/test-lk-smem-builder.py` checks the exact private image hash,
executes that helper with synthetic input and intercepts calloc, physical
allocation and logging. Sixteen scenarios passed: continuous/gapped/empty
regions, below/above-4-GiB AP addresses and MD view bases 0/0x08000000. Unexpected
code or writes fail. Neither allocations nor register operations occur on the
phone. The proprietary input is not committed or uploaded.

U-Boot `1d3b2cae4cb41ae90ac684aa81c25a7b2c807b8e` implements the matching
byte encoder, with stricter bounds, duplicate-ID and unknown-flag rejection,
overflow/alias checks and atomic failure. Native tests and the ARM64 build
passed CI `37779916561`.
This encoder consumes already resolved placements; the B4.1 planner below
supplies those from explicit inputs. Profile selection, metadata acquisition,
reservation and protection ownership remain integration gates.
U-Boot `eb0595920ee094edf499976cfbe285f172f8e5c5` reconciles the validator
with the pinned B4.1 consumer's `map_phy_to_kernel()` behavior. Padding may
repeat the following ID; zero-size ordinary rows may belong to a nonempty
mapping run. Contiguous AP offsets/physical addresses, reserved DRAM, known
flags and unique real IDs across NC/cache tables are required. That revision
conservatively rejected every internal mapping gap; the real-profile work below
refines this using the consumer's page rounding. Empty mapping runs remain
invalid. This producer profile is not universal stock table compatibility.

Twelve producer/validator scenarios plus a cross-table ID conflict regression
are included in CI
[37781309347](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37781309347)
(passed, including native handoff tests and the ARM64 build). Local whitespace
and checkpatch checks passed; no local build was run.
No new boot caller, DT activation, module load or phone flash was added.
Modem/SIM/calls remain unavailable; these are source-level handoff prerequisites.

### B4.1 service layout planner

U-Boot `b55c53989f` adds the actual B4.1 service profile: 18 NC regions and
5 cache regions, per-region alignment, explicit padding count and 64 KiB
reservation rounding (160 MiB NC / 128 MiB cache limits). Its explicit inputs
are DRDI version 3, UDC enable, CONSYS size, NVRAM cache size and effective
CCB gear after boot-policy resolution. Unknown gears fail rather than silently
disabling CCB. Zero NVRAM size selects the stock 3 MiB default. No actual
device allocation or universal SKU/profile selection is implied.

Evidence uses the same pinned LK hash above: tables `0x198318`/`0x198558`,
callbacks `0x21b1c..0x21fdc`, placement `0x223cc..0x22568` and
`0x22a94..0x22bec`. `patches/modem/test-lk-smem-plan.py` executes these actual
callbacks and loops with synthetic tag/environment responses. All 56 bank
calculations across 28 parameter combinations completed without hardware
access. Generated synthetic rows/capacities/counts are committed as the U-Boot
CI oracle; no firmware bytes or per-device data are included.

The NC profile exposes a real 2 KiB alignment gap that the previous validator
rejected. Pinned B4.1 `ccci_map_phy_addr()` masks the physical base to a page;
`vmap_reserved_mem()` rounds the byte count up to pages. The validator now
requires a 4 KiB-aligned mapping start and checks that the rounded mapping
covers all ordinary rows and remains in reserved DRAM. It accepts this exact
stock gap but still rejects an uncovered page-sized gap, empty mappings,
unaligned starts and rounding outside the reservation. This models the 4 KiB
consumer profile, not every kernel page-size configuration.

CI adds exact C-planner/oracle comparisons, overflow/unknown-input rejection
with unchanged output, serialization and a planner-to-encoder-to-validator
test for the real NC table and a small synthetic cache configuration. Local
Python syntax, JSON and checkpatch checks passed. CI
[37794393803](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37794393803)
passed all native and handoff tests, the ARM64 build and image packaging for
`b55c53989fba751b122122948f06736c5b26ebd9`. No local C build was run.
Phone and installed r172/loader remain unchanged.

### Authenticated service metadata and kernel mapping

U-Boot now prepares one result containing the authenticated ROM/DRDI/DSP
members, validated load layout, header-derived service inputs and both service
plans. The effective CCB gear remains explicit boot policy. Failed signatures,
unsupported metadata, oversized banks and output aliasing leave the result
unchanged. No boot caller or ready handoff is enabled yet.

Actual LK publication `0x24370..0x243e8` copies v6 header fields CONSYS
`+0x180`, UDC `+0x184`, NVRAM cache `+0x18c` and DRDI `+0x190` into four-byte
tags. `test-lk-smem-plan.py --modem` executed this code with the local ROM
header and confirmed all four values. The container hash is
`b15207a948125439a5957224d65774d9d44c558c6eb285372a520b27b8d7d6c5`.
All three component signatures also passed verification against the independent
LK-matched SPKI pin already used by the SCP loader:
`e1b5235d9411473a358c754f84843801b91f05b8fb9dc4863393e378e41a115e`.
This verification used the existing audited pin, not a pin selected from the
modem image. Rollback/device policy and secure-reset ownership remain open.

Real metadata is DRDI 3, UDC 0, CONSYS `0xd80000`, NVRAM `0x16a040`.
Effective gear 1 produces six cache runtime rows and `0x2560000` capacity,
including a `0x15fc0` gap before CCB. The reference oracle now covers 42 input
sets / 84 actual LK bank plans, including these field values.

The pinned kernel's mapper sums non-padding sizes while using offsets for
virtual addresses. The real cache gap exceeds page-rounding slack and would
leave the final region partly unmapped. r173 packages
`0173-vendor-ccci-smem-map-span.patch.vendor`: validate a contiguous physical
and offset span, include padding in mapping length, reject misaligned starts,
inconsistent rows and overflow before mapping. Negative IDs are rejected
before hash-table registration. NO_MAP boundaries and zero-size optional rows
are preserved. The new CI test extracts and executes the actual patched
functions, checking the real cache gap, boundaries and failure paths.

Local patch application, overlay validation, Python syntax and private LK
checks passed. U-Boot
[CI 37797407178](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37797407178)
passed native tests, ARM64 build and packaging for
`e05970e905c08b54be88d281854d56f70f1b88bc`.
pmOS [CI 37797116235](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37797116235)
passed the actual patched-function C tests, kernel/module build and r173 image
packaging for `37dc3d03734c2919b8d18c75ac1cf37b94b18694`.
All compilation remained in CI. r173 was subsequently clean-installed after
archive/image/sparse verification. Its first boot and subsequent automatic
sensor cold start passed; display, touch, desktop rotation and auto-brightness
were user-confirmed. See [the installed checkpoint](PORT_SUMMARY.md#latest-installed-checkpoint-r173).

U-Boot `30e73368db6477708cad54148c70ce33ab621bd7` now connects the explicit
partition reader to signed B4.1 metadata planning and ROM/DSP placement.
`tetris_modem_load_slot_b41()` performs scoped LMB staging, all three signature
checks, load/service planning, placement, snapshot cleanup and payload cache
synchronization. The output contains no references to freed staging RAM and
is published only after cleanup and synchronization succeed. Metadata failures
are before destination writes; cleanup/cache failures can follow verified
writes but must never authorize execution. Short reads, signed-invalid service
metadata, wrong root, invalid geometry/gear, allocation/release errors and RAM
aliases are covered. Native tests, ARM64 build and packaging passed in
[CI 37883464473](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/37883464473).
This entry point has no boot caller or activation side effects. The new loader
artifact was not installed; the sensor-validated loader remains in use.

Next integration gate: establish the span-mapping consumer contract (the old
U-Boot observation validator still rejects this large gap), reserve and
initialize the planned RAM, apply/read back protection and remapping, and own
boot/reset release before publishing a ready CCCI handoff. Modem boot, SIM
detection and network registration still need live evidence. GPU/GNSS/camera
hardware status is unchanged.

## Completion criteria

Compile success is `Untested`, a bound driver is `Partial`, and a modem boot is
still only `Partial`. `Works` requires clean-install automatic initialization,
SIM detect/PIN, network registration, calls, SMS, mobile data, call audio,
airplane mode, recovery, warm reboot, suspend/resume and coexistence stress with
USB, Wi-Fi and Bluetooth intact.
