#!/usr/bin/env python3
"""Source regressions for reviewed power, lock order and lifetime fixes."""
import unittest

from check import HERE, cold_power_contract, joint_lock_contract


class ColdJointContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cold = (HERE / "mt6878-camera-cold-reset.c").read_text()
        cls.joint = (HERE / "mt6878-camera-joint-reset.c").read_text()

    def rejects(self, checker, source, old, new):
        self.assertIn(old, source)
        with self.assertRaises((AssertionError, ValueError, IndexError)):
            checker(source.replace(old, new, 1))

    def test_actual_contracts(self):
        cold_power_contract(self.cold)
        joint_lock_contract(self.joint)

    def test_unused_clock_regression(self):
        self.rejects(cold_power_contract, self.cold, "i < 3", "i < c->num_clocks")

    def test_unselected_csi_regression(self):
        self.rejects(cold_power_contract, self.cold, "c->clocks[3 + port].clk", "c->clocks[3].clk")

    def test_shared_voltage_upper_vote_regression(self):
        self.rejects(cold_power_contract, self.cold,
                     "return voltage >= c->dvfs[5] ? 0 : -ERANGE;",
                     "return voltage >= c->dvfs[5] && voltage <= c->dvfs[6] ? 0 : -ERANGE;")

    def test_below_required_voltage_not_accepted(self):
        self.rejects(cold_power_contract, self.cold,
                     "return voltage >= c->dvfs[5] ? 0 : -ERANGE;", "return 0;")

    def test_sensor_before_core_regression(self):
        old = ("mutex_lock(&n->controller.core);\n\tmutex_lock(&n->direct.lock);\n"
               "\tsensor_state = v4l2_subdev_lock_and_get_active_state(n->platform.sensor);")
        new = ("sensor_state = v4l2_subdev_lock_and_get_active_state(n->platform.sensor);\n"
               "\tmutex_lock(&n->controller.core);\n\tmutex_lock(&n->direct.lock);")
        self.rejects(joint_lock_contract, self.joint, old, new)

    def test_missing_locked_bound_revalidation(self):
        self.rejects(joint_lock_contract, self.joint, "!n->bound || p->retired", "p->retired")

    def test_missing_supplier_identity_revalidation(self):
        self.rejects(joint_lock_contract, self.joint, "p->cam_main != supplier", "false")

    def test_unlocked_supplier_pin_regression(self):
        old = ("\tmutex_lock(&n->lock);\n\tret = joint_bound(n, NULL);\n"
               "\tif (!ret)\n\t\t*supplier = get_device(n->platform.cam_main);")
        new = ("\t*supplier = get_device(n->platform.cam_main);\n"
               "\tmutex_lock(&n->lock);\n\tret = joint_bound(n, NULL);")
        self.rejects(joint_lock_contract, self.joint, old, new)

    def test_zero_owner_must_not_lock_uninitialized_mutex(self):
        old = "if (!n || !supplier || !READ_ONCE(n->bound))"
        self.rejects(joint_lock_contract, self.joint, old, "if (!n || !supplier)")


if __name__ == "__main__":
    unittest.main()
