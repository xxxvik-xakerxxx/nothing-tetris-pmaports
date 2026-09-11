import unittest

from gps_stop_trace import FUNCTIONS, StopTrace, TraceError, run_traced


class Files:
    def __init__(self):
        self.values = {"available_tracers": "function_graph function nop",
                       "available_filter_functions": "\n".join(FUNCTIONS)}
        self.events = []
        self.fail = None
        self.loss = "0"
        self.existing = False

    def read(self, path, limit=None):
        if path.endswith("/trace"):
            return "reviewed function timing\n"
        return self.values[path]

    def write(self, path, value):
        self.events.append((path, value))
        if self.fail and path.endswith(self.fail):
            self.fail = None
            raise OSError("injected control failure")
        self.values[path] = value

    def mkdir(self, path):
        if self.existing:
            raise FileExistsError(path)
        self.events.append((path, "mkdir"))

    def rmdir(self, path):
        self.events.append((path, "rmdir"))

    def stats(self, path):
        return {path + "/per_cpu/cpu0/stats":
                f"overrun: {self.loss}\ncommit overrun: 0\ndropped events: 0\n"}


class TestStopTrace(unittest.TestCase):
    def test_success_and_isolation(self):
        files, calls = Files(), []
        result = run_traced(lambda: calls.append(1), files)
        self.assertEqual(calls, [1])
        self.assertIsNone(result["operation_error"])
        self.assertIsNone(result["trace_error"])
        self.assertTrue(result["ok"])
        self.assertIn("timing", result["trace"])
        self.assertTrue(all(p.startswith("instances/tetris-gps-stop-") for p, _ in files.events))
        self.assertEqual(files.events[-1][1], "rmdir")
        self.assertEqual(files.events[-2][1], "nop\n")

    def test_operation_failure_retains_trace(self):
        def fail():
            raise RuntimeError("first hardware failure")
        files = Files()
        result = run_traced(fail, files)
        self.assertIn("first hardware failure", result["operation_error"])
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["trace"])
        self.assertEqual(files.events[-1][1], "rmdir")

    def test_unavailable_no_writes(self):
        for field in ("available_tracers", "available_filter_functions"):
            with self.subTest(field=field):
                files = Files()
                files.values[field] = ""
                with self.assertRaises(TraceError):
                    run_traced(lambda: self.fail("must not run"), files)
                self.assertEqual(files.events, [])

    def test_existing_instance_untouched(self):
        files = Files()
        files.existing = True
        with self.assertRaises(FileExistsError):
            run_traced(lambda: self.fail("must not run"), files)
        self.assertEqual(files.events, [])

    def test_setup_failures_clean_own_instance(self):
        for control in ("buffer_size_kb", "set_ftrace_filter", "trace_clock",
                        "options/sleep-time", "current_tracer"):
            with self.subTest(control=control):
                files = Files()
                files.fail = control
                with self.assertRaises(OSError):
                    run_traced(lambda: self.fail("must not run"), files)
                self.assertEqual(files.events[-1][1], "rmdir")

    def test_overrun_rejected(self):
        files = Files()
        files.loss = "1"
        result = run_traced(lambda: None, files)
        self.assertIn("lost events", result["trace_error"])
        self.assertIsNotNone(result["trace"])
        self.assertFalse(result["ok"])
        self.assertEqual(files.events[-1][1], "rmdir")

    def test_wrong_filter_prevents_operation(self):
        files = Files()
        original = files.read
        files.read = lambda p, limit=None: "*" if p.endswith("/set_ftrace_filter") else original(p)
        with self.assertRaises(TraceError):
            run_traced(lambda: self.fail("must not run"), files)
        self.assertEqual(files.events[-1][1], "rmdir")

    def test_close_is_idempotent(self):
        files = Files()
        session = StopTrace(files)
        session.start()
        session.close()
        count = len(files.events)
        session.close()
        self.assertEqual(len(files.events), count)

    def test_cleanup_failure_does_not_hide_operation_failure(self):
        files = Files()
        def cleanup_fail(path):
            raise OSError("cleanup failed")
        def operation_fail():
            raise RuntimeError("first failure")
        files.rmdir = cleanup_fail
        result = run_traced(operation_fail, files)
        self.assertIn("first failure", result["operation_error"])
        self.assertIn("cleanup failed", result["cleanup_error"])
        self.assertIsNotNone(result["trace"])
        self.assertFalse(result["ok"])

    def test_invalid_statistics_retained_as_evidence(self):
        files = Files()
        files.stats = lambda path: {path + "/per_cpu/cpu0/stats": "entries: 1\n"}
        result = run_traced(lambda: None, files)
        self.assertIn("unrecognized", result["trace_error"])
        self.assertIsNotNone(result["stats"])
        self.assertIsNotNone(result["trace"])
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
