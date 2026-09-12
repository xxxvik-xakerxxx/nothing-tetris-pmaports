# MT6878 Panthor compile-only prerequisite

## Scope

This gate proves that the mainline Panthor driver builds in the pinned MT6878
kernel package while remaining unable to probe on the shipped Nothing Tetris
device tree. It does not claim GPU probe, firmware compatibility, a render
node, acceleration, power sequencing, or safe regulator control.

The prerequisite deliberately adds no kernel patch or device-tree node. The
current Linux 6.18 Panthor driver already matches the generic
`arm,mali-valhall-csf` compatible. Adding a synthetic MT6878 compatible or an
incomplete platform quirk would not close any known dependency.

## Pinned source trace

The package pins Linux commit
`d84b264a54a37611f2f46bc19363cb9b41606205`, NothingOSS device modules commit
`ee2be53cb75670b548948636a0db1d1ff112bf12`, and NothingOSS external modules
commit `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`.

The pinned NothingOSS device tree establishes only the hardware inventory:

- MMIO starts at `0x13000000` and spans `0x480000` bytes;
- the standard job, MMU, and GPU interrupts are SPI 271, 270, and 269;
- vendor-only event and power interrupts are also present;
- the vendor frequency driver names MT6319 USID 6 VBUCK2 as VGPU and MT6363
  VSRAM_CPUM as the SRAM rail;
- the vendor Mali node relies on GPUEB, protected-memory, GED, and vendor
  frequency-management contracts which are not represented by Panthor.

These facts are inputs for later DT and power work. They are not sufficient to
instantiate the GPU safely.

## Enforced off boundary

`CONFIG_DRM_PANTHOR=m` compiles and packages the upstream driver, but the
shipped DTB has no `gpu@13000000` or `mali@13000000` node. No device package
configuration, udev rule, service, initramfs list, or modules-load file names
Panthor. Therefore no modalias exists and the module is not requested at boot.

The existing GPU rail and MFG RPC patches remain inventory only. This gate
adds no regulator child, supply consumer, `regulator-always-on`, voltage, mode,
enable, or disable request. The MFG RPC syscon and provider remain disabled.

## Validation

Run the source and compile gate against a disposable, fully prepared copy of
the pinned Linux tree and local git mirrors containing the pinned NothingOSS
objects:

```sh
./scripts/check-panthor-compile-only.sh \
  /path/to/prepared-linux-6.18 \
  /path/to/android_kernel_device_modules_6.1_nothing_mt6878 \
  /path/to/android_kernel_modules_nothing_mt6878
```

The validator checks all three package pins, vendor MMIO/IRQ/supply evidence,
the module config, absence of a shipped GPU DT node and autoload rule, and a
targeted linked `panthor.o` build. This avoids requiring a full-kernel
`Module.symvers` for the cheap gate. The package CI independently builds and
checks `panthor.ko`, the shipped DTB, MFG RPC disabled state, and loader
absence.

## Next gate

Before any runtime DT node is added, document and validate the complete MFG0
and MFG RPC power order, all clocks and resets, VGPU/VSRAM coupling, GPUEB and
secure-memory ownership, the live GPU ID, and the matching redistributable CSF
firmware. Runtime work requires a separate recovery image and the full GPU
live-test matrix.
