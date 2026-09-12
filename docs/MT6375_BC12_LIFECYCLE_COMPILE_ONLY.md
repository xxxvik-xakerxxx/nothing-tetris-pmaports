# MT6375 BC1.2 compile-only lifecycle boundary

Updated: 2026-09-10.

## Scope

Patch `0090-power-supply-mt6375-bc12-lifecycle-compile-only.patch` records
the lifecycle contract required before MT6375 BC1.2 can own USB2 DP/DM. The
state machine and its host test are compiled explicitly by the kernel package,
but neither file is referenced by Kconfig or Makefile.

The patch has no production runtime path. It does not modify a device tree,
request or unmask an IRQ, acquire or program a PHY, access the MT6375 regmap,
register a driver, produce a module, change charging current, or alter USB
behavior.

## Correctness contract

The model closes the four lifecycle defects found in the withdrawn runtime
candidate:

1. DP/DM ownership is bounded by a 1500 ms deadline. Completion, detach, role
   loss, and timeout all request detector shutdown and role-neutral DP/DM
   release.
2. Cleanup tracks the detector and DP/DM independently. State is cleared only
   after the corresponding operation succeeds, so failed cleanup remains
   pending and retryable.
3. Detection requires an explicit grant from the owner of the current USB
   role. The model never requests a forced device mode and releases DP/DM
   without selecting a replacement role.
4. The same reconciliation operation consumes the current power-ready and USB
   role state at initial probe and after every attach indication. It therefore
   neither depends on an edge for a cable already present nor trusts a stale
   attach event without checking current state.

## Static and CI gates

The package builds `mt6375-bc12-lifecycle.o`, checks its lifecycle symbols and
requires it to have no undefined runtime dependencies. It then builds and runs
`mt6375-bc12-lifecycle-test.c` on the build host. Tests cover bounded timeout,
successful release, partial-start cleanup, repeated cleanup failure, role swap,
completion, cable-present initial reconciliation, denied arbitration, and
stale attach rejection.

`scripts/validate-pmaports-overlay.sh` requires those build and test gates. It
also rejects changes in patch `0090` to DTS, PHY, Kconfig, or Makefile files and
rejects IRQ, PHY, regmap, driver registration, enable-property, interrupt-name,
or PHY-name wiring. Packaging or autoload of either BC1.2 compile-only object is
also rejected.

## Runtime gate

Runtime work remains blocked until a local API can prove exclusive DP/DM
ownership while reporting the current USB role and coordinating gadget
disconnect/reconnect. A future runtime patch must translate the model into
that proven API, retain bounded recovery and retryable cleanup, reconcile
current power state at probe and on IRQs, and pass cold boot, warm reboot,
repeated attach/detach, data-role swap, suspend/resume, USB NCM, and persistent
SSH tests. Production DT IRQ and enable wiring must remain absent until then.
