# Native read-only ON adoption integration design

Defensible starting contract: trust the installed bootloader's actual completed
loader/BROM/EMI transaction, validate its immutable report/reservations, and
observe physical ON through the existing native MD supplier. There is no new
NS certificate requirement. Default adoption has no physical transition and
does not declare modem READY. The staged helper now also has an explicitly
marked supplier-init first-OFF diagnostic; see STAGING-CONTRACT.md. Its physical
validation and all restart support remain unproved. The historical read-only
activation design below does not describe that separate first-OFF transaction.

The concrete implementation is now `native-on-adoption.patch`, generated from
`mt6878-modem-adopt.h`. `STAGING-CONTRACT.md` supersedes the activation design
below with the agreed two-marker, supplier-only final producer contract. It also
records that consumer detach is void and cannot veto unbind; the implementation
retires on detach instead of claiming that requirement passed.

## Concrete activation dependency

Installed U-Boot's `tetris_modem_brom_only_board()` requires BOTH `mddriver` and
`mediatek,mt6878-modem-power-controller` disabled BEFORE its loader runs
(`tetris_modem_brom_board.c:225/227`). Its final producer leaves them disabled.
Simply enabling the supplier in the input DT breaks the authentic success path.
An executable adoption experiment therefore first needs the authentic final
producer to enable the native supplier AFTER successful BROM/metadata publication,
or another explicitly reviewed activation mechanism. Changing U-Boot or adding
such a mechanism is outside this scope. Do not bypass the BROM failure, adopt a
failed report, or use OF_DYNAMIC while claiming immutable static handoff.

The parent HIF DT/resource changes do not establish this activation step.
No physical HIF write-test phase has been requested here.

## Exact native hooks

Use the existing `mediatek,mt6878-modem-power-controller` onecell domain0 in
`mtk-pm-domains.c`; retain the real `power-domains` relationship. No new provider,
split/virtual device, removed property or platform-core opt-out is involved.

| Hook | Actual work | Failure behavior |
| --- | --- | --- |
| MD branch in `scpsys_add_one_domain()` | Consume unique modem node and copied actual report; require loader11/bootstrap15/board16, first errors0, no cleanup, BROM four ones, matching slot42/43 evidence and plain retained reservations | Reject absent/failed/mixed report before genpd publication |
| Existing SPM/IFR/NEMI regmaps | Read PWR_ON+ACK30+ACK31 all set; EXTISO bits1:0 zero; IFR9/IFR11/NEMI6:7 status bits zero | Reject OFF/partial transitions, retain first read error; no corrective writes |
| `pm_genpd_init(&pd->genpd, NULL, false)` | Register TRUE observed hardware ON only after admission/snapshot | No false software OFF or power-on callback during registration |
| Native `genpd.attach_dev` | Accept only the real platform modem device, unique handoff node and exact onecell domain0 relationship; recheck ON before attachment | Reject another consumer, genpd virtual device or stale state |
| Native `genpd.power_on` / `power_off` | Return `-EOPNOTSUPP` for physical transitions in the observational adoption profile | Never report a successful OFF or set physical transition ownership |
| Existing `platform_probe()` | Standard single-domain attach calls `genpd_power_on()`; actual already-ON status returns0 without a supplier transition | Actual modem driver still controls whether its probe can proceed |

The supplier needs to retain the copied report/geometry and actual consumer node,
but must not convert those fields into `md_owned=true`. That flag currently
denotes a completed native physical ON transaction. Adopted observation and
transition ownership are distinct states of this same real domain.

At attach time `genpd_add_device()` invokes `attach_dev` BEFORE taking the domain
lock (`core.c:1932/1936`). Therefore a future implementation must use a supplier
mutex for its retained consumer identity, not assume `attach_dev` runs under the
genpd mutex. Transition callbacks execute with genpd serialization; lock ordering
must not reenter runtime PM, attach or supplier probe from a held supplier lock.

Failed-probe detach, late unused-domain power-off, runtime/system suspend and
unbind can still reach supplier power-off. They must receive a real veto and
leave physical/software domain ON. A veto is not a successful shutdown and not
a proof that system suspend/secure idle is safe; do not enable that lifecycle as
validated support. Hardware loss of ON while adopted must fail revalidation,
not trigger automatic repair. Resource retention must survive failed probe.

## Caller closure and stop point

The current resource-only preparation rejects a power-domain-bearing modem
before registering its driver. Its frozen first-start owner also explicitly
requires an unattached platform modem plus a separate OFF-attached genpd device.
This design does not silently bypass either check or invent another domain.
Parent integration must deliberately change the REAL modem preparation caller
to consume the adopted native domain, with no physical startup in that phase.
Those parent-owned HIF resource files are unchanged in this scope.

The native backend0117 is not called from this observational profile. Calling
it would require its exclusive OFF/inhibit gate, native rails/clocks, powered
transport and pre-release checks. Ordinary bootloader trust satisfies initial
handoff provenance, and slot42/43 AID241=RW supports bounded initial service
access; neither proves that a running bootloader modem can be shut down or
restarted with execution inhibited until POWER/0.

In read-only mode the next step is native observational attachment after final
producer activation and real caller integration. The separate first-OFF mode
needs its new final marker and resolved no-idle/no-sleep/no-hotplug CI profile,
not attachment. Validate actual native objects/link before a controlled first-OFF
experiment. Its physical readback is untested; restart remains unsupported.
The adoption patch is staged only; no physical experiment was performed here.
