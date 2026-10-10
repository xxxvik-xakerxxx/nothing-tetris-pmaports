# CCCI resource preparation and explicit post-bind registration

Review draft only. No enabled DT, packaging, workflow changes, hardware operation
or firmware start. Frozen runtime-ports is unchanged. The generator uses pinned
B4.1 `ee2be53cb75670b548948636a0db1d1ff112bf12`, applies current APKBUILD
vendor adaptations in order, then frozen transport-owner and runtime-ports.
The patch is generated against this COMPLETE stack, not stock plus runtime.
Source drift is an error; git-apply checks run on the same complete base.

## Private Resource-Only Probe

`ccci_modem_init_common` selects a serialized private transaction: checked
modem/private allocation, both wakes, actual parked FSM task/wake, actual
generation-selected all-port table/minor region/common wakes/queues/locks,
modem init, and CCIF/DPMAIF provider module pins. Pre-success errors reverse only
privately acquired resources and latch the first failure. Hardware getter clock
and syscon failures propagate; acquired L2SRAM/sequencer mappings are unmapped.
OF IRQ mappings may pre-exist and are NOT disposed without ownership proof.

Success means ONLY privately prepared resources. Probe does not publish
modem_sys, platform_data, FSM entries, monitor, port proxy, sysfs or workers;
it does not run metadata memory setup or core registration. There is no fallible
commit after private success in probe. Owner mode excludes the legacy inherited
ON pm_runtime_get_sync path and probe's ccci_init. Consumer/HIF modules stay
pinned; ordinary bind/unbind attributes are suppressed.

## Explicit Post-Bind Commit

`ccci_tetris_register_prepared(pdev)` is exported with NO automatic caller.
It checks the exact prepared pdev and real device_is_bound, not a caller boolean.
device_trylock excludes bind/unbind and rejects erroneous in-probe/reentrant use
with EBUSY rather than deadlocking. Lock order is device then transaction mutex.
Unbound use returns EPROBE_DEFER without consuming the one-shot commit.
Binding establishes no AUTH, NS access or physical OFF permission.

Only this API marks exposure, performs checked core initialization (including
real class_create errors), configures memory and publishes modem/platform state,
then checks real FSM subordinate init, every actual port type, sysfs files and
proc publication. Main/port workers remain parked until all checked stages pass.
Any post-exposure fault returns its FIRST error to this explicit API caller,
NOT platform probe. Already-bound devres, including devm clocks, therefore
survive. The partial graph is retained/quarantined without retries, frees or
worker wake. Failure is never turned into successful registration.

This API is not a complete physical start path. A future caller must supply
reviewed authenticated metadata/access/lifecycle ownership before invocation.

## No Physical Control Through Prepare-Only Mode

- START is denied before the existing transport-owner entry. STOP is denied
  before legacy pre-stop/stop or GATED success. Neither command completion nor
  software state is proof of physical OFF.
- Actual monitor open, close, ioctl and compat ioctl return EOPNOTSUPP at entry
  throughout this configuration, EVEN AFTER successful commit. The central
  ccci_fsm_ioctl also refuses before its switch. SET_BOOT_DATA cannot touch an
  unpublished proxy; SET_EFUN/FORCE_MD_ASSERT cannot reach SMC/CCIF through these
  entry points. Monitor publication before port commit is not an access grant.
- Ordinary/IPC/RPC/SMEM and kernel port opens reject incomplete/quarantined
  registration. Character close owns usage through its final HIF/unregister
  callback; zero usage is NOT IRQ/workqueue/DMA drain.
- Consumer suspend/resume/restore are denied, preventing NULL platform_data
  access or physical lifecycle from a resource-only bound device.

## Limits

All nine actual configured types are dispatched: char, RPC, IPC, SMEM, net,
control, system, poller, UDC. Type commit is NOT wholly private: cdev/netdev,
SWTP delayed work, IPC conn-md, DEVAPC and FSM subordinate callbacks lack a
proven complete inverse. Network/control callback drain is not claimed.
Permanent pins and manual-unbind suppression do not fix forced platform/overlay
removal, shutdown or empty vendor remove/exit. Those remain unsupported.

SLBC's error-discarding registration and non-module SCP reject before allocation.
Hidden SMEM/CCMNI/dumper failures remain their existing contracts. Zero return
does not certify failures they do not expose. No working SIM/calls, modem READY,
security permission, physical OFF, safe unload or DMA quiescence is claimed.

## Verification

```sh
python3 check_prepare.py --vendor /path/to/pinned/vendor --emit-patch /tmp/prepare.patch
TETRIS_VENDOR_TREE=/path/to/pinned/vendor python3 -B -m unittest discover -s . -p test_static.py
# Ubuntu CI ONLY; strict warnings and ASAN/UBSAN, never local C compilation:
python3 check_prepare.py --vendor /path/to/pinned/vendor --native-ci
```

Native fixtures import actual new FSM/ports/registration code with explicit
boundary mocks. They cover allocations, every port position/type failure,
provider rollback, sysfs/core faults, first-error latch, unpublished cleanup,
bound/devres retention and parked workers. Mocks do not claim hardware execution.
Static tests verify complete-stack START ordering, monitor/central ioctl denial,
no commit API caller in probe, class/clock/syscon errors and publication ordering.
Native/object tests remain CI-pending for this revision. No local C build or
phone operation occurred.

Pinned anchors: fsm/modem_sys1.c, md_sys1_platform.c, ccci_fsm.c,
ccci_fsm_monitor.c, ccci_fsm_ioctl.c; port/port_proxy.c, port_cfg.c and actual
port type implementations; ccci_core.c. Linux
d84b264a54a37611f2f46bc19363cb9b41606205 kernel/kthread.c:448 checks SHOULD_STOP
before a never-woken thread body; drivers/base/dd.c defines device_is_bound;
include/linux/device.h defines device_trylock. These are lifetime contracts,
not firmware/security evidence.
