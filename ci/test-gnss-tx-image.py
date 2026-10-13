#!/usr/bin/env python3
"""Deterministic Python-only package-copy tests; no compiler, CI or hardware."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gnss_tx_stage", ROOT / "ci/stage-gnss-tx-image.py")
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
parent = stage.parent_stage()
real_parent_stage = stage.parent_stage
CI = {"CI": "true", "GITHUB_ACTIONS": "true"}
BASE_FILES = (parent.KERNEL + "/APKBUILD", parent.KERNEL + "/" + stage.CONFIG,
              parent.DEVICE + "/APKBUILD", parent.DEVICE + "/deviceinfo",
              parent.DEVICE + "/boot_image.its")
# Load historical fixtures once using read-only git show, then prohibit all
# external execution during tests (including parent reconstruction).
FROZEN_PATHS = tuple("pmaports/" + name for name in BASE_FILES) + tuple(parent.INPUTS) + (
    "patches/modem/drafts/runtime-hif-dt/mt6878-nothing-tetris-ccci-hif-resources.dts",
    "patches/camera-camisp/power/mt6878-cam-power.h",
    "patches/modem/md-pm-integration/mt6878-modem-adopt.h",
)
FROZEN = {name: parent.frozen(name) for name in FROZEN_PATHS}


def snapshot(tree):
    return {str(path.relative_to(tree)): stage.digest(path.read_bytes())
            for path in tree.rglob("*") if path.is_file()}


class GnssTxImage(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="gnss-tx-static-test-")
        self.addCleanup(self.directory.cleanup)
        self.tree = Path(self.directory.name).resolve() / "copy"
        self.tree.mkdir()
        self.report = self.tree / "evidence/candidate.json"
        self.parent_report = self.tree / "evidence/parent.json"
        self.addCleanup(patch.stopall)
        patch.object(stage, "parent_stage", return_value=parent).start()
        patch.object(parent, "frozen", side_effect=lambda path: FROZEN[path]).start()
        patch("subprocess.run", side_effect=AssertionError("external execution forbidden")).start()
        patch("subprocess.check_output", side_effect=AssertionError("external execution forbidden")).start()
        patch.dict(os.environ, CI | {"TETRIS_NATIVE_SOURCE_TREE": str(ROOT)}).start()

    def prepare(self):
        relative_files = BASE_FILES
        _, manifest = stage.inputs()
        relative_files += tuple(parent.KERNEL + "/" + name
                                for name in manifest["prerequisite_sha512"])
        for relative in relative_files:
            destination = self.tree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative in BASE_FILES:
                destination.write_bytes(FROZEN["pmaports/" + relative])
            else:
                shutil.copyfile(ROOT / "pmaports" / relative, destination)
        (self.tree / "unrelated-untracked.txt").write_text("preserve me\n")
        parent.stage(self.tree, self.parent_report)
        return self.tree / parent.KERNEL / "APKBUILD"

    def candidate(self, **options):
        return stage.stage(self.tree, self.parent_report, self.report,
                           **({"opt_in": True, "pkgrel": 186} | options))

    def refused_unchanged(self, message=None, **options):
        before = snapshot(self.tree)
        with self.assertRaisesRegex(ValueError, message or ".*"):
            self.candidate(**options)
        self.assertEqual(snapshot(self.tree), before)

    def test_exact_source_identity_and_historical_evidence(self):
        data, manifest = stage.inputs()
        self.assertEqual(stage.digest(data, "sha512"), stage.PATCH_SHA512)
        self.assertEqual(list(manifest["prerequisite_sha512"])[0][:4], "1001")
        self.assertEqual([name[:4] for name in manifest["prerequisite_sha512"]],
                         [str(n) for n in range(1001, 1009)])
        self.assertEqual(manifest["full_module_validation"]["run"], 38357565018)
        self.assertEqual(manifest["full_module_validation"]["commit"],
                         "f27228d3f101690e9f6592efa4c777b4b936363c")
        self.assertIn("21.1.2", manifest["full_module_validation"]["compiler"])
        self.assertIn("21.1.8", manifest["full_module_validation"]["compiler"])
        self.assertFalse(manifest["full_module_validation"]["phone_abi_compatible"])
        self.assertFalse(manifest["full_module_validation"]["hardware_tested"])

    def test_default_and_local_calls_refused_without_writes(self):
        self.refused_unchanged("explicit", opt_in=False)
        with self.assertRaisesRegex(ValueError, "explicit"):
            stage.stage(self.tree, self.parent_report, self.report)
        with patch.dict(os.environ, {"CI": "false"}):
            self.refused_unchanged("CI-only")
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
            self.refused_unchanged("CI-only")

    def test_shipping_and_frozen_source_paths_refused(self):
        for tree in (ROOT, ROOT / "pmaports", ROOT / "worktrees/candidate", ROOT.parent):
            with self.subTest(tree=tree), self.assertRaisesRegex(ValueError, "source inputs"):
                stage.stage(tree, tree / "parent.json", tree / "candidate.json", True, 186)
        with patch.dict(os.environ, {"TETRIS_NATIVE_SOURCE_TREE": str(self.tree)}):
            self.refused_unchanged("source inputs")

    def test_separate_revision_required(self):
        for revision in (None, True, "186", 182, 184, 185, -1):
            with self.subTest(revision=revision):
                self.refused_unchanged("pkgrel", pkgrel=revision)

    def test_exact_patch_and_only_three_candidate_outputs(self):
        apk_path = self.prepare()
        original = apk_path.read_text()
        before = snapshot(self.tree)
        result = self.candidate()
        after = snapshot(self.tree)
        changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
        self.assertEqual(changed, {parent.KERNEL + "/APKBUILD", parent.KERNEL + "/" + stage.PATCH,
                                   "evidence/candidate.json"})
        self.assertEqual((apk_path.parent / stage.PATCH).read_bytes(), (stage.HERE / stage.PATCH).read_bytes())
        revised = apk_path.read_text()
        self.assertEqual(revised.count("\t" + stage.PATCH + "\n"), 1)
        self.assertEqual(revised.count('< "$srcdir"/' + stage.PATCH + "\n"), 1)
        self.assertIn('\tpatch --fuzz=0 -p1 -d "$_connmods_dir" \\\n'
                      '\t\t< "$srcdir"/' + stage.PATCH + "\n", revised)
        restored = revised.replace("\t" + stage.PATCH + "\n", "", 1)
        restored = restored.replace('\tpatch --fuzz=0 -p1 -d "$_connmods_dir" \\\n'
                                    '\t\t< "$srcdir"/' + stage.PATCH + "\n", "", 1)
        self.assertEqual(restored.replace("pkgrel=186\n", "pkgrel=184\n", 1), original)
        self.assertEqual(result["source_order"], result["prepare_order"])
        self.assertEqual([name[:4] for name in result["source_order"]],
                         [str(n) for n in range(1001, 1010)])
        self.assertEqual(result["parent"]["kernel_package"], "7.2.1-r184")
        self.assertEqual(result["profile"], stage.PROFILE)
        self.assertEqual(result["apkbuild_before_sha256"], stage.digest(original.encode()))
        self.assertEqual(result["apkbuild_staged_sha256"], stage.digest(revised.encode()))
        self.assertEqual(json.loads(self.report.read_text()), result)
        for flag in ("matched_image_built", "phone_abi_compatible", "hardware_tested",
                     "gnss_activation_changed", "shipping_activation", "end_user_radio_functionality",
                     "modem_consumer_enabled"):
            self.assertIs(result[flag], False, flag)
        for flag in ("sleep_idle_hotplug_allowed", "camera_gpu_enabled", "modem_consumer_enabled"):
            self.assertIs(result["parent"][flag], False, flag)
        self.assertIn("pending pmbootstrap checksum", result["checksums"])
        self.assertIn("has not been built or executed", result["validation"])
        self.refused_unchanged("already exists")

    def test_repeated_copies_are_byte_deterministic(self):
        self.prepare()
        self.candidate()
        expected = snapshot(self.tree)
        other = Path(self.directory.name).resolve() / "second-copy"
        self.tree = other
        self.tree.mkdir()
        self.report = other / "evidence/candidate.json"
        self.parent_report = other / "evidence/parent.json"
        self.prepare()
        self.candidate()
        self.assertEqual(snapshot(other), expected)

    def test_existing_parent_pattern_with_current_package_inputs(self):
        self.prepare()
        for relative in BASE_FILES:
            shutil.copyfile(ROOT / "pmaports" / relative, self.tree / relative)
        parent.stage(self.tree, self.parent_report)
        self.assertEqual(self.candidate()["parent"]["kernel_package"], "7.2.1-r184")

    def test_each_prerequisite_hash_is_enforced(self):
        self.prepare()
        _, manifest = stage.inputs()
        for name in manifest["prerequisite_sha512"]:
            path = self.tree / parent.KERNEL / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n# altered\n")
            with self.subTest(name=name):
                self.refused_unchanged("prerequisite hash")
            path.write_bytes(original)

    def test_exact_patch_and_manifest_drift_fail_closed(self):
        copy = Path(self.directory.name) / "patch-inputs"
        copy.mkdir()
        for name in ("STAGING.json", stage.PATCH):
            shutil.copyfile(stage.HERE / name, copy / name)
        self.prepare()
        with patch.object(stage, "HERE", copy):
            patch_path = copy / stage.PATCH
            patch_path.write_bytes(patch_path.read_bytes() + b"\n")
            self.refused_unchanged("patch hash")
            manifest_path = copy / "STAGING.json"
            data = json.loads(manifest_path.read_text())
            data["patch_sha512"] = stage.digest(patch_path.read_bytes(), "sha512")
            manifest_path.write_text(json.dumps(data))
            self.refused_unchanged("source manifest")

    def test_frozen_parent_helper_hash_is_enforced(self):
        with patch.object(stage, "PARENT_SHA256", "0" * 64), \
                self.assertRaisesRegex(ValueError, "r184 helper changed"):
            real_parent_stage()

    def test_parent_manifest_and_package_drift_refused(self):
        apk = self.prepare()
        paths = [apk, apk.parent / stage.CONFIG, apk.parent / "0184-native-modem-single-ack.patch",
                 self.tree / parent.DEVICE / "deviceinfo", self.tree / parent.DEVICE / "boot_image.its",
                 self.tree / parent.DEVICE / "APKBUILD"]
        for path in paths:
            original = path.read_bytes()
            path.write_bytes(original + b"\n# drift\n")
            with self.subTest(path=path.name):
                self.refused_unchanged("r184 package input changed")
            path.write_bytes(original)
        raw = self.parent_report.read_bytes()
        for key, value in (("kernel_package", "7.2.1-r185"), ("source_commit", "wrong"),
                           ("modem_consumer_enabled", True), ("modem_consumer_enabled", 0),
                           ("changes", {})):
            metadata = json.loads(raw)
            metadata[key] = value
            self.parent_report.write_text(json.dumps(metadata))
            with self.subTest(key=key):
                self.refused_unchanged("parent manifest")
        self.parent_report.write_bytes(raw)

    def test_source_and_prepare_order_negative_controls(self):
        apk = self.prepare().read_text()
        _, manifest = stage.inputs()
        names = list(manifest["prerequisite_sha512"])
        stage.ordered_stack(apk, names)
        for changed in (apk.replace("\t" + names[0] + "\n", ""),
                        apk.replace("\t" + names[0] + "\n", "\t" + names[1] + "\n"),
                        apk.replace('< "$srcdir"/' + names[0], '< "$srcdir"/' + names[1]),
                        apk.replace("\t" + names[-1] + "\n", "\t" + stage.PATCH + "\n"),
                        apk.replace("\t" + names[0] + "\n", ("\t" + names[0] + "\n") * 2),
                        apk.replace('source="\n', 'unreviewed_source="\n', 1)):
            with self.subTest(change=changed[:40]), self.assertRaises(ValueError):
                stage.ordered_stack(changed, names)
        altered = apk.replace(names[0], "PLACEHOLDER").replace(names[1], names[0]).replace("PLACEHOLDER", names[1])
        with self.assertRaises(ValueError):
            stage.ordered_stack(altered, names)

    def test_collisions_and_report_locations_refused(self):
        apk = self.prepare()
        for path in (self.parent_report, apk, apk.parent / "new-report.json",
                     self.tree / parent.DEVICE / "new-report.json",
                     Path(self.directory.name) / "outside.json"):
            original = self.report
            self.report = path
            with self.subTest(path=path):
                self.refused_unchanged()
            self.report = original
        destination = apk.parent / stage.PATCH
        destination.write_text("existing unrelated bytes\n")
        self.refused_unchanged("output exists")

    def test_report_parent_file_refused_before_package_writes(self):
        self.prepare()
        self.report = self.parent_report / "new-report.json"
        self.refused_unchanged("parent is not a directory")

    def test_hardlinked_apkbuild_refused_before_any_write(self):
        apk = self.prepare()
        outside = Path(self.directory.name) / "shared-apkbuild"
        original = apk.read_bytes()
        apk.rename(outside)
        os.link(outside, apk)
        self.refused_unchanged("independent COPY")
        self.assertEqual(outside.read_bytes(), original)

    def test_symlinked_inputs_and_outputs_refused(self):
        apk = self.prepare()
        outside = Path(self.directory.name) / "outside"
        outside.mkdir()
        for path in (apk, self.parent_report, apk.parent / stage.PATCH, self.report):
            existed = path.exists()
            original = path.read_bytes() if existed else None
            target = outside / path.name
            target.write_bytes(original or b"outside sentinel\n")
            if existed:
                path.unlink()
            path.symlink_to(target)
            with self.subTest(path=path):
                self.refused_unchanged()
            self.assertEqual(target.read_bytes(), original or b"outside sentinel\n")
            path.unlink()
            if existed:
                path.write_bytes(original)
        alias = self.tree / "report-alias"
        alias.symlink_to(outside, target_is_directory=True)
        self.report = alias / "new.json"
        self.refused_unchanged("symlinks|source inputs")
        self.assertFalse((outside / "new.json").exists())

    def test_cli_requires_explicit_opt_in(self):
        self.prepare()
        arguments = ["stage-gnss-tx-image.py", "--pmaports", str(self.tree),
                     "--parent-report", str(self.parent_report), "--report", str(self.report),
                     "--candidate-pkgrel", "190"]
        before = snapshot(self.tree)
        with patch.object(sys, "argv", arguments), self.assertRaisesRegex(ValueError, "explicit"):
            stage.main()
        self.assertEqual(snapshot(self.tree), before)
        with patch.object(sys, "argv", arguments + ["--include-exact1009"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            stage.main()
        self.assertEqual(json.loads(output.getvalue())["kernel_package"], "7.2.1-r190")


if __name__ == "__main__":
    unittest.main()
