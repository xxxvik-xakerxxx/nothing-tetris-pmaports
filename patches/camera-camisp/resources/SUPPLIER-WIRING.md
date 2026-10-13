# Supplier board wiring: Untested

`mt6878-nothing-tetris-camisp-supplier.dts` is a separate, dormant supplier
diagnostic candidate. It includes the unchanged native board and two new
fragments. The exact DT delta adds the source-backed rail/domain/resource
descriptions while preserving every baseline property and node, including
display, SCP firmware/memory, USB, SPM, MM_INFRA clocks/HWV, the USID6 observer
and existing VBUCK2. Its intended boot compatibility is based on that inert
delta; **it has not been compiled or booted**. It does not register a regulator,
perform a new observation, construct VMM, publish camera domains or capture an
image. The baseline USID6 observer remains disabled, exactly as inherited.

The old `camisp-disabled` board compiled in CI38317130122 but disables SPM,
MM_INFRA and display IOMMU. That is a nonbootable compile fixture, not evidence
for this candidate. Its generated DTS, fragments, patches and `STAGING.json`
are preserved byte-for-byte.

## Concrete graph and rail migration

| Object | Actual description |
| --- | --- |
| PMIC | Extend the existing unique `&mt6319_gpu`, direct SPMI USID6, native `mediatek,mt6315-regulator` fallback, buck1 phase mask 1; no second PMIC |
| VMM rail | `regulators/vbuck1`, label `mt6319_6_vbuck1`, name `6_vbuck1`, 300000..1193750 uV, 256 us ramp constraint; disabled |
| Other shared rail | `regulators/vbuck4`, exact same stock bounds/ramp and stock always-on constraint; disabled, never registered |
| Existing GPU rail | Existing disabled VBUCK2 and its properties unchanged |
| Domain tree | Extend real MM_INFRA ID7 with disabled CAM_VCORE ID10 -> CAM_MAIN ID13, and sibling ISP_VCORE ID16 |
| CAM_MAIN | Real TOPCKGEN `cam` followed by all eight ordered B4.1 protection clocks, with bank-correct native IDs |
| Physical resources | Disabled CAM_MAIN/MRAW/CAM_VCORE clocks, common31 -> subcommons16/19 -> larbs13/14; real SPM domain phandles and display common reset supplier |
| Logical resources | Disabled CAMISP larbs13/14 with ports416/417/448/449; no physical MMIO or clock ownership |
| Display IOMMU | Entire existing node and larb membership unchanged; disabled camera larbs are not enrolled in its live probe |

The canonical native integration creates the internal software graph
MM_INFRA -> shared VMM -> CAM_VCORE / ISP_VCORE, with CAM_VCORE -> CAM_MAIN.
There is no DT node or invented hardware ID for software VMM, and no dummy
MM_INFRA. All unsupported camera/ISP descendants and all camera consumers
remain disabled. No clock rate, voltage, regulator mode, OPP, boot-on or
firmware readiness property is invented.

`mt6878-camisp-vmm-ownership-blocked.dtsi` contains the actual owner selection:

```dts
&mt6319_gpu {
    /delete-property/ mediatek,observe-vgpu-only;
};
&spm {
    cam-vcore-supply = <&mt6319_6_vbuck1>;
    isp-vcore-supply = <&mt6319_6_vbuck1>;
};
```

This is included only by `mt6878-nothing-tetris-camisp-vmm-ownership-blocked.dts`,
a **compile-only, forbidden-to-boot** target. It keeps PMIC, rails and new domains
disabled; it contains no enablement hunk. The paired properties opt the active
SPM into the canonical native VMM guard. That guard checks available real rail
identity before exclusive acquisition, then requires all three available
domains. This blocked description fails those checks and prevents SPM provider
publication, including display. Removing the observer alone does not supply
VMM: the observer branch returns before registration and exposes no regulator.
Enabling PMIC alone retains observer behavior; enabling disabled children alone
also cannot make a supplier. No such partial enablement is a boot candidate.

## Exact unresolved blockers

All stock facts refer to Nothing Tetris-B4.1-260415-1709 device modules
`ee2be53cb75670b548948636a0db1d1ff112bf12`; camera resource provenance remains
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. Native source is Linux
`d84b264a54a37611f2f46bc19363cb9b41606205`. Existing `evidence.json` freezes
stock DT/rail/clock/graph facts; new `supplier-evidence.json` freezes the
following additional source bytes and read-only parent contracts.

