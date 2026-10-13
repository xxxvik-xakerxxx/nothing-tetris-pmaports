#!/usr/bin/env python3
"""Synthetic full-tree and source mutations; no dtc, kernel execution or phone."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import importlib.util

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dt = load("supplier_dt_check", "check-dt.py")
old = load("supplier_fixture_inputs", "test-dt.py")
source = load("supplier_source_check", "check-supplier.py")
u32, strings = dt.u32, dt.strings
SPM, MM, PMIC, REGS, IOMMU, SOC = old.SPM, old.MM, old.PMIC, old.REGS, old.IOMMU, old.SOC
SCP = SOC + "/scp@10720000"
USB = SOC + "/usb@11200000"
DISP = MM + "/power-domain@8"


def fixture(data, profile="supplier"):
    base, tree = old.fixture(data)
    for current in (base, tree):
        current[DISP] = {"reg": u32(8), "#power-domain-cells": u32(0), "phandle": u32(40)}
        current[SCP] = {"compatible": strings("mediatek,mt6878-scp"), "status": strings("okay"),
                        "clocks": u32(2, 0), "firmware-name": strings("scp.img")}
        current[USB] = {"compatible": strings("mediatek,mt6878-mtu3"), "status": strings("okay"),
                        "clocks": u32(2, 1), "dr_mode": strings("peripheral")}
        current[SOC + "/display"] = {"power-domains": u32(40), "status": strings("okay")}
    for path in (SPM, MM, IOMMU):
        tree[path] = copy.deepcopy(base[path])
    if profile == "ownership-blocked":
        tree[SPM].update({"cam-vcore-supply": u32(30), "isp-vcore-supply": u32(30)})
        tree[PMIC].pop("mediatek,observe-vgpu-only")
    return base, tree


class SupplierTreeGuards(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "evidence.json").read_text())
        self.base, self.tree = fixture(self.data)

    def reject(self, tree=None, profile="supplier", base=None):
        with self.assertRaises((ValueError, KeyError)):
            dt.validate(base or self.base, tree or self.tree, self.data, profile)

    def test_baseline_preserving_candidate(self):
        dt.validate(self.base, self.tree, self.data, "supplier")

    def test_blocked_delta_is_description_only(self):
        base, tree = fixture(self.data, "ownership-blocked")
        dt.validate(base, tree, self.data, "ownership-blocked")
        self.reject(tree, base=base)
        self.reject(profile="ownership-blocked")

    def test_all_existing_properties_are_preserved(self):
        for path, props in self.base.items():
            for key in set(props) - {"phandle", "linux,phandle"}:
                for remove in (False, True):
                    tree = copy.deepcopy(self.tree)
                    if remove:
                        tree[path].pop(key)
                    else:
                        tree[path][key] = strings("changed")
                    with self.subTest(path=path, key=key, remove=remove):
                        self.reject(tree)

    def test_no_existing_node_may_be_removed(self):
        for path in self.base:
            tree = copy.deepcopy(self.tree)
            tree.pop(path)
            with self.subTest(path=path):
                self.reject(tree)

    def test_each_new_node_stays_disabled(self):
        for path in set(self.tree) - set(self.base):
            for status in (strings("okay"), None):
                tree = copy.deepcopy(self.tree)
                if status:
                    tree[path]["status"] = status
                else:
                    tree[path].pop("status")
                with self.subTest(path=path, status=status):
                    self.reject(tree)

    def test_exact_new_resource_properties(self):
        for path in set(self.tree) - set(self.base):
            for key in set(self.tree[path]) - {"phandle", "linux,phandle"}:
                tree = copy.deepcopy(self.tree)
                tree[path][key] = strings("changed")
                with self.subTest(path=path, key=key):
                    self.reject(tree)
            tree = copy.deepcopy(self.tree)
            tree[path]["regulator-init-microvolt"] = u32(700000)
            self.reject(tree)

    def test_disabled_larbs_must_not_join_live_display_iommu(self):
        self.tree[IOMMU]["mediatek,larbs"] += self.tree[SOC + "/smi@1a001000"]["phandle"]
        self.reject()

    def test_pair_is_not_safe_opt_in_on_dormant_candidate(self):
        self.tree[SPM].update({"cam-vcore-supply": u32(30), "isp-vcore-supply": u32(30)})
        self.reject()

    def test_blocked_pair_cannot_diverge_or_use_gpu_buck(self):
        base, tree = fixture(self.data, "ownership-blocked")
        tree[REGS + "/vbuck2"]["phandle"] = u32(31)
        for prop in ("cam-vcore-supply", "isp-vcore-supply"):
            for value in (u32(31), u32(30, 0), u32(99), b""):
                mutated = copy.deepcopy(tree)
                mutated[SPM][prop] = value
                self.reject(mutated, "ownership-blocked", base)

    def test_blocked_description_cannot_enable_registration(self):
        base, tree = fixture(self.data, "ownership-blocked")
        for path in (PMIC, REGS + "/vbuck1", MM + "/power-domain@a", MM + "/power-domain@10"):
            mutated = copy.deepcopy(tree)
            mutated[path]["status"] = strings("okay")
            self.reject(mutated, "ownership-blocked", base)

    def test_observer_must_remain_on_candidate_and_be_deleted_only_on_blocked(self):
        self.tree[PMIC].pop("mediatek,observe-vgpu-only")
        self.reject()
        base, tree = fixture(self.data, "ownership-blocked")
        tree[PMIC]["mediatek,observe-vgpu-only"] = b""
        self.reject(tree, "ownership-blocked", base)

    def test_new_dummy_or_duplicate_owners_are_rejected(self):
        for path, props in ((SOC + "/fake-spm", self.tree[SPM]),
                            (SOC + "/spmi@1cc04000/duplicate@6", self.tree[PMIC]),
                            (SPM + "/dummy-mm-infra", self.tree[MM]),
                            ("/dummy-regulator", {"compatible": strings("regulator-fixed")})):
            tree = copy.deepcopy(self.tree)
            tree[path] = dict(props, phandle=u32(91))
            self.reject(tree)

    def test_clock_order_not_just_set_membership(self):
        path = MM + "/power-domain@a/power-domain@d"
        raw = self.tree[path]["clocks"]
        self.tree[path]["clocks"] = raw[:8] + raw[16:24] + raw[8:16] + raw[24:]
        self.reject()

    def test_competing_vbuck1_users_cannot_be_added(self):
        for owner in ("vmmspm", "mmdvfs-debug", "other"):
            base, tree = fixture(self.data, "ownership-blocked")
            tree[SOC + "/" + owner] = {"vmm-pmic-supply": u32(30)}
            self.reject(tree, "ownership-blocked", base)
        base, tree = fixture(self.data, "ownership-blocked")
        tree[SCP]["vmm-pmic-supply"] = u32(30)
        self.reject(tree, "ownership-blocked", base)

    def test_unsupported_baseline_descendants_must_also_be_disabled(self):
        for domain in (3, 11, 12, 14, 15, 17, 18):
            base, tree = fixture(self.data)
            path = MM + f"/power-domain@{domain:x}"
            for current in (base, tree):
                current[path] = {"reg": u32(domain), "status": strings("okay")}
            self.reject(tree, base=base)

    def test_typed_phandles_can_renumber_without_changing_owners(self):
        owners = dt.phandle_owners(self.tree)
        plain = {"mediatek,hardware-voter", "mediatek,smi", "mediatek,smi-supply", "mediatek,larbs"}
        for props in self.tree.values():
            for prop, value in list(props.items()):
                if prop in ("phandle", "linux,phandle"):
                    props[prop] = u32(dt.cells(value)[0] + 100)
                elif prop in plain or prop in ("clocks", "iommus", "power-domains"):
                    refs = dt.reference_value(self.tree, owners, prop, value)
                    # Provider cell widths remain unchanged while handles move.
                    handles = {path: handle for handle, path in owners.items()}
                    props[prop] = b"".join(u32(handles[path] + 100, *args) for path, args in refs)
        dt.validate(self.base, self.tree, self.data, "supplier")

    def test_invalid_phandles_are_rejected(self):
        self.tree[REGS + "/vbuck1"]["phandle"] = u32(2)
        self.reject()


class SupplierSourceGuards(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "evidence.json").read_text())
        self.files = source.wiring.outputs(self.data, source.generate.fragment, source.generate.power_fragment)

    def test_source_and_patch_closure(self):
        source.check()

    def test_every_generated_payload_and_plan_is_guarded(self):
        for name in self.files:
            files = dict(self.files)
            files[name] += "/* unexpected */\n"
            with self.subTest(name=name), self.assertRaises(ValueError):
                source.source_contract(files, self.data)

    def test_mutated_stock_constraints_cannot_regenerate_their_way_in(self):
        self.data["power"]["rails"]["1"]["regulator-min-microvolt"] = 700000
        files = source.wiring.outputs(self.data, source.generate.fragment, source.generate.power_fragment)
        with self.assertRaises(ValueError):
            source.source_contract(files, self.data)

    def test_ownership_provenance_cannot_change(self):
        facts = json.loads((HERE / "supplier-evidence.json").read_text())
        facts["provenance"][0]["commit"] = "0" * 40
        with self.assertRaises(ValueError):
            source.evidence_contract(facts)

    def test_staging_checks_all_payloads_and_header(self):
        plan = json.loads(self.files["SUPPLIER-STAGING.json"])
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            for src, dest in plan["sources"].items():
                target = tree / dest
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source.ROOT / src).read_bytes())
            header = plan["requires_existing_resource_header"]
            target = tree / source.generate.DESTINATIONS[Path(header).name]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source.ROOT / header).read_bytes())
            source.check(staged=tree)
            target.write_text("stale header\n")
            with self.assertRaises(ValueError):
                source.check(staged=tree)


if __name__ == "__main__":
    unittest.main()
