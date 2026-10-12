# Native camera power prerequisite: Untested

The next integration candidate is the [shared VMM supplier](SHARED-SUPPLIER.md):
native genpd aggregation, exclusive regulator ownership, checked isolation,
MM_INFRA retention and child fault guards. It remains uncalled and unactivated.
The original leaf payload below passed ARM64 CI38245658821 per the user's
reported result; that build does not cover the new shared-supplier object.

This candidate contains two real Linux `scpsys_domain_data` descriptors and
checked, bounded leaf transactions. It registers no provider, runs no probe,
exports no module symbols, changes no existing source or DT, and is not in the
shipping patch list. There is no camera power-on success claim. The earlier
clock/resource candidate's CI38236217805 result is an input supplied by the
parent; it does not validate this candidate or establish power ownership.

`mt6878_cam_ctl_set()` implements only the local
SPM control-register portion: first switch/ACK, 50 us delay, second switch/ACK,
clock-disable clear, isolation clear, reset release; OFF asserts isolation,
holds reset, disables the clock, then switches off and verifies each ACK
separately. It checks every register error. OFF cannot succeed merely because
one ACK disappeared. Each ACK poll has a 10 us interval and 1 s timeout.

`mt6878_vmm_iso_set()` implements only the evidenced MT6878 W1S/W1C transaction:
clear bits 24, 25, 26 at SPM+0xf30 after VMM enable; set bits 26, 25, 24 at
SPM+0xf2c before the last VMM disable; verify all three at SPM+0xf28. It returns
the original register error or `-EIO` on a readback mismatch. It has no panic,
semaphore, retry, firmware call, readiness flag, or successful-power cache.
The source's hardware semaphore is used by the DEFAULT/MT6886 branches, not
the MT6878 branch. Do not introduce it into the MT6878 sequence.

Both functions require the existing shared SPM regmap and serialized ownership.
They do not enable rails, set voltage/rate, acquire parent domains or clocks,
operate SRAM/protection, or publish a genpd state. A failed transaction can
leave partial hardware state. Its caller must keep suppliers held, stop bus
access and disallow another attempt until recovery is established. No automatic
rollback sequence or teardown safety is inferred from the vendor code.

## Exact source basis

`evidence.json` hashes the original git objects at Nothing OS B4.1
`ee2be53cb75670b548948636a0db1d1ff112bf12`, release
`Tetris-B4.1-260415-1709`. The device-module checkout currently has an older
HEAD; the trace intentionally uses `git show` of the requested commit.
The native base is `d84b264a54a37611f2f46bc19363cb9b41606205`. Its members are
read directly from the local archive after verifying the APKBUILD SHA512;
the extracted kernel working directory is not trusted as a pristine base.
Packaged prerequisite patches `0018`, `0057`, `0074` are hashed separately.

Source ownership is explicit:

| Evidence | Source path within the pinned device-module repository |
| --- | --- |
| Domain data, protections, parent edges | `drivers/soc/mediatek/mtk-scpsys-mt6878.c` |
| Separate ACK order, clocks/SRAM/protection order, HWCCF request | `drivers/soc/mediatek/mtk-scpsys.c` |
| Domain IDs 10/13 and MM_INFRA ID 7 | `include/dt-bindings/power/mt6878-power.h` |
| VMM aliases, bits, order, regulator event placement | `drivers/misc/mediatek/vmm_spm/mtk-vmm-spm.c` |
| Shared buck and all eight CAM_MAIN subsystem clocks | `arch/arm64/boot/dts/mediatek/mt6878.dts` |
| CAM_MAIN/MRAW and CAM_VCORE clock-bank domain membership | `arch/arm64/boot/dts/mediatek/mt6878-disable-unused.dtsi` |
| Generic notifier/firmware route, not MT6878 board evidence | `drivers/misc/mediatek/vmm/mtk-vmm-notifier.c`, `drivers/soc/mediatek/mtk-mmdvfs-v3.c` |

The descriptor flags already exist in Linux plus packaged `0018`:
`MTK_SCPD_STATUS_IN_CTL` reads control bits 30/31; `MTK_SCPD_DOMAIN_SUPPLY`
requires native `domain-supply` on CAM_VCORE. No new capability bit is invented.
There is no `KEEP_DEFAULT_OFF`: it would initialize software OFF without
establishing the actual inherited hardware state.

## Required supplier closure

| Dependency | Established source contract | Native integration needed |
| --- | --- | --- |
| SPM and protection | Shared SPM 0x1c001000, INFRACFG_AO 0x10001000 | Existing syscon/regmap ownership, no overlapping private mapping |
| MM_INFRA | Parent of CAM_VCORE; HWV bit 0, SET/CLR 0x198/0x19c, DONE 0x141c, ENABLE 0x1410, SET/CLR status 0x146c/0x1470, `mm_infra` basic clock | Reuse native `0057`/`0074`, its voter syscon and actual clock supplier |
| VMM rail | CAM_VCORE and ISP_VCORE share `mt6319_6_vbuck1` | Shared native regulator ownership, voltage/rate agreement, synchronous checked isolation |
| CAM_VCORE | Parent of CAM_MAIN; control 0xe5c, no SRAM handshake | Real genpd descriptor, required rail, ordered MMSYS protections bit 31 then bits 9/10 |
| CAM_MAIN | Control 0xe48, SRAM PDN bit 8/ACK bit 12 | Parent acquired first, `cam` basic clock, eight subsystem clocks, protections bit 29 then bit 30 |
| CAM_MAIN clocks before SRAM/protection release | CAM2MM0/1_GALS, LARB13/14/29, CAM_MRAW, MRAW GALS/LARBX | Existing native CAM_MAIN bank plus resource candidate's MRAW bank; use DT clock handles |
| CAM_VCORE resources | CAM_VCORE bank and common31 need CAM_VCORE powered | Bind actual domain without creating clock/PM dependency cycles |
| CAM_MAIN resources | Both subcommons 16/19, physical larbs 13/14 and MRAW bank need CAM_MAIN | Preserve resource candidate's SMI supplier links and all required PM leases |
| Logical CAMISP | Logical larb13/14 own IOMMU ports, not physical power MMIO | Preserve CAMSV PM links to physical suppliers and bound IOMMU ownership |

