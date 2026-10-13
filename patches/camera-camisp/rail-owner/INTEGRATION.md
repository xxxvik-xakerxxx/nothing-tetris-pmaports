# Camera GPIO rail owner: Untested

This implements a native, board-specific regulator provider, not an audit or
a fixed-regulator override. The real path after parent integration is
`tetris_camera_rail_driver.probe -> tetris_camera_rail_probe ->
tetris_rail_gpio_contract -> devm_gpiod_get(ASIS) -> tetris_rail_startup_observe ->
gpiod_direction_output(OFF) -> devm_regulator_register`. Native regulator core
then calls the checked enable/disable/is_enabled operations for real consumers.

`provider.patch` installs the C driver, binding, default-n bool Kconfig and
normal regulator Kbuild entry. `disabled-description.patch` changes the four
existing rail nodes to the new compatible and `enable-gpios`, preserving their
labels, voltages and disabled status. There is no generic fixed.c, GPIO,
pinctrl, framework, APKBUILD or workflow change. These deltas are uninstalled
staging and no GPIO has been acquired or changed in this task.

## Startup without inherited-ON adoption

The native MediaTek GPIO request callback can select GPIO mux mode even when
the consumer uses ASIS. Before that request, the provider resolves the actual
bound MT6878 platform/pinctrl owner, checks its native driver identity before
interpreting private data and requires a registered GPIO chip. It locks the
owner's device lifetime and existing
register lock, and reads MODE, DIR, DO and DI with its exported
`mtk_hw_get_value` interface. It makes no private mapping or hardware write.
Non-GPIO mode, output-latch ON, pad ON, unknown direction or an unsupported/read
error rejects startup before GPIO request. Every read error is propagated.
The MT6878 DIR register uses 1 for output; the GPIO API uses 0 for output.
Both contracts come from the pinned native owner, not a guessed register bit.

After this preflight the provider requests one exclusive GPIO descriptor with
ASIS and verifies active-high polarity. The startup-only observation accepts
either known GPIO direction, but requires physical DI=0. Preflight additionally
requires MODE=GPIO and stored DO=0. GPIO input-low is a legitimate cold-start
candidate, not a measured rail-OFF or readiness claim. The checked Paris
direction-output operation writes DO=0 first, stops on error, then selects
DIR=output. The provider requires output direction and DI=0 read-back before
publishing the regulator. Steady-state callbacks remain output-only; they
cannot use the startup input-low allowance to adopt a later direction change.
There is no fixed-regulator fallback, boot-on/always-on acceptance, early
`config.ena_gpiod`, nonexclusive GPIO request, force-OFF or inherited-ON takeover.
The schema and candidate DT exclude default provider pinctrl states, which
driver core could otherwise apply before probe. Runtime validation also rejects
those properties; it cannot undo effects from an invalid DT applied earlier.

These are real observations, not handoff proof flags. GPIO fields are not rail
voltage measurements and do not exclude a later firmware writer. The check is
immediately before acquisition, after allocation/constraint validation, but
its locks are released before `devm_gpiod_get`: it is a snapshot, not an atomic
observe-and-claim transaction. The request callback still writes MODE even if
the snapshot already read GPIO mode. No unchanged inherited state is claimed.

## Exact ASIS request and ownership trace

The SHA512-verified d84 archive, not an extracted checkout, supplies these
source checks and the CI comparison inputs:

1. `gpiolib-devres.c`: `devm_gpiod_get -> devm_gpiod_get_index -> gpiod_get_index`.
2. `gpiolib.c`: `gpiod_find_and_request` calls `gpiod_request` before
   `gpiod_configure_flags`. `gpiod_request_commit` claims `GPIOD_FLAG_REQUESTED`
   and calls `gc->request` before direction observation. Errors clear the claim.
3. `pinctrl-paris.c`: `mtk_build_gpiochip` installs `gpiochip_generic_request`.
   It delegates through `pinctrl_gpio_request` in `pinctrl/core.c`, which locks
   `pctldev->mutex`, resolves the pin range and calls `pinmux_request_gpio`.
