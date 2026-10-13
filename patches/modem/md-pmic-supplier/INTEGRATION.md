# Future Native MT6363 Rail Diagnostic

Hardware status: **Untested**. This helper is not connected to shipping inputs,
the parent staging helper, or a workflow. The r184 ACK30 image and run
38356364811 remain unchanged. No new build, phone operation, commit or push is
part of this side task.

`ci/stage-native-modem-rails.py` consumes a **disposable copy** of the already
staged r184 package tree and its parent report. It appends the exact verified
`native-modem-rails.patch` as `0185-native-modem-rails.patch`, SHA256
`459f5c85b0b8372ce8328d8825013fc692873be1b7f70342d9c5c2d20fc3a832`.
The parent-reported ARM64 KUnit y/n runs are 38332592584 and 38336059980.
`0186-native-modem-rails-registration-dt.patch` then binds the real suppliers
and TOP to the existing disabled modem and preserves inherited voltage at
registration. The disposable kernel package becomes `7.2.1-r185`; the parent
device package, configuration, FIT selection and U-Boot pairing are retained.

The mapping is Nothing B4.1 device modules
`ee2be53cb75670b548948636a0db1d1ff112bf12`, not a measured handset constant:

| Consumer | Actual MT6363 child | Consumer target |
| --- | --- | --- |
| `md-vmodem` | `vbuck2` | 800000 uV |
| `md-vsram` | `vsram-modem` | 800000 uV |
| `md-vdigrf` | `vbuck1` | 700000 uV |

`ccci-topckgen` resolves to the existing MT6878 TOP syscon at `0x10000000`.
The standard native child bounds remain 300000..1193750 uV for VBUCK1/2
and 400000..1193750 uV for VSRAM_MODEM, delay 180 us, modes `<0 2>`.
The exact consumer target pairs live on the **disabled consumer**, not as
fixed regulator constraints. No boot-on, always-on, initial mode, load,
GPIO, suspend control, fixed regulator or modem ON callback is introduced.

## Registration Policy

Linux `d84b264a54a37611f2f46bc19363cb9b41606205` OF parsing sets `apply_uV`
when both DT bounds are nonzero. `machine_constraints_voltage()` then reads
the current selector and may request a clamp. The verified native driver
rejects such probe-time writes through `state->registering`; without the
follow-up, an out-of-range inherited selector can fail registration.

The future diagnostic follow-up clears only
`init_data->constraints.apply_uV` after successful exact-node parsing
and before registration. Parsed ranges, allowed modes, standard operation
permissions, mutation admission, error latches and real callbacks are retained.
The mutable pointer returned by the single OF parse is retained locally and
then assigned to the const-qualified `config.init_data` view; no const cast or
second parse is used. This uses the regulator core's existing constraint API. It neither fabricates
readback nor silently grants ownership. The header already includes
`linux/regulator/machine.h`. Connectivity/GPU descriptor and probe blocks
remain byte-identical to the verified extension.

With no initial enable/mode/load or coupling properties, registration cannot
request a PMIC write through these callbacks. Debug/status reads may still
return real errors. Later core unused-regulator cleanup can request disable;
the unchanged native callback rejects an inherited enable with `-EBUSY`
because it owns no enable request. OP banks, SSHUB, shared FCCM keys and
hardware voters remain untouched. This registration policy is statically
checked here; it was not part of the earlier native KUnit builds.

## Reusable Entry Points

Future authorized CI, **only after copying the parent snapshot**, may use:

```sh
python3 -B ci/stage-native-modem-rails.py stage \
  --pmaports /tmp/future-rails-pmaports \
  --parent-report /tmp/future-rails-pmaports/parent.json \
  --report /tmp/future-rails-pmaports/rails.json \
  --activate-native-rails
```

Omitting `--activate-native-rails` stages the same real driver and supply
wiring with all three native children disabled. Passing it changes only those
children to standard DT `status = "okay"`; the modem, NEMI and input SPM
supplier/domain remain disabled. No custom DT activation permission exists.
The parent U-Boot first-OFF behavior is inherited; this is not a PMIC-only
boot profile and does not enable modem execution.

Before any future build, recompute package checksums with the normal
pmbootstrap checksum path. Do not bypass checksum verification. Check the
actual prepared post-r184 kernel and all three compiled DTBs in that future
CI environment:

```sh
python3 -B ci/stage-native-modem-rails.py check-kernel /path/to/prepared-r184 \
  --activate-native-rails
python3 -B ci/stage-native-modem-rails.py check-dt \
  /path/to/shipping-native.dtb /path/to/parent-r184.dtb /path/to/rails.dtb \
  --activate-native-rails
```

`check-kernel` never modifies its input; application happens in a temporary
copy, pins the core/OF initialization source hashes, verifies every native
output hash, and restores the follow-up text to
prove the verified callbacks are identical. `check-dt` validates the full
shipping -> parent -> rail delta by node identity and typed references,
including both connectivity rails and every unrelated node/property. It
rejects changed consumers, incorrect supply owners/TOP, extra/missing nodes,
unexpected regulator controls and accidental modem activation. It reads
existing DTBs with `fdtget`; it does not compile them.

Local static verification only:

```sh
python3 -B ci/test-native-modem-rails.py
```

## Next Hardware Gate

After separately authorized future CI and image preparation: record artifact
identities, baseline USB/SSH and recovery route; cold boot the explicit rail
diagnostic and verify genuine provider names, the disabled modem and preserved
connectivity. Inspect inherited selectors/control banks and retain the first
read/admission error. Registration is not electrical voltage verification or
permission to set a rail: guarded callbacks still require the source-defined
normal AP profile and inactive SSHUB. No modem restart, rail operation,
automatic radio initialization or hardware success is claimed here.
