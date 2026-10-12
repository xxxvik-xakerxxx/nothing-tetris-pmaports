# Native MD attachment decision

Status: concrete read-only native ON adoption staging patch implemented; first
shutdown/startup remains blocked. See `STAGING-CONTRACT.md` for exact producer
markers, validation, source tests, CI object staging and the failed unbind-veto
requirement. The EMI/trust follow-up corrects the earlier blanket NS-grant
and independent-kernel-signature requirements: see `EMI-PERMISSIONS.md` and
`ON-ADOPTION.md`. Ordinary trusted-bootloader handoff is a valid starting model.
Source/patch checks only. The staged physical callbacks veto every transition;
they never return fabricated power-off/start success. No target C compilation,
dtc, firmware/instruction execution,
emulation, JIT, SSH, commit, push or shared-file change was performed.

Inputs are vendor device modules
`ee2be53cb75670b548948636a0db1d1ff112bf12`, Linux base
`d84b264a54a37611f2f46bc19363cb9b41606205`, and user-identified installed U-Boot
`8d2ccc12e7861c5726e9c37a07f62c4ae18db7b5`. U-Boot is read with `git show`
at that commit. Personal `ddb4...`/HEAD and pending private work are not used as
installed evidence. This audit does not independently measure installed binaries
or current physical state.

Run the read-only census from this repository:

```sh
python3 -B patches/modem/md-pm-integration/audit.py
```

It emits JSON with exact source hashes, line anchors and blockers. A successful
audit exit means its source anchors/ordering were checked, not that integration
or any hardware test passed. Paths can be supplied with `--vendor`, `--uboot`,
and `--linux`. Local native Linux base files are hashed; the vendor and U-Boot
files are obtained from the exact Git objects. This is not a C semantic verifier
or a proof excluding unobserved firmware actors. `audit_emi.py` separately pins
the vendor permission definitions, NS CPU AID and actual ATF readback cells.

## Actual causal path

1. Installed `tetris_modem_loaded_boot_once()` obtains the real allocations,
   authenticates/copies the bundle through its slot loader, initializes services,
   then calls `tetris_modem_bootstrap_once()`. Initial `cold_off()` precedes placed
   memory writes. The optional `startup_off()` is an INITIAL bootloader ownership
   step, not the state delivered after successful bootstrap.
2. Bootstrap checks OFF, programs EMI/remaps and locks bootloader remapping,
   ungates TOP bits 8/9, removes external isolation, sets only PWR_ON bit 2,
   waits both ACK bits, releases NEMI then IFR11 then IFR9, calls LK CCCI
   request 6/command 1, and polls request 6/command 7 for four equal-one flags.
   It returns COMPLETE while ON. Success has no shutdown. Failure cleanup can
   attempt OFF but never publishes a successful final handoff.
3. `tetris_modem_brom_only_board()` publishes the actual retained report as
   observation. The board Linux fixup invokes `tetris_modem_publish_final()` only
   after a successful BROM-only result and metadata-handoff configuration.
   Final tags/evidence derive from the completed owner. Consumers stay disabled.
   The BROM hook REQUIRES the native MD supplier disabled before its loader;
   input-DT provider activation therefore prevents this successful handoff.
4. Native `0113` calls `mt6878_md_check_off()` during supplier creation. ON,
   mixed ACKs, missing isolation or incomplete protections returns `-EBUSY`.
   Thus successful U-Boot's ON state prevents this provider from registering.
5. If the physical state instead satisfies OFF, `0113` registers a software-OFF
   genpd. Linux `platform_probe()` applies clock defaults, calls
   `dev_pm_domain_attach(...ATTACH_POWER_ON...)`, and only then calls driver
   probe. `__genpd_dev_pm_attach()` invokes `genpd_power_on()`. `0113` then
   executes isolation/PWR_ON/bus writes BEFORE any modem-driver proof checks.
   The OFF snapshot alone does not authorize those writes or execution.
6. The frozen first-start caller rejects an attached modem platform device and
   requires another device on the genpd bus sharing its OF node. `0117` separately
   requires authenticated handoff and exclusive OFF/boot inhibition before
   binding, BROM calls, rails, TOP clocks, runtime power and execution release.
   A normal ON-attached modem does not satisfy either contract.

This produces two distinct barriers: inherited ON prevents native supplier
registration; inherited OFF allows an automatic ON transition before driver
checks. Fixing only the latter with an extra driver check cannot resolve either.

## What ON adoption would and would not establish

Linux `genpd_power_on()` returns immediately when domain status is already ON.
Initializing this EXISTING native supplier with `pm_genpd_init(..., false)` after
validating the real trusted producer and a complete physical ON snapshot is
therefore a legitimate no-transition observational adoption path. It preserves
the real `power-domains`
relationship. This is a useful route, not permission to set `md_owned=true`.

Managed adoption also needs a real owner for the first power-off, late unused
domain shutdown, failed-probe detach, runtime suspend and system suspend. Those
paths can invoke supplier `power_off` outside modem probe. Existing `md_owned`
means this supplier completed its own ON transition; it is not evidence that
the kernel owns U-Boot's running modem. Setting it from an ON observation would
grant shutdown/repower without closing the handoff. Leaving it false merely
vetoes power-off and cannot run the vendor first-boot OFF sequence. Returning
success without physical shutdown would lie to genpd. No such substitute is
implemented here.

