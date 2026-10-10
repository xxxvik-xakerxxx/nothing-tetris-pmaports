# Dedicated sealed load-only parent

New production entry points: `b41_sealed_probe_cli.py` admits source-pinned
copies, then FD-execs `b41_sealed_probe_parent.c` in the SAME dedicated process.
No subprocess/Python reaper duplicates the lease. Existing ProbeResources
move/close, LoaderResources, sealed copy admission, corrected supervisor,
immutable root builder and frozen isolate policy are reused, not edited.

Inputs are independent selected stock and probe CI artifacts. The selected
stock root from CI38048111345 contains both system/APEX providers and vendor
libraries; it is used for BOTH provider roots, never CI37898372984's stale root.
The separate probe artifact must contain `/probe` matching the already accepted
independent PROBE_SHA in b41_mipc_probe_resources.py. libmnl matches its existing
independent MNL_SHA at an explicit one-of-two vendor layout. No expected hash is
calculated from an input, manifest or caller argument. Provider files are
opened once, copied into sealed memfds and hashed AFTER sealing; native handoff
uses retained descriptors only. The native parent is trusted CI-built operator
code, not an arbitrary executable admitted by vendor pins: install it under
root-owned non-writable ancestors, then exec the opened FD without path reopen.
This does not claim immutable bytes for that trusted native program against a
privileged root writer; all directories and trusted code are operator-owned.

## Build and admission

CI-only native Linux build (not Bionic API28); parent owns shared CI:

```sh
cc -std=c11 -Wall -Wextra -Werror -pthread \
  -ffunction-sections -fdata-sections -Wl,--gc-sections -I. \
  b41_sealed_probe_parent.c b41_mipc_sealed_isolate.c \
  b41_mipc_loader_root.c b41_mipc_supervised_child.c \
  b41_native_receiver_host.c -o b41-sealed-probe-parent
PYTHONDONTWRITEBYTECODE=1 python3 test_b41_sealed_probe_cli.py
```

Explicit transitive source dependency: b41_mipc_sealed_isolate.c includes the
frozen mnl-isolate.c. Python imports existing b41_mipc_probe_resources,
b41_mipc_provider_resources, b41_mipc_sealed_stage, b41_mipc_init_resources,
b41_mipc_version_closure and their pyelftools dependency. No hidden patch step.

Run ONLY in a dedicated single-thread root CI process in a cgroup-v2 with actual
`memory.max <=128 MiB`, with namespace/mount/capability permission. Install the
native parent, for example under protected `/root/b41-probe/`. Invoke each
mode once with a distinct nonexistent protected log path:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 b41_sealed_probe_cli.py \
  --selected-stock /root/artifacts/stock-port-assets \
  --probe-artifact /root/artifacts/independent-probe \
  --parent /root/b41-probe/b41-sealed-probe-parent \
  --log /root/b41-probe/control.log \
  --mnl-layout vendor/lib64/mt6878/libmnl.so --mode control
```

After a successful actual control run, use `--mode load` and a new log path.
The actual artifact manifest determines whether the explicit libmnl path is
vendor/lib64 or vendor/lib64/mt6878; there is no fallback/search substitution.
No artifacts are executed during offline Python tests. No local native build
or launcher/probe/ELF execution has been performed for this bundle.

## Ownership and finite operation

FD0 becomes actual read-only /dev/null; FD1/2 share one newly created root-owned
0600 append-only regular log. C validates actual inode/type/mode/access, rejects
all other inherited descriptors and any existing child/thread. The parent log
has a 1 MiB soft file limit with a 64 MiB hard ceiling. Only trusted child setup
raises the soft limit for the bounded provider copy; after root construction
the child's soft and hard limits become 1 MiB before control or vendor code.
The operator must keep trusted directories/code exclusively owned.
The native parent makes its own exclusive empty /run root and the existing
adapter checks the REAL cgroup limit before namespace/fork. The absolute20s
monotonic budget includes Python admission; cleanup gets at most5s extra.
No phase resets that deadline. No caller readiness flags exist.

Only the corrected supervisor waits/reaps. Catchable termination signals are
blocked in the parent; the child restores an empty signal mask before setup,
so CPU/file limits and termination signals retain normal child semantics.
SIGCHLD disposition is explicit default, not auto-reap. Failed spawn
before bind aborts only the unstarted owner. ANY bind attempt requires finish;
traced STOP is never terminal. Cleanup exhaustion logs quarantine and retains
all FDs/root; polling permits late terminal reap without extending operation
or retrying startup. The first error persists. Only actual EXITED/SIGNALED reap
permits release and root removal. If an external actor SIGKILLs the parent this
in-process retention cannot survive; do not use an outer parent-only timeout
as a claimed cleanup acknowledgement. Quarantine requires operator containment,
not unloading/reinitializing or calling forced exit an RX stop/join.

## Actual boundary

`control` executes only the existing denial checks. `load` executes only the
independently pinned original dlopen-only probe with the real linker and library
paths; it calls no vendor entry point and does not unload/reinitialize. Native
parent compilation, actual control/namespace checks, sealed load and terminal
reap passed on ARM64 in
[CI 38050310221](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38050310221)
at `43b4a2d`. These are load-only results, not hardware claims.

INIT remains blocked on complete first/second semantic configuration and
legitimate per-device calibration, property service/branch provenance, real
modem/CCCI transport handshake/ownership, mandatory host-service/assistance
responses and native engine RX stop acknowledgement. None are replaced by
success stubs, caller-cleared masks or Android behavior invented for gpsd.
Sealed load success would not prove navigation, modem readiness or a GNSS fix.
