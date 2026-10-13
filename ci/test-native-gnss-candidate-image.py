#!/usr/bin/env python3
"""Python-only reviewed APK composition fixtures; no build, network or device."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fixtures = module("candidate_frozen_fixtures", "test-gnss-tx-image.py")
compose = module("candidate_frozen_composer", "stage-native-gnss-image.py")
candidate = module("candidate_apk_bridge", "stage-native-gnss-candidate-image.py")
CURRENT_APK = (fixtures.ROOT / "pmaports" / fixtures.parent.KERNEL / "APKBUILD").read_bytes()
PATCH_BYTES = {name: (fixtures.ROOT / "pmaports" / fixtures.parent.KERNEL / name).read_bytes()
               for name in candidate.PATCHES}
APK = fixtures.parent.KERNEL + "/APKBUILD"
CONFIG = fixtures.parent.KERNEL + "/" + fixtures.stage.CONFIG


def snapshot(tree):
    result = {}
    for path in tree.rglob("*"):
        name = str(path.relative_to(tree))
        if path.is_symlink():
            result[name] = ("symlink", os.readlink(path))
        elif path.is_dir():
            result[name] = ("directory",)
        elif path.is_file():
            result[name] = ("file", path.read_bytes())
    return result


class CandidateComposition(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.GnssTxImage(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.tree = fixture.tree
        self.report = self.tree.parent / "native.json"
        self.tx_report = self.tree.parent / "tx.json"
        patch.object(compose, "helper", return_value=fixtures.stage).start()
        # Keep actual helper hash checks, but reuse the fixtures' read-only
        # frozen Git bytes instead of invoking git during each composition.
        patch.object(candidate, "module", return_value=compose).start()
        self.populate(self.tree)

    def populate(self, tree):
        _, manifest = fixtures.stage.inputs()
        for relative in fixtures.BASE_FILES:
            path = tree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(CURRENT_APK if relative == APK else fixtures.FROZEN["pmaports/" + relative])
        for name in manifest["prerequisite_sha512"]:
            shutil.copyfile(fixtures.ROOT / "pmaports" / fixtures.parent.KERNEL / name,
                            tree / fixtures.parent.KERNEL / name)
        for name, data in PATCH_BYTES.items():
            (tree / fixtures.parent.KERNEL / name).write_bytes(data)
        (tree / "unrelated-untracked.txt").write_bytes(b"preserve unrelated data\n")

    def run_candidate(self, include_tx=True):
        return candidate.stage(self.tree, self.report, self.tx_report, include_tx)

    def refused(self, message, include_tx=True, report=None, tx_report=None):
        before = snapshot(self.tree.parent)
        with self.assertRaisesRegex(ValueError, message):
            candidate.stage(self.tree, report or self.report, tx_report or self.tx_report, include_tx)
        self.assertEqual(snapshot(self.tree.parent), before)

    def oracle(self, include_tx):
        with tempfile.TemporaryDirectory(prefix="gnss-candidate-oracle-") as directory:
            root = Path(directory).resolve()
            tree = root / "copy"
            self.populate(tree)
            (tree / APK).write_bytes(fixtures.FROZEN["pmaports/" + APK])
            native = compose.stage(tree, root / "native.json", root / "tx.json", include_tx)
            tx = json.loads((root / "tx.json").read_text()) if include_tx else None
            return native, tx, {str(path.relative_to(tree)): path.read_bytes()
                                for path in tree.rglob("*") if path.is_file()}

    def test_exact_two_deltas_and_patch_bytes_are_source_pinned(self):
        frozen = fixtures.FROZEN["pmaports/" + APK]
        self.assertEqual(candidate.digest(frozen), candidate.FROZEN_APK_SHA256)
        self.assertEqual(candidate.digest(CURRENT_APK), candidate.REVIEWED_APK_SHA256)
        restored = candidate.restore_reviewed_deltas(frozen.decode(), fixtures.parent).encode()
        self.assertEqual(restored, CURRENT_APK)
        for name, data in PATCH_BYTES.items():
            self.assertEqual(candidate.digest(data, "sha512"), candidate.PATCHES[name])
        for filename, expected in candidate.HELPERS.items():
            self.assertEqual(candidate.digest((fixtures.ROOT / "ci" / filename).read_bytes()), expected)

    def test_candidate_equals_frozen_composition_plus_only_reviewed_apk_deltas(self):
        for include_tx in (True, False):
            with self.subTest(include_tx=include_tx):
                native, tx, expected = self.oracle(include_tx)
                before = {str(p.relative_to(self.tree)): p.read_bytes()
                          for p in self.tree.rglob("*") if p.is_file()}
                result = self.run_candidate(include_tx)
                expected[APK] = candidate.restore_reviewed_deltas(expected[APK].decode(), fixtures.parent).encode()
                actual = {str(p.relative_to(self.tree)): p.read_bytes()
                          for p in self.tree.rglob("*") if p.is_file()}
                self.assertEqual(actual, expected)
                for name, data in before.items():
                    if name not in fixtures.BASE_FILES:
                        self.assertEqual(actual[name], data)
                compat = result.pop("apk_candidate_compatibility")
                self.assertEqual(compat["restored_composed_apk_sha256"], candidate.digest(actual[APK]))
                self.assertEqual(compat["reviewed_source_commit"], candidate.REVIEWED_SOURCE)
                self.assertEqual(compat["frozen_source_commit"], fixtures.parent.SOURCE)
                self.assertEqual(result["profile"], native["profile"] + candidate.PROFILE_SUFFIX)
                result["profile"] = native["profile"]
                for name in candidate.PATCHES:
                    self.assertEqual(result["changes"].pop(name), candidate.digest(PATCH_BYTES[name]))
                self.assertEqual(result, native)
                loader = module("candidate_loader", "select-native-modem-uboot.py")
                self.assertEqual(result["required_uboot_commit"], loader.COMMIT)
                self.assertEqual(result["kernel_package"], "7.2.1-r188" if include_tx else "7.2.1-r187")
                config = actual[CONFIG].decode()
                for symbol in ("CPU_IDLE", "HIBERNATION", "KEXEC_CORE", "KVM",
                               "MTK_DVFSRC", "MTK_GPUEB_MBOX"):
                    self.assertIn("# CONFIG_" + symbol + " is not set\n", config)
                for symbol in ("SUSPEND", "PM_SLEEP", "PM_SLEEP_SMP", "HOTPLUG_CPU"):
                    self.assertIn("CONFIG_" + symbol + "=y\n", config)
                recorded = json.loads(self.report.read_text())
                self.assertEqual(recorded["apk_candidate_compatibility"], compat)
                for flag in ("sleep_idle_hotplug_allowed", "modem_consumer_enabled",
                             "camera_gpu_enabled", "end_user_radio_functionality"):
                    self.assertIs(recorded[flag], False)
                if include_tx:
                    self.assertIs(recorded["shipping_activation"], False)
                    self.assertIs(recorded["gnss_activation_changed"], False)
                    recorded_tx = json.loads(self.tx_report.read_text())
                    self.assertEqual(recorded_tx.pop("apk_candidate_compatibility"), compat)
                    self.assertEqual(recorded_tx["profile"], tx["profile"] + candidate.PROFILE_SUFFIX)
                    recorded_tx["profile"] = tx["profile"]
                    self.assertEqual(recorded_tx, tx)
                    self.assertEqual(tx["parent"]["kernel_package"], "7.2.1-r184")
                    self.assertEqual(tx["source_order"], tx["prepare_order"])
                else:
                    self.assertFalse(self.tx_report.exists())
                    self.assertFalse((self.tree / fixtures.parent.KERNEL / fixtures.stage.PATCH).exists())
                # A fresh COPY is mandatory for each route; never restage.
                self.refused("already exists")
                for path in (self.report, self.tx_report):
                    if path.exists():
                        path.unlink()
                shutil.rmtree(self.tree)
                self.tree.mkdir()
                self.populate(self.tree)

    def test_arbitrary_apk_changes_and_historical_apk_are_refused(self):
        for data in (CURRENT_APK + b"\n", CURRENT_APK.replace(b"pkgrel=182\n", b"pkgrel=185\n"),
                     CURRENT_APK.replace(b"--fuzz=0", b"--fuzz=1", 1),
                     fixtures.FROZEN["pmaports/" + APK]):
            with self.subTest(data_sha=candidate.digest(data)):
                (self.tree / APK).write_bytes(data)
                self.refused("exact two reviewed deltas")
        (self.tree / APK).write_bytes(CURRENT_APK)

    def test_non_apk_frozen_inputs_cannot_be_normalized(self):
        for relative in fixtures.BASE_FILES[1:]:
            path = self.tree / relative
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.subTest(relative=relative):
                self.refused("non-APK frozen input")
            path.write_bytes(original)

    def test_actual_patch_hashes_not_just_apk_rows_are_checked(self):
        for name in candidate.PATCHES:
            path = self.tree / fixtures.parent.KERNEL / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.subTest(name=name):
                self.refused("reviewed patch hash")
            path.write_bytes(original)

    def test_prerequisite_hashes_checked_on_both_routes(self):
        _, manifest = fixtures.stage.inputs()
        name = next(iter(manifest["prerequisite_sha512"]))
        path = self.tree / fixtures.parent.KERNEL / name
        path.write_bytes(path.read_bytes() + b"\n")
        self.refused("prerequisite hash", True)
        self.refused("prerequisite hash", False)

    def test_no_ci_or_implicit_nonboolean_tx_selection(self):
        for variable in ("CI", "GITHUB_ACTIONS"):
            with patch.dict(os.environ, {variable: "false"}):
                self.refused("CI-only")
        for selection in (None, 1, "true"):
            self.refused("boolean", selection)

    def test_all_generated_outputs_remain_reserved(self):
        names = ("0180-native-md-first-off.patch", "0181-native-camera-after-md.patch",
                 "0182-native-md-first-off-board.patch", "0183-native-camera-header-parent.patch",
                 "0184-native-modem-single-ack.patch", "0187-native-modem-wakeup-sleep-veto.patch",
                 fixtures.stage.PATCH)
        for name in names:
            path = self.tree / fixtures.parent.KERNEL / name
            path.write_bytes(b"reserved\n")
            with self.subTest(name=name):
                self.refused("reserved", include_tx=False)
            path.unlink()
        (self.tree / candidate.EVIDENCE).mkdir()
        self.refused("evidence")

    def test_report_alias_overlap_and_bad_parent_fail_before_writes(self):
        self.refused("distinct", tx_report=self.report)
        self.refused("overlapping", tx_report=self.report / "child.json")
        self.refused("overlaps", report=self.tree / fixtures.parent.KERNEL / "new-report.json")
        self.refused("overlaps", report=self.tree / candidate.EVIDENCE / "new-report.json")
        blocker = self.tree.parent / "blocker"
        blocker.write_bytes(b"not a directory\n")
        self.refused("not a directory", report=blocker / "report.json")

    def test_existing_report_even_without_tx_is_not_overwritten(self):
        for path in (self.report, self.tx_report):
            path.write_bytes(b"existing report\n")
            self.refused("already exists", include_tx=False)
            path.unlink()

    def test_symlink_input_output_and_hardlink_inputs_refused(self):
        path = self.tree / APK
        saved = self.tree.parent / "saved-apk"
        path.rename(saved)
        path.symlink_to(saved)
        self.refused("symlinked input")
        path.unlink()
        os.link(saved, path)
        self.refused("independent COPY")
        path.unlink()
        saved.rename(path)
        self.report.symlink_to(self.tree.parent / "absent")
        self.refused("symlink")

    def test_shipping_and_source_paths_remain_refused(self):
        before = snapshot(self.tree.parent)
        for tree in (fixtures.ROOT, fixtures.ROOT / "pmaports", fixtures.ROOT / "ci",
                     fixtures.ROOT.parent):
            with self.subTest(tree=tree), self.assertRaisesRegex(ValueError, "source inputs"):
                candidate.stage(tree, self.report, self.tx_report, True)
        self.assertEqual(snapshot(self.tree.parent), before)

    def test_helper_hash_drift_is_refused(self):
        for name in candidate.HELPERS:
            with patch.dict(candidate.HELPERS, {name: "0" * 64}):
                self.refused("helper changed")

    def test_late_composition_failure_cannot_partially_stage_target(self):
        real_stage = compose.stage

        def fail_after_composition(*args):
            real_stage(*args)
            raise ValueError("late composition failure")

        with patch.object(compose, "stage", side_effect=fail_after_composition):
            self.refused("late composition failure")

    def test_unexpected_composer_output_cannot_reach_target(self):
        real_stage = compose.stage

        def extra_output(tree, *args):
            result = real_stage(tree, *args)
            (tree / "unexpected.txt").write_bytes(b"not authorized\n")
            return result

        with patch.object(compose, "stage", side_effect=extra_output):
            self.refused("unexpected composer output")

    def test_read_set_rechecked_after_preparation(self):
        real_stage = compose.stage
        path = self.tree / fixtures.parent.KERNEL / candidate.GPUEB
        modified = path.read_bytes() + b"external writer\n"
        before = snapshot(self.tree.parent)

        def input_drift(*args):
            result = real_stage(*args)
            path.write_bytes(modified)
            return result

        with patch.object(compose, "stage", side_effect=input_drift), \
                self.assertRaisesRegex(ValueError, "input changed during preparation"):
            self.run_candidate()
        expected = dict(before)
        expected[str(path.relative_to(self.tree.parent))] = ("file", modified)
        self.assertEqual(snapshot(self.tree.parent), expected)

    def test_actual_ci_copy_and_out_reports_layout(self):
        work = self.tree.parent / "work"
        new_tree = work / "upstream/pmaports"
        self.populate(new_tree)
        with patch.object(fixtures.stage, "ROOT", work), \
                patch.dict(os.environ, {"TETRIS_NATIVE_SOURCE_TREE": str(work / "out/native-source")}):
            result = candidate.stage(new_tree, work / "out/native.json", work / "out/tx.json", True)
        self.assertEqual(result["kernel_package"], "7.2.1-r188")
        self.assertTrue((work / "out/tx.json").is_file())


if __name__ == "__main__":
    unittest.main()