The vendor is evidence for the intended ON -> OFF -> ON -> release lifecycle,
not a ready adoption implementation. Its MD data has `BYPASS_INIT_ON` and
`REMOVE_MD_RSTB`, but `mtk_register_power_domains()` sets `on=false` for bypass
and initializes software OFF without measuring hardware ON. Its MD power-on
still performs writes. Its `md_start_platform()` polls BROM, reads flags, then
calls `md_cd_power_off()`; that uses runtime PM, then flight/TOP operations and
the gen99 post-OFF delay. Copying the bypass flag would reproduce the false
initial software state, not implement truthful native adoption.

## Actual Limits After Permission Review

| Boundary | Existing evidence | Missing condition |
| --- | --- | --- |
| Handoff trust | U-Boot verifies its retained bundle before placement; final ABI derives from its completed owner | Validate the genuine successful report and matching resources under the trusted-loader model; independent kernel cryptographic verification is an optional stronger model, not a prerequisite imposed here |
| Supplier activation | Installed BROM hook requires supplier disabled on input and final producer leaves it disabled | Activate the existing native supplier only after authentic final publication through a reviewed producer/activation change |
| Power takeover | Actual successful BROM report and observed ON geometry | Kernel owner accepting the authentic boot transaction, resource/rail/clock identities and lifecycle responsibility before genpd can power-off |
| Initial Linux service access | Actual enabled slot42/43 range readbacks and v2 AID241=3; vendor identifies241 as NS CPU | Positive initial NS CPU RW within reported extents; current EL, effective overlapping/NSR/KP policy, coherency and intervening writers remain operation/lifetime dependencies; no generic NS certificate is required |
| Execution inhibition | U-Boot already submitted LK POWER/1; kernel POWER/0 is the later release | Proven domain-cycle/latch semantics keeping execution inhibited during new ON before transport and POWER/0; no guessed reset, POWER/5 or flight proof |
| Secure policy lifetime | Existing census identifies DVFSRC INIT/readiness and secure idle entry/restore routes | Actual competing AP callers and lower SPM/PCM effects excluded/accounted for throughout OFF/start; INIT serialization alone is insufficient |
| Native startup supplier | Native DVFSRC wrapper candidate exists | Packaged CONFIG_MTK_DVFSRC is disabled; pinned native match table supports mt6893/mt8183/mt8195, not MT6878. This blocks the frozen startup scope, not read-only ON observation |
| First-start caller | Frozen owner and 0117 perform real sequencing after proof callbacks | Redesign around adopted native domain and its actual device/reference state; present virtual-OFF-only caller cannot consume normal ON adoption |

The existing reservation handoff owner's authentication callback explicitly
returns `-ENOKEY`. The frozen startup scope requires a completed scoped DVFSRC
supplier and an authentication callback. It cannot create either by being called.
That particular interface is incompatible with the observational adoption design;
its stronger verification requirement must not be mistaken for a general rule
for trusting bootloader handoff. No scope/backend gate is bypassed here.
Its authentication occurs before backend OFF/NS gates; plugging in a verifier
that reads installed ROM at that point would also violate the existing ownership
order. No new generic proof callback or permissive property repairs these gaps.

## Most useful next implementation

Keep the successful installed boot owner's ON handoff as the starting contract.
Use its actual report, AID241 RW and retained resource identities under ordinary
bootloader trust for bounded observational adoption. Change the authentic final
activation and actual consumer caller as specified in `ON-ADOPTION.md`; these
cannot be replaced with input-DT enablement or a fake split domain. Close the
first ON -> OFF operation and subsequent inhibited ON separately using matching
secure/LK source and controlled evidence.

Once those conditions are established, a reviewable native patch can:

1. Consume the immutable handoff before registering the existing MD genpd,
   validate all ON bits/protections/clock state, and initialize true software ON.
2. Bind the sole real modem consumer through supplier `attach_dev`, retaining
   boot transaction and device identities; serialize admission/transition with
   existing genpd locks and the actual secure-policy supplier's lifecycle.
3. Execute the source-backed first shutdown through that supplier, with first
   failure retained and no compensating reset/retry. Preserve resource claims.
4. Update the real first-start caller/backend to use the native domain and its
   actual PM reference state through OFF, rails/clocks, ON, powered transport and
   kernel POWER/0. Preserve the trusted firmware/resource identity through release;
   independently verify signatures only if that stronger threat model is chosen.
5. Account for late power-off, failed-probe detach, suspend, unbind and every
   competing legacy/secure caller. Validate patches and real target objects in
   parent CI before any controlled device experiment.

The input scope prohibits changing U-Boot or shared infrastructure here. More
fundamentally, these sources do not yet close the first shutdown/restart operation.
The result includes positive initial EMI NS-CPU RW evidence and a concrete native
observational adoption design. It is not a claimed live attachment fix, current
write-test result, modem start or SIM result.
