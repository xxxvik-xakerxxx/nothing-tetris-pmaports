"""Offline CLI orchestration/failure tests; no cgroup or ELF execution."""
import errno
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import b41_sealed_probe_ci as runner


CONTROL = "CONTROL: eight network/device/namespace/privilege denials, failures=0\n"
LOAD = "LOAD_OK: no vendor API called; no dlclose or destructors\n"
TERMINAL = "TERMINAL: status=0 first=0\n"


class RunnerTests(unittest.TestCase):
    def test_wrong_arch_rejected_before_process_or_kernel_state(self):
        with patch.dict(runner.os.environ, {"CI": "true"}), \
                patch.object(runner.os, "geteuid", return_value=0), \
                patch.object(runner.platform, "system", return_value="Linux"), \
                patch.object(runner.platform, "machine", return_value="x86_64"), \
                patch.object(Path, "iterdir") as state:
            with self.assertRaisesRegex(RuntimeError, "actual ARM64 Linux"):
                runner.require_ci()
            state.assert_not_called()

    def test_exact_control_load_terminal_protocol(self):
        runner.verify_result("control", CONTROL + TERMINAL, 0)
        runner.verify_result("load", LOAD + TERMINAL, 0)

    def test_reject_false_success_and_nonterminal(self):
        cases = [(CONTROL, 0), (CONTROL + TERMINAL, 1),
                 (CONTROL + "TERMINAL: status=4991 first=0\n", 0),
                 (CONTROL + TERMINAL + TERMINAL, 0),
                 (CONTROL + TERMINAL + "QUARANTINE: child\n", 0),
                 (LOAD + TERMINAL, 0)]
        for text, result in cases:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                runner.verify_result("control", text, result)
        with self.assertRaises(RuntimeError):
            runner.verify_result("load", LOAD + TERMINAL + "LOAD_FAILED: error\n", 0)

    def test_never_enable_global_cgroup_controller(self):
        with self.assertRaises(ValueError):
            runner.delegated_parent(Path("/sys/fs/cgroup"))
        with patch.object(runner, "trusted_ancestors", return_value=Path("/sys/fs/cgroup/delegated")), \
                patch.object(Path, "read_text", return_value="cpu io"), \
                patch.object(Path, "write_text") as write:
            with self.assertRaises(RuntimeError):
                runner.delegated_parent(Path("/sys/fs/cgroup/delegated"))
            write.assert_not_called()

    def test_observation_timeout_retains_reaper_and_containment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group, results = root / "group", root / "results"
            group.mkdir(); results.mkdir()
            child = Mock(pid=123, wait=Mock(side_effect=subprocess.TimeoutExpired("parent", 30)))
            args = SimpleNamespace(selected_stock=Path("/selected"), probe_artifact=Path("/probe-ci"),
                parent=Path("/root/native-parent"), mnl_layout="vendor/lib64/mt6878/libmnl.so")
            with patch.object(runner.tempfile, "mkdtemp", return_value=str(group)), \
                    patch.object(runner.subprocess, "Popen", return_value=child) as launch:
                with self.assertRaisesRegex(RuntimeError, "containment retained"):
                    runner.run_one("control", args, root, results)
            child.kill.assert_not_called(); child.terminate.assert_not_called()
            child.wait.assert_called_once_with(timeout=30)
            self.assertTrue(group.exists())
            report = json.loads((results / "control-result.json").read_text())
            self.assertEqual(report["status"], "quarantined-parent-running")
            self.assertEqual(report["parent_pid"], 123)
            command = launch.call_args.args[0]
            self.assertIn("/selected", command); self.assertIn("/probe-ci", command)
            self.assertTrue(launch.call_args.kwargs["close_fds"])
            self.assertEqual((group / "memory.max").read_text(), "134217728")

    def test_parent_exit_not_enough_if_group_populated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group, results = root / "group", root / "results"
            group.mkdir(); results.mkdir()
            (group / "cgroup.procs").write_text("987\n")
            child = Mock(pid=123, wait=Mock(return_value=0))
            args = SimpleNamespace(selected_stock=Path("/selected"), probe_artifact=Path("/probe-ci"),
                parent=Path("/root/native-parent"), mnl_layout="vendor/lib64/libmnl.so")
            with patch.object(runner.tempfile, "mkdtemp", return_value=str(group)), \
                    patch.object(runner.subprocess, "Popen", return_value=child):
                with self.assertRaisesRegex(RuntimeError, "containment still populated"):
                    runner.run_one("control", args, root, results)
            self.assertTrue(group.exists())
            self.assertEqual(json.loads((results / "control-result.json").read_text())["status"],
                             "failed-retained-containment")

    def test_recording_error_does_not_mask_limit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group, results = root / "group", root / "results"
            group.mkdir(); results.mkdir()
            args = SimpleNamespace()
            def fail(path, *args, **kwargs):
                if path.name == "memory.max":
                    raise OSError(errno.EROFS, "limit denied")
                raise OSError(errno.ENOSPC, "record full")
            with patch.object(runner.tempfile, "mkdtemp", return_value=str(group)), \
                    patch.object(Path, "write_text", fail), \
                    patch.object(runner.subprocess, "Popen") as launch:
                with self.assertRaises(OSError) as caught:
                    runner.run_one("control", args, root, results)
                launch.assert_not_called()
            self.assertEqual(caught.exception.errno, errno.EROFS)
            self.assertIn("record full", caught.exception.__notes__[0])

    def test_control_failure_prevents_load_and_final_success_report(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results"
            args = SimpleNamespace(selected_stock=Path("/selected"), probe_artifact=Path("/probe-ci"),
                parent=Path("/root/native-parent"), cgroup_parent=Path("/sys/fs/cgroup/delegated"),
                results=results, mnl_layout="vendor/lib64/libmnl.so")
            with patch.object(runner.sys, "argv", ["runner"]), patch.object(runner, "require_ci"), \
                    patch.object(runner.argparse.ArgumentParser, "parse_args", return_value=args), \
                    patch.object(runner, "trusted_parent", return_value=77), patch.object(runner.os, "close"), \
                    patch.object(runner, "delegated_parent", return_value=args.cgroup_parent), \
                    patch.object(runner, "trusted_ancestors", return_value=results), \
                    patch.object(runner, "run_one", side_effect=RuntimeError("control failed")) as execute:
                with self.assertRaisesRegex(RuntimeError, "control failed"):
                    runner.main()
            self.assertEqual([call.args[0] for call in execute.call_args_list], ["control"])
            self.assertFalse((results / "RESULT.json").exists())


if __name__ == "__main__":
    unittest.main()
