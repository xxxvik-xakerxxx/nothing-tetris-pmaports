# VGPU readback host gate

Status: host source characterization passed; GPU remains Broken and runtime
readback compatibility is Untested. This gate deliberately records a source
difference, rather than asserting that the two providers are interchangeable.

Run from the Panthor worktree:

```sh
python3 scripts/check-panthor-vgpu-readback.py \
  /path/to/prepared-linux-6.18 /path/to/device-modules-git
```

Only a host C compiler, Python standard library and local git objects are used.
Temporary files are removed. The vendor checkout is ignored: functions and
register definitions come from Nothing 4.1 commit
`ee2be53cb75670b548948636a0db1d1ff112bf12`. The kernel input is read-only;
its three source hashes are printed so a prepared/patched tree is traceable.

## Boundary established

Baseline: hardware-integration `aecf4f44f4170952709a7dd514538f0d75b55e22`;
worktree starting point: `5a3485792cccbdf88cb75e0ce009beb5cdad5f83`.
The baseline's patch 0035 already sets MFG0 `KEEP_DEFAULT_OFF`, despite the
GPU bring-up document listing that flag as future work. This does not prove
registration is free of register access or that power sequencing is usable.

The pinned vendor `mt6878.dts` connects VGPU to MT6319 USID 6 VBUCK2.
Its regulator descriptor uses the MT6315 register layout. The next narrow
regulator question is which voltage is observable while that rail is enabled:

| Read | Vendor MT6315 callback | Mainline MT6315 callback |
| --- | --- | --- |
| Enable indication | VBUCK2 DBG4, bit 0 (`0x151d`) | Not read |
| Enabled selector | VBUCK2 DBG0 (`0x1519`) | ELR2 (`0x144b`) |
| Disabled selector | ELR2 (`0x144b`) | ELR2 (`0x144b`) |

For example, a fake enabled rail with ELR2=80 and DBG0=96 reports 500000 uV
through mainline and 600000 uV through vendor (6250 uV per step). These are
synthetic test values, not measurements or proposed operating voltages.

The test compiles the actual vendor callback and the actual mainline generic
helper selected by `mt6315_volt_range_ops`; it does not reimplement their
branching. Small fake regulator structures and a read-only regmap verify
73728 selector/state combinations, exact access order, unrelated status bits,
and five read failures. Two compiled mutations must fail: selecting ELR2 while
enabled and swallowing read errors. Descriptor shape guards fail closed on
relevant source drift. This is a narrow source fixture, not a full C/DT parser,
regulator-core test, or kernel compilation.

Validated on the local Linux tree from `d84b264a54a37611f2f46bc19363cb9b41606205`:

```text
drivers/regulator/mt6315-regulator.c
3c3cfcbf91795a7ecb08fe3f00c9c1ba69d987315f5ce1c6704f97fa733a611a
include/linux/regulator/mt6315-regulator.h
73dc1bb4ae5e342a6ab215b17cbbea569bbbe25548a0e8fa13791eb2f8778e26
drivers/regulator/helpers.c
860f6e07370505cf909331d120390a3f622056af8d1c197dac795b1f5f9fa981
```

## Remaining risk and next live gate

Do not add or enable a regulator/GPU DT consumer based on this result. It
does not establish whether ELR2 and DBG0 differ on hardware, nor ownership
between Linux, GPUEB and secure firmware. The mainline provider also registers
all four regulator descriptors and has a shutdown callback that writes PMIC
registers; a consumer-free provider is not automatically read-only. Voltage
coupling, mode/enable writes, late regulator cleanup and cold-state ownership
remain separate blockers. CSF firmware identity is still unknown and GPUEB
partition contents are not a substitute.

Next minimal live gate, outside this host-only task: on a separately authorized
clean boot, record software/hardware identity, USB/SSH baseline and rollback;
use an already validated read-only PMIC access path to observe USID 6 DBG4,
ELR2 and DBG0, with no regulator registration or voltage/mode/enable writes.
Record stability and enabled-state readback agreement or divergence. Stop at
the first access error or USB regression. If no validated read-only path
exists, preparing that diagnostic path is the prerequisite, not enabling the
generic regulator driver. This observation cannot by itself authorize a GPU
probe, render-node claim, load test, or firmware selection.
