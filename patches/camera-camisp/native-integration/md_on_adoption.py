#!/usr/bin/env python3
"""Exact MD-first/camera-second source composition; no local build or activation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "MD-ON-ADOPTION-PROFILE.json"
OVERLAY = HERE / "native-provider-after-md.patch"
REPORT = HERE / "md-on-adoption-report.json"
PREFIX = "drivers/pmdomain/mediatek/"
MD_DIR = "patches/modem/md-pm-integration/"
MD_PATCH = MD_DIR + "native-on-adoption.patch"
MD_STAGE = MD_DIR + "stage.py"
MD_HELPER = MD_DIR + "mt6878-modem-adopt.h"
CFILE = PREFIX + "mtk-pm-domains.c"
DATA = PREFIX + "mt6878-modem-pm.h"
ADOPT = PREFIX + "mt6878-modem-adopt.h"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hashes(files):
    return {path: digest(text.encode()) for path, text in files.items()}


def compact(text):
    return re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S))


def load_profile(gen):
    profile = json.loads(PROFILE.read_text())
    require(profile["profile"] == "md-on-adoption-v1", "unknown MD composition profile")
    require((profile["kernel_commit"], profile["vendor_commit"], profile["modules_commit"]) ==
            (gen.KERNEL, gen.VENDOR, gen.MODULES), "MD composition source pins drift")
    require(set(profile["md_source_sha256"]) == {MD_PATCH, MD_STAGE, MD_HELPER}, "fixed MD input closure")
    for path, expected in profile["md_source_sha256"].items():
        require(digest((gen.ROOT / path).read_bytes()) == expected, "MD profile input drift: " + path)
    for name, expected in profile["canonical_camera_sha256"].items():
        require(name in ("native-provider.patch", "evidence.json"), "fixed canonical camera input")
        require(digest((HERE / name).read_bytes()) == expected, "canonical camera input drift: " + name)
    return profile


def canonical_baseline(gen, native, vendor, patches):
    evidence = json.loads((HERE / "evidence.json").read_text())
    base = {n: c for n, c in native.items() if n != "mt6878-modem-pm.h"}
    require(hashes(base) == evidence["native_input_sha256"], "exact packaged native baseline required")
    require(list(patches.items()) == list(evidence["package_patch_sha256"].items()), "exact ordered packaged provider patches required")
    require({p: digest(c) for p, c in vendor.items()} == evidence["vendor_input_sha256"], "pinned vendor/modules source drift")
    require({n: digest((gen.POWER / n).read_bytes()) for n in evidence["baseline_payload_sha256"]} ==
            evidence["baseline_payload_sha256"], "frozen camera source payload drift")
    gen.verify_vendor_contract(vendor)
    camera = gen.payload(base, vendor)
    require(hashes(camera) == evidence["payload_sha256"], "canonical camera generation drift")
    require(gen.patch_text(base, camera) == (HERE / "native-provider.patch").read_text(), "canonical camera patch drift")
    return camera


def stage_candidate(gen, native, profile):
    require(hashes({gen.native_path(n): c for n, c in native.items()}) ==
            profile["pre_md_input_sha256"], "exact pre-MD input profile required")
    # Import only the reviewed, hash-pinned stage generator; call its pure functions.
    spec = importlib.util.spec_from_file_location("camera_pinned_md_stage", gen.ROOT / MD_STAGE)
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    require((stage.CFILE, stage.DATA, stage.ADOPT) == (CFILE, DATA, ADOPT), "MD stage scope drift")
    before = {p: native[p.removeprefix(PREFIX)] for p in (CFILE, DATA, PREFIX + "mtk-pm-domains.h")}
    after = stage.candidate(before)
    require(set(after) == set(before) | {ADOPT}, "MD stage payload closure drift")
    raw = (gen.ROOT / MD_PATCH).read_text()
    require(raw == stage.diff(before, after), "MD patch differs from its pinned deterministic stage payload")
    result = {gen.native_path(n): c for n, c in native.items()}
    result.update(after)
    require(hashes(result) == profile["post_md_input_sha256"], "exact MD result profile required")
    # Recheck inputs after generation to catch an agent changing them mid-read.
    load_profile(gen)
    return result, raw


def apply_exact(tree, text, expected):
    paths = re.findall(r"^diff --git a/(\S+) b/(\S+)$", text, re.M)
    require(len(paths) == len(expected) and {a for a, b in paths if a == b} == set(expected),
            "exact application scope required; no ignored files or renames")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(HERE)}
    command = ["git", "apply", "--verbose", "--whitespace=error", "-"]
    for check_only in (True, False):
        result = subprocess.run(command + (["--check"] if check_only else []), input=text,
                                text=True, cwd=tree, env=env, capture_output=True)
        log = result.stdout + result.stderr
        require(result.returncode == 0, "exact patch application failed: " + log)
        require(not re.search(r"offset|fuzz|Skipped patch", log, re.I), "offset/fuzz/skipped application rejected: " + log)
        for path in expected:
            require("Checking patch " + path in log, "application did not check: " + path)
    for path, content in expected.items():
        require((tree / path).read_bytes() == content.encode(), "actual applied bytes differ: " + path)


def combined_contract(gen, files, md_after):
    code = files[CFILE]
    c = compact(code)
    helper = files[ADOPT]
    require(helper == md_after[ADOPT] and files[DATA] == md_after[DATA], "camera must not change MD helper/data")
    for token in ("structmt6878_md_adoption*md_adoption;", "ret=mt6878_md_adopt_init(pd,node);if(ret)gotoerr_put_subsys_clocks;",
                  "pd->genpd.power_on=mt6878_md_adopt_transition;", "pd->genpd.power_off=mt6878_md_adopt_transition;",
                  "pd->genpd.attach_dev=mt6878_md_adopt_attach;", "pd->genpd.detach_dev=mt6878_md_adopt_detach;"):
        require(token in c, "MD adoption missing from combined native provider: " + token)
    require("if(MTK_SCPD_CAPS(pd,MTK_SCPD_MT6878_MD)){ret=pm_genpd_init(&pd->genpd,NULL,"
            "pd->md_adoption->state==MT6878_MD_FIRST_OFF_COMPLETE);"
            "if(ret){mt6878_md_first_off_publication_fault(scpsys,ret);gotoerr_put_subsys_clocks;}"
            "}elseif(MTK_SCPD_CAPS(pd,MTK_SCPD_KEEP_DEFAULT_OFF))" in c,
            "MD measured-state genpd init/error chain must survive camera insertion")
    require("err_cleanup_domains:mt6878_md_first_off_publication_fault(scpsys,ret);"
            "if(scpsys_vmm_retain(scpsys,ret))return0;" in c,
            "retain the first MD publication error before camera cleanup")
    require("if(!MTK_SCPD_CAPS(pd,MTK_SCPD_MT6878_MD)&&scpsys_domain_is_on(pd))" in c,
            "combined cleanup must retain the MD shutdown veto")
    require("if(scpsys_vmm_domain(scpsys,id)){pd->genpd.power_off=scpsys_vmm_off;"
            "pd->genpd.power_on=scpsys_vmm_on;}else#endif"
            "if(MTK_SCPD_CAPS(pd,MTK_SCPD_MT6878_MD)){pd->genpd.power_off=mt6878_md_adopt_transition;"
            "pd->genpd.power_on=mt6878_md_adopt_transition;pd->genpd.attach_dev=mt6878_md_adopt_attach;"
            "pd->genpd.detach_dev=mt6878_md_adopt_detach;}" in c,
            "camera and MD callbacks must retain their separate predicates in one chain")
    require("if(scpsys_vmm_domain(pd->scpsys,pd->vmm_id)){}else#endif"
            "if(!MTK_SCPD_CAPS(pd,MTK_SCPD_MT6878_MD)&&scpsys_domain_is_on(pd))" in c,
            "camera cleanup skip must precede the unchanged MD cleanup exclusion")
    require("mt6878_md_cleanup" not in c and "mt6878_md_power_on" not in c and "md_owned" not in c,
            "legacy MD transition ownership must not return")
    transition = compact(gen.trace.body_after(helper, "static int mt6878_md_adopt_transition("))
    require(transition == "structmt6878_md_adoption*owner=to_scpsys_domain(genpd)->md_adoption;intret;"
            "mutex_lock(&owner->lock);ret=owner->first_error?owner->first_error:-EOPNOTSUPP;"
            "mutex_unlock(&owner->lock);returnret;", "actual MD power transition veto must remain")
    attach = compact(gen.trace.body_after(helper, "static int mt6878_md_adopt_attach("))
    require("dev->bus!=&platform_bus_type" in attach and "dev->of_node!=owner->modem" in attach and
            attach.index("mt6878_md_adopt_revalidate(pd,owner)") < attach.index("get_device(dev)"),
            "real MD attach validation must precede publication")
    require("mt6878_md_adopt_fault(owner,ret)" in attach, "MD attach must retain its original fault")
    first_off = gen.function(helper, "static int mt6878_md_first_off(struct scpsys_domain *pd,\n"
                                     "\t\t\t     struct mt6878_md_adoption *owner)\n")
    remainder = compact(helper.replace(first_off, "", 1))
    require(not re.search(r"\b(?:regmap_(?:write|raw_write|bulk_write|update_bits\w*|set_bits|clear_bits)|"
                          r"arm_smccc_\w+|writel\w*|iowrite\w*|regulator_\w+|clk_\w+)\s*\(", remainder),
            "MD writes must remain restricted to the explicit one-boot first-OFF transaction")
    operation = compact(first_off)
    require(not re.search(r"\b(?:regmap_(?:raw_write|bulk_write|update_bits\w*)|arm_smccc_\w+|"
                          r"writel\w*|iowrite\w*|regulator_\w+|clk_\w+)\s*\(", operation),
            "first-OFF may not gain secure, rail, clock or other write operations")
    for call in ("regmap_write(", "regmap_clear_bits(", "regmap_set_bits("):
        require(operation.count(call) == 1, "exact first-OFF write primitive count: " + call)
    require(operation.index("mt6878_md_first_off_profile(pd)") < operation.index("regmap_write("),
            "first-OFF profile must precede every mutation")
    require(operation.index("mt6878_md_first_off_readback(pd,owner->off)") <
            operation.index("owner->state=MT6878_MD_FIRST_OFF_COMPLETE"), "measured OFF must precede software OFF")
    for token in ("pd->genpd.power_on=scpsys_vmm_on;", "pd->genpd.power_off=scpsys_vmm_off;",
                  "pd->genpd.dev_ops.start=scpsys_vmm_start;", "pd->genpd.dev_ops.stop=scpsys_vmm_stop;",
                  "pd->genpd.domain.ops.runtime_resume=scpsys_vmm_resume;",
                  'scpsys_vmm_construct(scpsys);if(ret)gotoerr_cleanup_domains;ret=of_genpd_add_provider_onecell'):
        require(token in c, "VMM callback/construction missing from combined provider: " + token)
    require(c.count('#include"mt6878-native-vmm.inc"') == 1 and
            c.count('#include"mt6878-modem-pm.h"') == 1, "both integrations must enter the same provider exactly once")
    require("if(scpsys_vmm_retain(scpsys,ret))return0;" in c,
            "combined provider must retain partial VMM ownership")


def validate(gen, archive=None, vendor_repo=None, modules_repo=None):
    profile = load_profile(gen)
    native, patches = gen.native_inputs(archive, include_md=True)
    vendor = gen.vendor_inputs(vendor_repo, modules_repo)
    canonical = canonical_baseline(gen, native, vendor, patches)
    md_after, md_patch = stage_candidate(gen, native, profile)
    md_native = {p.removeprefix(PREFIX) if p.startswith(PREFIX) else p: c for p, c in md_after.items()}
    camera = gen.payload(md_native, vendor, md_on_adoption=profile)
    overlay = gen.patch_text(md_native, camera)
    expected = {**md_after, **camera}
    combined_contract(gen, expected, md_after)
    for path in camera:
        if path != CFILE:
            require(camera[path] == canonical[path], "MD profile must not alter other camera payloads: " + path)
    with tempfile.TemporaryDirectory(prefix=".md-composite-", dir=HERE) as directory:
        tree = Path(directory)
        for n, content in native.items():
            path = tree / gen.native_path(n)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        apply_exact(tree, md_patch, {p: md_after[p] for p in (CFILE, DATA, ADOPT)})
        apply_exact(tree, overlay, camera)
        actual = {str(p.relative_to(tree)): p.read_bytes().decode() for p in tree.rglob("*") if p.is_file()}
        require(actual == expected, "combined tree contains ignored/extra/missing files")
        combined_contract(gen, actual, md_after)
    report = dict(profile=profile["profile"], kernel_commit=gen.KERNEL, vendor_commit=gen.VENDOR,
                  modules_commit=gen.MODULES, profile_sha256=digest(PROFILE.read_bytes()),
                  canonical_camera_sha256=profile["canonical_camera_sha256"],
                  md_source_sha256=profile["md_source_sha256"], package_patch_sha256=patches,
                  pre_md_input_sha256=profile["pre_md_input_sha256"],
                  post_md_input_sha256=profile["post_md_input_sha256"],
                  camera_overlay_sha256=digest(overlay.encode()), combined_payload_sha256=hashes(expected),
                  native_provider_sha256=digest(expected[CFILE].encode()),
                  application_order=[MD_PATCH, str(OVERLAY.relative_to(gen.ROOT))],
                  config_variants=[{"KUNIT": "y"}, {"KUNIT": "n"}],
                  validation="actual exact MD application then camera application; shared-provider source checks only",
                  compiled=False, hardware_tested=False, activation="none; camera selector still default n")
    report["report_sha256"] = digest(json.dumps(report, sort_keys=True, separators=(",", ":")).encode())
    return overlay, report, expected, md_after


def check_prepared(tree, md_after, expected):
    for path, text in md_after.items():
        require((tree / path).is_file(), "prepared MD baseline file is missing: " + path)
        require((tree / path).read_bytes() == text.encode(), "prepared tree is not the exact MD-applied baseline: " + path)
    for path in set(expected) - set(md_after):
        require(not (tree / path).exists(), "prepared tree already contains camera payload: " + path)


def run(args, generator):
    require(not args.ci_apply or (args.prepared_kernel and not args.write and
            os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true"),
            "--ci-apply requires --prepared-kernel, no --write, CI=true and GITHUB_ACTIONS=true")
    overlay, report, expected, md_after = validate(generator, args.kernel_archive, args.vendor_repo, args.modules_repo)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.write:
        require(not args.prepared_kernel, "artifact generation must not mutate or depend on a prepared tree")
        OVERLAY.write_text(overlay)
        REPORT.write_text(serialized)
    require(OVERLAY.read_text() == overlay and REPORT.read_text() == serialized, "MD composite overlay/report drift")
    if args.prepared_kernel:
        tree = args.prepared_kernel
        check_prepared(tree, md_after, expected)
        if args.ci_apply:
            apply_exact(tree, overlay, {p: expected[p] for p in expected if p not in md_after or expected[p] != md_after[p]})
            for path, text in expected.items():
                require((tree / path).read_bytes() == text.encode(), "prepared combined output differs: " + path)
    print("MD-first/camera-second exact application and shared provider checks passed; no compilation")
    print("overlay_sha256=" + report["camera_overlay_sha256"])
    print("native_provider_sha256=" + report["native_provider_sha256"])
    print("report_sha256=" + report["report_sha256"])
