# Actual IMX882 streaming owner: Untested

This is a concrete delta to the packaged `imx882-tetris-stream.c`, not another
identity probe or an alternate power provider. The installed code path, after
parent integration, is `imx882_camera_probe -> imx882_resources_get`, then
the existing V4L2 `.s_stream -> imx882_stream -> imx882_power_on ->
imx882_mclk_acquire`, checked reset/rails/pad/clock and chip ID, followed by
the existing mode/control/stream-on writes. Controls and repeated stream-on
validate actual suppliers, clock parent/rates/gate and reset before I2C.
Stop, failed start, suspend and remove all account for partial power state.

`stream-owner.patch` modifies only the real streaming driver, its binding and
its Kconfig entry. It is **uninstalled staging**, default n, with no DTS,
APKBUILD, workflow, frozen rail-owner or identity/activation changes. A staged
source or compiled object is not a capture result.

## Clock, Reset And Power

The MCLK acquire/release functions come byte-for-byte from the current
APKBUILD's checksum-verified 0121 identity source, composed from the exact
shipping patch stack. They acquire exclusive rate protection on the actual
CAMTG2_SEL output and UVPLL192M_D8 source, reject an already enabled output,
require the source already at 24000000 Hz, select that parent and verify both
parent identity and output rate. There is no `clk_set_rate`, shared PLL retune,
factor-clock substitution, new clock provider or invented CSI link rate.
Exclusive-rate references protect rates/parents, not exclusive gate-enable
ownership. Gate/supplier observations are snapshots; another enable or firmware
writer can race them. This contract is not an atomic firmware/clock handoff and
does not authorize board activation.

Probe acquires ordinary resources and registers the unchanged media interface.
It observes rails/clock idle before requesting active-low reset with ASIS; it
does not assert/reset or explicitly select pad state or enable power at probe.
ASIS **still invokes the native mux-writing request callback**. Its request
and idle observation are not an atomic reset/pad/firmware ownership handoff.
Likewise a default pinctrl state applied by driver core precedes probe. This
candidate does not claim untouched inheritance or prove ownership by observing
a low GPIO. The real reset/pad mux handoff and the frozen rail-owner's
observation-to-claim gap remain activation blockers; keep DT disabled.

At start, after the exclusive clock contract and repeated idle observations,
reset direction-output assertion and GPIO read-back are checked. The existing
AFVDD -> AVDD -> DVDD -> DOVDD order and nominal voltages/delays remain. Only
successful regulator acquisitions enter the bitmap. Pad selection, clock enable,
actual source/rate/gate and enabled suppliers are checked before a checked
reset release and read-back. The sensor's actual 0x8202 chip ID is still checked
on each powered start before init/mode writes. Register arrays, controls,
formats, C-PHY three-trio endpoint mapping, RAW10/PDAF descriptors and the
documented no-QSC branch are unchanged, not a calibration claim.

The port's previous helper enabled the clock later than the vendor's first
MCLK power-table row. This delta preserves that existing rail/pad timing; it
fixes source acquisition and lifecycle, not the complete vendor sequencing or
receiver electrical qualification. MCLK pad drive/routing still needs physical
evidence.

Rails retain **normal** regulator framework handles and shared accounting;
there is no exclusive rail consumer, private shared-client count or force-off.
Cold-start preflight conservatively rejects every already-enabled supply,
including DOVDD legitimately held by another sensor, because this slice cannot
distinguish that from unestablished boot ownership. Normal shutdown releases
only this sensor's references; it does not require another client's DOVDD to
become physically OFF. A cached shared core enable is followed by real supplier
observation before reset release, not accepted as readiness.

## Errors And Lifetime

A reset, regulator, pad, enabled-clock validation or shutdown error latches the
first power errno and blocks subsequent hardware transitions. There is no
retry, guessed rollback, forced reset or fault-clear. An uncertain regulator
enable can have a physical effect even without a successful new reference;
only earlier **successful** references are tracked and retained. Core APIs may
unwind their own unsuccessful acquisitions; the driver does not invent ownership
of those failed acquisitions.

Shutdown checks reset assertion before dropping the clock, refuses to force
the pad OFF if another clock enable is observed, then selects pad OFF and
releases supplies in reverse order. Each successful supply disable clears only
its own bitmap bit immediately. The first failure stops that sequence and
retains the remaining references and both rate locks. Rate protection is put
only after the complete successful shutdown. Void clock-disable APIs release
this owner's enable reference, not a fabricated hardware ACK; subsequent gate
observation must be OFF before pad/supply teardown continues.

An I2C programming failure preserves its original errno. Checked reset and
complete successful reference teardown can contain an ambiguous stream write
and allow a fresh start; an uncertain power transition cannot. Failed starts
and explicit stop operate on partial acquisitions even if `streaming` never
became true. Suspend rejects active/faulted/retained dependencies rather than
silently dropping capture. Media locks and API signatures stay unchanged.

