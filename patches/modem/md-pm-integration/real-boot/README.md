# Genuine modem boot: actual native ON callback

Partial, uninstalled and hardware untested. This delta wires the **real genpd
power_on and attach_dev callbacks** after the r188 first-OFF path. It executes
source-backed rail voltage/sync, TOP ungate, FLIGHT(false), external isolation
down, PWR_ON/ACK30 and reverse bus-protection release. Success means the current
physical ON readbacks passed, not secure/firmware/radio readiness. No reset-inhibit
gate is carried over from the obsolete execution-inhibited diagnostic promise.

All workspace edits are new files here. Applying the patch modifies a future
disposable kernel copy; the frozen adoption/provider/post-off files, CI and
APKBUILD are untouched by this task. Current r188/newUboot f25 does not contain
this callback, and its CCCI consumer remains disabled.

## Callers and ownership

The base is the actual image's native MD and shared-provider patches from repo
object `cbb777d415b564c1e40598740288c0c9d953e745`, plus ACK30 and the current
0187 wakeup/sleep/hotplug ordering. The TOP helper is
copied unchanged from `06fa22493cb8686e67c82236fdd26741e8da0378`.

1. Native probe validates the retained genuine v2 descriptor, boot evidence and
   resources, then performs real first-OFF, including >=4ms settle.
2. New probe continuation submits FLIGHT(true), checks/logs/retains only defined
   a0 and calls the existing checked TOP gate. It publishes the domain initially OFF.
3. Linux `platform_probe` calls `dev_pm_domain_attach` before CCCI driver probe.
   `__genpd_dev_pm_attach` calls the new `attach_dev`, then the **real
   genpd_power_on -> mt6878_md_real_boot_power_on** callback.
4. Admission accepts only the sole actual platform device/node and domain0,
   revalidates retained handoff/resources and current physical OFF.
5. ON validates all three real MT6363 rail inputs, acquires non-devm regulator
   handles for a retained real consumer reference, requires inherited rail
   enable, sets/syncs/checks 800000/800000/700000uV, then performs TOP ungate ->
   FLIGHT(false) -> ISO down -> PWR_ON/ACK30 -> NEMI/IFR11/IFR9 release.
6. Current five-register ON readback must pass before assigning ATTACHED_ON.
   First errors, supply handles/node references and raw FLIGHT registers survive
   errors/detach until reboot. No rollback, retry or guessed rail enable is added.

The pinned MT6878 flow selector is absent/zero; SRC/O1/PLL/sequencer operations
are excluded. Vendor voltage setting does not enable these child rails, and its
SRAM delay string does not match its actual hyphenated supply name. This delta
requires real inherited enable and preserves source voltage order rather than
inventing rail enable writes or a delay. The native provider's control-bank
checks can return EBUSY; such an error is retained rather than bypassed.

OFF/restart lifecycle is still vetoed. **Runtime activation requires a real start
adapter first:** it must consume this native attached ON device/reference and
retained authenticated v2/evidence, avoid the old virtual-OFF backend, and avoid
calling the legacy first-OFF/power-on path a second time. In particular,
`md_start_platform` and `md_cd_power_on` cannot simply be left in that old sequence
after attach-time native ON. Physical ON can occur before CCCI probe later fails;
legacy shutdown can then gate TOP despite a vetoed physical OFF. This compile
candidate keeps the actual CCCI consumer disabled. Full modem boot/handshake is
not implemented or claimed here.

## Concrete callback inputs

Both Kconfig fragments are sourced by the delta and default to n. A future CI
candidate needs explicit REAL_BOOT_STAGING=y and POST_OFF_TOP_STAGING=y,
REGULATOR_MT6363 and the existing permanent first-OFF no-idle/sleep/hotplug
profile. r188 retains PM_SLEEP/SUSPEND/HOTPLUG APIs through0187, a permanent PM
prepare veto and real boot-lifetime hotplug-disable owner; those APIs must stay
enabled for sensorproxy/conninfra. Both physical continuations also trylock the
actual system-transition mutex and retain EBUSY instead of racing a transition.
SCSI_UFS_MEDIATEK_DBG must be n, including no module variant.

The **final post-loader FDT** must retain the genuine descriptor/evidence and
existing first-OFF supplier/chosen markers, enable the actual md_spm/domain0 and
CCCI consumer, and contain these source-backed resources:

