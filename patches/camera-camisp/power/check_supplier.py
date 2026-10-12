#!/usr/bin/env python3
"""Source-only checks of the unactivated shared VMM integration candidate."""
import argparse
import hashlib
import json
import re
import tarfile

import check

HERE = check.HERE
FILES = check.PAYLOAD + ("mt6878-vmm-supplier.c", "mt6878-vmm-supplier.h", "Kbuild.shared")
require = check.require
clean = check.clean


def body(code, name):
    return clean(check.source_trace.body_after(code, name + "("))


def source_contract(code, header):
    c = clean(code)
    for forbidden in ("devm_", "regulator_put(", "regulator_set_", "arm_smccc",
                      "platform_driver", "module_init", "of_genpd_add_provider",
                      "ioremap", "regmap_write", "regmap_update_bits", "GENPD_FLAG_ALWAYS_ON",
                      "GENPD_FLAG_RPM_ALWAYS_ON", "first_error=0", "udelay", "msleep"):
        require(forbidden not in c, "no unsafe ownership/policy/activation: " + forbidden)
    require("structgeneric_pm_domaingenpd;" in clean(header), "native genpd aggregation")
    require("users" not in c and "refcount" not in c, "no parallel consumer refcount")
    require(body(code, "vmm_fail") ==
            "if(!vmm->first_error){vmm->first_error=ret;"
            'dev_err(vmm->dev,"VMMfirstfault:%d;recoveryrequired\\n",ret);}'
            "returnvmm->first_error;",
            "first fault is permanent")
    require("#defineVMM_ISO_STATUS0x0f28" in c and
            "#defineVMM_ISO_BITSGENMASK(26,24)" in c, "B4.1 MT6878 isolation readback")
    require(body(code, "vmm_check_isolation") ==
            "u32value;intret;ret=regmap_read(vmm->spm,VMM_ISO_STATUS,&value);"
            "if(ret)returnret;return(value&VMM_ISO_BITS)==(isolated?VMM_ISO_BITS:0)?0:-EIO;",
            "checked full-mask isolation observation")
    require(body(code, "vmm_check_rail") ==
            "intret=regulator_is_enabled(vmm->buck);if(ret<0)returnret;return!!ret==on?0:-EIO;",
            "negative rail reads are errors, not ON")
    sequences = {
        "vmm_power_on": ["vmm_check_rail(vmm,false)", "vmm_check_isolation(vmm,true)",
                         "regulator_enable(vmm->buck)", "vmm_check_rail(vmm,true)",
                         "mt6878_vmm_iso_set(vmm->spm,false)"],
        "vmm_power_off": ["vmm_check_rail(vmm,true)", "vmm_check_isolation(vmm,false)",
                          "mt6878_vmm_iso_set(vmm->spm,true)", "regulator_disable(vmm->buck)",
                          "vmm_check_rail(vmm,false)"],
        "mt6878_vmm_check": ["vmm_check_rail(vmm,true)", "vmm_check_isolation(vmm,false)"],
        "mt6878_vmm_cam_ctl_set": ["vmm_check_rail(vmm,true)",
                                   "vmm_check_isolation(vmm,false)",
                                   "mt6878_cam_ctl_set(vmm->spm,domain,on)"],
    }
    for name, calls in sequences.items():
        b = body(code, name)
        actual = re.findall(r"ret=((?:vmm_check_\w+|regulator_\w+|mt6878_vmm_iso_set|mt6878_cam_ctl_set)\([^;]+\));", b)
        require(actual == calls, "ordered shared transaction: " + name)
        for call in calls:
            require("ret=" + call + ";if(ret)gotofault;" in b, "stop on first failure: " + call)
        require("fault:ret=vmm_fail(vmm,ret);out:mutex_unlock(&vmm->lock);returnret;" in b,
                "fault latch, unlock, original errno: " + name)
        require(b.index("vmm->first_error") < b.index(calls[0]), "sticky fault before any I/O")
        sticky = ("ret=vmm->first_error;if(ret)gotoout;" if name in
                  ("mt6878_vmm_check", "mt6878_vmm_cam_ctl_set") else
                  "if(vmm->first_error){ret=vmm->first_error;gotoout;}")
        require(sticky in b, "sticky fault must actually stop: " + name)
        require(b.count("mutex_lock(&vmm->lock)") == 1 and b.count("mutex_unlock(&vmm->lock)") == 1,
                "serialized callback: " + name)
    leaf = body(code, "mt6878_vmm_cam_ctl_set")
    require(leaf ==
            "intret;if(!vmm||!vmm->initialized)return-EINVAL;"
            "if(domain!=MT6878_POWER_DOMAIN_CAM_MAIN&&domain!=MT6878_POWER_DOMAIN_CAM_VCORE)"
            "return-EINVAL;mutex_lock(&vmm->lock);ret=vmm->first_error;if(ret)gotoout;"
            "ret=vmm_check_rail(vmm,true);if(ret)gotofault;"
            "ret=vmm_check_isolation(vmm,false);if(ret)gotofault;"
            "ret=mt6878_cam_ctl_set(vmm->spm,domain,on);if(ret)gotofault;gotoout;"
            "fault:ret=vmm_fail(vmm,ret);out:mutex_unlock(&vmm->lock);returnret;",
            "owned CAM control phase: validate, check, transact and latch before unlocking")
    require("intmt6878_vmm_cam_ctl_set(structmt6878_vmm_supplier*vmm,"
            "unsignedintdomain,boolon);" in clean(header), "checked CAM control API")
    init = body(code, "mt6878_vmm_supplier_init")
    signature = ("intmt6878_vmm_supplier_init(structmt6878_vmm_supplier*vmm,"
                 "structdevice*dev,constchar*supply_id,structregmap*spm,"
                 "structgeneric_pm_domain*mm_infra)")
    require(signature + "{" in c and signature + ";" in clean(header),
            "provider selects the actual consumer supply ID in the public API")
    validation = ("if(!vmm||!dev||!supply_id||!*supply_id||"
                  "IS_ERR_OR_NULL(spm)||!mm_infra)return-EINVAL;")
    require(init.startswith("intret,enabled;" + validation),
            "null/empty supply rejected before acquisition or owner mutation")
    require(re.findall(r"regulator_(?:get\w*|\w+_get)\([^;]+\)", init) ==
            ["regulator_get_exclusive(dev,supply_id)"],
            "one exclusive acquisition of the selected supply, no alias fallback")
    require("vmm->buck=regulator_get_exclusive(dev,supply_id);"
            "if(IS_ERR(vmm->buck)){ret=PTR_ERR(vmm->buck);vmm->buck=NULL;returnret;}" in init,
            "missing/unready/busy rail preserves acquisition errno without publication")
    require("if(vmm->buck)returnvmm->first_error?vmm->first_error:-EBUSY;" in init,
            "no reinitialization of a held/faulted owner")
    require("enabled=regulator_is_enabled(vmm->buck);if(enabled<0)returnvmm_fail(vmm,enabled);"
            "if(enabled)returnvmm_fail(vmm,-EBUSY);"
            "ret=vmm_check_isolation(vmm,true);if(ret)returnvmm_fail(vmm,ret);" in init,
            "observed OFF and full isolation before software OFF")
    require("vmm->genpd.power_on=vmm_power_on;vmm->genpd.power_off=vmm_power_off;"
            "ret=pm_genpd_init(&vmm->genpd,NULL,!enabled);if(ret)returnvmm_fail(vmm,ret);"
            "ret=pm_genpd_add_subdomain(mm_infra,&vmm->genpd);if(ret)returnvmm_fail(vmm,ret);"
            "vmm->initialized=true;return0;" in init, "checked native callbacks and initialization")
    guard = body(code, "vmm_child_notify")
    require("if(event==GENPD_NOTIFY_PRE_ON||event==GENPD_NOTIFY_PRE_OFF){"
            "ret=mt6878_vmm_check(guard->supplier);if(!ret){guard->pending=event;"
            "guard->transitioning=true;}"
            "returnnotifier_from_errno(ret);}" in guard, "guard cached-ON supplier and veto errors")
    require("if(guard->transitioning&&((event==GENPD_NOTIFY_OFF&&guard->pending==GENPD_NOTIFY_PRE_ON)||"
            "(event==GENPD_NOTIFY_ON&&guard->pending==GENPD_NOTIFY_PRE_OFF)))"
            "ret=mt6878_vmm_fail_child(guard->supplier,-EIO);" in guard,
            "pin shared supplier on leaf failure before genpd unwind")
    require("guard->transitioning=false;" in guard, "clear pending transition, PRE_OFF equals zero")
    fail = body(code, "mt6878_vmm_fail_child")
    require("error>=0" in fail and "ret=vmm_fail(vmm,error);" in fail, "original leaf errno handoff")
    child = body(code, "mt6878_vmm_add_child")
    require("guard_dev->pm_domain!=&child->domain" in child and
            "child->status!=GENPD_STATE_OFF" in child and
            "child->flags&GENPD_FLAG_IRQ_SAFE" in child, "quiescent sleeping domain guard")
    require("ret=dev_pm_genpd_add_notifier(guard_dev,&guard->nb);if(ret)returnret;"
            "guard->registered=true;ret=pm_genpd_add_subdomain(&vmm->genpd,child);"
            "if(ret)returnvmm_fail(vmm,ret);guard->linked=true;return0;" in child,
            "guard installed before native parent link, checked partial construction")


