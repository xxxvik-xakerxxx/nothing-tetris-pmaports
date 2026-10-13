#!/usr/bin/env python3
"""Source/patch regressions only; no local C compiler, emulation or JIT."""
import json
import re
import unittest
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import audit
import ci
import stage

START = (stage.HERE / "ccci_tetris_native_start.c").read_text()
HIF = (stage.HERE / "native-hif-owner.h").read_text()
PROVIDER = (stage.HERE / "native-on-provider.h").read_text()


def ordered(text, *items):
    at = 0
    for item in items:
        found = text.find(item, at)
        stage.require(found >= 0, "missing/reordered native start operation: " + item)
        at = found + len(item)


def validate(start=START, hif=HIF, provider=PROVIDER):
    ordered(start.split("int ccci_tetris_owner_start(", 1)[1],
        "lock_system_sleep()", "device_trylock(dev)", "mutex_lock(&native_start_lock)",
        "native_start.first_error", "native_start.md != md", "native_start.step = 1;",
        "ccci_tetris_native_admit(md)", "pm_runtime_resume_and_get(dev)", "if (ret < 0)",
        "ccci_tetris_native_admit(md)", "native_brom_check()", "ccci_tetris_hif_lock()", "ccci_tetris_wdt_init_owned(md)",
        "ccci_tetris_hif_start()", "ccci_tetris_publish_hs1()", "ccci_tetris_native_admit(md)",
        "MD_POWER_CONFIG,", "MD_KERNEL_BOOT_UP, 0, 0, 0, 0, 0, &native_start.power0",
        "native_start.power0.a0 ? -EIO", "native_start.power0.a3 != 1 ? -EPROTO",
        "wdt_enable_irq(md)", "ccci_tetris_hif_unlock()", "native_fault(ret)",
        "device_unlock(dev)", "unlock_system_sleep(sleep_flags)")
    probe = start.split("int ccci_tetris_native_probe(", 1)[1].split("int ccci_tetris_owner_entry", 1)[0]
    ordered(probe, "ccci_tetris_native_admit(md)", "pm_runtime_enabled(dev)", "pm_runtime_set_active(dev)",
            "pm_runtime_get_noresume(dev)", "pm_runtime_enable(dev)", "get_device(dev)")
    stage.require("queue_start(" not in probe and "arm_smccc_smc(" not in probe, "probe autostart")
    for bad in ("pm_runtime_put", "start_platform(md)", "power_on(md)", "mt6878_ccci_first_start(",
                "proofs.", ".verify", "execution_inhibited", "PWR_RST", "MD_FLIGHT_MODE_SET"):
        stage.require(bad not in start, "obsolete/fabricated start dependency: " + bad)
    stage.require("bool " not in start + hif + provider, "invented native-start proof boolean")
    for required in ("owner->attached != dev", "dev->pm_domain != &pd->genpd.domain",
                     "pd->genpd.power_on != mt6878_md_real_boot_power_on", "owner->first_error",
                     "mt6878_md_adopt_revalidate_resources", "mt6878_md_adopt_on(pd, on)",
                     "regulator_is_enabled(rail)", "regulator_get_voltage(rail)"):
        stage.require(required in provider, "missing actual retained native-ON check: " + required)
    ordered(hif, "int ccci_tetris_hif_claim", "request_mem_region(res.start", "claim_count++",
            "int ccci_tetris_hif_register", "native_hif[id].dev != dev", "try_module_get(ops->owner)",
            "native_hif[id].data = data;", "ccci_hif[id] = data;", "int ccci_tetris_hif_lock",
            "device_trylock(dev)", "device_is_bound(native_hif[id].dev)",
            "native_hif[id].ops != ccci_hif_op[id]", "int ccci_tetris_hif_start", "ops->start(id)")
    stage.require("ret < 0 ? ret : -EPROTO" in hif, "HIF positive failure discarded")


class NativeStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundles = stage.build()

    def test_native_operation_contract(self):
        validate()

    def test_exact_source_evidence(self):
        self.assertEqual(audit.evidence(), json.loads((stage.HERE / "SOURCE-EVIDENCE.json").read_text()))

    def test_manifest_closure(self):
        stage.verify_manifest()

    def test_both_complete_stack_patches_apply_without_offsets(self):
        for name, (data, before, after) in self.bundles.items():
            self.assertEqual(data, (stage.HERE / name).read_text())
            stage.apply_check(data, before, after)

    def test_real_probe_and_fsm_start_callers(self):
        after = self.bundles["ccci-native-start.patch.vendor"][2]
        registration = after[stage.E + "fsm/register_prepare.h"]
        ordered(registration, "tetris_ccci_mem_prepare(md)", "ccci_tetris_native_probe(md)", "tetris_prepared_md = md")
        main = after[stage.E + "fsm/modem_sys1.c"]
        self.assertIn("return ccci_tetris_owner_start(md);", main)
        fsm = after[stage.E + "fsm/ccci_fsm.c"]
        self.assertIn("fsm_append_command(ccci_fsm_entries, CCCI_COMMAND_START, 0)", fsm)
        self.assertEqual(fsm.count("/* No physical stop/start contract is provided by registration. */"), 2)
        self.assertIn("CONFIG_MTK_ECCCI_TETRIS_OWNER) && !" + stage.FLAG, fsm)
        self.assertIn("fsm/ccci_tetris_native_start.o\nelse", after[stage.E + "Makefile"])

    def test_hif_real_probe_and_registration_callers(self):
        after = self.bundles["ccci-native-start.patch.vendor"][2]
        for path, claim, registration in (("hif/ccci_hif_ccif.c", "ccci_tetris_hif_claim(pdev, CCIF_HIF_ID)",
                                          "ccci_tetris_hif_register(ccif_ctrl->hif_id"),
                                         ("hif/ccci_dpmaif_com.c", "ccci_tetris_hif_claim(pdev, DPMAIF_HIF_ID)",
                                          "ccci_tetris_hif_register(DPMAIF_HIF_ID")):
            self.assertIn(claim, after[stage.E + path])
            self.assertIn(registration, after[stage.E + path])
        self.assertIn("native HIF rejects legacy registration", after[stage.E + "hif/ccci_hif.c"])

    def test_default_off_no_dt_or_automatic_entry(self):
        for name in ("native-start.Kconfig", "vendor-start.Kconfig"):
            text = (stage.HERE / name).read_text()
            self.assertIn("default n", text)
            self.assertNotRegex(text, r"\bselect\b|default [ym]")
        for _, _, after in self.bundles.values():
            self.assertFalse(any(name.endswith((".dts", ".dtsi")) for name in after))
        self.assertNotRegex(START, r"module_init\(|module_platform_driver\(")

    def test_no_inhibited_restart_or_fake_backend(self):
        self.assertNotIn("verify", re.sub(r"/\*.*?\*/", "", START, flags=re.S))
        self.assertNotIn("mt6878_ccci_start_alloc", START)
        self.assertNotIn("pm_runtime_put", START)

    def test_real_brom_predicate_and_four_defined_flags_before_transport(self):
        brom = START.split("static int native_brom_check(", 1)[1].split("int ccci_tetris_owner_start", 1)[0]
        ordered(brom, "remaining = 100", "MD_CHECK_DONE, 0, 0, 0, 0, 0",
                "if (!native_start.brom_done.a0)", "native_start.brom_done.a0 != 1",
                "msleep(20)", "return -ETIMEDOUT", "MD_CHECK_FLAG, 0, 0, 0, 0, 0")
        for cell in ("a0", "a1", "a2", "a3"):
            self.assertIn("native_start.brom_flags." + cell + " != 1", brom)

    def test_mutant_early_wdt_enable(self):
        wrong = START.replace("native_start.step = 3;", "wdt_enable_irq(md);\n\tnative_start.step = 3;").replace(
            "\twdt_enable_irq(md);\n\t/* Genuine", "\t/* Genuine")
        with self.assertRaises(ValueError):
            validate(start=wrong)

    def test_mutant_unchecked_secure_return(self):
        with self.assertRaises(ValueError):
            validate(start=START.replace("native_start.power0.a0 ? -EIO", "0 ? -EIO"))

    def test_mutant_boot_status_misread_as_flags(self):
        with self.assertRaises(ValueError):
            validate(start=START.replace("native_start.power0.a3 != 1 ? -EPROTO", "native_start.power0.a1 != 1 ? -EPROTO"))

    def test_mutant_removed_physical_readback(self):
        with self.assertRaises(ValueError):
            validate(provider=PROVIDER.replace("mt6878_md_adopt_on(pd, on)", "0"))

    def test_mutant_fake_proof_boolean(self):
        with self.assertRaises(ValueError):
            validate(start="bool secure_ready;\n" + START)

    def test_mutant_hidden_hif_error(self):
        with self.assertRaises(ValueError):
            validate(hif=HIF.replace("ret < 0 ? ret : -EPROTO", "0"))

    def test_mutant_stale_native_base_rejected(self):
        before = dict(self.bundles["native-on-api.patch"][1])
        name = stage.P + "mt6878-modem-real-boot.h"
        before[name] = before[name].replace("owner->attached = get_device(dev);", "owner->attached = dev;")
        with self.assertRaises(ValueError):
            stage.native_candidate(before)

    def test_ci_guard_precedes_native_compilation_and_source_mutation(self):
        with patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}), \
             patch.object(ci.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "CI-only"):
                ci.build(stage.HERE, stage.HERE, stage.HERE, stage.HERE, stage.HERE, stage.HERE, True)
            run.assert_not_called()

    def test_ci_preserves_real_helper_stage_namespace(self):
        real = ci.real_ci()
        self.assertNotEqual(real.stage.__file__, stage.__file__)
        self.assertTrue(callable(real.stage.digest))

    def test_ci_actual_units_and_no_link_targets(self):
        self.assertIn("fsm/ccci_tetris_native_start.o", ci.OBJECTS)
        self.assertIn("fsm/md_sys1_platform.o", ci.OBJECTS)
        source = (stage.HERE / "ci.py").read_text()
        self.assertIn("real.disabled_consumer_rails", source)
        self.assertIn("for enabled in (False, True)", source)
        self.assertIn("-DCONFIG_MTK_ECCCI_TETRIS_NATIVE_START=1", source)

    def test_explicit_three_file_pristine_input_reconstructs_identical_patches(self):
        linux = stage.UPSTREAM / ("linux-" + stage.LINUX)
        hashes = stage.pristine_inputs(linux)
        self.assertEqual(set(hashes), {stage.P + name for name in
                                      ("mtk-pm-domains.c", "mtk-pm-domains.h", "Kconfig")})
        with tempfile.TemporaryDirectory(prefix="tetris-native-start-pristine-") as directory:
            pristine = Path(directory).resolve()
            for name in hashes:
                target = pristine / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(linux / name, target)
            minimal = stage.build(linux=pristine)
            self.assertEqual({name: value[0] for name, value in minimal.items()},
                             {name: value[0] for name, value in self.bundles.items()})
            target.write_text(target.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "non-pristine d84"):
                stage.pristine_inputs(pristine)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "missing/non-pristine d84"):
                stage.pristine_inputs(pristine)

    def test_ci_passes_explicit_pristine_not_local_default(self):
        source = (stage.HERE / "ci.py").read_text()
        self.assertIn('parser.add_argument("--pristine-kernel", type=Path, required=True)', source)
        self.assertIn("stage.build(vendor, pristine)", source)
        self.assertNotIn("stage.build(vendor)", source)


if __name__ == "__main__":
    unittest.main()