The candidate becomes **built-in only**, default n, with manual bind attributes
suppressed. Resources and owner storage have explicit, non-devm lifetimes.
Probe error releases only its constructor references, with no power-off write.
Remove unregisters/cleans the media API, attempts checked stop, and frees
resources/storage/device reference only if no uncertain power state or retained
acquisition remains. Otherwise those real handles, bitmap and device storage
remain until reboot; they cannot disappear through module unload or devres
cleanup. This is deliberate retention, not successful shutdown. Dynamic I2C/DT
removal, repeated lifecycle and recovery still need validation; there is no
automatic reinitialization or complete hardware-safety claim.

## Exact Inputs And CI

- Linux `d84b264a54a37611f2f46bc19363cb9b41606205`, archive SHA512 checked against APKBUILD.
- NOS device `ee2be53cb75670b548948636a0db1d1ff112bf12`: board camera include, sensor0 clock phandles/names and top CAMTG2 parent table.
- NOS camera `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`: adaptor MCLK source operation, both sensor power tables and IMX882 register arrays.

`generate.py` reads exact git objects, not HEAD or working files, then strictly
applies only relevant packaged file sections in **current APKBUILD source
order** onto the verified archive. Every adopted patch is tracked and SHA512
checked. It includes shipping 0112 and 0121; pre-existing untracked CCD is not
used. `evidence.json` identifies archive/native/baseline/vendor blob, template,
patch and payload hashes. No complete package or DT validation is inferred
from these focused source/application checks.

From repository root, static checks only:

```sh
python3 -B patches/camera-camisp/stream-owner/generate.py
python3 -B patches/camera-camisp/stream-owner/check.py
python3 -B patches/camera-camisp/stream-owner/test_source.py
```

Regenerate only this scope with `generate.py --write` after changing templates.
The CI-ready stage helper takes actual input paths, without a sibling-source
assumption. Use a fresh **normal packaged** prepared kernel, before unrelated
camera review overlays; source/binding/core/tables/clock framework/Kconfig/
Kbuild hashes must equal the reconstructed baseline. Any drift or already
applied stream delta fails before mutation. The read-only mode omits
`--ci-apply --report` and checks source hashes/patch applicability only.

```sh
python3 -B patches/camera-camisp/stream-owner/stage.py \
  --prepared-kernel "$prepared_kernel" \
  --kernel-archive "$kernel_archive" \
  --device-repo "$device_modules_repo" \
  --modules-repo "$camera_modules_repo" \
  --ci-apply --report "$stream_report"
```

The mutating mode requires both CI=true and GITHUB_ACTIONS=true before any
processes/writes. It records `STAGE-MANIFEST.json` as **staged**, never compiled
or passed capture. It does not rewrite `.config` or invoke any compiler, linker,
dtc, emulation or JIT. Parent CI must enable the dependencies and
`CONFIG_VIDEO_IMX882_TETRIS=y` in its isolated config, preserve original
ThinLTO/CFI/security options after olddefconfig, build the actual
`drivers/media/i2c/imx882-tetris-stream.o` and use the existing
`ci/kernel-object-smoke.py:object_identity` for AArch64 bitcode/ELF evidence.
Require final link/DT/binding checks separately. Replaying old streaming helper
overlays afterwards could replace this lifecycle; verify the staged driver hash
immediately before compile. No local native compilation or CI dispatch occurred.

## Remaining Capture Path

- Rail/reset/MCLK pad ownership and mux handoff, real voltages, source/gate
  behavior and cold electrical sequencing. The frozen rail owner is not proof
  that AP/bootloader/firmware ownership has migrated.
- Native USID-6 VMM regulator constraints and a real voltage/rate operating
  point, MMUP/MMDVFS/firmware voting/ownership, including vmmspm/debug clients.
  Absence of an available DT consumer does not establish secure quiescence.
- Bound SENINF C-PHY receiver and source-pad media link, verified three-trio
  routing/CSI clock, CAMSV/RAW/ISP descendants, reset/protection/clocks and
  CCU/firmware ownership. The native CAM_VCORE/CAM_MAIN/ISP_VCORE candidate is
  disabled and rejects unsupported descendants; a sensor stream is not that
  receiver/ISP activation.
- IOMMU mappings, finite DMA buffers, V4L2 capture queue and checked shutdown,
  with real VC0 RAW10 DT0x2b and PDAF DT0x30 handling and received frames.
- Module/supplier/SKU identity, owned per-device QSC/calibration, repeated
  start/stop, suspend/resume and portability while USB remains healthy.

No capture, successful secure handoff or readiness is claimed.
