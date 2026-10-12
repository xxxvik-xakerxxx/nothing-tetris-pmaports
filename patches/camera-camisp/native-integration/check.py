#!/usr/bin/env python3
"""Static wiring/error gates, with in-memory negative source checks only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_generator", HERE / "generate.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compact(text):
    return re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S))


def body(code, name):
    return compact(gen.trace.body_after(code, name + "("))


def contract(code, native_patch):
    c = compact(code)
    for token in ("regulator_set_", "arm_smccc", "GENPD_FLAG_ALWAYS_ON", "force_off",
                  "first_error=0", "power_ready", "secure_ready", "regulator_get(", "udelay", "msleep"):
        require(token not in c, "no invented ownership, policy or force transition: " + token)
    construct = body(code, "scpsys_vmm_construct")
    require('mm=scpsys->domains[MT6878_POWER_DOMAIN_MM_INFRA];if(!mm)return-ENODEV;' in construct,
            "constructor uses existing MM_INFRA, no fabricated genpd")
    require('ret=mt6878_vmm_supplier_init(&owner->supplier,scpsys->dev,"cam-vcore",scpsys->base,mm);'
            'if(ret)returnret;' in construct, "real checked supplier constructor call")
    require(construct.index("gpd->status!=GENPD_STATE_OFF") < construct.index("mt6878_vmm_supplier_init"),
            "all leaves OFF before exclusive acquisition")
    require('ret=pm_genpd_add_device(gpd,dev);if(ret)gotofault;'
            'ret=mt6878_vmm_add_child(&owner->supplier,gpd,dev,&owner->guard[i]);if(ret)gotofault;' in construct,
            "real child device/notifier attachment before parent link")
    require('fault:returnmt6878_vmm_fail_child(&owner->supplier,ret);' in construct,
            "construction error is latched before retained ownership")
    prepare = body(code, "scpsys_vmm_prepare")
    require('if(!cam||!isp||cam!=isp)gotoput_rails;' in prepare, "CAM/ISP must reference the same real regulator")
    require('ret=scpsys_vmm_rail_identity(cam);if(ret)gotoput_rails;' in prepare and
            'address[0]!=6||address[1]!=SPMI_USID' in body(code, "scpsys_vmm_rail_identity") and
            'if(mask!=BIT(0))ret=-EINVAL;' in body(code, "scpsys_vmm_rail_identity"),
            "real native USID-6 VBUCK1 and B4.1 phase mask before acquisition")
    require('for_each_of_allnodes(node)' in prepare and 'for_each_property_of_node(node,prop)' in prepare and
            'shared=rail==cam;' in prepare and 'ret=-EBUSY;gotoput_rails;' in prepare,
            "reject independent described rail owners")
    topology = body(code, "scpsys_vmm_topology")
    require('MT6878_POWER_DOMAIN_CAM_VCORE:MT6878_POWER_DOMAIN_MM_INFRA' in topology and
            'of_property_present(child,"domain-supply")' in topology and 'ret=-EOPNOTSUPP;' in topology,
            "native hierarchy, no per-leaf supply and no uncovered descendants")
    require('if(count!=9||of_property_count_strings(node,"clock-names")!=9)return-EINVAL;' in
            body(code, "scpsys_vmm_clocks"), "all basic and eight subsystem clocks required")
    observe = body(code, "scpsys_vmm_observe_off")
    require('GENMASK(31,30)|PWR_ON_BIT|PWR_ON_2ND_BIT|PWR_RST_B_BIT' in observe and
            'if(ret)returnret;' in observe and 'bpd->bus_prot_sta_mask' in observe,
            "checked full control/SRAM/bus OFF observation")
    require('regmap_write' not in observe and 'regmap_update' not in observe, "no force-OFF adoption")
    for name, calls in {
        "scpsys_vmm_on": ["mt6878_vmm_check", "clk_bulk_prepare_enable(pd->num_clks", "scpsys_vmm_ctl(pd,true)",
                          "clk_bulk_prepare_enable(pd->num_subsys_clks", "scpsys_vmm_sram(pd,true)", "scpsys_vmm_bus(pd,false)"],
        "scpsys_vmm_off": ["mt6878_vmm_check", "scpsys_vmm_bus(pd,true)", "scpsys_vmm_sram(pd,false)",
                           "clk_bulk_disable_unprepare(pd->num_subsys_clks", "scpsys_vmm_ctl(pd,false)",
                           "clk_bulk_disable_unprepare(pd->num_clks"],
    }.items():
        b = body(code, name)
        indexes = [b.index(call) for call in calls]
        require(indexes == sorted(indexes), "ordered native leaf phases: " + name)
        for match in re.finditer(r"ret=(\w+)\([^;]+\);", b):
            tail = b[match.end():]
            expected = ("if(ret)returnret;" if match[1] in ("mt6878_vmm_check", "scpsys_vmm_ctl") else
                        "if(ret)returnscpsys_vmm_fault(pd,ret);")
            require(tail.startswith(expected), "first leaf error stops without unwind: " + match[1])
    require("returnmt6878_vmm_check(&pd->scpsys->vmm->supplier);" in body(code, "scpsys_vmm_start"),
            "cached-ON start guard before driver callback")
    resume = body(code, "scpsys_vmm_resume")
    require(resume.count("if(READ_ONCE(vmm->first_error))returnmt6878_vmm_check(vmm);") == 2 and
            "ret=pd->native_runtime_resume(dev);" in resume, "native resume retained and original supplier errno exposed")
    retain = body(code, "scpsys_vmm_retain")
    require('if(!owner||(!owner->supplier.buck&&!owner->retained))returnfalse;' in retain and
            'if(!owner->first_error)owner->first_error=ret;' in retain,
            "no failed devm probe after permanent ownership; preserve first construction errno")
    p = compact(native_patch.replace("\n+", "\n"))
    require('ret=scpsys_vmm_construct(scpsys);if(ret)gotoerr_cleanup_domains;'
            'ret=of_genpd_add_provider_onecell(np,&scpsys->pd_data);' in p,
            "actual native construction before provider publication")
    require('if(scpsys_vmm_retain(scpsys,ret))return0;' in p and
            'if(scpsys_vmm_unlink(scpsys)){scpsys_vmm_retain(scpsys,ret);return0;}' in p,
            "partial ownership skips cleanup and publication")
    for token in ('pd->genpd.power_on=scpsys_vmm_on;', 'pd->genpd.power_off=scpsys_vmm_off;',
                  'pd->genpd.dev_ops.start=scpsys_vmm_start;', 'pd->genpd.dev_ops.stop=scpsys_vmm_stop;',
                  'pd->genpd.domain.ops.runtime_resume=scpsys_vmm_resume;'):
        require(token in p, "callable native callback installed: " + token)
    require('obj-$(CONFIG_MTK_MT6878_NATIVE_VMM)+=native-vmm/' in p and
            'dependsonMTK_SCPSYS_PM_DOMAINS&&REGULATOR&&OF' in p and 'defaultn' in p,
            "native build closure with default-off selector")
    paths = set(re.findall(r"^diff --git a/(\S+) b/\S+$", native_patch, re.M))
    expected = {gen.DEST + n for n in ("mtk-pm-domains.c", "Makefile", "Kconfig", "mt6878-native-vmm.inc")}
    expected.update(gen.DEST + "native-vmm/" + n for n in (
        "Makefile", "mt6878-cam-power.c", "mt6878-cam-power.h", "mt6878-vmm-supplier.c",
        "mt6878-vmm-supplier.h", "mt6878-native-vmm.h"))
    require(paths == expected | {gen.BINDING}, "exact native provider/binding scope, no shipping DT or config")
    require("CONFIG_KUNIT" not in native_patch, "same actual provider path for both KUNIT selections")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--md-on-adoption", action="store_true")
    parser.add_argument("--write", action="store_true", help="write composite artifacts only, requires MD profile")
    parser.add_argument("--kernel-archive", type=Path)
    parser.add_argument("--vendor-repo", type=Path)
    parser.add_argument("--modules-repo", type=Path)
    parser.add_argument("--prepared-kernel", type=Path)
    parser.add_argument("--ci-apply", action="store_true")
    args = parser.parse_args()
    if not args.md_on_adoption and any((args.write, args.kernel_archive, args.vendor_repo,
                                       args.modules_repo, args.prepared_kernel, args.ci_apply)):
        parser.error("composite options require --md-on-adoption")
    code = (HERE / "mt6878-native-vmm.inc").read_text()
    patch = (HERE / "native-provider.patch").read_text()
    evidence = json.loads((HERE / "evidence.json").read_text())
    plan = json.loads((HERE / "STAGING.json").read_text())
    require((plan["kernel_commit"], plan["vendor_commit"], plan["modules_commit"]) ==
            (gen.KERNEL, gen.VENDOR, gen.MODULES), "three exact source pins")
    require(evidence["patch_sha256"] == hashlib.sha256(patch.encode()).hexdigest(), "patch identity")
    contract(code, patch)
    mutants = [
        (code.replace("scpsys->domains[MT6878_POWER_DOMAIN_MM_INFRA]", "NULL"), patch),
        (code.replace("cam != isp", "false"), patch),
        (code.replace("address[0] != 6", "false"), patch),
        (code.replace("shared = rail == cam", "shared = false"), patch),
        (code.replace("gpd->status != GENPD_STATE_OFF", "false"), patch),
        (code.replace("return scpsys_vmm_fault(pd, ret)", "return 0"), patch),
        (code.replace("READ_ONCE(vmm->first_error)", "false"), patch),
        (code.replace("owner->first_error = ret", "owner->first_error = 0"), patch),
        (code, patch.replace("+\tret = scpsys_vmm_construct(scpsys);", "+\tret = 0;")),
        (code, patch.replace("+\t\tpd->genpd.dev_ops.start = scpsys_vmm_start;", "+\t\tpd->genpd.dev_ops.start = NULL;")),
        (code, patch.replace("+\tdefault n", "+\tdefault y")),
    ]
    for n, (mutant, mutated_patch) in enumerate(mutants):
        try:
            contract(mutant, mutated_patch)
        except (ValueError, IndexError):
            continue
        raise ValueError("unsafe source mutation escaped: " + str(n))
    print(f"Native provider wiring/error gates passed; {len(mutants)} unsafe source mutations rejected; no C execution")
    if args.md_on_adoption:
        spec = importlib.util.spec_from_file_location("camera_md_composite", HERE / "md_on_adoption.py")
        composite = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(composite)
        composite.run(args, generator=gen)


if __name__ == "__main__":
    main()
