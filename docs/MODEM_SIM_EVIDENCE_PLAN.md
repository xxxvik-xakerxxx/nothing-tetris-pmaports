# MT6878 modem and SIM evidence plan

This document defines the smallest safe next step toward modem support on the
Nothing CMF Phone 1 (`nothing-tetris`). It does not promote modem support and
does not authorize loading a modem module or enabling a DT node.

## Source identity

- Current port branch: `codex/hardware-integration`, current candidate recorded in
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

### Current r153 observation

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

## Completion criteria

Compile success is `Untested`, a bound driver is `Partial`, and a modem boot is
still only `Partial`. `Works` requires clean-install automatic initialization,
SIM detect/PIN, network registration, calls, SMS, mobile data, call audio,
airplane mode, recovery, warm reboot, suspend/resume and coexistence stress with
USB, Wi-Fi and Bluetooth intact.