```dts
&md_spm {
    status = "okay";
    power-domain@0 { status = "okay"; };
};

&mddriver {
    status = "okay";
    power-domains = <&md_spm 0>;
    ccci-topckgen = <&topckgen>;
    md-vmodem-supply = <&mt6363_vbuck2>;
    md-vmodem = <800000 800000>;
    md-vsram-supply = <&mt6363_vsram_modem>;
    md-vsram = <800000 800000>;
    md-vdigrf-supply = <&mt6363_vbuck1>;
    md-vdigrf = <700000 700000>;
};
```

The three real regulator children must be available under the MT6363 regulator
provider, using the native rail-provider extension and inherited-voltage-preserving
registration from `ci/stage-native-modem-rails.py`. A phandle alone does not create
a registered provider; unavailable nodes fail ENODEV and unresolved providers
can return EPROBE_DEFER. Any callback error becomes terminal in the retained
owner. Linux may translate the first attach-time power error to EPROBE_DEFER;
the next admission returns the retained underlying error.

The trusted loader still expects disabled bootstrap input nodes. Final activation
must follow its real successful handoff, not enable the original input DT early.
This directory does not change U-Boot, shipping DT or CCCI probe/start code.

## Exact secure dispatch for binary inspection

| Operation | x0 | x1 | x2 | x3..x7 |
| --- | --- | --- | --- | --- |
| FLIGHT(false), before native ON | 0xc2000505 | 7 | 0 | 0 |
| FLIGHT(true), after native OFF | 0xc2000505 | 7 | 1 | 0 |
| Separate kernel execution release POWER/0 | 0xc2000505 | 6 | 0 | 0 |

The requesting Linux function is `flight_mode_set_by_atf` in exact ee2be53
`md_sys1_platform.c:648`; request7 is enumerated in `modem_secure_base.h`,
and SiP function0x505 is defined by `mtk_sip_svc.h`. The vendor's void API logs
four flags, but that is not the matched secure return ABI. The committed
[ATF contract](../../TRANSPORT_OWNER.md) and fixture source identify payload
SHA256 `05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`:

- Payload base 0x48800000, dispatch offsets 0xbf2c/0xbfa0 -> wrapper 0x1bf58 ->
  registry dispatcher 0x1efc0; callbacks 0x33d3c, 0x33aec, 0x33c5c.
- The first two callbacks do nothing for event7. The third sets/clears only
  secure RAM policy halfword bit0x40 at offset0x5a9fa, using lock0xf73b4 and
  helpers0x331b4/0x3313c. It sets iff u32 argument==1; otherwise it clears.
- Kernel dispatch zero-extends w0 into a0. Missing registry yields
  0x00000000ffffffff; traversal stops on first nonzero callback. A null callback
  terminates with zero without guaranteeing policy applied. The third callback
  discards helper status. **a1/a2/a3 are not defined outputs.**

The new wrapper retains only full-width a0, stops on any nonzero value with
local -EIO, and logs the actual raw value rather than casting it to a Linux
errno. It never logs or assigns meaning to a1..a3. Zero permits the next
source operation but does not prove policy applied, outer admission, inhibition
or readiness. Current physical ON readbacks remain independent and mandatory.
This task reads the committed contract/fixture source without importing or
executing Unicorn; no fresh private-binary decode or fixture PASS is claimed.

Physical operations: TOP 0x10000000 bits8/9; SPM ISO 0x1c001f24 bits0/1;
SPM MD_CTL 0x1c001e00 PWR_ON bit2 and ACK bit30; NEMI CLR/STA
0x10270088/0x1027008c bits6/7; IFR11 CLR/STA 0x10001c48/0x10001c4c;
IFR9 CLR/STA 0x10001c58/0x10001c5c. All accesses use the retained real syscon
maps and DT geometry. POWER/0 remains separate; outer SMC admission is not inferred
from this inner policy handler or from a0 alone.

## UFS and remaining work

Exact-object census establishes modem RPC AFC/UFC as the calibration acquisition
caller. The debug provider takes a WLUN runtime reference and blocks requests;
release drops that actual reference. A timeout can leave a hold that the vendor
wrapper forgets, so it is unsuitable as a native ownership API. This candidate
excludes the provider/API/RPC calibration case with DBG=n, therefore performs no
unowned release. Supporting DBG=y/m needs a real hold owner and failure unwind.

