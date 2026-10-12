# Real CCIF / DPMAIF DT binding

This is a separate, explicit r182 diagnostic DT, not an automatic modem boot.
It inherits the working native display/sensor/USB tree unchanged and describes
the actual B4.1 CCIF/DPMAIF register windows, GIC SPIs, nine CCF handles, CCIF4/5
windows and shared reset syscons. The existing AO syscon gains #clock-cells=1.
Addresses/IRQs/clock IDs come from Nothing device modules
`ee2be53cb75670b548948636a0db1d1ff112bf12`, not a current-handset memory dump.

CI compiles this DT, validates the complete normal-to-diagnostic delta, and
repackages the exact original r182 FIT while preserving kernel, initramfs,
addresses, configuration and boot filesystem. Current normal DT, APKBUILD,
installed module selection and the disabled root modem anchor stay unchanged.
The research modules are absent from the installed r182; this DT cannot cause
udev to load them. The controlled test must use the reviewed resource-only CCCI
profile, never legacy HIF initialization. Keep loaded owners until reboot.

Expected next evidence is an actual bound CCIF/DPMAIF device, completed memory
claims, real OF clock lookups and owned IRQ descriptors with no clock enables,
MMIO mapping, IRQ handlers, DMA or transport publication by the module helpers.
OF platform population can create IRQ mappings/program trigger configuration
before our probe; the test is not advertised as hardware-free. Preserve the
first failure and USB/sensors, with original r182 FIT/stock lk_b as recovery.

## Full startup remains separate

The source MD node's genpd relationship is not removed or faked to permit a
passive consumer. MD remains the shipping disabled metadata anchor; no private
preparation or START is requested. Full DPMAIF runtime also needs the actual
DVFSRC/interconnect/required-OPP ownership, which this resource-only DT does not
pretend to provide. No dummy performance provider, inferred SIM EINT conversion,
fallback address, guessed regulator voltage or missing firmware reservation is
introduced. Complete lifecycle, secure handoff and native radio/audio userspace
are mandatory before SIM, registration, calls or data can be claimed.

```sh
python3 -B patches/modem/drafts/runtime-hif-dt/test_dt.py
python3 -B patches/modem/drafts/runtime-hif-dt/check.py normal.dtb candidate.dtb
```

Source/typed tests do not compile DT locally. Actual DT compilation/FIT building
is CI-only; raw private vendor images and per-unit calibration are not committed.
