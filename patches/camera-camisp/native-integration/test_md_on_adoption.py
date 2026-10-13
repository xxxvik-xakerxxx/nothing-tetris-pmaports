#!/usr/bin/env python3
"""Composition/application tests only; never compile or execute kernel C."""
import ast
import difflib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import check
import generate as gen
import md_on_adoption as md


class CompositeProvider(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = gen.ROOT.parent / ("linux-" + gen.KERNEL + ".tar.gz")
        vendor = gen.ROOT.parent / gen.trace.VENDOR_REPO
        modules = gen.ROOT.parent / "android_kernel_modules_nothing_mt6878"
        with mock.patch.object(gen, "native_inputs", wraps=gen.native_inputs) as native_call, \
             mock.patch.object(gen, "vendor_inputs", wraps=gen.vendor_inputs) as vendor_call:
            cls.overlay, cls.report, cls.files, cls.md_after = md.validate(gen, archive, vendor, modules)
            native_call.assert_called_once_with(archive, include_md=True)
            vendor_call.assert_called_once_with(vendor, modules)

    def assert_bad_native(self, old, new):
        source = self.files[md.CFILE]
        self.assertIn(old, source)
        changed = {**self.files, md.CFILE: source.replace(old, new)}
        with self.assertRaises(ValueError):
            md.combined_contract(gen, changed, self.md_after)

    def test_actual_combined_application_and_artifact_identity(self):
        self.assertEqual(md.OVERLAY.read_text(), self.overlay)
        self.assertEqual(json.loads(md.REPORT.read_text()), self.report)
        self.assertEqual(self.report["native_provider_sha256"], md.digest(self.files[md.CFILE].encode()))
        check.contract((md.HERE / "mt6878-native-vmm.inc").read_text(), self.overlay)
        self.assertFalse(self.report["compiled"])
        self.assertFalse(self.report["hardware_tested"])
        self.assertEqual(self.report["config_variants"], [{"KUNIT": "y"}, {"KUNIT": "n"}])

    def test_md_and_camera_callback_predicates_survive(self):
        self.assert_bad_native("pd->genpd.attach_dev = mt6878_md_adopt_attach;", "pd->genpd.attach_dev = NULL;")
        self.assert_bad_native("pd->genpd.power_on = mt6878_md_adopt_transition;", "pd->genpd.power_on = scpsys_power_on;")
        self.assert_bad_native("pd->genpd.power_off = scpsys_vmm_off;", "pd->genpd.power_off = NULL;")
        self.assert_bad_native("if (scpsys_vmm_domain(scpsys, id)) {\n\t\tpd->genpd.power_off", "if (false) {\n\t\tpd->genpd.power_off")

    def test_md_init_and_cleanup_and_vmm_constructor_cannot_disappear(self):
        self.assert_bad_native("pd->md_adoption->state == MT6878_MD_FIRST_OFF_COMPLETE", "true")
        self.assert_bad_native("mt6878_md_first_off_publication_fault(scpsys, ret);", "ret = 0;")
        self.assert_bad_native("!MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD) && scpsys_domain_is_on(pd)", "scpsys_domain_is_on(pd)")
        self.assert_bad_native("ret = scpsys_vmm_construct(scpsys);", "ret = 0;")
        self.assert_bad_native("if (scpsys_vmm_retain(scpsys, ret))", "if (false)")

    def test_md_veto_and_real_attach_are_checked_in_helper(self):
        for old, new in (("owner->first_error ? owner->first_error : -EOPNOTSUPP", "0"),
                         ("dev->of_node != owner->modem", "false")):
            source = self.files[md.ADOPT]
            self.assertIn(old, source)
            changed = source.replace(old, new)
            with self.assertRaises(ValueError):
                md.combined_contract(gen, {**self.files, md.ADOPT: changed}, {**self.md_after, md.ADOPT: changed})

    def test_profile_rejects_input_drift_before_stage(self):
        with mock.patch.object(md, "digest", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "MD profile input drift"):
                md.load_profile(gen)
        profile = json.loads(md.PROFILE.read_text())
        source = {p.removeprefix(md.PREFIX) if p.startswith(md.PREFIX) else p: c for p, c in self.md_after.items()}
        source["mtk-pm-domains.c"] += "\n"
        with self.assertRaisesRegex(ValueError, "exact MD-applied input profile"):
            gen.payload(source, {}, md_on_adoption=profile)

    def test_restart_helpers_cannot_disappear_or_gain_hardware_operations(self):
        changed = {**self.files, md.RESTART: self.files[md.RESTART] + "\n"}
        with self.assertRaisesRegex(ValueError, "must not change restart"):
            md.combined_contract(gen, changed, self.md_after)
        for operation in ("arm_smccc_smc(0);", "regulator_get(NULL, NULL);", "regmap_write(NULL, 0, 0);"):
            source = self.files[md.RESTART] + "\nstatic void bad(void) { " + operation + " }\n"
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "must not acquire rails"):
                md.combined_contract(gen, {**self.files, md.RESTART: source}, {**self.md_after, md.RESTART: source})

    def test_profile_refresh_is_explicit_and_never_a_ci_fallback(self):
        args = SimpleNamespace(ci_apply=False, prepared_kernel=None, write=False,
                               refresh_md_profile=True, kernel_archive=None)
        with mock.patch.object(md, "refresh_profile") as refresh:
            with self.assertRaisesRegex(ValueError, "requires explicit --write"):
                md.run(args, generator=gen)
            refresh.assert_not_called()

    def test_patch_offsets_and_partial_scope_are_rejected(self):
        old = "a\nb\nc\nd\nold\ne\nf\ng\nh\ni\n"
        new = old.replace("old\n", "new\n")
        patch = "diff --git a/sample.c b/sample.c\n" + "".join(difflib.unified_diff(
            old.splitlines(True), new.splitlines(True), fromfile="a/sample.c", tofile="b/sample.c"))
        with tempfile.TemporaryDirectory(prefix=".md-negative-", dir=md.HERE) as directory:
            tree = Path(directory)
            (tree / "sample.c").write_text("shift\n" + old)
            with self.assertRaisesRegex(ValueError, "offset/fuzz/skipped"):
                md.apply_exact(tree, patch, {"sample.c": new})
            self.assertEqual((tree / "sample.c").read_text(), "shift\n" + old)
            with self.assertRaisesRegex(ValueError, "exact application scope"):
                md.apply_exact(tree, patch, {"foreign.c": new})

    def test_prepared_tree_requires_md_once_and_camera_absent(self):
        with tempfile.TemporaryDirectory(prefix=".md-prepared-", dir=md.HERE) as directory:
            tree = Path(directory)
            for path, text in self.md_after.items():
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            md.check_prepared(tree, self.md_after, self.files)
            camera = tree / (md.PREFIX + "mt6878-native-vmm.inc")
            camera.write_text("already applied\n")
            with self.assertRaisesRegex(ValueError, "already contains camera"):
                md.check_prepared(tree, self.md_after, self.files)
            camera.unlink()
            (tree / md.CFILE).write_bytes(self.md_after[md.CFILE].replace("\n", "\r\n").encode())
            with self.assertRaisesRegex(ValueError, "exact MD-applied baseline"):
                md.check_prepared(tree, self.md_after, self.files)
            (tree / md.CFILE).write_text("wrong preimage\n")
            with self.assertRaisesRegex(ValueError, "exact MD-applied baseline"):
                md.check_prepared(tree, self.md_after, self.files)

    def test_local_prepared_mutation_is_rejected_before_validation(self):
        args = SimpleNamespace(ci_apply=True, prepared_kernel=Path("unused"), write=False)
        with mock.patch.dict(md.os.environ, {}, clear=True), mock.patch.object(md, "validate") as validate:
            with self.assertRaisesRegex(ValueError, "CI=true and GITHUB_ACTIONS=true"):
                md.run(args, generator=gen)
            validate.assert_not_called()

    def test_python_parse_and_canonical_artifacts_unchanged(self):
        for path in md.HERE.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
        for name, expected in self.report["canonical_camera_sha256"].items():
            self.assertEqual(md.digest((md.HERE / name).read_bytes()), expected)


if __name__ == "__main__":
    unittest.main()
