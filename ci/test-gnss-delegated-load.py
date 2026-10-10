"""Offline ownership validation; never writes real cgroups or executes ELF."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("delegation", Path(__file__).with_name("gnss-delegated-load.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DelegationTests(unittest.TestCase):
    def check(self, text="0::/system.slice/tetris-sealed-1-2.service\n", unit="tetris-sealed-1-2.service",
              pids="123\n", controllers="memory pids\n", enabled=""):
        with tempfile.TemporaryDirectory() as root:
            filesystem = Path(root)
            group = filesystem / "system.slice/tetris-sealed-1-2.service"
            group.mkdir(parents=True)
            for name, value in (("cgroup.procs", pids), ("cgroup.controllers", controllers),
                                ("cgroup.subtree_control", enabled)):
                (group / name).write_text(value)
            return module.owned_group(text, unit, 123, filesystem).name

    def test_fresh_owned_service(self):
        self.assertEqual(self.check(), "tetris-sealed-1-2.service")

    def test_global_other_or_traversal_identity(self):
        for text in ("0::/\n", "0::/system.slice/other.service\n",
                     "0::/system.slice/tetris-sealed-1-2.service\n1:memory:/other\n"):
            with self.assertRaises(ValueError):
                self.check(text=text)
        for unit in ("../tetris-sealed-1-2.service", "ssh.service", "tetris-sealed-x-2.service"):
            with self.assertRaises(ValueError):
                self.check(unit=unit)

    def test_unowned_processes_or_preused_controller(self):
        for inputs in ({"pids": "123\n456\n"}, {"pids": "456\n"}, {"controllers": "pids\n"},
                       {"enabled": "memory\n"}):
            with self.assertRaises(RuntimeError):
                self.check(**inputs)


if __name__ == "__main__":
    unittest.main()
