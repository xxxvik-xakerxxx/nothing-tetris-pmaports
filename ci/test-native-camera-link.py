#!/usr/bin/env python3
"""Validate native camera link inputs without executing any compiler."""
import ast
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("camera_link", ROOT / "ci/link-native-camera-vmm.py")
LINK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LINK)


class NativeCameraLink(unittest.TestCase):
    def test_supplier_names_exist_in_canonical_provider_patch(self):
        source = (LINK.DRAFT / "native-provider.patch").read_text()
        for name in LINK.SUPPLIER_SYMBOLS:
            self.assertIn("+int " + name + "(", source)

    def test_local_build_refused_before_subprocess(self):
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}), \
                patch.object(LINK.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "CI-only"):
                LINK.main()
            run.assert_not_called()

    def test_real_final_link_and_no_symbol_stubs(self):
        source = (ROOT / "ci/link-native-camera-vmm.py").read_text()
        ast.parse(source)
        self.assertIn('run([*make, "vmlinux"])', source)
        self.assertIn('"KBUILD_EXTRA_SYMBOLS"', source)
        self.assertIn('"llvm-nm", "--defined-only", supplier', source)
        self.assertNotIn('"llvm-nm", "--defined-only", output / "vmlinux"', source)
        self.assertIn('for unit in ("y", "n"):', source)
        self.assertIn('if resolved.get("KUNIT", "n") != unit:', source)
        self.assertLess(source.index('output.mkdir(exist_ok=False)'), source.index('for unit in ("y", "n")'))

    def test_combined_md_uses_real_source_and_resolved_static_config(self):
        source = (ROOT / "ci/link-native-camera-vmm.py").read_text()
        self.assertIn('"--prepared-kernel", kernel, "--ci-apply"', source)
        self.assertIn('"--md-on-adoption"', source)
        self.assertIn('md_plan["ci"]["required_resolved_config"]', source)
        for symbol in ("OF_DYNAMIC", "OF_OVERLAY", "I2C_DEMUX_PINCTRL", "CHROMEOS_OF_HW_PROBER",
                       "VIDEO_QCOM_VENUS", "PCI_DYNAMIC_OF_NODES", "STM32_FIREWALL"):
            self.assertIn(symbol, LINK.STATIC_DIAGNOSTIC_DISABLE)
        fragment = (ROOT / "patches/modem/md-pm-integration/diagnostic.config").read_text().splitlines()
        for symbol in LINK.STATIC_DIAGNOSTIC_DISABLE:
            self.assertIn("# CONFIG_" + symbol + " is not set", fragment)

    def test_hidden_false_symbols_and_positive_requirements(self):
        for lines in ([], ["# CONFIG_OF_DYNAMIC is not set"]):
            self.assertEqual(LINK.config_values(lines).get("OF_DYNAMIC", "n"), "n")
        for value in ("y", "m"):
            self.assertNotEqual(LINK.config_values(["CONFIG_OF_DYNAMIC=" + value]).get("OF_DYNAMIC", "n"), "n")
        self.assertNotEqual(LINK.config_values([]).get("OF", "n"), "y")

    def test_object_evidence_survives_final_link_failure(self):
        source = (ROOT / "ci/link-native-camera-vmm.py").read_text()
        start = source.index('run([*make, "vmlinux"])')
        for marker in ('shutil.copyfile(compiled, retained)',
                       'outcome["status"] = "objects-compiled"',
                       'outcome["status"] = "vmlinux-link-started"'):
            self.assertLess(source.index(marker), start)
        self.assertGreater(source.index('"status": "passed",'), start)
        self.assertIn('finally:', source)


if __name__ == "__main__":
    unittest.main()
