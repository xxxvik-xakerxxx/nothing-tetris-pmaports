# USB stable identity

Status: staged, default-off, untested on device.

The pmaports patch adds an opt-in initramfs mechanism that hashes a validated
binary property below `/sys/firmware/devicetree/base/chosen/` and derives
distinct, locally administered unicast host and device MAC addresses. It runs
after the NCM function is created and before configfs linking or UDC activation.

With no `deviceinfo_usb_network_mac_seed_path`, the helper returns without
writing either configfs address. A missing, symlinked, unreadable, undersized,
oversized, out-of-tree, or unhashable seed also leaves the function-generated
random addresses in place. An explicit legacy
`deviceinfo_usb_network_host_addr` retains precedence.

## Current evidence gate

The captured live inventory at
`local/live-logs/booted-pmos-r2/simplefb-iomem.txt` lists the complete published
`/chosen` subtree. It contains `u-boot,version`, boot arguments, initrd bounds,
and simple-framebuffer properties, but no `atag,devinfo`. The empty
`local/live-logs/booted-pmos-r2/devicetree-chosen.txt` provides no contrary
evidence.

Current U-Boot source was audited at branch `codex/scp-handoff-inventory`.
Commit `6ab33f59df8b5116c1d63bd637cda4efbbaeb6ef` adds validated copying of
`atag,devinfo`, while `73faaa2d0ecfaf8fe8da3330a45ff11f5d0c5a99` safely preserves the LK FDT
through relocation. The packaged bootloader remains pinned to
`b76e47e774304ab550a6354f3286860b7caffb3a`; live evidence does not prove that
this path publishes the property on the current boot chain.

The live r155/r9 boot `d9d69266-fb08-464f-a7d7-fb7b2fdf1a7a` was rechecked on
2026-09-12 with USB SSH healthy. `/chosen` still exposes no files, so the
existing allowlisted seed path remains unavailable. The root device tree does
expose a 13-byte `serial-number`, a `mediatek,mt6878-devinfo` provider, and
`consys@18000000/adie-sku = 0000000000000001`; the serial value itself was not
printed into the log. These are candidates for a reviewed identity source, not
an enabled seed.

Therefore Tetris does not set `deviceinfo_usb_network_mac_seed_path`. This is a
deliberate fail-open gate: existing random NCM addresses and enumeration remain
unchanged.

The existing suspend hook only unbinds and rebinds the UDC. Its package test now
also verifies that host and device MAC attributes survive that cycle unchanged.
This is static/package evidence only; the ten-cycle device lifecycle gate remains
untested.

## Requirements before opt-in

1. Capture the exact bootloader, kernel, DTB, modules, rootfs, slot, command
   line, and source commits with USB NCM and one SSH control session healthy.
2. Prove the candidate property exists, is structurally valid, contains no
   secrets that must not be hashed, and is stable across three cold boots and
   warm reboots. If root `serial-number` is used instead of a `/chosen`
   property, first extend the initramfs allowlist and tests deliberately rather
   than widening path access generically.
3. Confirm the property differs on a second handset or justify its device-level
   uniqueness from an authoritative source.
4. Build artifacts in CI, then test repeated enumeration, DHCP/SSH, sustained
   transfer, and at least ten suspend/resume cycles without USB loss.
5. Only after those gates pass, add the seed path to Tetris deviceinfo and bump
   the device package revision and checksum.

No bootloader update, flash, or live USB reconfiguration is part of this stage.
