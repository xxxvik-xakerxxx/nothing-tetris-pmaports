"""Offline admission/ownership tests; no native executable or vendor call."""
import errno
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import b41_sealed_probe_cli as cli


class AdmissionTests(unittest.TestCase):
    def test_explicit_layout_before_open(self):
        with patch.object(cli, "LoaderResources") as load:
            with self.assertRaises(ValueError):
                cli.SelectedProbeResources("selected", "probe", "../libmnl.so")
            load.assert_not_called()

    def test_selected_artifact_providers_and_independent_probe(self):
        base = Mock()
        base.move.return_value = list(range(20, 30))
        with patch.object(cli, "LoaderResources", return_value=base) as load, \
                patch.object(cli.os, "open", side_effect=[8, 9]) as opened, \
                patch.object(cli, "seal_provider", side_effect=[30, 31]) as seal, \
                patch.object(cli.os, "fchmod") as modes, patch.object(cli.os, "close"):
            resources = cli.SelectedProbeResources("selected", "independent-probe",
                "vendor/lib64/mt6878/libmnl.so")
            load.assert_called_once_with("selected", "selected")
            self.assertEqual([c.args[0] for c in opened.call_args_list],
                [Path("independent-probe/probe"), Path("selected/vendor/lib64/mt6878/libmnl.so")])
            self.assertEqual([c.args for c in seal.call_args_list],
                [(8, cli.PROBE_SHA), (9, cli.MNL_SHA)])
            self.assertEqual([c.args for c in modes.call_args_list], [(30, 0o555), (31, 0o444)])
            self.assertEqual(resources.move(), list(range(20, 32)))

    def test_admission_error_survives_cleanup(self):
        base = Mock(close=Mock(side_effect=OSError(errno.EIO, "base cleanup")))
        with patch.object(cli, "LoaderResources", return_value=base), \
                patch.object(cli.os, "open", return_value=8), \
                patch.object(cli, "seal_provider", side_effect=OSError(errno.EBADMSG, "pin mismatch")), \
                patch.object(cli.os, "close", side_effect=OSError(errno.EIO, "source cleanup")):
            with self.assertRaises(OSError) as caught:
                cli.SelectedProbeResources("selected", "probe", "vendor/lib64/libmnl.so")
        self.assertEqual(caught.exception.errno, errno.EBADMSG)
        self.assertIn("source cleanup", caught.exception.__notes__[0])
        self.assertIn("base cleanup", caught.exception.__notes__[1])

    def test_no_engine_mode_or_arbitrary_library_layout(self):
        required = ["cli", "--selected-stock", "selected", "--probe-artifact", "probe",
                    "--parent", "/root/parent", "--log", "/run/log"]
        for extra in (("--mode", "init", "--mnl-layout", "vendor/lib64/libmnl.so"),
                      ("--mode", "load", "--mnl-layout", "arbitrary")):
            with patch.object(sys, "argv", required + list(extra)), \
                    patch.object(sys, "stderr", Mock()), self.assertRaises(SystemExit) as caught:
                cli.arguments()
            self.assertEqual(caught.exception.code, 2)

    def test_parent_is_explicit_trusted_not_operator_pin(self):
        with self.assertRaises(ValueError):
            cli.trusted_parent("relative/native-parent")

    def test_same_process_fd_exec_failure_closes_transferred_lease(self):
        resources = Mock()
        resources.move.return_value = list(range(20, 32))
        args = SimpleNamespace(selected_stock="selected", probe_artifact="independent",
            mnl_layout="vendor/lib64/libmnl.so", parent=Path("/root/parent"),
            log=Path("/root/log"), mode="control")
        with patch.object(cli, "arguments", return_value=args), \
                patch.object(cli.os, "geteuid", return_value=0), \
                patch.object(cli.Path, "iterdir", return_value=iter([Path("task")])), \
                patch.object(cli.os, "fstat"), patch.object(cli, "trusted_parent", return_value=10), \
                patch.object(cli, "trusted_ancestors", return_value=args.log), \
                patch.object(cli, "SelectedProbeResources", return_value=resources), \
                patch.object(cli.time, "monotonic_ns", return_value=123), \
                patch.object(cli.os, "open", side_effect=[11, 12]), \
                patch.object(cli.os, "dup2") as duplicate, \
                patch.object(cli.os, "set_inheritable") as inherited, \
                patch.object(cli.os, "close") as closed, \
                patch.object(cli.os, "execve", side_effect=OSError(errno.ENOEXEC, "exec fault")) as execute, \
                patch.object(cli.os, "supports_fd", {execute}):
            with self.assertRaises(OSError) as caught:
                cli.main()
            self.assertEqual(caught.exception.errno, errno.ENOEXEC)
            self.assertEqual(execute.call_args.args[0], 10)
            self.assertEqual(execute.call_args.args[1], ["b41-sealed-probe-parent", "control",
                "20000000123", "25000000123", *map(str, range(20, 32))])
            self.assertEqual([c.args for c in duplicate.call_args_list], [(12, 0), (11, 1), (11, 2)])
            self.assertEqual([c.args for c in inherited.call_args_list], [(fd, True) for fd in range(20, 32)])
            self.assertEqual([c.args[0] for c in closed.call_args_list], [12, 11, *range(20, 32), 10])
            resources.close.assert_called_once()

    def test_source_lifecycle_and_fd_exec(self):
        here = Path(__file__).parent
        parent = (here / "b41_sealed_probe_parent.c").read_text()
        wrapper = (here / "b41_sealed_probe_cli.py").read_text()
        self.assertIn("while (!owner.reaped)", parent)
        self.assertLess(parent.index("while (!owner.reaped)"), parent.index("rmdir(root)"))
        self.assertIn("owner.wait_error ? owner.wait_error : error", parent)
        self.assertIn("admitted_descriptors(stage)", parent)
        self.assertIn("os.execve(parent, argv", wrapper)
        for text in (parent, wrapper):
            self.assertNotIn("mnl_run(", text)
            self.assertNotIn("mipc_init(", text)


if __name__ == "__main__":
    unittest.main()
