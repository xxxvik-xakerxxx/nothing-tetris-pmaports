# Native Infrastructure Clocks

CCCI needs six CCIF and three DPMAIF clock handles. Linux d84 already defines
their IDs and topckgen parents but lacks the infrastructure AO provider. This
candidate implements the complete 13-clock bank using the standard MediaTek
CCF gate/provider helpers, including their normal cleanup. No Android clock
framework, hard-coded virtual mapping, forced parent enable, or secure call is
added. Native compatible matches the existing IFR syscon, not a second device
aliasing its register region.

The exact B4.1 device-module input is
`ee2be53cb75670b548948636a0db1d1ff112bf12:drivers/clk/mediatek/clk-mt6878-bus.c`.
The native IDs and parent names are checked against Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`. `check.py` compares every ID,
parent, bit and SET/CLR/STA bank, and rejects mutated tables.
Vendor `top_` parent names are translated to native factor names by their exact
clock IDs, upstream mux identity and unchanged 1:1 divider; no orphan aliases.

Read-only stored handset DT evidence independently agrees: CCIF clock IDs
3/4/1/2/11/7, DPMAIF 10/5/12, all under the same `syscon@10001000` provider.
That stored slot's OS release has not been proven; source pin is authoritative.
The legacy global `mediatek,infracfg` reset window is instead at `0x1020e000`.
It must not be replaced by this AO clock/syscon block.

## Integration Boundary

CI stages and compiles this source in an isolated clock subdirectory, then links
the real module against the unchanged, hash-checked r181/r182 config and kernel
exports. Strict modpost is mandatory; genuine imports, AArch64 identity,
vermagic, source hash and absence of external module dependencies are recorded.
The linked module is preserved for a subsequent controlled device test. It is not
selected in APKBUILD/Kconfig/DT, installed, bound or loaded on r182. Compilation
does not establish hardware accessibility. Provider registration can read gate
state; consumer enable/disable and CCF unused-clock cleanup can write hardware.
Before installation, verify the existing IFR regmap ownership, controlled
registration, all parent/consumer references and the quiescent modem handoff.
Do not drop `clk_ignore_unused` or add blanket critical/ignore-unused flags to
make an unowned transport appear initialized. The modem power relationship,
transport resources, IRQ/DMA lifetimes and secure boot release still require
integration before SIM or calls can work.

```sh
python3 -B patches/modem/infra-clocks/check.py \
  --vendor ../android_kernel_device_modules_6.1_nothing_mt6878 \
  --linux-archive ../linux-d84b264a54a37611f2f46bc19363cb9b41606205.tar.gz
```