4. `pinctrl/pinmux.c`: `pin_request` checks/records Linux pin owners under
   `desc->mux_lock`, takes the pinctrl module reference, and invokes
   `ops->gpio_request_enable`. Paris does not set `.strict`; its GPIO request
   does not exclude an existing non-GPIO mux owner. The same pinmux core also
   allows non-strict mux clients independently of GPIO ownership.
5. Paris `mtk_pinmux_gpio_request_enable` unconditionally calls
   `mtk_hw_set_value(... MODE, hw->soc->gpio_m)`. MT6878 defines `gpio_m=0`.
   Common-v2 `mtk_rmw` takes `hw->lock` for the actual register read/write.
6. Only afterwards does `gpiod_configure_flags` apply ASIS=0 and skip direction
   setup. This does not suppress step 5. Startup output-low separately uses
   Paris's checked DO-before-DIR sequence, not fixed-regulator OUT_LOW request.

GPIO/module references protect descriptor/driver lifetime, not firmware
ownership. The preflight device/register locks neither hold the pinctrl owner
mutex across acquisition nor reserve a pin; holding the register spinlock
across the sleeping GPIO request would also deadlock its MODE write. Native
Linux mux clients or firmware can therefore change state between observation
and request, or while a non-strict GPIO owner exists. Post-request DI=0 cannot
prove that no mux change happened first. No local provider-only public API here
atomically reserves the pin without the mux-writing callback. A real owner-level
read-before-write reservation and mux-client exclusion, plus AP/bootloader/
firmware reconciliation, remain required. No generic owner rewrite or private
owner duplication is supplied. Keep all rail DT nodes disabled; CI compile is
not authorization to activate this candidate.

## Shared users and errors

One physical rail has one regulator node/device. GPIO exclusivity rejects a
second physical driver; consumers use ordinary regulator handles on the same
phandle. The provider never duplicates `use_count`/`enable_count`, acquires an
exclusive consumer handle, or disables a shared rail from sensor teardown.
The pinned core calls enable for the first consumer and disable for the last,
retaining the last reference when the provider's disable fails.

The callbacks verify direction and observed level before a transition, check
the GPIO setter's actual errno, then read back before updating `last_level`.
That integer tracks a completed GPIO transition, not consumer ownership or
readiness. The first error is latched and blocks further callback transitions;
there is no guessed rollback, fault-clear or retry. A partial write can leave a
rail ON. The built-in driver suppresses manual bind/unbind and does not install
a shutdown/reset policy that could remove another client's rail.

The core can satisfy an additional shared enable reference from an existing
nonzero count without calling the provider again. This candidate does not
claim a per-consumer fault check on that path. Sensor start must observe/check
the supplier state and stop on error before reset release or I2C access.
Dynamic DT removal, ownership migration while active, recovery and lifecycle
remain unvalidated. A clean reboot is the current recovery boundary.

## Exact source basis

