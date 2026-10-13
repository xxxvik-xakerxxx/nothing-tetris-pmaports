# Staged post-OFF TOP ownership

Partial, hardware untested. This implements the actual TOP gate primitive in
`mt6878-modem-post-off.h`, not the full vendor shutdown sequence. All files here
are new; the frozen provider, image helper and APKBUILD are untouched.
The Kconfig fragment is unsourced and defaults to `n`; both entry points return
`-EOPNOTSUPP` before touching resources when the symbol is off. There is no
registered driver, initcall, automatic call site or ON operation.

## Source mapping

The authoritative source is the **git object** at Nothing
`ee2be53cb75670b548948636a0db1d1ff112bf12`, not the sibling checkout's current
working files. `SOURCE-EVIDENCE.json` records exact hashes and line anchors.

| Implementation or omission | Exact source |
| --- | --- |
| TOP offset 0, set bits 8/9, read back | `md_sys1_platform.c:661-695`, `md_cd_topclkgen_off` |
| MTCMOS OFF, UFS unblock, 4ms settle, FLIGHT(true), TOP gate order | `md_sys1_platform.c:899-961` |
| Real TOP phandle lookup | `md_sys1_platform.c:1548-1550` |
| TOP compatible/base/size and modem phandle | `mt6878.dts:2620-2625`, `6223-6243` |
| UFS release only for a tracked held calibration state | `ccci_fsm.c:116-148` |
| UFS release unblocks requests and drops runtime reference | `ufs-mediatek-dbg.c:1803-1817` |
| FLIGHT setter has void return; only logs secure a0..a3 | `md_sys1_platform.c:648-659` |
| Power-on sequence and separate execution release | `md_sys1_platform.c:1302-1402` |
| MD reset handling deliberately omitted | `mtk-scpsys-mt6878.c:121` |
| Shared cached syscon and checked locked masked RMW | pinned Linux `syscon.c`, `regmap.c`, `regmap.h` anchors |

The new primitive strengthens vendor error handling: the vendor ignores its TOP
write return and the caller ignores the TOP helper return. Here, the locked
masked RMW preserves unrelated shared bits, every return is checked, and missing
gate bits cause `-EIO`. A single verification read matches the source operation;
there is no invented hardware timeout or retry protocol.

## Caller contract and remaining integration

Allocate one zeroed **non-devm** `mt6878_md_post_off_top` sidecar for the retained
native first-OFF owner and keep it, its node reference and cached map through
reboot, including errors. Include this header after the frozen adoption header
only in a later integration change. The caller holds the existing takeover lock
and then `owner->lock` throughout acquisition, preceding shutdown steps and TOP
gating. Lockdep asserts those locks; they serialize software, not modem execution.

`mt6878_md_post_off_top_acquire(pd, owner, top)` checks the retained supplier and
native OFF profile, binding and resources, resolves exactly one `ccci-topckgen`
phandle, validates the real syscon geometry and 32-bit access, and retains the
cached map. It does not read or write TOP. Acquisition failure is terminal in
the existing owner, including `-EPROBE_DEFER`.

Before `mt6878_md_post_off_top_gate(pd, owner, top)`, the caller must finish
**owned UFS unblock -> >=4ms settle -> actual FLIGHT(true)**. The current frozen
first-OFF helper settles after isolation but does not own UFS or FLIGHT. Its
completion enum is therefore insufficient to call this primitive as a complete
shutdown continuation. This header deliberately offers a low-level TOP primitive,
with no fabricated prerequisite flags or success tokens. No current call site
can execute it. Missing predecessors must be resolved before wiring a caller.

The gate rechecks all five current physical OFF values, attempts one TOP masked
RMW and checks both bits. Failures retain the first errno through the native
owner; the sidecar and mappings remain available for diagnosis. It never performs
a corrective ungate, reset, ON action or retry. `top_only_complete` means only
this primitive completed, not full shutdown, execution inhibition or boot.
The bound is on register operations, not a wall-clock guarantee if an MMIO bus
itself stalls. Regmap locking only covers users of that same cached map; direct
MMIO or secure competing writers still need review before hardware integration.

UFS inputs/returns are traceable, but native calibration hold ownership is absent:
the vendor wrapper returns `-1` if already unheld or disabled, and its release
function drops a runtime reference. Importing it blindly is incorrect. FLIGHT's
arguments are known but its secure success/failure contract is not established
by these sources. Neither operation is included here, and no secure return is
interpreted as proof.

## Genuine boot versus inhibited diagnostics

The existing restart staging specifically promises an **execution-inhibited
diagnostic restart**, so it needs an active inhibit owner and readback before
power/rail actions that might allow execution. That promise does not apply to an
intentional genuine modem boot: execution is the intended result. The vendor
power-on chain precedes a separate `MD_KERNEL_BOOT_UP` release, and the MD domain
uses `MTK_SCPD_REMOVE_MD_RSTB`; neither establishes an artificial reset/inhibit
mechanism. An intentional boot should implement its owned shutdown, rails/TOP,
FLIGHT/power, secure firmware/authentication/EMI and transport chain, with actual
return contracts and lifecycle evidence. It should not inherit a diagnostic
inhibition requirement solely from the old staging mode. This is a scope
distinction, not permission to perform any unowned ON action or a claim that
the genuine boot chain is ready.

## Static validation

From this directory, run `python3 -B audit.py` and
`python3 -B -m unittest -v test_static.py`. These read exact vendor objects and
hashed pinned Linux sources, verify anchors and implementation/error boundaries,
and check default-off isolation. They do not compile or execute kernel code.
There has been no phone access, native compile, commit or CI run.