| Blocker | Pinned evidence and missing contract |
| --- | --- |
| Registration is writable | Native `of_regulator.c:99-111` derives `apply_uV` from both voltage bounds; `core.c:1209-1261` can program a selector to apply them. `core.c:6132` documents disabling unused rails. Packaged 0110 registers only available described rails; 0113 limits owned mode phases. Registering VBUCK1 is not observation. Missing safe registration, unused-rail and shutdown policies for this shared PMIC. |
| PMIC shutdown | Native MT6315 shutdown and packaged 0111 write protection keys and TOP2_ELR7; the observer bypasses this in 0114. Switching this one PMIC from observation to registration changes its shutdown behavior even with VBUCK2/VBUCK4 unregistered. Missing demonstrated shared-PMIC shutdown ownership. |
| Voltage/rate | Stock `mt6878.dts:13601-13604` gives a permitted range, ramp and vendor mode enum, not a selected voltage or native CAM/ISP OPP contract. Native supplier does not request voltage/rate. Missing validated cold operating voltage, selector readback, clock limits, sequencing and concurrent display/SCP/MMDVFS policy. Vendor mode enum is not copied into the native binding. |
| Linux isolation owner | Stock DT `:2993-2997` and `mtk-vmm-spm.c:428,445-446` acquire `vmm-pmic` and register the isolation notifier; `:372-405` changes isolation on ENABLE/PRE_DISABLE. Missing migration of that handle/notifier to the checked shared owner, including error and inherited-ON handling. |
| Linux DVFS owner | Stock DT `:3944-3954` and `mtk-mmdvfs-debug.c:839` acquire another `vmm-pmic` handle; it also holds VBUCK4 VCORE. Missing replacement for this independently acquired VBUCK1 user without disturbing VCORE/display. |
| Firmware owner | `mtk-mmdvfs-v3.c:243-358` sends/acknowledges requests through VCP `IPI_OUT_MMDVFS`; `:401,431` vote OPPs, `:496` sends VMM genpd notifications, `:1092` forces voltage and `:1124` forces clocks. Missing release-matched MMUP/VCP firmware ABI and acknowledged quiescent handoff of voltage/clock/isolation control. Exclusive Linux regulator lookup and absent DT clients prove none of that. SCP must remain operational; disabling it is not an ownership migration. |
| Cold state | Canonical native owner requires observed OFF buck plus all three isolation bits, OFF requests/ACKs, SRAM and bus protection; inherited ON is rejected and no forced-OFF takeover exists. Missing live baseline, safe handoff and recovery evidence, then cold repeats, clean installation, lifecycle and portability. |

Those blockers prevent justifying a supplier-active diagnostic, even with camera
consumers disabled. An ownership-ready DT cannot be made safe by adding a fixed
voltage, always-on flag or deleting conflicting supplies. The blocked target
deliberately makes the remaining boundary reviewable without crossing it.

## Static checks and parent handoff

`generate.py` deterministically generates the separate files and additive
`supplier-description.patch` / `ownership-description.patch`; neither changes
any shipping source. `SUPPLIER-STAGING.json` is distinct from the old object
manifest and is not consumed automatically by parent CI. It lists both targets,
exact payload hashes, required existing resource header and config variants.

```sh
python3 -B patches/camera-camisp/resources/generate.py --check --verify-vendor
python3 -B patches/camera-camisp/resources/check.py
python3 -B patches/camera-camisp/resources/check-supplier.py --verify-vendor
python3 -B patches/camera-camisp/resources/test-source.py
python3 -B patches/camera-camisp/resources/test-dt.py
python3 -B patches/camera-camisp/resources/test-supplier.py
```

The DT checker compares every baseline property using typed reference owner
paths, validates the entire additive inventory, all resource properties and
ordered clock/SMI/IOMMU links, enforces exact disabled stock constraints,
rejects duplicates/dummies and competing available buck users, and distinguishes
the permitted observer deletion/supply pair from the boot-preserving profile.
Synthetic Python fixtures mutate all baseline properties, new resources,
statuses, supply pairs, clock order, phandles, manifests and provenance. These
are static tests, not kernel or regulator execution.

Parent CI must explicitly stage/compile the baseline and each planned target
using normal board Kbuild flags, without `-@`, then validate each full DT delta:

```sh
python3 -B patches/camera-camisp/resources/check-dt.py --profile supplier \
  --base path/to/mt6878-nothing-tetris-native.dtb \
  --fixture path/to/mt6878-nothing-tetris-camisp-supplier.dtb
python3 -B patches/camera-camisp/resources/check-dt.py --profile ownership-blocked \
  --base path/to/mt6878-nothing-tetris-native.dtb \
  --fixture path/to/mt6878-nothing-tetris-camisp-vmm-ownership-blocked.dtb
```

Compilation, schema validation, canonical provider linkage and boot compatibility
remain untested. Only the dormant candidate has a defensible baseline-preserving
DT delta; no active supplier, camera support or live gate is claimed. No local
native compilation/DT compilation, phone access, commit or push was performed.