def staging_contract(plan):
    require(plan["kernel_commit"] == check.source_trace.KERNEL and
            plan["vendor_commit"] == check.source_trace.VENDOR, "shared staging source pins")
    require(plan["sources"] == {"patches/camera-camisp/power/" + n:
                                check.DEST + ("Kbuild" if n == "Kbuild.shared" else n) for n in FILES},
            "complete isolated source closure")
    require(plan["source_sha256"] == {"patches/camera-camisp/power/" + n:
                                     hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in FILES},
            "exact parent staging payload hashes")
    require(plan["research_objects"] == [check.DEST + n.replace(".c", ".o")
                                         for n in FILES if n.endswith(".c")], "isolated objects")
    require(plan["include_directory"] == "drivers/pmdomain/mediatek", "real native headers")
    require(plan["required_enabled"] == ["OF", "PM", "REGMAP", "REGULATOR", "PM_GENERIC_DOMAINS"],
            "no regulator/genpd stubs")
    require(plan["required_reachable"] == ["MTK_SCPSYS_PM_DOMAINS"] and
            plan["config_variants"] == [{"KUNIT": "y"}, {"KUNIT": "n"}], "staging dependencies")
    require(plan["runtime_activation"] == "disabled", "no activation")
    require(plan["object_smoke"] == {
        "scope": "object-only; shared composite/vmlinux link untested",
        "supplier_directory": "drivers/pmdomain/mediatek/tetris-vmm-supplier-smoke",
        "excluded_payload": ["Kbuild.shared"],
        "leaf_route": "existing power/STAGING.json, staged exactly once",
        "makefile": "harness-generated; no parent Kbuild replacement",
    }, "current object-only harness contract")
    require(plan["link_plan"] == {
        "composite_object": check.DEST + "tetris-vmm-candidate.o",
        "parent_research_entry": "obj-y += tetris-cam-power-smoke/",
        "final_target": "vmlinux",
        "original_leaf_route": "replace research entry, never link leaf object twice",
        "shipping_integration": "none",
        "activation": "no initcall, OF provider, DT enablement or exported module symbols",
    }, "full native link with no duplicate leaf symbols or activation")
    kbuild = (HERE / "Kbuild.shared").read_text().splitlines()
    require([line for line in kbuild if line and not line.startswith("#")] == [
        "ccflags-y += -I$(srctree)/drivers/pmdomain/mediatek",
        "obj-y += tetris-vmm-candidate.o",
        "tetris-vmm-candidate-y := mt6878-cam-power.o mt6878-vmm-supplier.o",
    ], "native Kbuild composite closure")


