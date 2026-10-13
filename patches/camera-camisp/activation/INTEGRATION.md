# IMX882 sensor MCLK acquisition: Untested

`sensor-mclk.patch` changes the existing identity driver's real probe and its
paired binding/disabled sensor fixture. It replaces an implicit rate request
through the CAMTG2 factor with the B4.1 operation: acquire CAMTG2_SEL, select
its explicit UVPLL192M_D8 parent, and require the existing source to be 24 MHz.
There is no shared PLL rate write and no VMM voltage or firmware vote change.

The reviewed delta is packaged as `0121-media-i2c-imx882-acquire-mclk-source.patch`
after the existing native patches. The identity driver remains compile-only
in the package and is also registered in CI's isolated object smoke config.
When the packaged source is compiled and intentionally selected, the actual
call path is `imx882_identity_driver.probe -> imx882_identity_probe ->
imx882_mclk_acquire -> imx882_power_on -> imx882_read_reg -> imx882_power_off`.
The C fragment is inserted into that driver, not linked as another owner.
The streaming driver's copied power helpers are deliberately outside this
slice: it does not acquire this new source and must not be enabled on this basis.

## Real acquisition and failure paths

The probe first requires raw I2C transfers, all four explicit supply references,
the two mandatory CCF handles and active-low reset. GPIO acquisition uses ASIS.
Observed ON sensor rails or an enabled MCLK return `-EBUSY` before reset writes.
The existing normal regulator references preserve shared supply accounting;
they are not an exclusive rail or secure-owner handoff.

The MCLK operation holds actual rate references on the selector and source,
rejects source/output aliasing, rejects a source rate other than 24000000 with
`-ERANGE`, propagates parent-selection failure, and checks the resulting CCF
parent/rate before proceeding. The two booleans track acquired CCF references,
not readiness, ownership proof or calibration. A failed acquisition releases
only those references and returns the first error. It does not assert sensor
reset, power down an inherited output, retry or force a provider transition.

After acquisition, the probe asserts reset with a checked direction operation
and uses the unchanged vendor-derived AFVDD/AVDD/DVDD/DOVDD delays, 4 mA pin
state, clock enable and reset release. It reads only 0x0016/0x0017, accepts only
the existing physical ID 0x8202, then attempts the existing checked shutdown.
An I2C/power error stays the result if cleanup also fails. No register table,
stream write, EEPROM or calibration transfer is added. Physical ID does not
distinguish IMX882 from IMX882TXD supplier/calibration identity.

## Source pins

All vendor facts come from `git show <pin>:<path>`, regardless of checkout HEAD.
The Linux archive must match its APKBUILD SHA512. `evidence.json` freezes the
source, packaged input, scoped baseline, delta and resulting payload hashes.

| Pin | Source and fact |
| --- | --- |
| `ee2be53cb75670b548948636a0db1d1ff112bf12` | `arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts` includes `cust_mt6878_camera_v4l2.dtsi`; its sensor0@1a maps `24` to UVPLL192M_D8 and `mclk` to CAMTG2_SEL, without a sensor power-domain property. GPIO93/25 and sensor rails remain the existing packaged fixture's resources. |
| Same device-module pin | `drivers/clk/mediatek/clk-mt6878.c`: CAMTG2 parents contain UVPLL192M_D8, derived from UNIVPLL /104. |
| `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` | `mtkcam/imgsensor/src-v4l2/adaptor-hw.c`: the 24 MHz clock handle is selected with `clk_set_parent`; both IMX882/IMX882TXD `pw_seq` tables supply the existing rail values/delays/reset sequence. |
| `d84b264a54a37611f2f46bc19363cb9b41606205` | `drivers/clk/mediatek/clk-mt6878-topckgen.c`: CAMTG2 is a factor wrapper; CAMTG2_SEL is the real mux/gate with the same parent route. `drivers/clk/clk.c` supplies the real rate-reference, enabled-state and parent APIs. |
| Same Linux pin | `arch/arm64/boot/dts/mediatek/mt6878.dtsi`: I2C8 uses IMP_I3C8 and PERAOP_DMA_B, with no CAM/ISP genpd attachment. `drivers/i2c/busses/i2c-mt65xx.c` enables/checks those adapter clocks around transfers. |

## Parent integration and activation inputs

The package applies this after the identity/reset/shutdown/rate patches and
disabled fixture. Compile the real identity object with the existing kernel/CCF/GPIO/
regulator headers, and validate the changed binding and complete board DTB in
CI. The shipping config and all five fixture statuses remain unchanged here.
`STAGING.json` gives the parent the object, config and DT targets. This slice
requires no duplicate supplier, fake clock, owner cookie or firmware-ready flag.

Before an intentionally selected runtime ID probe, establish sensor rail and
pin OFF handoff **before** fixed-regulator registration: GPIO-backed regulator
registration can drive its initial level before this consumer observes it.
The consumer's OFF checks cannot certify that earlier state or secure ownership.
Establish all shared AFVDD/DOVDD clients and exclude a concurrent sensor client.
CCF rate exclusivity does not exclude another consumer enabling an output.
The enabled-state API is the existing native gate observation, not an
independent checked MMIO or secure-world ownership interface. Require the real
CCF source to already be 24 MHz; a different rate fails instead of retuning it.
I2C8/pinctrl/GPIO suppliers and installation of the driver are parent inputs.

The external sensor-ID path uses those existing owners, with no added CAM/ISP
attachment or VMM access. It does not solve the separate MM_INFRA/shared-VMM/
CAM_VCORE/CAM_MAIN/ISP_VCORE graph. Its voltage/rate and MMUP/firmware handoff,
receiver/DMA graph, module identity and per-device calibration remain required
before capture. No secure status, functional camera or activation is claimed.

## Validation scope

Run the three commands in `STAGING.json` from the repository root. All are
static/application checks; the Python mutation tests do not execute C or
simulate hardware. The checker uses tracked package inputs and their APKBUILD
hashes; pre-existing untracked camera work is not consumed.

The reviewed package copy, its source order and APKBUILD SHA512 are checked
against the canonical delta. The generator excludes only that reviewed copy
while reconstructing its pre-delta baseline; it does not adopt other untracked
package inputs. The driver, binding, Kconfig/Makefile, clock and I2C inputs are reconstructed
from the verified Linux archive plus relevant packaged file hunks. The DT
delta is checked against the complete I2C8 sensor subtree added by tracked
0055, including its disabled status; it is not a full board assembly test.
Attempts to reconstruct the whole board locally encountered legacy package
patch formatting/context failures outside this slice. Those files were not
edited. Parent CI must check the delta against the fully prepared kernel and
compile/schema-check the complete DT. Local checks neither prove nor replace
that gate. No native build, dtc, emulation, JIT, phone access or CI dispatch was run.
