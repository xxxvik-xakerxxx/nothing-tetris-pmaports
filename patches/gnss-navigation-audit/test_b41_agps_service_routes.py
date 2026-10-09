#!/usr/bin/env python3
"""Post-snapshot audit: pinned selector routes, no real service or engine call.

Run with PYTHONDONTWRITEBYTECODE=1; imports the frozen startup harness.
"""
from pathlib import Path
import sys
from test_b41_startup import Machine, MNLD_SHA, DATA


def audit(path):
    m = Machine(path, MNLD_SHA, [(0x5fa80, 0x5feb0), (0x5ff38, 0x5ff68)])
    calls = []
    for target in (0x493c0, 0x494b0):
        m.mock(target, lambda args, target=target:
               calls.append((target, args[0], args[1])) or 0xffffffff)
    for selector, target, mode in ((12, 0x493c0, 1), (13, 0x494b0, 1),
                                   (14, 0x493c0, 0), (15, 0x494b0, 0)):
        for parameter, pointer in ((0, 0), (1, DATA), (0xffffffff, DATA + 128)):
            calls.clear()
            m.run(0x5fa80, args=(selector, parameter, pointer))
            # Start passes the original pointer through x1; stop leaves x1
            # carrying the original parameter. Neither is a length copy here.
            expected_x1 = pointer if target == 0x493c0 else parameter
            assert calls == [(target, mode, expected_x1)]
            assert m.args()[0] == 0
    print("PASS: twelve pinned AGPS12..15 selector/operand routes; intercepted service failure masked")
    print("OFFLINE ONLY: no data-center service executed, no navigation start or stop proved")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_b41_agps_service_routes.py PINNED_MNLD")
    audit(Path(sys.argv[1]))