def verify_sources():
    base = json.loads((HERE / "evidence.json").read_text())
    check.evidence_contract(base)
    require(check.source_trace.trace(check.source_trace.ROOT.parent) == base,
            "exact B4.1 and SHA512-verified kernel archive")
    evidence = json.loads((HERE / "supplier-evidence.json").read_text())
    require(evidence["kernel_commit"] == check.source_trace.KERNEL and
            evidence["vendor_commit"] == check.source_trace.VENDOR, "supplier provenance pins")
    archive = check.source_trace.ROOT.parent / ("linux-" + check.source_trace.KERNEL + ".tar.gz")
    found = {}
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            path = member.name.removeprefix("linux-" + check.source_trace.KERNEL + "/")
            if path in evidence["kernel_sha256"]:
                found[path] = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
    require(found == evidence["kernel_sha256"], "pinned native regulator/genpd API objects")
    for name, expected in evidence["package_sha256"].items():
        require(hashlib.sha256((check.source_trace.PACKAGE / name).read_bytes()).hexdigest() == expected,
                "packaged buck-provider drift: " + name)
    print("Exact B4.1, kernel archive, genpd/regulator API and seven buck patches verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-sources", action="store_true")
    args = parser.parse_args()
    source_contract((HERE / FILES[2]).read_text(), (HERE / FILES[3]).read_text())
    staging_contract(json.loads((HERE / "SHARED-STAGING.json").read_text()))
    if args.verify_sources:
        verify_sources()
    print("Shared VMM source and staging checks passed; no C execution or hardware validation")


if __name__ == "__main__":
    main()
