# Source-backed MFG0 cold prefix

Default-off, uninstalled native acquisition prefix. This directory is the only
new scope; frozen power/root/DRAM files are unchanged. No phone, local native
compilation, firmware execution, secure calls, PLL/PMIC programming or activation.

## Correction To The Frozen Candidate

Absence of MFG0 regulator/basic-clock handles is **not a physical missing-power
condition**. The pinned NOS MFG0 descriptor has no basic/LP/subsystem clock list.
Its common supplier accepts a missing optional regulator. Do not create dummy
handles, add DOMAIN_SUPPLY, attach GPUFREQ rails, or interpret zero handles as
either a hardware fault or proof that no electrical dependency exists.

The frozen power candidate's mandatory-handle gate is an unsupported admission
assumption. Leave that batch frozen for review, but do not solve its failure by
inventing dependencies. This new patch is an **alternative MFG0-only source
variant** of the original supplier, not an additive drop-in to owner-power.patch.
It must not link a second supplier copy alongside the full-power variant.

## Actual Prefix

`mt6878_gpueb_cold_prefix_prepare()` is a concrete staged C caller:

1. Validate and lock the fixed bound parent through the existing MFG0 owner.
2. Check the actual native SCPSYS/genpd identity and MFG0 data pointer. No
   regulator/clock existence requirement or caller permission flag.
3. Validate the original eight GPUEB resources; claim the one complete SRAM
   owner before any PM transition. Do not clear, upload or inspect firmware.
4. Publish the retained parent object before the original `pm_runtime_get_sync`.
   Native SCPSYS performs its existing SPM/SRAM/bus-protection sequence.
5. Read SPM through that SAME supplier's regmap and mutex; enforce the actual
   signed-LK entry condition and check native control effects. Read bus enable
   registers through existing supplier regmaps, without inventing an ACK poll
   that NOS's BUS_PROT_IGN intentionally omits.
6. Preserve the first failure, PM/device/module pins and SRAM after an attempted
   transition. On success release the task mutex but retain the real MFG0 lease.

No new RPC/clock/regulator/MMIO owner, provider publication or parent driver is
created. The API is not installed or scheduled by any runtime caller. The prefix
ends here intentionally: no RPC store, reset assertion/release, signed install,
GPR programming, IRQ activation or BOOTREADY producer. Success describes only
the acquired native prefix, never GPUEB boot, OFF or whole-GPU readiness.

## Exact Cold Boundaries

Authenticated B4.1 LK payload:
`431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a`.

- Caller `0xed58 -> 0x16eb0`: the hook is `mov w0,wzr; ret`, not a power owner.
  The caller accepts success or -16, then `0xed94 -> 0x1eb88` enters the loader.
- At `0x1ebc8`/`0x1ebd8`, SPM **0x1c001eb4** must already have ACK[31:30]=3,
  bit12 clear, and **bit13 SET**. `tbnz w2,#13` at `0x1ebe0` branches to success
  `0x1ec54`. A cleared bit13 logs sleep-mode failure; it is not an accepted state.
  Failure returns -16 at `0x1ec18`, before allocation or secure firmware loading.
- The selected loader path calls allocation/mapping, EMI protection, secure
  firmware loading and cache-clean helpers before RPC. Its transitive callees
  are NOT declared side-effect-free. None can explain the already-required
  MFG0 entry state retroactively.
- RPC **0x13f91030 = 0x10f00** is stored at `0x1edf0`, then reset/clear/copy and
  release follow in the already audited root path. They are not executed here.
- The timeout path reads **GPUEBPLL PCW 0x13fa080c** at `0x1ef74` and logs it.
  A timeout diagnostic after release is not a cold PLL enable/program producer.

**First causal unresolved producer:** the owner/order establishing the MFG0
entry ACK/SRAM bit13 state before `0x1ebc8`/`0x1ebd8`. NOS MFG0 only describes
PDN bit8/ACK bit12 and SRAM isolation; it does not supply a MFG0 sleep bit9/ACK13
transition. Another domain's sleep sequence cannot be copied as evidence for
MFG0. The new prefix can observe whether native acquisition reaches LK's state,
but no hardware test establishes that yet. The earlier owner could be earlier
LK, preloader or secure world; this trace does not select one without evidence.

The boot PLL/PMIC producer is also unresolved. No concrete Linux rail/bootclock
composition can responsibly be added from these checked sources alone.

## NOS Runtime Phases

Exact device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`:

- `drivers/soc/mediatek/mtk-scpsys-mt6878.c:367` defines MFG0 without clock
  lists; `mtk-scpsys.c:224` permits absent optional supply, and `:1677` gets it
  by domain name. The cold prefix preserves this actual ownership model.
- `gpufreq_mt6878.c:673` gets `vgpu`/`vsram`; no AP regulator-enable, voltage
  setter, clock-enable or platform power callback is supplied by that file.
- DT links VGPU to MT6319 USID6 VBUCK2 and VSRAM to MT6363 CPUM. The actual
  MT6319 provider compatible is `mediatek,mt6315_6-regulator`, implemented in
  `drivers/regulator/mt6315-regulator.c:334`, not the mt6316 driver.
- Base DTS always-on rail policies are Linux regulator constraints, not proof
  of which earlier cold-boot actor programmed the PMIC. Tetris overlay/customer
  inputs are hash-checked; this inspection is not a compiled effective DT audit.
- FHCTL gpu1 names GPUEBPLL at 0x13fa0800, PCW +0xc. Its runtime hopping function
  `clk-fhctl-gpueb.c:128` sends GPUEB IPI. The normal MT6878 CCF file has no
  GPUEBPLL provider. A running-firmware DFS method cannot bootstrap that firmware.
- GPUFREQ's wrapper reads GPR13 and sends INIT_SHARED_MEM/POWER_CONTROL in the
  later session phase; 0118 belongs there, not before the cold loader.

Exact modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835` select r44p1 through
the actual `gpu/mt6878/mali_avalon` symlink blob, `../gpu_mali/mali_avalon/`.
The MT6878 Mali runtime power-on callback calls GPUFREQ at line111 of
`platform/mt6878/mali_kbase_config_mt6878.c`. That is not a cold GPUEB producer.

SOURCE-EVIDENCE.json records checked paths/lines and direct LK call boundaries.
It contains no image dump, dynamic PA, calibration or fabricated secure status.

## Checks And CI

Local static checks, with the existing offline Capstone installation for LK:

```
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 python3 -B patches/gpu/boot-owner/power/cold-deps/test_prefix.py -v
python3 -B patches/gpu/boot-owner/power/cold-deps/generate_prefix.py --check
python3 -B patches/gpu/boot-owner/power/cold-deps/ci_prefix.py --check
```

Tests use exact git objects, authenticate LK, mutate source/image identities,
apply the generated delta to the exact packaged native preimage, and verify
ownership order and scratch isolation. Optional missing git/LK fixture inputs
are explicit skips, not successful hardware evidence. No C fixtures with dummy
or zero-valued dependencies are used.

Parent may call `ci_prefix.py --kernel ... --output ... --baseline ...` in CI
after a passed research-owner build. Both CI guards precede compiler execution.
It checks pinned source provenance, creates fresh disjoint source/O= copies,
compiles six complete actual ARM64 objects with real headers, and checks their
internal ELF/LLVM link. It does not stage the full-power or canonical upload
variant, mutate shared native inputs, run a C mock, or modify a workflow. There
is no final kernel link/modpost or hardware-state proof. Compilation has not
been performed locally.
