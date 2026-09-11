# Reusing stock LK before U-Boot: bounded offline feasibility

2026-09-11. Status: **plausible architecture, not a proven bootable chain**.
There is no evidence here that rewriting the modem secure-authentication stack
is necessary. There is also no proof that the current U-Boot binary can simply
replace the Android kernel. No image was generated or executed, no phone was
accessed, and no shared U-Boot source was edited.

## What changes architecturally

Current packaging in U-Boot `c931695bb963efaa0dfdf928ea475440581838b4`,
`tools/tetris_lk_image.py`, substitutes the first LK payload and retains its
container tail. `gimme-uboot.py` likewise replaces the `lk` member. This runs
U-Boot **instead of** the stock LK modem producer; retaining another BL2 member
does not retain the replaced code. `doc/board/mediatek/mt6878-tetris.rst`
documents that deployment, but provides no proof it is the only possible one.
It gives U-Boot control of FIT loading and its own recovery UI without going
through stock Android image policy. That is a practical benefit, not proof
that stock LK cannot launch an intermediate payload.

The alternative under investigation is:

    compatible earlier stages -> stock LK -> accepted Android kernel payload
      containing U-Boot -> mainline Linux

Stock LK would own its existing modem lookup/authentication/allocation and DT
publication, rather than U-Boot reproducing its crypto. This is an explicit
cold-boot chain, not reliance on residual state from an earlier Android boot.
The LK producer/auth contract is in PRODUCER.md; publication alone still does
not establish a successfully loaded modem or SIM service.

## Exact stock exit contract

Input identities are the same hash-pinned B4.1 LK in README.md. Offsets are
first-payload offsets; add `0x200` for offsets in lk.img. Bounded disassembly
and 15 instruction-mutation checks are reproducible with bootchain_audit.py.

* `0xf5f0`: boot routine saves its argument0 in x19 and argument1 in x26
  (`0xf618/1c`). The storage path calls it at `0x1047c` after obtaining boot
  metadata; the later path rejoins it through `0x1066c -> 0x1046c`.
* `0xfea0..0xfebc`: dispatches trampoline `0x10380` through `0x188f0`,
  supplying `0xc2000115`, x19, x26, zero. This follows the log reference
  "lk finished --> jump to linux kernel" at `0xfe80/84`.
* `0x188f0..0x18960`: preserves those arguments, translates the trampoline
  address via `0x67114`, then invokes `0x1868c`.
* `0x1868c..0x186c8`: moves trampoline to x5, shifts arguments down one
  register, updates VBAR_EL1, clears SCTLR_EL1.M, invalidates EL1 TLB and
  branches to the trampoline. `0x10380` sets x4=1 and executes SMC.
* Therefore the **monitor input** is x0=`0xc2000115`, x1=kernel argument,
  x2=FDT argument, x3=0, x4=1. It is NOT proof that U-Boot receives FDT in
  x2: the monitor owns the final entry ABI. The matching U-Boot bootm code
  independently labels the same x1/x2 convention kernel/FDT.
* CCCI publication at `0x28118..0x28138` uses the previously established
  48-byte raw descriptor. Its referenced tag buffer and modem ranges must
  survive too; copying only FDT bytes is insufficient.

## Concrete incompatibilities and open gates

### Second kernel-entry SMC: an actual design issue

`arch/arm/mach-mediatek/Kconfig:12` selects `MTK_SMC_JUMP` for MT6878.
`arch/arm/lib/bootm.c:291` uses **the same `0xc2000115`** for U-Boot -> Linux
and hangs if it returns. Thus the proposed unmodified chain calls the kernel
entry service twice. Neither repeatability of that service nor its acceptance
after the first LK exit has been proved. Do not replay it to find out.

This is a smaller, concrete boundary than replacing modem authentication:
establish the matching ATF handler's final EL, register, cache and one-shot
state contract; then decide whether a kernel-entry U-Boot variant must use
the standard direct Linux handoff instead of `MTK_SMC_JUMP`. A direct handoff
is a candidate, not implemented or proved safe by this audit.

### Kernel envelope and relocation

`configs/mt6878_tetris_defconfig` sets `POSITION_INDEPENDENT=y`, TEXT_BASE
`0x50f00000`, and embedded DT. `arch/arm/cpu/armv8/start.S:61` enforces 4 KiB
runtime alignment and applies relative relocations. A different load address
is therefore not inherently impossible, but the runtime footprint including
BSS, early stack, malloc and later relocation must fit stock reservations.