Common31 also depends on the existing display common, and its reset-owner
`mediatek,smi-supply` link is distinct from its power domain. The display branch
is MM_INFRA -> DISP. CAM_SUBA/B, CCU/CCU_AO, CSI_RX, sensors and SENINF are
separate consumers/domains, not additional prerequisites invented for this
CAMISP larb13/14 candidate.

The full B4.1 leaf power ON callback is rail -> basic clocks -> the implemented
SPM control sequence -> subsystem clocks -> SRAM enable/ACK -> protection clear
in reverse table order. OFF is protection set in table order -> SRAM disable/ACK
-> subsystem clocks off -> the implemented SPM control OFF -> basic clocks off
-> rail disable. VMM isolation belongs around the *shared rail's actual*
transition, not unconditionally around each camera consumer reference.

## Concrete unresolved contracts

1. **VMM errors and shared users.** Native regulator core sends ENABLE after
   physical enable and ignores notifier errors. It omits that event when the
   rail is already enabled, vetoes PRE_DISABLE through notifier flags, and
   emits ABORT_DISABLE if the physical disable fails. B4.1's MT6878 notifier
   neither propagates checked readback errors nor handles ABORT_DISABLE.
   Copying it cannot establish a synchronous isolation prerequisite. A shared
   owner must validate/reconcile inherited isolation, preserve ISP_VCORE and
   every other rail user, propagate failure before releasing camera reset/bus
   access, and define recovery when isolation succeeds but buck disable fails.
   The new shared-supplier candidate implements that Linux ownership contract
   and checked callbacks; see SHARED-SUPPLIER.md for the all-user migration,
   verified-OFF handoff and permanent-lifetime activation requirements.

2. **Voltage and firmware policy.** The PMIC's 300000..1193750 uV DT constraints
   are its allowed range, not a camera operating point. Neither a safe fixed VMM
   voltage for the native `cam_sel` rate nor a complete voltage/rate ownership
   contract is established here. No voltage is guessed. The generic VMM genpd
   notifier is not instantiated in `mt6878.dts`. Its MMDVFS helpers discard IPI
   results (and `genpd_notify` returns zero when uninitialized), so they cannot
   prove readiness. A VCP/CCU firmware stack must not be imported on that basis.

3. **Secure/parent contract.** The CAM leaf callbacks use direct SPM accesses;
   there is no evidenced CAM-specific SMC to substitute for them. MM_INFRA
   requests SiP HWCCF function 0x540 with x1=1/0 around its hardware vote.
   Packaged `0074` permits only the observed optional-hint `-EPERM`, preserving
   other errors and actual voter acknowledgement. That is an existing parent
   policy, not proof of VMM isolation/voltage permissions after a cold boot.
   Secure-world ownership/reconciliation of SPM+0xf28 bits 24..26, the shared
   buck and inherited state under the selected bootloader/firmware remains
   unestablished. No additional SMC, address, policy bit or success value is made up.

4. **Native callback completion.** Sparse descriptors alone do not fix the
   generic provider's combined-ACK OFF predicate, unchecked register operations
   or ignored regulator-disable errors. Wire the checked local sequence only
   when the rest of the callback propagates first failure and retains safe
   supplier ownership, with real DT nesting MM_INFRA -> CAM_VCORE -> CAM_MAIN.
   Do not attach these descriptors to an enabled DT using current generic
   callbacks and claim the sequence has been implemented end to end.

## Static checks and parent CI

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 patches/camera-camisp/power/check.py --verify-sources
PYTHONDONTWRITEBYTECODE=1 python3 patches/camera-camisp/power/test_source.py
```

`trace.py` verifies the frozen source trace; `--write` regenerates evidence
only after an intentional source review. `check.py --write-patch` generates
the additive `leaf-transactions.patch`; normal checks enforce byte identity and
apply it in a temporary directory inside this scope. It adds only the C/header
to an isolated research directory, with no edits to parent Kbuild, providers,
bindings, DTS, packages or CI. Negative Python tests mutate source, evidence
and staging to reject swallowed errors, incorrect/partial ACKs, wrong VMM
variants/order/readback, missing rail/parent, invented flags and activation.
These tests are static checks, not runtime fault injection or C execution.

Parent CI can consume `STAGING.json`, copy the exact C/header bytes, and compile
the research object with the fully applied pinned packaged kernel. Its include
path must point to `drivers/pmdomain/mediatek` for the actual Linux structures
and flags. Test both KUnit configs; this candidate has no KUnit runtime fixture.
Do not replace the parent Makefile, link/install a driver, include a board DT,
or compile this with fabricated userspace Linux types/flags. The additive patch
and staging copy are equivalent routes; use one. The parent must record actual
source hashes and compiler/config identity in its ARM64 artifact manifest.

Local result: source/static Python tests and additive patch application only.
No SSH, compilation, emulation, CI dispatch, push or hardware access performed.
Original leaf ARM64 compilation passed CI38245658821 per the user's report;
new shared-supplier compilation is pending. Power transitions, recovery,
cold start, camera capture and lifecycle/variant validation remain Untested.
