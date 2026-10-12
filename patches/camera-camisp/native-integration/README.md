# Native CAM/ISP provider integration: Untested

`native-provider.patch` connects the existing Linux `mtk-pm-domains.c` probe to
the shared supplier. It installs real CAM_VCORE, CAM_MAIN and ISP_VCORE power
callbacks, creates the shared owner under **the existing MM_INFRA genpd**, and
attaches persistent child guard devices/notifiers before OF publication.
There is no replacement MM_INFRA, dummy regulator or fabricated hardware ID.
The native MM_INFRA HWV/HWCCF behavior from packaged 0057/0074 stays in use.

The software graph is MM_INFRA -> shared VMM -> CAM_VCORE -> CAM_MAIN, with
ISP_VCORE as VMM's other child. Existing direct MM_INFRA -> VCORE DT edges
remain. The graph uses native genpd's shared-child accounting. CAM_MAIN failure
latches the original errno before its VCORE parent's notifier/unwind.

## Source and Build Contract

- Linux: `d84b264a54a37611f2f46bc19363cb9b41606205`, archive SHA512 checked against APKBUILD.
- B4.1 device modules: `ee2be53cb75670b548948636a0db1d1ff112bf12`.
- Camera modules: `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`.

The patch is generated against native pmdomain hunks in the current APKBUILD's
actual source order, including the parent's modem and GPUEB changes. The checker
applies those **provider/power-ID hunks**, then checks and applies the integration
patch, and verifies resulting bytes. It does not claim a full package/DT check.
The paired binding YAML is parsed structurally; dt-schema/DTB validation stays
with the parent CI workflow.
`evidence.json` records the source, baseline payload, packaged patch, output and
integration patch hashes. No checkout HEAD is used for vendor evidence.

`CONFIG_MTK_MT6878_NATIVE_VMM` is a bool, **default n**, depending on the existing
native provider, OF and REGULATOR. When disabled, probe hooks are inert stubs and
supplier objects are absent from Kbuild. For combined CI, enable it with the
requirements and KUNIT y/n variants in `STAGING.json`; build the actual native
provider plus both helper objects, then link vmlinux. Do not also link either
standalone power smoke route: that would duplicate the original leaf/supplier
symbols. Original `power/` files and manifests remain unchanged.

The generator reuses the frozen checked CAM/supplier sources, adds a checked
ISP_VCORE control adapter from their existing transactions, and translates the
B4.1 ISP_VCORE descriptor into Linux's descriptor format. ISP_VCORE's offset is
`0xe34`; protection is bit 8 at `0xc14/0xc18/0xc1c`, then bits 7/8 at
`0xc24/0xc28/0xc2c`, with ignored clear ACK but checked writes. Its two control
ACKs use the same sequential B4.1 ON/OFF path, not the native generic simultaneous
ON or boolean OFF check. The supplier mutex covers rail/isolation checks,
control writes/ACKs and the first-error latch for both CAM and ISP.

## Parent DT Contract

This patch extends the existing binding schema with the paired controller
supplies, restricted to the existing MT6878 compatible. Their phandle equality
is enforced by the driver. It adds no DTS, FIT selection, shipping config or
package entry; the parent owns those changes. Under the existing
`mediatek,mt6878-power-controller`, describe MM_INFRA's actual HWV and clocks,
CAM_VCORE under MM_INFRA, CAM_MAIN under CAM_VCORE, and ISP_VCORE under MM_INFRA.
Only these three CAM/ISP leaves are covered. Active CAM_SUBA/SUBB, CCU/CCU_AO,
ISP_MAIN/DIP1 descendants are rejected with `-EOPNOTSUPP`; no callback silently
pretends to operate them.

The controller device must carry **both** `cam-vcore-supply` and
`isp-vcore-supply`, referencing the same real regulator node. Each leaf must
omit `domain-supply`. B4.1 `mt6878.dts:2930/2931` references
`mt6319_6_vbuck1` for this pair. Lines 13585-13605 describe USID 6, VBUCK1,
the `mediatek,mt6315_6-regulator` provider and buck1 mode mask `0x1`.
The constructor requests one exclusive `cam-vcore` handle on the controller;
the phandle-equality check occurs before either domain can acquire a supply.
The candidate requires the native direct SPMI `regulators/vbuck1` hierarchy,
`mediatek,mt6315-regulator` compatible, USID 6, and explicit
`mediatek,buck1-mode-mask = <1>`, with all three nodes available. This translates
the vendor MFD description using the packaged native regulator binding; equal
phandles to another buck or a dummy regulator are rejected before acquisition.

