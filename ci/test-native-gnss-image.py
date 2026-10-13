#!/usr/bin/env python3
"""Static composition tests using the pinned package fixtures; no C execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fixtures = module("tx_fixtures", "test-gnss-tx-image.py")
compose = module("tx_compose", "stage-native-gnss-image.py")


class Composition(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.GnssTxImage(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.tree = fixture.tree
        fixture.prepare()
        for relative in fixtures.BASE_FILES:
            (self.tree / relative).write_bytes(fixtures.FROZEN["pmaports/" + relative])
        self.report = self.tree.parent / "native.json"
        self.tx_report = self.tree.parent / "tx.json"
        self.addCleanup(patch.stopall)
        patch.object(compose, "helper", return_value=fixtures.stage).start()

    def test_matched_profile_and_real_package_revision(self):
        result = compose.stage(self.tree, self.report, self.tx_report)
        apk = (self.tree / fixtures.parent.KERNEL / "APKBUILD").read_text()
        self.assertIn("pkgrel=188\n", apk)
        self.assertEqual(result["kernel_package"], "7.2.1-r188")
        self.assertEqual(result["profile"], fixtures.stage.PROFILE + "-wakeup")
        self.assertEqual(result, json.loads(self.report.read_text()))
        self.assertEqual(result["gnss_tx_patch_sha512"], fixtures.stage.PATCH_SHA512)
        self.assertIn(fixtures.stage.PATCH, result["changes"])
        tx = json.loads(self.tx_report.read_text())
        self.assertEqual(tx["parent"]["kernel_package"], "7.2.1-r184")
        self.assertEqual(tx["kernel_package"], result["kernel_package"])
        self.assertTrue(result["wakeup_source_apis_enabled"])
        config = (self.tree / fixtures.parent.KERNEL / fixtures.stage.CONFIG).read_text()
        for symbol in ("SUSPEND", "PM_SLEEP", "PM_SLEEP_SMP"):
            self.assertIn("CONFIG_" + symbol + "=y\n", config)
        for symbol in ("CPU_IDLE", "HOTPLUG_CPU", "HIBERNATION", "KEXEC_CORE"):
            self.assertIn("# CONFIG_" + symbol + " is not set\n", config)
        for flag in ("gnss_activation_changed", "shipping_activation",
                     "camera_gpu_enabled", "modem_consumer_enabled",
                     "end_user_radio_functionality", "sleep_idle_hotplug_allowed"):
            self.assertIs(result[flag], False)

    def test_existing_outputs_fail_before_package_writes(self):
        self.report.write_text("existing\n")
        before = fixtures.snapshot(self.tree)
        with self.assertRaises(ValueError):
            compose.stage(self.tree, self.report, self.tx_report)
        self.assertEqual(fixtures.snapshot(self.tree), before)

    def test_aliasing_outputs_fail_before_package_writes(self):
        before = fixtures.snapshot(self.tree)
        with self.assertRaisesRegex(ValueError, "distinct"):
            compose.stage(self.tree, self.report, self.report)
        self.assertEqual(fixtures.snapshot(self.tree), before)

    def test_workflow_keeps_old_profile_and_separate_candidate_artifact(self):
        workflow = (fixtures.ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("gnss_tx_image:\n", workflow)
        self.assertIn("if [ '${{ inputs.gnss_tx_image }}' = true ]; then", workflow)
        self.assertIn("test '${{ inputs.native_modem_first_off }}' = true", workflow)
        self.assertIn("else\n            python3 -B ci/stage-native-gnss-image.py", workflow)
        self.assertIn("nothing-tetris-native-md-gnss-tx-images", workflow)
        self.assertIn("/work/out/gnss-tx-image-profile.json", workflow)
        self.assertIn('["profile"]', workflow)

    def test_wakeup_only_revision_is_distinct_and_has_no_tx_patch(self):
        result = compose.stage(self.tree, self.report, self.tx_report, include_tx=False)
        self.assertEqual(result["kernel_package"], "7.2.1-r187")
        self.assertEqual(result["profile"], "native-md-first-off-wakeup-diagnostic")
        self.assertNotIn(fixtures.stage.PATCH, result["changes"])
        self.assertFalse(self.tx_report.exists())

    def test_veto_registration_and_revalidation_precede_first_write(self):
        wakeup = module("wakeup_test", "stage-native-wakeup-image.py")
        before, after = wakeup.patched_header(fixtures.parent)
        self.assertNotIn("register_pm_notifier", before)
        begin = after.index("static int mt6878_md_first_off(struct scpsys_domain")
        transaction = after[begin:after.index("static void mt6878_md_first_off_publication_fault", begin)]
        positions = [transaction.index(token) for token in (
            "mutex_trylock(&system_transition_mutex)",
            "mt6878_md_adopt_revalidate(pd, owner)",
            "register_pm_notifier(&mt6878_md_sleep_notifier)",
            "owner->supplier = get_device", "regmap_write(map,")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("if (transition_locked)\n\t\tmutex_unlock(&system_transition_mutex);", transaction)
        self.assertNotIn("unregister_pm_notifier", after)
        for event in ("PM_SUSPEND_PREPARE", "PM_HIBERNATION_PREPARE", "PM_RESTORE_PREPARE"):
            self.assertIn(event, after)
        self.assertIn("return notifier_from_errno(-EBUSY);", after)
        self.assertIn("!IS_ENABLED(CONFIG_PM_SLEEP)", after)


class WakeupPatchApplication(unittest.TestCase):
    def test_exact_kernel_header_patch_applies_without_fuzz(self):
        wakeup = module("wakeup_patch", "stage-native-wakeup-image.py")
        parent = fixtures.real_parent_stage()
        before, after = wakeup.patched_header(parent)
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            header = tree / wakeup.HEADER
            header.parent.mkdir(parents=True)
            header.write_text(before)
            data = wakeup.patch_text(parent).encode()
            for check in (True, False):
                subprocess.run(["git", "apply", "--whitespace=error"] +
                               (["--check"] if check else []) + ["-"],
                               cwd=tree, input=data, check=True, capture_output=True)
            self.assertEqual(header.read_text(), after)


if __name__ == "__main__":
    unittest.main()
