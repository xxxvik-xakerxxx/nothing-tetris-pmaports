# CCCI runtime registration draft: partial closure, disabled

Base: vendor B4.1 `ee2be53cb75670b548948636a0db1d1ff112bf12`.
All changes reside in this directory. No DT, firmware start, shared owner,
APKBUILD, workflow or running-phone change. This is NOT a loadable runtime
stack release and does not assert modem/SIM readiness.

## Executable changes

`runtime-ports.patch.vendor` inserts a pre-probe dependency transaction before
`md_cd_get_modem_hw_info`, which otherwise maps registers and obtains rails.
The transaction uses the actual `ccci,modem_info_v2` raw little-endian 32-byte
ABI (version 2, 21 tags, zero firmware errors/flags), requires unique available
CCIF/DPMAIF nodes, obtains real platform devices, creates managed device links
without runtime-PM activation, and checks bound suppliers plus the existing HIF
registration slots. Missing platform/binding/registration defers probing;
ambiguous nodes or bad descriptor shape fail before resources are allocated.
Shape validation is NOT signature, reservation or tag-content validation.
The existing utility parser remains responsible for consuming actual metadata.

Driver core owns AUTOREMOVE_CONSUMER cleanup on failed probe or unbind.
`device_link_add` can return a pre-existing link; the draft deliberately does
not manually delete it or stop a provider. Acquired platform-device references
are balanced on every return. These links order dependencies; they do NOT
repair the vendor consumer's empty remove callback.

The actual ordinary character-port registration now uses `cdev_alloc`, retains
the cdev in the port, checks `cdev_add` BEFORE creating a node, preserves its
first error, and rolls back the cdev on node failure. A concrete paired
unpublication function removes the node and cdev without freeing port storage.
It is not wired to an unsafe global remove: open-file/RX lifetime must first be
closed. This fixes the source bug where device creation overwrote cdev_add's
error and the heap-allocated cdev was lost. Existing channel/fops configuration
is used unchanged; no AT/GSM channel is invented. Changes are conditional on
the already default-off Tetris owner config.

## Exact remaining runtime blockers

1. BROM-only U-Boot intentionally publishes no CCCI descriptor. It cannot satisfy
   this registration path. Actual report and later successful final tag/DT
   publication are required, not a synthesized property.
2. APKBUILD's FSM/port/DPMAIF closure is compile-only and must not install its
   modules. Full modpost/link/provider dependency evidence precedes packaging.
3. `fsm/modem_sys1.c:ccci_md_register` discards FSM/port errors; common init
   registers/publishes before all wake sources and WDT fields exist. Returning
   an error alone is unsafe because platform probe frees `md_hw` after partial
   publication. This draft does not pretend that changing one return fixes it.
4. `port/port_proxy.c:proxy_init_all_ports` discards individual init errors.
   `port_struct_init` acquires wake sources; IPC/RPC/control/system/UDC ports
   create threads. Their lifetime needs explicit cancellation and drain before
   proxy/modem storage can be freed. IPC/RPC/SMEM and monitor cdevs remain legacy;
   the ordinary-char fix is not a claim that all port kinds are transactional.
5. `fsm/ccci_fsm.c:ccci_fsm_init` does not check kthread_run, leaks its ctl on
   wake-source failure, and has no paired complete shutdown. CCIF/DPMAIF module
   exits and modem remove are empty. Device links cannot make those safe.
6. The frozen first-start owner requires actual authenticated reservation,
   transport-access and secure-resource producers. Registration is not an
   authorization producer; HS1/HS2 and runtime negotiation remain actual modem
   events. SIM/calls also require an evidenced userspace protocol and audio path.

Next executable change: transactional preparation of FSM and every configured
port kind, storing worker/cdev/wake handles, then one publication point AFTER
all resources succeed. On faults after vendor publication, retain referenced
storage and stop further start attempts until cold recovery; never free md_hw
while callbacks retain it. Until that graph is implemented, do not enable DT,
autoload modules, unbind, suspend-test or attempt firmware start with this draft.

## Review / CI

Apply after the frozen owner/vendor API overlays, and before compiling the
actual composite. The emitted diff is against exact pinned stock source; its
pre-probe include/call and char path do not alter the frozen owner hunks.

```sh
python3 check_runtime_ports.py --vendor /path/to/vendor --emit-patch /tmp/runtime.patch
git -C /path/to/vendor apply --check /tmp/runtime.patch
python3 -m unittest discover -s . -p test_static.py
# Ubuntu CI only; compiles imported production helpers, not alternate algorithms:
python3 check_runtime_ports.py --vendor /path/to/vendor --native-ci
```

Native fixtures mock driver core/OF/cdev allocation boundaries, not MMIO or
firmware. They exercise descriptor corruption, absent/ambiguous/disabled nodes,
deferred/unbound/unregistered providers, link allocation failure, balanced
references and char allocation/add/node/duplicate/unpublish faults. Driver-core
autoremove is a fixture boundary, not claimed hardware teardown proof.
Production object builds must additionally use the real kernel/vendor headers.
No C compilation/execution has been performed locally; CI result is pending.
