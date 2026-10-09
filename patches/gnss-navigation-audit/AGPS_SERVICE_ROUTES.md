# Post-Snapshot AGPS Service Routes

Separate follow-up research; frozen adapter/test/header files are unchanged.
Pinned B4.1 mnld hash285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83.

The dispatcher byte table22fcb covers selectors6..23. Four apparently simple
control routes are **LPP/RTCM data-center services**, not receiver navigation
start/stop:

| Selector | Branch | Helper and mode | Literal-backed service |
| --- | --- | --- | --- |
| 12 | 5ff38 | 493c0(mode1) | RTCM start |
| 13 | 5ff40 | 494b0(mode1) | RTCM stop |
| 14 | 5ff4c | 493c0(mode0) | LPP start |
| 15 | 5ff5c | 494b0(mode0) | LPP stop |

493c0 uses literalsbf8c/1d125/1fe8d naming data-center start/LPP/RTCM;
494b0 usesbfb4/ff78/16029 naming corresponding stop. Start mode0 calls44440,
mode1 calls4e8e0; stop mode0 calls44730, mode1 calls4eae0. Those actual service
backends/owners are not implemented by the adapter and remain unexecuted.

The frozen adapter correctly refuses these selectors. Generic copying based
on w1 would be wrong: selector15 can carry parameter1 with NULL, while start
passes the saved original pointer to helper x1. The helper does not directly
read that pointer in the traced body, but an indirect/deeper callee can still
observe argument registers: **pointer ignorance is not established**.

`test_b41_agps_service_routes.py` executes the complete selector routing with
intercepted493c0/494b0 endpoints. It checks twelve parameter/pointer variants,
including NULL and UINT32_MAX, and preserves stock's masking of an injected
service failure to zero. This establishes routing, not real IPC completion.
Run with `PYTHONDONTWRITEBYTECODE=1` to avoid generated files in the repository.

Next service gate is the data-center endpoint/envelope and ownership behind
44440/4e8e0/44730/4eae0, rather than treating selector15 as GPS engine shutdown.
