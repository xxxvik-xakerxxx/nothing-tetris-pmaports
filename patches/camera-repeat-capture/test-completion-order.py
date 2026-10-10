#!/usr/bin/env python3
"""Regress actual production call order, not a mock DONE/stop provider."""
import unittest

from check import HERE, completion_contract


class CompletionOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (HERE / "mt6878-capture-epoch.c").read_text()

    def reject(self, old, new):
        self.assertEqual(self.source.count(old), 1)
        with self.assertRaises((AssertionError, ValueError)):
            completion_contract(self.source.replace(old, new, 1))

    def test_actual_irq_wait_before_abort(self):
        completion_contract(self.source)

    def test_original_early_stop_regression(self):
        self.reject("\tif (!wait_for_completion_timeout(&n->platform.stopped, timeout)) {",
                    "\tmt6878_camsv_platform_stop_async(&n->platform);\n"
                    "\tif (!wait_for_completion_timeout(&n->platform.stopped, timeout)) {")

    def test_abort_before_failure_latch_regression(self):
        self.reject("\t\tret = -ETIMEDOUT;", "\t\tmt6878_camsv_platform_stop_async(&n->platform);\n"
                    "\t\tret = -ETIMEDOUT;")

    def test_timeout_must_not_continue_to_rearm(self):
        self.reject("\t\tmt6878_camsv_platform_stop_async(&n->platform);\n\t\tgoto fail;",
                    "\t\tmt6878_camsv_platform_stop_async(&n->platform);")

    def test_late_done_must_see_direct_error(self):
        self.reject("\t\t\td->first_error = e->first_error;", "\t\t\t(void)d;")


if __name__ == "__main__":
    unittest.main()
