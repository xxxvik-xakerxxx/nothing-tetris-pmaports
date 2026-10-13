#!/usr/bin/env python3
"""Static package composition and actual pinned1001..1010 patch application.

No native compilation, network, CI dispatch or device access. Actual patch tests
use TETRIS_MODULES_TREE (CI's out/lna-kernel-source), or the existing local Git
object tree. Composition fixtures prohibit external processes after loading the
historical Git bytes. No shipping package, frozen helper or source is edited.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


old = module("session_candidate_fixtures", ROOT / "ci/test-native-gnss-candidate-image.py")
stage = module("session_image_stage", ROOT / "ci/stage-native-session-image.py")
g = module("session_image_source_generator", ROOT / "patches/gnss/native-session/generate.py")
APK = old.APK
snapshot = old.snapshot


class SessionComposition(unittest.TestCase):
    def setUp(self):
        fixture = old.CandidateComposition(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.tree = fixture.tree
        self.report = self.tree.parent / "session-native.json"
        self.tx_report = self.tree.parent / "session-tx.json"
        self.session_report = self.tree.parent / "session.json"
        patch.object(stage, "module", return_value=old.candidate).start()

    def candidate(self, **options):
        return stage.stage(self.tree, self.report, self.tx_report, self.session_report,
                           **({"opt_in": True} | options))

    def refused(self, reason, **options):
        before = snapshot(self.tree.parent)
        with self.assertRaisesRegex(ValueError, reason):
            self.candidate(**options)
        self.assertEqual(snapshot(self.tree.parent), before)

    def parent_oracle(self):
        with tempfile.TemporaryDirectory(prefix="session-parent-oracle-") as directory:
            root = Path(directory).resolve()
            tree = root / "copy"
            self.fixture.populate(tree)
            native = old.candidate.stage(tree, root / "native.json", root / "tx.json", True)
            return native, (root / "native.json").read_bytes(), (root / "tx.json").read_bytes(), {
                str(path.relative_to(tree)): path.read_bytes() for path in tree.rglob("*") if path.is_file()}

    def test_actual_pinned_assets_and_frozen_helpers(self):
        bridge, gnss, manifest, data, readset = stage.assets()
        self.assertIs(bridge, old.candidate)
        self.assertIs(gnss, old.fixtures.stage)
        self.assertEqual(stage.digest(data, "sha512"), stage.PATCH_SHA512)
        self.assertEqual(stage.digest((stage.SESSION / "STAGING.json").read_bytes()), stage.MANIFEST_SHA256)
        self.assertEqual(manifest["connectivity_commit"], stage.PIN)
        for path, raw in readset.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(set(manifest["frozen_api_sha256"]), {"session.c", "session.h", "gpsdl_v051_session.h"})

    def test_exact_delta_over_frozen_reviewed_1009_and_only_expected_outputs(self):
        parent, parent_raw, tx_raw, expected = self.parent_oracle()
        original_apk = expected[APK]
        result = self.candidate()
        actual = {str(p.relative_to(self.tree)): p.read_bytes() for p in self.tree.rglob("*") if p.is_file()}
        session = result["native_session"]
        revised = actual[APK].decode()
        self.assertEqual(revised.count("\t" + stage.PATCH + "\n"), 1)
        self.assertEqual(revised.count('< "$srcdir"/' + stage.PATCH + "\n"), 1)
        restored = revised.replace("\t" + stage.PATCH + "\n", "", 1)
        restored = restored.replace('\tpatch --fuzz=0 -p1 -d "$_connmods_dir" \\\n'
                                    '\t\t< "$srcdir"/' + stage.PATCH + '\n', '', 1)
        restored = restored.replace(stage.PATCH_SHA512 + "  " + stage.PATCH + "\n", "", 1)
        self.assertEqual(restored.replace("pkgrel=189\n", "pkgrel=188\n", 1).encode(), original_apk)
        expected[APK] = actual[APK]
        expected[old.fixtures.parent.KERNEL + "/" + stage.PATCH] = (stage.SESSION / stage.PATCH).read_bytes()
        expected[stage.EVIDENCE + "/native-session-parent.json"] = parent_raw
        expected[stage.EVIDENCE + "/gnss-session.json"] = self.session_report.read_bytes()
        self.assertEqual(actual, expected)
        self.assertEqual(self.tx_report.read_bytes(), tx_raw)
        self.assertEqual(json.loads(self.report.read_bytes()), result)
        self.assertEqual(json.loads(self.session_report.read_bytes()), session)
        self.assertEqual(session["parent_native_report_sha256"], stage.digest(parent_raw))
        self.assertEqual(session["parent_tx_report_sha256"], stage.digest(tx_raw))
        self.assertEqual(session["apkbuild_before_sha256"], stage.digest(original_apk))
        self.assertEqual(session["apkbuild_staged_sha256"], stage.digest(actual[APK]))
        self.assertEqual(result["kernel_package"], "7.2.1-r189")
        self.assertEqual(result["profile"], parent["profile"] + stage.PROFILE_SUFFIX)
        self.assertEqual(result["artifact"], stage.ARTIFACT)
        self.assertEqual(result["required_uboot_commit"], parent["required_uboot_commit"])
        self.assertEqual(session["module"], "connectivity/gps/data_link/plat/v051/gps_drv_dl_v051.ko")
        self.assertEqual(session["source_order"], session["prepare_order"])
        self.assertEqual([n[:4] for n in session["source_order"]], [str(n) for n in range(1001, 1011)])
        for flag in ("shipping_activation", "gnss_activation_changed", "end_user_radio_functionality",
                     "matched_image_built", "phone_abi_compatible", "hardware_tested",
                     "navigation_validated", "normal_close_validated", "physical_stop_validated"):
            self.assertIs(session[flag], False, flag)
        for flag in ("sleep_idle_hotplug_allowed", "modem_consumer_enabled", "camera_gpu_enabled"):
            self.assertEqual(result[flag], parent[flag])
            self.assertIs(result[flag], False)
        self.assertIn("pmbootstrap checksum", session["checksums"])
        stripped = dict(result)
        for name in ("native_session", "artifact"):
            stripped.pop(name)
        stripped["profile"] = parent["profile"]
        stripped["kernel_package"] = parent["kernel_package"]
        stripped["changes"] = dict(stripped["changes"])
        stripped["changes"].pop(stage.PATCH)
        self.assertEqual(stripped, parent)
        self.refused("already exists")

    def test_explicit_future_revision_and_determinism(self):
        self.candidate(pkgrel=190)
        self.assertIn("pkgrel=190\n", (self.tree / APK).read_text())
        first = snapshot(self.tree)
        first_reports = [p.read_bytes() for p in (self.report, self.tx_report, self.session_report)]
        other = self.tree.parent / "other-copy"
        self.fixture.populate(other)
        result = stage.stage(other, self.tree.parent / "second-native.json", self.tree.parent / "second-tx.json",
                             self.tree.parent / "second-session.json", True, 190)
        self.assertEqual(snapshot(other), first)
        self.assertEqual(result["kernel_package"], "7.2.1-r190")
        for expected, path in zip(first_reports, (self.tree.parent / "second-native.json",
                                 self.tree.parent / "second-tx.json", self.tree.parent / "second-session.json")):
            self.assertEqual(path.read_bytes(), expected)

    def test_default_nonboolean_and_non_ci_admission(self):
        for selection in (False, None, 1, "true"):
            self.refused("explicit", opt_in=selection)
        for name in ("CI", "GITHUB_ACTIONS"):
            with patch.dict(os.environ, {name: "false"}):
                self.refused("CI-only")

    def test_invalid_revision_is_refused_before_writes(self):
        for revision in (True, False, "189", 0, 182, 184, 185, 187, 188, -1, 2147483648):
            with self.subTest(revision=revision):
                self.refused("pkgrel", pkgrel=revision)

    def test_all_outputs_and_1010_slot_are_reserved(self):
        for name in ("0180-native-md-first-off.patch", "0187-native-modem-wakeup-sleep-veto.patch",
                     old.fixtures.stage.PATCH, stage.PATCH, "1010-other-candidate.patch.vendor"):
            path = self.tree / old.fixtures.parent.KERNEL / name
            path.write_bytes(b"reserved\n")
            with self.subTest(name=name):
                self.refused("reserved|already exists")
            path.unlink()
        (self.tree / stage.EVIDENCE).mkdir()
        self.refused("evidence")

    def test_reports_alias_ancestor_package_evidence_and_bad_parent(self):
        for attr, target in (("session_report", self.report), ("session_report", self.tx_report),
                             ("session_report", self.report / "child.json"),
                             ("tx_report", self.session_report / "child.json"),
                             ("report", self.tree / old.fixtures.parent.KERNEL / "new.json"),
                             ("session_report", self.tree / stage.EVIDENCE / "new.json")):
            saved = getattr(self, attr)
            setattr(self, attr, target)
            with self.subTest(attr=attr, target=target):
                self.refused("distinct|overlapping|overlaps")
            setattr(self, attr, saved)
        blocker = self.tree.parent / "not-dir"
        blocker.write_bytes(b"not a directory\n")
        self.session_report = blocker / "report.json"
        self.refused("not a directory")

    def test_existing_each_report_is_never_overwritten(self):
        for path in (self.report, self.tx_report, self.session_report):
            path.write_bytes(b"retain report\n")
            self.refused("already exists")
            path.unlink()

    def test_input_output_and_directory_symlinks_and_hardlinks(self):
        path = self.tree / APK
        saved = self.tree.parent / "saved-apk"
        path.rename(saved)
        path.symlink_to(saved)
        self.refused("symlinked")
        path.unlink()
        os.link(saved, path)
        self.refused("independent COPY")
        path.unlink()
        saved.rename(path)
        self.session_report.symlink_to(self.tree.parent / "absent")
        self.refused("symlink")
        self.session_report.unlink()
        directory = self.tree / old.fixtures.parent.KERNEL
        alternate = self.tree.parent / "saved-package"
        directory.rename(alternate)
        directory.symlink_to(alternate, target_is_directory=True)
        self.refused("symlink|unsafe")

    def test_source_and_current_package_trees_are_not_targets(self):
        before = snapshot(self.tree.parent)
        for tree in (ROOT, ROOT / "pmaports", ROOT / "ci", ROOT.parent):
            with self.subTest(tree=tree), self.assertRaisesRegex(ValueError, "source inputs"):
                stage.stage(tree, self.report, self.tx_report, self.session_report, True)
        self.assertEqual(snapshot(self.tree.parent), before)

    def test_copy_readset_hashes_and_exact_frozen_apk_contract(self):
        for relative in (APK, old.CONFIG, old.fixtures.BASE_FILES[2],
                         old.fixtures.parent.KERNEL + "/" + old.candidate.GPUEB,
                         old.fixtures.parent.KERNEL + "/" + next(iter(old.fixtures.stage.inputs()[1]["prerequisite_sha512"]))):
            path = self.tree / relative
            raw = path.read_bytes()
            path.write_bytes(raw + b"drift\n")
            with self.subTest(relative=relative):
                self.refused("exact two reviewed|frozen input|patch hash|prerequisite hash")
            path.write_bytes(raw)

    def test_frozen_helper_loader_manifest_patch_and_api_hashes(self):
        for name in stage.HELPERS:
            with patch.dict(stage.HELPERS, {name: "0" * 64}):
                self.refused("helper/loader changed")
        with patch.object(stage, "MANIFEST_SHA256", "0" * 64):
            self.refused("session manifest changed")
        with patch.object(stage, "PATCH_SHA512", "0" * 128):
            self.refused("patch/source identity")
        real_regular = stage.regular

        def api_drift(path):
            raw = real_regular(path)
            return raw + b"drift\n" if path == stage.SESSION / "session.h" else raw

        with patch.object(stage, "regular", side_effect=api_drift):
            self.refused("session API changed")

    def test_late_parent_failure_and_unexpected_outputs_have_no_target_writes(self):
        real_stage = old.candidate.stage

        def fail(*args, **kwargs):
            real_stage(*args, **kwargs)
            raise ValueError("late parent failure")

        with patch.object(old.candidate, "stage", side_effect=fail):
            self.refused("late parent failure")
        for kind in ("file", "directory", "symlink", "retained-input"):
            def extra(tree, *args, **kwargs):
                result = real_stage(tree, *args, **kwargs)
                if kind == "file":
                    (tree / "unexpected").write_bytes(b"extra\n")
                elif kind == "directory":
                    (tree / "unexpected").mkdir()
                elif kind == "symlink":
                    (tree / "unexpected").symlink_to(tree / APK)
                else:
                    (tree / old.fixtures.parent.KERNEL / old.candidate.CAMERA).write_bytes(b"modified\n")
                return result
            with self.subTest(kind=kind), patch.object(old.candidate, "stage", side_effect=extra):
                self.refused("unexpected composer|retained input")

    def test_late_target_input_drift_is_preserved_without_publication(self):
        real_stage = old.candidate.stage
        path = self.tree / old.fixtures.parent.KERNEL / old.candidate.GPUEB
        changed = path.read_bytes() + b"concurrent writer\n"
        before = snapshot(self.tree.parent)

        def drift(*args, **kwargs):
            result = real_stage(*args, **kwargs)
            path.write_bytes(changed)
            return result

        with patch.object(old.candidate, "stage", side_effect=drift), \
                self.assertRaisesRegex(ValueError, "input changed during preparation"):
            self.candidate()
        before[str(path.relative_to(self.tree.parent))] = ("file", changed)
        self.assertEqual(snapshot(self.tree.parent), before)

    def test_late_source_asset_drift_is_refused_without_publication(self):
        prepared = False
        real_stage, real_regular = old.candidate.stage, stage.regular

        def compose(*args, **kwargs):
            nonlocal prepared
            result = real_stage(*args, **kwargs)
            prepared = True
            return result

        def source(path):
            raw = real_regular(path)
            return raw + b"drift\n" if prepared and path == stage.SESSION / stage.PATCH else raw

        with patch.object(old.candidate, "stage", side_effect=compose), \
                patch.object(stage, "regular", side_effect=source):
            self.refused("input changed during preparation")

    def test_late_report_reservation_is_preserved_without_other_writes(self):
        real_stage = old.candidate.stage
        before = snapshot(self.tree.parent)

        def compose(*args, **kwargs):
            result = real_stage(*args, **kwargs)
            self.session_report.write_bytes(b"external report\n")
            return result

        with patch.object(old.candidate, "stage", side_effect=compose), \
                self.assertRaisesRegex(ValueError, "already exists"):
            self.candidate()
        before[self.session_report.name] = ("file", b"external report\n")
        self.assertEqual(snapshot(self.tree.parent), before)

    def test_cli_help_default_rejection_and_success(self):
        before = snapshot(self.tree.parent)
        with patch.object(sys, "argv", ["stage-native-session-image.py", "--help"]), \
                contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as error:
            stage.main()
        self.assertEqual(error.exception.code, 0)
        self.assertIn("--include-session1010", output.getvalue())
        self.assertEqual(snapshot(self.tree.parent), before)
        argv = ["stage-native-session-image.py", "--pmaports", str(self.tree),
                "--report", str(self.report), "--tx-report", str(self.tx_report),
                "--session-report", str(self.session_report)]
        with patch.object(sys, "argv", argv), self.assertRaisesRegex(ValueError, "explicit"):
            stage.main()
        self.assertEqual(snapshot(self.tree.parent), before)
        with patch.object(sys, "argv", argv + ["--include-session1010"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            stage.main()
        self.assertEqual(json.loads(output.getvalue())["kernel_package"], "7.2.1-r189")

    def test_actual_ci_copy_and_out_layout(self):
        root = self.tree.parent / "work"
        tree = root / "upstream/pmaports"
        self.fixture.populate(tree)
        with patch.object(old.fixtures.stage, "ROOT", root), \
                patch.dict(os.environ, {"TETRIS_NATIVE_SOURCE_TREE": str(root / "out/native-source")}):
            result = stage.stage(tree, root / "out/native.json", root / "out/tx.json",
                                 root / "out/session.json", True)
        self.assertEqual(result["artifact"], stage.ARTIFACT)
        self.assertTrue((root / "out/session.json").is_file())


class ActualPinnedPatchApplication(unittest.TestCase):
    def test_real_cli_uses_unmodified_frozen_composers_on_a_disposable_copy(self):
        with tempfile.TemporaryDirectory(prefix="session-real-cli-") as directory:
            root = Path(directory).resolve()
            tree = root / "copy"
            for relative in old.fixtures.BASE_FILES:
                path = tree / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(old.CURRENT_APK if relative == APK else old.fixtures.FROZEN["pmaports/" + relative])
            _, manifest = old.fixtures.stage.inputs()
            for name in (*old.candidate.PATCHES, *manifest["prerequisite_sha512"]):
                shutil.copyfile(ROOT / "pmaports" / old.fixtures.parent.KERNEL / name,
                                tree / old.fixtures.parent.KERNEL / name)
            env = dict(os.environ, CI="true", GITHUB_ACTIONS="true", PYTHONDONTWRITEBYTECODE="1")
            argv = [sys.executable, "-B", str(ROOT / "ci/stage-native-session-image.py"),
                    "--pmaports", str(tree), "--report", str(root / "native.json"),
                    "--tx-report", str(root / "tx.json"), "--session-report", str(root / "session.json")]
            before = snapshot(root)
            rejected = subprocess.run(argv, env=env, text=True, capture_output=True, timeout=60)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("explicit --include-session1010", rejected.stderr)
            self.assertEqual(snapshot(root), before)
            result = subprocess.run(argv + ["--include-session1010"], env=env, text=True,
                                    capture_output=True, check=True, timeout=60)
            native = json.loads(result.stdout)
            self.assertEqual(native["kernel_package"], "7.2.1-r189")
            self.assertEqual(json.loads((root / "native.json").read_bytes()), native)
            self.assertEqual((tree / old.fixtures.parent.KERNEL / stage.PATCH).read_bytes(), g.PATCH.read_bytes())
            self.assertEqual(json.loads((root / "session.json").read_bytes()), native["native_session"])
            self.assertEqual(json.loads((root / "tx.json").read_bytes())["kernel_package"], "7.2.1-r188")

    def test_real_full_stack_zero_fuzz_and_exact1010_postimages(self):
        # No composition fixture is active here: only immutable git show,
        # actual GNU patch and git apply execute, never a C/native compiler.
        manifest = json.loads((g.HERE / "STAGING.json").read_bytes())
        self.assertEqual(stage.digest(g.PATCH.read_bytes(), "sha512"), stage.PATCH_SHA512)
        with tempfile.TemporaryDirectory(prefix="session-real-stack-") as directory:
            tree = Path(directory).resolve()
            g.write.populate(tree)
            # Earlier patches do not touch this header, so the minimal stack
            # fixture must retain its actual pinned Git blob for1010.
            header = tree / g.FSM_H
            self.assertFalse(header.exists())
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(g.write.source(g.FSM_H))
            tx_manifest = json.loads((g.write.HERE / "STAGING.json").read_bytes())
            self.assertEqual({name: stage.digest((tree / name).read_bytes(), "sha512")
                              for name in tx_manifest["stacked_source_sha512"]},
                             tx_manifest["stacked_source_sha512"])
            before_tx = {name: (tree / name).read_text() for name in g.write.SOURCES}
            g.write.checked(["git", "apply", "--check", "--whitespace=error", str(g.write.PATCH)], tree)
            g.write.checked(["git", "apply", "--whitespace=error", str(g.write.PATCH)], tree)
            for name, raw in before_tx.items():
                self.assertEqual((tree / name).read_text(), g.write.transform(name, raw))
            original = {name: (tree / name).read_text() if (tree / name).exists() else ""
                        for name in manifest["baseline_sha512"]}
            self.assertEqual({name: stage.digest(raw.encode(), "sha512") for name, raw in original.items()},
                             manifest["baseline_sha512"])
            retained = {str(p.relative_to(tree)): p.read_bytes() for p in tree.rglob("*") if p.is_file()}
            g.write.checked(["git", "apply", "--check", "--whitespace=error", str(g.PATCH)], tree)
            g.write.checked(["git", "apply", "--whitespace=error", str(g.PATCH)], tree)
            for name, raw in original.items():
                self.assertEqual((tree / name).read_text(), g.transform(name, raw))
            for name, raw in retained.items():
                if name not in original:
                    self.assertEqual((tree / name).read_bytes(), raw)
            self.assertIn("case GPSDL_V051_IOC_SESSION_SNAPSHOT:", (tree / g.DEVICE).read_text())
            self.assertIn("return READ_ONCE(g_gps_dsp_state[link_id]);", (tree / g.FSM).read_text())
            with self.assertRaises(ValueError):
                g.write.checked(["git", "apply", "--check", "--whitespace=error", str(g.PATCH)], tree)


if __name__ == "__main__":
    unittest.main()