This defconfig does not request `LINUX_KERNEL_IMAGE_HEADER`. U-Boot already
provides that ARM64 header in `arch/arm/include/asm/boot0-linux-kernel-header.h`
and its text-offset option in `arch/arm/Kconfig:94`; a dedicated configuration
is preferable to inventing a wrapper. No configuration/build was run here.

Stock LK `0xc020` compares eight bytes against ANDROID!, with a separate
vendor header comparison at `0xc048`. Storage loading compares header versions
against 3 and 4 at `0x10420` and `0x10648`. Decompressor classification at
`0xe460..0xe4b0` recognizes gzip/legacy LZ4; the unrecognized branch at
`0xe744` reports "No magic number of compression is found!" through `0x68bf0`.
This establishes a real compression gate **when this routine is used**, not
a complete proof that every uncompressed-kernel path is forbidden.

The local TWRP BoardConfig.mk corroborates header v4, Image.gz, separate
vendor_boot/DTBO and a 64 MiB boot partition. It is secondary, unpinned-to-B4.1
evidence, not an exact B4.1 boot header. No boot/vendor_boot image was extracted
in this pass. Exact original header, compressed payload limits, DT selection,
load allocation and signature footer remain required before any candidate
image can be specified. No new image is supplied.

### Lock / AVB is not modem authentication

The local recovery configuration enables AVB; stock LK contains libavb code
and diagnostic references. Those facts do not close the locked/unlocked
acceptance branch for a modified boot payload. This audit has NOT proved
whether the exact device policy would admit it, and does not suggest bypassing
verification. A changed kernel payload cannot inherit the original boot
signature's validity. Stock modem verification can remain unchanged even if
an authorized unlocked boot policy permits a custom kernel; those are distinct
checks. No assumption is made about current lock state or archive slot match.

### Prior FDT consumer exists, memory lifetime is not closed

At c931695, `arch/arm/lib/save_prev_bl_data.c:362` prefers a validated x2 FDT
with devinfo, otherwise validated x0. This supports a normal x0 FDT entry
without a new decoder. `reserve_prev_bl_fdt()` copies the FDT and board code
already validates/publishes CCCI. The strict 32/48 candidate is in f111bfd;
main owns its integration. Nonzero extra16 semantics remain open.

But `common/board_f.c:946` calls `dram_init()` before the FDT reservation at
line988. `arch/arm/mach-mediatek/mt6878/init.c:31` uses `get_ram_size()` over
2 GiB; `common/memsize.c:65,74` actually writes probe patterns before restoring
values. Such probing cannot be assumed harmless with stock modem/secure RAM
already occupied. U-Boot's embedded memory description and allocation choices
must honor the complete stock reserved map before any RAM probing, stack,
relocation, FIT load or firmware preparation can overlap it. This audit does
not prove a collision on this handset; it proves the existing path does not
establish that exclusion before probing.

## Decision / smallest next offline prerequisite

Do not require a modem-auth rewrite on the evidence available. Retain stock LK
as an architectural option. However, neither a proven end-to-end alternative
nor an impossibility result has been obtained: exact AVB acceptance and ATF
exit/re-entry are unresolved, and current memory initialization is not a
verified preservation path.

The highest-value next bounded source audit is the exact ATF `0xc2000115`
handler and stock boot/kernel header/allocation contract, followed by a
host-tested reserved-memory exclusion model for a dedicated kernel-entry
U-Boot configuration. Do not duplicate main's CCCI decoder ownership.

The installed preserved BL2 extension (711336 bytes, SHA prefix17058309)
differs from B4.1 BL2 (1384080 bytes, prefixedf44835). Restoring just stock LK
into that mixed chain is not established compatible. LK reset/recovery is
unproven, so **no live gate or flash procedure is authorized by this report**.
Before any future live proposal, recovery and exact earlier-stage compatibility
must be independently established.

## Reproduction

From this owned worktree:

```sh
python3 -B patches/modem-stock-audit/bootchain_audit.py ../hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img
```

Reads the local and existing Docker input, verifies both identities, decodes
11 small windows in two bounded batches, and rejects 15 instruction mutations.
Writes only bootchain-evidence.json beside the script. No vendor code executes.
The first run correctly hit the helper's eight-window limit; batching fixed
the runner without weakening that bound. Source references above are pinned
to c931695, available in worktrees/uboot-ccci-prev-fdt; no source changes there.
