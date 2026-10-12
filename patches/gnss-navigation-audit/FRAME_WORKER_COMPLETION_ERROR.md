# Production frame-worker completion failure

Status: Partial lifecycle correction. Native sanitizer fixture execution and
AArch64 Bionic linkage passed CI38287450780 at e73b771; all validation jobs
succeeded. Engine INIT and hardware lifecycle remain unperformed.

The reverse receiver's completion write was already checked in the snapshot
validated by CI38274644174. Its implementation and LNA query wrapper are unchanged.
The separate production `b41_frame_worker.c` still discarded its terminal
completion write result. That worker is started by
`b41_native_arguments_prepare` and stopped by `b41_native_session_execute`.

If its terminal write failed without an earlier dispatch error, no completion
was published and no original error was retained. Quiescence eventually latched
`-ETIMEDOUT`, obscuring the actual publication failure. Fortified Linux builds
can also reject the unchecked write under warnings-as-errors.

The worker now checks exactly one write. A negative result latches `-errno`;
a short result latches `-EIO`. The existing compare/exchange preserves any
earlier error. Successful publication has no subsequent owner access. Failed
publication creates no replacement ACK and still requires the controller's
deadline and quarantine. No descriptor, callback storage or library is released.

## Exact changed files

- `b41_frame_worker.c`: check terminal completion publication.
- `test_b41_native_receiver_host.c`: four isolated CI fixture children inject
  interrupted/short writes, with and without an earlier `-EPIPE`; check one
  attempt, no ACK, original error, quarantine and retained descriptors.
- `run_native_receiver_host_ci.sh`: connect the write wrapper and enable
  optimized fortified compilation alongside the existing sanitizers.
- `test_b41_engine_registration_shape.py`: source-only lifetime/error checks,
  mutation rejection and CI fixture wiring checks.
- `FRAME_WORKER_COMPLETION_ERROR.md`: this handoff and remaining boundaries.

The injection wrapper is linked only into the CI fixture. Production gains
no callback, retry, property source, service-ready flag or alternate transport.

## Validation

Executed locally from the repository root:

```sh
python3 -B patches/gnss-navigation-audit/test_b41_engine_registration_shape.py --source-only
sh -n patches/gnss-navigation-audit/run_native_receiver_host_ci.sh
git diff --check -- patches/gnss-navigation-audit
```

Nine controller/lifecycle source tests passed, including mutations that ignore
the result, miss short writes, replace the original errno, or access the owner
after successful publication. The eight existing reverse-receiver static tests
also passed against their exact hash-pinned mnld/libmnl inputs, using the
existing offline Capstone dependency. No emulation, JIT or vendor execution was
used. These source checks do not establish C build or fixture execution success.

For parent-owned CI, the existing command now includes the new failure fixtures:

```sh
CI=true sh patches/gnss-navigation-audit/run_native_receiver_host_ci.sh
```

Parent integration also selects the write wrapper for the AArch64 Bionic
`native_receiver_host` fixture; the unrelated native-arguments fixture is not
wrapped. No package, DT, kernel or hardware file was changed. Native fixture
execution remains CI-only, with no phone execution or gate relaxation.

## Remaining INIT And Safety Boundaries

`b41_native_arguments_config_missing` still forces SECOND_POLICY and
AGPS_RECEIVER; `b41_native_session_execute` still rejects any missing contract.
The reverse receiver still provides nine bounded inbound routes only and does
not complete the legitimate forward assistance service.

There is no established native producer for the full forward type150/152
service effects and enabled frame3/4/5 responses, with its owned peer identity
and pre-INIT service semantics. Binding the reverse socket or setting an
unassisted constellation mask cannot supply that evidence. Its activation and
quiescence hooks also remain outside the production controller: any eventual
complete service must activate only after actual run return18 and quiesce
reverse dispatch before destroying native agent queues.

First/config/XML and second-policy producers remain independently required.
Stock DTB topology without matching release/SKU provenance does not establish
an LNA control profile. No gate is relaxed here. Actual INIT, GNSS fix,
cold-start repeatability, suspend/resume, clean installation and SKU portability
remain unvalidated. Existing supervised child exit/reap remains the final
resource boundary; no claim about phone USB/SSH health follows from static tests.
