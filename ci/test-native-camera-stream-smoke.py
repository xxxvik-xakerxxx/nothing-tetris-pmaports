#!/usr/bin/env python3
"""Camera compile orchestration only; never stage or compile a local kernel."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stream_smoke", HERE / "native-camera-stream-smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class StreamSmoke(unittest.TestCase):
    def test_local_guard_precedes_input_access_and_processes(self):
        for ci, github in (("", ""), ("true", ""), ("", "true")):
            with patch.dict(os.environ, CI=ci, GITHUB_ACTIONS=github), \
                    patch.object(smoke.subprocess, "run", side_effect=AssertionError("no local subprocess")):
                with self.assertRaisesRegex(ValueError, "GitHub CI-only"):
                    smoke.build(None)

    def test_security_profile_tracks_positive_and_negative_settings(self):
        text = "CONFIG_LTO_CLANG_THIN=y\nCONFIG_CFI=y\n# CONFIG_CFI_PERMISSIVE is not set\nCONFIG_ARM64_BTI_KERNEL=y\nCONFIG_I2C=y\n"
        self.assertEqual(smoke.security_profile(text), {"LTO_CLANG_THIN": "y", "CFI": "y",
            "CFI_PERMISSIVE": "n", "ARM64_BTI_KERNEL": "y"})

    def test_compile_is_builtin_and_preserves_source_config_identity(self):
        source = (HERE / "native-camera-stream-smoke.py").read_text()
        self.assertIn('"--enable", "VIDEO_IMX882_TETRIS"', source)
        self.assertIn('"CONFIG_VIDEO_IMX882_TETRIS=y" not in resolved.splitlines()', source)
        self.assertLess(source.index('"olddefconfig"'), source.index('"kernel_command"] ='))
        self.assertIn('actual.get(key, "n") != value', source)
        self.assertIn('stage["staged_sha256"][DRIVER]', source)
        self.assertIn('smoke.object_identity(output / OBJECT)', source)
        self.assertIn('"KCFLAGS=-Werror"', source)
        self.assertNotIn("KBUILD_MODPOST_WARN", source)

    def test_camera_jobs_do_not_depend_on_modem_success(self):
        workflow = (HERE.parent / ".github/workflows/ci.yml").read_text()
        condition = "if: ${{ always() && !inputs.research_owner_smoke && steps.kernel_candidates.outcome == 'success' && steps.hardware_sources.outcome == 'success' }}"
        for name in ("Compile observed-OFF camera rail provider", "Compile real IMX882 streaming lifecycle"):
            self.assertIn("- name: " + name + "\n        " + condition, workflow)
        self.assertIn("/tmp/tetris-camera-stream-evidence/", workflow)
        self.assertNotIn("/tmp/tetris-modem-real-on-objects/\n", workflow)


if __name__ == "__main__":
    unittest.main()
