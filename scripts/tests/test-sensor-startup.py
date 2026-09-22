#!/usr/bin/env python3
"""Offline startup contracts: no device access or real modprobe."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "pmaports/device/testing/device-nothing-tetris/nothing-tetris-sensors"
loader = SourceFileLoader("sensor_startup", str(SOURCE))
spec = spec_from_loader(loader.name, loader)
startup = module_from_spec(spec)
loader.exec_module(startup)


class Startup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dt = self.root / "dt"
        self.modules = self.root / "modules"
        self.modules.mkdir()
        self.boot = self.root / "boot-id"
        self.boot.write_text("fixture-boot\n")
        self.marker = self.root / "attempted"
        overrides = patch.multiple(startup, DT=self.dt, MODULES=self.modules,
                                   DEVICE=Path("/dev/null"), STATE=self.marker,
                                   BOOT_ID=self.boot, TIMEOUT=0)
        overrides.start()
        self.addCleanup(overrides.stop)
        self.put("compatible", b"nothing,tetris\0mediatek,mt6878\0")
        self.put("chosen/nothing,scp-prepare-stage", b"secure-handoff-prepared\0")
        self.put("chosen/nothing,scp-prepare-error", bytes(4))
        self.put("chosen/nothing,scp-secure-state", struct.pack(">I", 3))
        self.put("chosen/nothing,scp-secure-error", bytes(8))
        self.put("soc/scp/compatible", b"mediatek,scp\0")
        self.put("soc/scp/status", b"okay\0")
        self.put("soc/scp/mediatek,infracfg", struct.pack(">I", 19))
        self.put("soc/infra/compatible", b"mediatek,mt6878-infracfg-ao\0syscon\0")
        self.put("soc/infra/phandle", struct.pack(">I", 19))

    def put(self, name, data):
        path = self.dt / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def ready(self, count="24", mask="31", flag="Y"):
        for name in ("scp", "hf_manager", "sensorhub"):
            (self.modules / name).mkdir(exist_ok=True)
        params = self.modules / "sensorhub/parameters"
        params.mkdir(exist_ok=True)
        for name, value in (("firmware_ready", flag), ("sensor_count", count),
                            ("physical_sensor_mask", mask)):
            (params / name).write_text(value + "\n")

    def test_preflight(self):
        startup.preflight()

    def test_rejected_handoffs_never_load(self):
        failures = (
            ("compatible", b"different,board\0"),
            ("compatible", b"nothing,tetris"),
            ("chosen/nothing,scp-prepare-stage", b"preflight\0"),
            ("chosen/nothing,scp-prepare-error", struct.pack(">I", 16)),
            ("chosen/nothing,scp-prepare-error", b"\0"),
            ("chosen/nothing,scp-secure-state", struct.pack(">I", 2)),
            ("chosen/nothing,scp-secure-error", struct.pack(">II", 0, 1)),
            ("soc/scp/status", b"disabled\0"),
            ("soc/scp/mediatek,infracfg", bytes(4)),
            ("soc/scp/mediatek,infracfg", struct.pack(">I", 20)),
            ("soc/infra/compatible", b"different,syscon\0syscon\0"),
        )
        for name, bad in failures:
            with self.subTest(name=name, bad=bad):
                path = self.dt / name
                original = path.read_bytes()
                path.write_bytes(bad)
                try:
                    with patch.object(startup, "load") as load:
                        with self.assertRaises(RuntimeError):
                            startup.start()
                        load.assert_not_called()
                        self.assertFalse(self.marker.exists())
                finally:
                    path.write_bytes(original)

    def test_missing_and_duplicate_nodes(self):
        self.put("soc/other/compatible", b"mediatek,scp\0")
        with self.assertRaises(RuntimeError):
            startup.preflight()
        (self.dt / "soc/other/compatible").unlink()
        self.put("soc/other/phandle", struct.pack(">I", 19))
        with self.assertRaises(RuntimeError):
            startup.preflight()
        (self.dt / "soc/other/phandle").unlink()
        (self.dt / "chosen/nothing,scp-prepare-error").unlink()
        with self.assertRaises(OSError):
            startup.preflight()

    def test_already_ready_is_idempotent(self):
        self.ready()
        with patch.object(startup, "load") as load:
            self.assertEqual(startup.start()["sensor_count"], 24)
            load.assert_not_called()
        self.assertFalse(self.marker.exists())

    def test_partial_state_never_reloads(self):
        (self.modules / "scp").mkdir()
        with patch.object(startup, "load") as load:
            with self.assertRaisesRegex(RuntimeError, "partial sensor state"):
                startup.start()
            load.assert_not_called()

    def test_success_order_and_second_start(self):
        calls = []
        def load(name, *options):
            calls.append((name, *options))
            if name == "sensorhub":
                self.ready()
        with patch.object(startup, "load", side_effect=load):
            self.assertEqual(startup.start()["physical_sensor_mask"], 31)
            startup.start()
        self.assertEqual(calls, [("scp", "bootstrap_26m=1"), ("sensorhub",)])
        self.assertEqual((self.marker / "boot-id").read_text(), "fixture-boot\n")

    def test_timeout_cannot_retry(self):
        with patch.object(startup, "load") as load:
            with self.assertRaisesRegex(RuntimeError, "inventory timeout"):
                startup.start()
            self.assertEqual(load.call_count, 2)
            with self.assertRaisesRegex(RuntimeError, "already attempted"):
                startup.start()
            self.assertEqual(load.call_count, 2)

    def test_modprobe_failure_cannot_retry(self):
        with patch.object(startup, "load", side_effect=subprocess.TimeoutExpired("modprobe", 25)) as load:
            with self.assertRaises(subprocess.TimeoutExpired):
                startup.start()
            self.assertEqual(load.call_count, 1)
            with self.assertRaisesRegex(RuntimeError, "already attempted"):
                startup.start()
            self.assertEqual(load.call_count, 1)

    def test_inventory_requires_all_classes_and_device(self):
        for count, mask in (("0", "31"), ("256", "31"), ("24", "15"), ("24", "-1")):
            self.ready(count=count, mask=mask)
            with self.assertRaises(RuntimeError):
                startup.inventory()
        self.ready(flag="N")
        self.assertIsNone(startup.inventory())
        self.ready()
        with patch.object(startup, "DEVICE", self.root / "missing"):
            with self.assertRaises(RuntimeError):
                startup.inventory()

    def test_load_is_bounded(self):
        with patch.object(startup.subprocess, "run") as run:
            startup.load("scp", "bootstrap_26m=1")
            run.assert_called_once_with(["/sbin/modprobe", "scp", "bootstrap_26m=1"],
                                        check=True, timeout=25)


if __name__ == "__main__":
    unittest.main()