Remaining: parent CI compile/link and candidate FDT integration; actual CCCI
native PM/start adaptation; firmware/EMI lifetime and ordered transport/POWER0;
independent matching secure dispatch/admission verification; calibration if requested by firmware;
controlled hardware, clean install, lifecycle and SKU validation.

## Static checks

From this directory:

```sh
python3 -B audit.py
python3 -B stage.py
python3 -B -m unittest -v test_static.py
python3 -B -m unittest -v test_ci.py
```

The audit reads exact NOS git objects ee2be53 and e96f60, and byte-compares Linux
files to the d84 archive after verifying its APKBUILD SHA512. Staging reconstructs
the packaged/frozen shared native sources and ACK30, then checks/applies the new
patch to disposable text copies only, rejecting skipped files, offsets, fuzz and
stale output. Tests cover callback wiring, ordering, physical success readbacks,
rail errors, incorrect secure arguments, UFS ownership, defaults and error/lifetime
retention. No target C, local native compilation, emulation/JIT, phone access,
CI dispatch, commit/push or remote mutation has been performed.

## Parent CI entry point

`ci.py` is self-contained below this directory and does not edit global helpers,
APKBUILD or workflows. It imports the unchanged tracked GNSS/r188/wakeup and rail
stagers, checks their source hashes and exact1009/e96 identity, and applies this
ordered native recipe to an **independent disposable prepared kernel COPY**:
0180 MD ->0181 shared provider ->0182 board ->0183 parent header ->0184 ACK30 ->
0187 wakeup ->0185 actual rails ->0186 inherited-voltage registration + disabled
rail/consumer DT ->0188 realON. GNSS1009 applies to external connectivity sources,
not these native translation units; parent must prepare that package through
`stage-native-gnss-image.py --include-exact1009` for a matched full image.

Use `--input-profile r188` if the kernel already has the exact GNSS/native MD/
wakeup prefix, or `packaged` immediately after the normal packaged kernel patches
before that prefix. Exact prepared-source hashes distinguish them; a pre0187 or
mixed current research adoption header is rejected rather than silently adopted.
Parent calls this after normal packaged `ci/kernel-object-smoke.py` completes,
outside research-owner mode, in the Linux GitHub runner:

```sh
python3 -B patches/modem/md-pm-integration/real-boot/ci.py check \
  --prepared-kernel /tmp/tetris-kernel-smoke/linux-d84b264a54a37611f2f46bc19363cb9b41606205 --input-profile packaged
python3 -B patches/modem/md-pm-integration/real-boot/ci.py build \
  --prepared-kernel /tmp/tetris-kernel-smoke/linux-d84b264a54a37611f2f46bc19363cb9b41606205 --input-profile packaged \
  --config pmaports/device/testing/linux-postmarketos-mediatek-mt6878/config-postmarketos-mediatek-mt6878.aarch64 \
  --output "$ci_work/real-on-output" --report "$ci_work/real-on.json" \
  --enable-real-on
```

The runner needs the project's existing make/LLVM/fdtget toolchain, complete
prepared kernel, package config and the frozen source objects used
by the unchanged stagers (`TETRIS_NATIVE_SOURCE_TREE` when needed). Source/output
must be fresh independent copies, not symlinks or hardlinks into the checkout.
`check` is source-only and permitted locally; `prepare`/`build` reject non-Linux,
non-GitHub-CI execution before mutation or a compiler subprocess.

`build` compiles both default-off and explicitly enabled realON configurations,
retaining ThinLTO/CFI. Actual targets are `mtk-pm-domains.o` and
`mt6363-regulator.o`, plus the native first-OFF board DTB. It checks AArch64 object
identity (including LLVM bitcode), resolves retained callback pointers to actual
definitions including LLVM suffixes/aliases, and requires the compiled CCCI
consumer and three rail children disabled. Supplier/domain0 status is preserved,
not forced disabled; current parent `SUPPLIER_DTS` input is already disabled.
Each result contains resolved config, source/object/DTB hashes and logs;
failures stay failures. No module/kernel link, install image, activation, fixture
execution or phone operation is included. An unrun helper is not a CI compile
PASS: parent must retain the actual run's report/artifacts before making that claim.