CAM_MAIN needs one basic clock named `cam`, followed by the eight B4.1 protection
clocks named `cam_main-0` through `cam_main-7`, in this order:

1. CAM_MAIN CAM2MM0_GALS
2. CAM_MAIN CAM2MM1_GALS
3. CAM_MAIN LARB13
4. CAM_MAIN LARB14
5. CAM_MAIN LARB29
6. CAM_MAIN CAM_MRAW
7. CAM_MRAW GALS
8. CAM_MRAW LARBX

CAM_VCORE and ISP_VCORE have no clocks in these B4.1 descriptors. Missing or
misordered clock names/counts fail construction; actual clock phandles must
still be validated by the parent's DT/source checks. There are no guessed
clock IDs or compatibility aliases in this slice.

All other available DT `*-supply` properties referring to this buck are rejected.
This includes B4.1 `vmmspm` (`mt6878.dts:2997`) and MMDVFS debug (`:3954`).
Exclusive acquisition also rejects already-held Linux regulator handles and
prevents later competing handles. Neither test establishes firmware ownership.
Those existing clients must have a demonstrated replacement/ownership migration
before activation; deleting their supply properties is not proof of migration.

## Failure and Lifetime

Construction observes control requests, both ACKs, reset/isolation/clock-disable,
SRAM and bus-protection state, requiring actual safe OFF without hardware writes.
The supplier then requires the buck OFF and all three VMM isolation bits set.
Inherited ON and inconsistent or unreadable state fail; there is no forced OFF
or inherited-ON takeover. The original exclusive-get adoption behavior and its
retained enable reference on rejected inherited ON are preserved.

ON: supplier check, basic clocks, checked control, subsystem clocks, SRAM,
bus release. OFF: supplier check, bus protection, SRAM off, subsystem clocks
off, checked control/ACKs, basic clocks off. Each fallible phase stops and latches
its original error; no rollback releases prior successful dependencies.
`clk_bulk_prepare_enable()` can unwind its own unsuccessful acquisition; this
candidate cannot override that core API behavior. Supplier failures retain
their first errno and prevent later transitions, keeping native parent references
where genpd still owns them. Regulator failure can still alter physical state.

Each managed domain installs `dev_ops.start`, paired `stop`, and a native resume
wrapper. The start guard runs before a driver resumes even with cached-ON genpd
state. The wrapper preserves a latched supplier errno instead of genpd's `-1`
for a failed start. It does not repair unrelated driver errors or change core ABI.
System resume/noirq and bus-access lifetime still require CI/hardware validation.

Before exclusive acquisition, cleanup unlinks native edges before removing
observed-OFF domains; camera cleanup never invokes force-OFF. After acquisition,
graph/notifier/publication failure **binds with the OF provider withheld**, logs
and stores the first error, and retains devres, guard devices, regulator and
genpd storage until recovery. Returning success to bind is solely the permanent
lifetime mechanism; consumers have no published provider and cannot attach.
It is not readiness or a successful power transition. There is no unbind,
reconstruction, retry, fault-clear or shutdown policy; use the existing built-in
provider's suppressed bind attributes and clean reboot recovery. Dynamic DT
removal remains unsupported.

## Unresolved Activation Inputs

The entire board wiring is not yet justified. Native USID-6 rail registration
and constraints, the voltage/rate policy and firmware/MMUP ownership handoff
must be supplied and demonstrated. B4.1's VMM/MMDVFS sources show separate rail
users; their absence from an available DT does not establish a quiescent secure
owner. The B4.1 voltage bounds are not an operating point. This integration
does not invent one or set voltage/rate, issue an SMC, or assert a ready flag.
Wider CAM/ISP clock providers and descendants also remain outside this slice.
This therefore advances callable provider binding, not camera functionality.

Static commands, from repository root:

```sh
python3 -B patches/camera-camisp/native-integration/generate.py
python3 -B patches/camera-camisp/native-integration/check.py
python3 -B patches/camera-camisp/power/check_supplier.py
python3 -B patches/camera-camisp/power/test_supplier.py
python3 -B patches/camera-camisp/power/check.py
python3 -B patches/camera-camisp/power/test_source.py
```

After an authorized source change, regenerate with `generate.py --write` first.
All local validation is static/application only. No native compilation, dtc,
emulation, JIT, SSH, activation, commit or push was performed. ARM64 combined
objects/vmlinux, DT validation, live OFF/ON evidence, cold repeats and lifecycle
checks remain for the parent's CI/hardware workflow.
