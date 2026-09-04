# MT6375 BC1.2 compile-only boundary

Updated: 2026-09-04.

## Scope

Patch `0054-power-supply-mt6375-bc12-compile-only.patch` adds one standalone
translation unit to the pinned MT6878 mainline kernel:

`drivers/power/supply/mt6375-bc12-decode.c`

The file records the stock MT6375 BC1.2 `PORT_STAT` encoding and implements a
pure conversion to Linux `enum power_supply_usb_type` plus a bounded current
limit. It is intentionally absent from kernel `Kconfig` and `Makefile`, so the
normal kernel build does not compile or link it. It can only be compiled by an
explicit object target during static validation.

The object contains no driver registration, module metadata, MMIO or regmap
access, register writes, PHY operation, IRQ request, device-tree description,
power-supply registration, notifier, workqueue or runtime entry point.

## Authoritative provenance

The hardware inventory comes from the official Nothing OS 4.1 Tetris source:

- repository: `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878`;
- release: `Tetris-B4.1-260415-1709`;
- commit: `ee2be53cb75670b548948636a0db1d1ff112bf12`;
- `drivers/power/supply/mt6375-charger.c` defines `MT6375_REG_BC12_FUNC`
  (`0x150`), `MT6375_REG_BC12_STAT` (`0x151`),
  `enum mt6375_port_stat`, `mt6375_chg_bc12_work_func()` and the stock
  SDP/CDP/DCP current publication;
- `include/dt-bindings/mfd/mt6375.h` defines
  `MT6375_FL_BC12_DN` as hardware interrupt 31.

The target kernel is `MT6878-mainline/linux` commit
`d84b264a54a37611f2f46bc19363cb9b41606205`, as pinned by the kernel package.

## Pure decode contract

| `PORT_STAT` | Stock meaning | Linux USB type | Current limit |
| ---: | --- | --- | ---: |
| 0 | No information | `UNKNOWN` | 0 uA |
| 8-12 | Apple/Samsung/unknown adapter classes | `DCP` | 2000000 uA |
| 13 | SDP | `SDP` | 500000 uA |
| 14 | CDP | `CDP` | 1500000 uA |
| 15 | DCP | `DCP` | 2000000 uA |
| all other values | Invalid or incomplete | `UNKNOWN` | 0 uA |

The 8-12 mapping follows `mt6375_chg_bc12_work_func()` in the pinned stock
driver. It is recorded as source behavior, not yet accepted as a production
charging policy.

## Fail-closed boundary

This patch does not enable BC1.2 detection. In particular, it does not:

- set `F_BC12_EN` or any other MT6375 field;
- route USB DP/DM through `PHY_MODE_BC11_SET` or `PHY_MODE_BC11_CLR`;
- request or unmask `MT6375_FL_BC12_DN`;
- read `F_PORT_STAT` from hardware;
- publish SDP/CDP/DCP through a runtime power supply;
- pass a result into TCPM `get_current_limit()` or the Tetris charging policy.

Consequently the installed behavior remains unchanged: Type-C default current
without a PD contract continues to publish `CURRENT_MAX=0`, and the board
policy retains its 500 mA fallback.

## Static validation

Required checks are:

1. apply the patch exactly to the pinned mainline commit;
2. compile only `drivers/power/supply/mt6375-bc12-decode.o` with the pinned
   kernel configuration and compiler where available;
3. confirm the patch contains no registration, hardware-write, PHY, IRQ-request,
   DT or module-metadata path;
4. confirm the source is absent from kernel `Kconfig` and `Makefile` and is
   invoked only by the package's explicit object-only build gate.

Runtime BC1.2 work remains blocked until USB2 DP/DM ownership, attach/detach
ordering and the publication bridge to TCPM are independently proven without
degrading USB NCM/SSH recovery.

## Validation evidence

Validated on 2026-09-04 against an isolated copy of the exact pinned kernel
tree:

- `git apply --check` passed against
  `linux-d84b264a54a37611f2f46bc19363cb9b41606205`;
- the patch applied without fuzz or offset;
- GNU Make 4.4.1 and Alpine Clang/LLVM 21.1.8 compiled the explicit ARM64
  target `drivers/power/supply/mt6375-bc12-decode.o` successfully;
- `file` identified the result as an ARM aarch64 ELF64 relocatable object;
- `nm` reported only the local text symbol
  `mt6375_bc12_decode_port_stat` and no unresolved symbols;
- static searches found no registration, module metadata, regmap/MMIO write,
  PHY mode change, IRQ request, DT, notifier, workqueue or power-supply
  publication path;
- repository searches confirmed that neither kernel `Kconfig` nor `Makefile`
  references the new translation unit;
- pmaports CI run `33880650257` at commit `ab97ff85966495b60fc206f616f39f72109392c5`
  completed overlay validation, kernel/device package builds, final images and
  artifact uploads. Rootfs checks rejected any decoder object, module or
  runtime loader from the produced image.
