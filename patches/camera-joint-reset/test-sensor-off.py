#!/usr/bin/env python3
"""Source-only regression fixtures; no C compilation or hardware execution."""
import unittest
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
from unittest.mock import patch

from check import SENSOR_PATH, applied_sensor, main, packaged_sensor, sensor_off_contract


class SensorOffContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = applied_sensor()

    def reject(self, old, new):
        self.assertIn(old, self.source)
        with self.assertRaises((AssertionError, IndexError)):
            sensor_off_contract(self.source.replace(old, new, 1))

    def test_applied_overlay(self):
        sensor_off_contract(self.source)

    def test_shipping_without_overlay(self):
        with self.assertRaises((AssertionError, IndexError)):
            sensor_off_contract(packaged_sensor())

    def test_missing_core_registration(self):
        self.reject(".core = &imx882_core_ops,", ".core = NULL,")

    def test_missing_power_callback(self):
        self.reject(".s_power = imx882_power,", ".s_power = NULL,")

    def test_stopped_sensor_still_needs_cleanup(self):
        self.reject("? -EBUSY : imx882_stop(camera);",
                    "? -EBUSY : (camera->streaming ? imx882_stop(camera) : 0);")

    def test_no_owned_rails_still_needs_reset(self):
        self.reject("gpiod_set_value_cansleep(imx882->reset, 1);",
                    "if (enabled_supplies) gpiod_set_value_cansleep(imx882->reset, 1);")

    def test_stop_must_not_skip_power_off(self):
        self.reject("cleanup = imx882_power_off(&camera->power, camera->enabled_supplies,",
                    "if (camera->streaming) cleanup = imx882_power_off(&camera->power, camera->enabled_supplies,")

    def test_reset_polarity(self):
        self.reject("gpiod_set_value_cansleep(imx882->reset, 1);",
                    "gpiod_set_value_cansleep(imx882->reset, 0);")

    def test_staged_only_missing_tree_argument(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            main(["--staged-only"])
        self.assertEqual(result.exception.code, 2)

    def test_full_check_requires_vendor_repo(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            main([])
        self.assertEqual(result.exception.code, 2)

    def test_actual_staged_files(self):
        with tempfile.TemporaryDirectory(prefix="sensor-staged-mode-test-") as name:
            tree = Path(name)
            source = tree / SENSOR_PATH
            args = ["--staged-only", "--kernel-tree", name]
            # A vendor dependency must not leak into the bounded staging mode.
            with patch("check.subprocess.check_output", side_effect=AssertionError("Git read")), \
                    patch("check.subprocess.run", side_effect=AssertionError("overlay replay")):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                    main(args)
                self.assertEqual(result.exception.code, 1)
                source.parent.mkdir(parents=True)
                source.write_text(packaged_sensor())
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                    main(args)
                self.assertEqual(result.exception.code, 1)
                source.write_text(self.source)
                output = io.StringIO()
                with redirect_stdout(output):
                    main(args)
                self.assertIn("Actual staged sensor OFF contract PASS", output.getvalue())


if __name__ == "__main__":
    unittest.main()