| Source pin | Contract |
| --- | --- |
| NOS device modules `ee2be53cb75670b548948636a0db1d1ff112bf12` | `k6878v1_64_tetris.dts` includes `cust_mt6878_camera_v4l2.dtsi`. GPIO1 is AFVDD at 2.8 V; GPIO23 is common DOVDD at 1.8 V. Main AVDD/DVDD use GPIO22/GPIO21. Sensor0@1a uses AFVDD; sensor0@1a, sensor1@10 and sensor2@36 all use the same DOVDD phandle. |
| NOS camera modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` | Both IMX882/IMX882TXD `pw_seq` tables specify AFVDD/AVDD 2800000, DVDD 1200000 and DOVDD 1800000 uV. Those are nominal sensor rail values, not VMM policy or measured voltage. Sensor-specific delays remain in the sensor driver. |
| Linux `d84b264a54a37611f2f46bc19363cb9b41606205` | `fixed.c` selects OUT_LOW/OUT_HIGH before registration; `core.c` owns shared references and callback errors. `gpio/consumer.h` exposes checked setters. Paris pinctrl supplies the actual MODE selection, DIR/DI/DO operations and platform driver data. The common-v2 exported read helper reuses that existing owner's mappings. |

`evidence.json` records exact vendor blob IDs/hashes, the SHA512-verified Linux
archive, native framework sources, the tracked 0055 rail fixture, output and
delta hashes. No vendor checkout HEAD or pre-existing untracked CCD source is
used. The new provider is deliberately coupled to the pinned MT6878 pinctrl
owner layout; it depends on `PINCTRL_MT6878`, not an invented owner API.

## CI and remaining gates

Local static/application checks, from repository root:

```sh
python3 -B patches/camera-camisp/rail-owner/generate.py
python3 -B patches/camera-camisp/rail-owner/check.py
python3 -B patches/camera-camisp/rail-owner/test_source.py
```

Regenerate scoped deltas/evidence with `generate.py --write` after source review.
The provider delta applies strictly to pinned regulator Kconfig/Makefile inputs;
the DT delta applies to all four complete packaged 0055 rail-node bodies. Full
parent board assembly, binding schema validation and DTB checks are still required.
No schema success is inferred from parsing the YAML.

The CI-only runner requires a fresh prepared pinned kernel and the same pinned
source inputs. It verifies unchanged generic owner/framework sources, applies
only the provider patch, resolves a separate config, builds the real regulator
object and requires actual AArch64 LLVM bitcode or ELF. It records source/config/
compiler/object identity and errors, and produces no module, kernel link or DT.
The isolated config preserves shipping ThinLTO, CFI and hardening selections;
after `olddefconfig`, security-profile drift fails the build. The runner uses
the existing `ci/kernel-object-smoke.py:object_identity` to inspect actual
AArch64 LLVM bitcode or ELF, with `llvm-dis`/`llvm-readelf`, without execution,
JIT or disabling security for object format. It records the identity helper,
shipping/resolved config and verified prepared-owner hashes. For example,
inside the parent's authorized CI job, pass existing input locations explicitly:

```sh
python3 -B patches/camera-camisp/rail-owner/run_ci.py \
  --prepared-kernel "$prepared_kernel" \
  --kernel-archive "$ci_work/linux-postmarketos-mediatek-mt6878-d84b264a54a37611f2f46bc19363cb9b41606205.tar.gz" \
  --device-repo "$device_modules_repo" \
  --modules-repo "$camera_modules_repo" \
  --output "$ci_work/rail-owner-objects" \
  --report "$ci_report/rail-owner"
```

The archive argument must be the packaged SHA512-verified Linux archive used
to prepare the tree. Device/camera repo arguments can be any location: the
checker reads the exact NOS git objects, never HEAD or untracked working files.
Unlike local static checks, the CI runner has no sibling archive/repo fallback.
The listed prepared GPIO/pinctrl implementation sources, including
`pinctrl-mt6878.c` and the owner/ABI headers, must match archive bytes. The SoC
pin table header must instead match the strict application of tracked,
APKBUILD-SHA512-verified `0006-pinctrl-mediatek-mt6878-eint.patch`. Its GPIO pin
metadata remains unchanged; evidence records both archive and prepared hashes.
Regulator Kconfig/Makefile allow existing packaged additions, with strict
provider patch application. A missing/mismatched source
fails before staging or compilation. Full board assembly is still the parent.

The runner refuses locally before subprocesses or writes. No CI dispatch,
native compilation, dtc, emulation, JIT, phone access, commit or push occurred.
Cold OFF acquisition, actual rail voltages, shared-client operation, failures
and lifecycle require CI artifacts and controlled hardware evidence.

## Capture follow-up

The packaged 0121 MCLK delta reaches only `imx882-identity.c`. The actual
`imx882-tetris-stream.c` still has the copied old `clk_set_rate_exclusive`
power helper and no explicit UVPLL192M_D8 handle. Before capture, integrate
CAMTG2_SEL/source acquisition into `imx882_camera_probe`, `imx882_stream`,
`imx882_stop`, `imx882_camera_remove` and the stream binding,
including checked OFF startup, first-error propagation and clock reference
retention across uncertain teardown. Keep ordinary shared regulator accounting.
Do not enable the streaming compatible just because the identity or rail owner
compiles. The bound SENINF/CAMSV/ISP graph, VMM voltage/rate, MMUP/firmware
handoff, captured frames, supplier identity and per-device calibration remain
separate dependencies. This does not complete the camera gate.
