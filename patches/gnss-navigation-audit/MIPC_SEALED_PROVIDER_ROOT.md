# B4.1 sealed provider root

Source artifact CI38039798135 at4e73: release Tetris_B4.1-260415-1709,
system image SHA256 ce53560d05e6caa8ad8c27a4c85eefbb93479b879e8c610be650be6b689108e6.
Actual system/lib64/liblog.so is102352 bytes, SHA256
dce4ece329f925cdc0b181b3e5f11b54d92a24e49b1b90b121a4e0f960df84fd.
Trust is pinned mirror archive identity plus independent library pins, NOT OEM
signature verification. No NDK import stub is accepted as liblog.

## Resource integration

`acquire_providers(stock_root, bionic_root)` reuses frozen acquire/version
validation with the fixed real liblog pin. The actual ten providers resolve385
bindings, zero missing libraries and zero required symbol errors. Weak symbols
retain existing reporting. Both mtkrillog LIBLOG imports bind to real liblog.
No property service, runtime namespace, modem readiness or INIT is certified.

`LoaderResources` reuses SealedStage; hashes sealed copies before returning
fixed-order descriptors. Linker mode0555 and library modes0444 admit legitimate
read/map/execute access after privilege drop. Source lease is closed only after
copies exist. Move transfers ownership once to the parent's supervisor.
Prepare failure leaves descriptors caller-owned; successful prepare moves them.
Forked child reads supervisor's retained stage array in the same fixed order.

`b41_mipc_loader_root` creates its own private mount namespace and fresh tmpfs
under a fresh, empty root-owned directory controlled exclusively by the parent.
The parent must own/protect this directory and its ancestors through handoff;
it is not an attacker-controlled path or shared mutable staging tree. Fixed
paths are read-only bind mounts from the actual sealed FDs, not copies or source
path reopens. All directories and root are read-only for the eventual child.
`ld-android.so`'s provider is the actual pinned linker64 at its executable path.
Partial failure requires child exit; there is no mount rollback/reinit on a live
worker. Parent retains descriptors until EXITED/SIGNALED terminal reap using the
existing corrected supervisor. No forced exit is described as an RX join.

The existing load-only isolate cannot simply rebind this root nonrecursively:
its MS_BIND root operation would hide the nested sealed-file mounts. Parent
integration must call this builder in the child and consume its prepared root
without that extra bind, then retain existing proc/chroot/drop/seccomp/bounds.
This bundle does NOT modify or run the frozen isolate. The separate adapter
below supplies an independently pinned /probe and libmnl via sealed descriptors.
INIT remains prohibited pending config, property and actual
modem/CCCI readiness contracts; no property or transport fakes are added.

## CI commands and dependencies

Set TETRIS_B41_STOCK_ROOT to the existing extracted stock artifact root and
TETRIS_BIONIC_ROOT to the legitimate pinned runtime root. No archive download
is needed. `PYTHONDONTWRITEBYTECODE=1 python3 test_b41_mipc_provider_resources.py`
requires pyelftools and runs real closure tests without C or ELF execution.
Mac explicitly skips the Linux sealing vector; it does not claim a sealing pass.

`CI=true sh run_mipc_loader_resources_ci.sh mounts` requires Linux memfd, Ubuntu native
compiler/sanitizers, timeout, and root/CAP_SYS_ADMIN for the child-only mount
fixture. No asset is executed: native fixture uses labelled non-ELF filesystem
data only. Pinned real bytes are tested by the Python sealing vector. Add Bionic
API28 object compile of b41_mipc_loader_root.c to parent's existing native build.
No local C compilation, namespace operation or phone call was performed.

`CI=true TETRIS_B41_STOCK_ROOT=... TETRIS_BIONIC_ROOT=... sh
run_mipc_loader_resources_ci.sh providers` is an independent asset-required
mode. The mount mode does not import Python resource audits or require cached
stock artifacts; it also compiles the separate immutable isolate adapter object.
Neither mode silently skips missing CI prerequisites.

Cleanup faults are attached to the original producer exception using add_note;
they never replace its errno. Offline vectors cover validation, staging and
mode failure with failing cleanup. Native mount vectors impose actual kernel
seccomp EACCES on bind and bind-remount after private tmpfs creation. They check
unchanged parent root, retained supervisor FDs before exit, original mount error
through the report pipe, and FD release only after terminal child reap.

## Separate immutable executable adapter

`ProbeResources` appends two fully sealed descriptors to the ten providers:
the existing CI37898372984 load-only probe (SHA256
011a0dd90ab2043fd2eb8312024f000769d093b8e1b58e0e3540509122e7c214)
and libmnl (SHA256
3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90).
No caller-selected executable, hash, mutable reopen or replacement stub is
accepted. `b41_mipc_loader_root_probe` mounts these at fixed paths. The distinct
`b41_mipc_sealed_probe_spawn` reuses the frozen isolate's actual filter/control,
cgroup check and resource limits without its submount-hiding root bind.
Call only from a dedicated root launcher: network/PID namespace creation changes
that launcher. Its prepared supervisor owns all twelve FDs and the absolute
deadline, checked before namespace/fork; finish/reap remains mandatory after any
bind attempt, including failed bind. Unreaped children retain the lease. A
deadline expiring during startup is enforced by the parent's existing waiter.

The adapter offers only control or the original dlopen-only executable. It does
not supply property services, CCCI handshake, configuration or engine INIT/RX.
Load/control execution has NOT been tested locally. For CI object validation:
`cc -std=c11 -Wall -Wextra -Werror -I. -c b41_mipc_sealed_isolate.c`.
Executable linkage needs b41_mipc_loader_root.c, b41_mipc_supervised_child.c,
b41_native_receiver_host.c and parent's entry point; use function/data sections
and linker garbage collection for the native host's unused functions. The
frozen mnl-isolate.c include is an explicit source dependency. This adapter is
Linux-only, not an Android API28 namespace library. Validate Python admission
with `PYTHONDONTWRITEBYTECODE=1 python3 test_b41_mipc_probe_resources.py` using
the same explicit stock/Bionic roots; actual sealing vectors require Linux.
