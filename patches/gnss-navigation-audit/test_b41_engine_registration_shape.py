#!/usr/bin/env python3
"""Actual24-slot engine registration shape; retained global side effects offline."""
from pathlib import Path
import struct
import sys
import re
import unittest


def admission_barriers(source):
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    start = source.index("int b41_native_session_execute(")
    session = source[start:source.index("static int snapshot(", start)]
    barrier = "status = b41_native_worker_admission(worker);\n    if (status) return status;"
    registration = session.index("result->registration_entered = 1;")
    registered = session.index("if (registration(&arguments->callbacks)) return -EPROTO;")
    run = session.index("result->run_entered = 1;")
    first = session.find(barrier)
    second = session.find(barrier, first + len(barrier))
    assert 0 <= first < registration, "worker failure must reject before registration"
    assert registered < second < run, "worker failure must be rechecked before run"


class WorkerAdmissionSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).with_name("b41_native_receiver_host.c").read_text()

    def test_registration_and_run_reject_dead_worker(self):
        admission_barriers(self.source)

    def test_completion_is_observed_without_consuming_quiescence_wake(self):
        start = self.source.index("int b41_native_worker_admission(")
        helper = self.source[start:self.source.index("int b41_native_session_execute(", start)]
        self.assertIn("atomic_load(&worker->failure)", helper)
        self.assertIn("atomic_load(&worker->stop_requested)", helper)
        self.assertIn("poll(&done, 1, 0)", helper)
        self.assertIn("return status ? status : -ESHUTDOWN", helper)
        self.assertNotIn("read(", helper)
        self.assertNotIn("close(", helper)
        self.assertNotIn("atomic_store(", helper)

    def test_worker_dispatch_failure_does_not_change_controller_state(self):
        source = Path(__file__).with_name("b41_frame_worker.c").read_text()
        run = source[source.index("static void *run("):source.index("int b41_frame_worker_start(")]
        self.assertIn("status = w->dispatch(w->ipc, &event)", run)
        self.assertIn("if (status) { fail(w, status); break; }", run)
        self.assertNotIn("w->state =", run)

    def test_missing_or_unchecked_barriers_are_rejected(self):
        barrier = "status = b41_native_worker_admission(worker);\n    if (status) return status;"
        for index in (0, 1):
            start = self.source.index(barrier)
            if index:
                start = self.source.index(barrier, start + len(barrier))
            for replacement in ("", "status = b41_native_worker_admission(worker);"):
                mutant = self.source[:start] + replacement + self.source[start + len(barrier):]
                with self.subTest(barrier=index, replacement=replacement):
                    with self.assertRaises(AssertionError):
                        admission_barriers(mutant)

    def test_existing_ci_runner_runs_source_checks_and_real_worker_fixture(self):
        runner = Path(__file__).with_name("run_native_receiver_host_ci.sh").read_text()
        self.assertLess(runner.index("--source-only"), runner.index('"${CC:-cc}"'))
        for source in ("b41_native_receiver_host.c", "b41_startup_adapter.c", "b41_agps_host.c",
                       "b41_navigation_output.c", "b41_frame_worker.c", "test_b41_native_receiver_host.c"):
            self.assertIn('"$here/' + source + '"', runner)

def verify(path):
    from test_b41_startup import Machine, LIB_SHA, DATA, STOP
    for missing in [None] + list(range(10)):
        m=Machine(path,LIB_SHA,[(0x52f9d0,0x52fbb0)])
        slots=[STOP+0x100+8*i if i!=missing else 0 for i in range(10)]+[0]*14
        m.u.mem_write(DATA,struct.pack("<24Q",*slots))
        m.run(0x52f9d0,args=(DATA,))
        required=missing is not None and bool(0x3fb & (1<<missing))
        assert m.args()[0]==(0xffffffff if required else 0)
        for slot,got in ((1,0x6e6800),(3,0x6e6d30),(4,0x6e6d28)):
            assert struct.unpack("<Q",m.u.mem_read(m.global_at(got),8))[0]==slots[slot]
    print("PASS: actual24-slot table with all14 optional NULL; mandatory0x3fb; failed calls retain globals")

if __name__ == "__main__":
    if sys.argv[1:] == ["--source-only"]:
        unittest.main(argv=[sys.argv[0]])
    elif len(sys.argv) == 2:
        verify(Path(sys.argv[1]))
    else:
        raise SystemExit("usage: test_b41_engine_registration_shape.py --source-only | libmnl.so")
