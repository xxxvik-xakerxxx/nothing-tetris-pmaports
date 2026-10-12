#!/usr/bin/env python3
"""Generate/apply a native provider patch from pinned sources; never compile."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
POWER = HERE.parent / "power"
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
KERNEL = "d84b264a54a37611f2f46bc19363cb9b41606205"
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
DEST = "drivers/pmdomain/mediatek/"
BINDING = "Documentation/devicetree/bindings/power/mediatek,power-controller.yaml"
spec = importlib.util.spec_from_file_location("native_trace", POWER / "trace.py")
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("absent/ambiguous native source anchor: " + old[:100])
    return text.replace(old, new, 1)


def function(text, signature):
    body = trace.body_after(text, signature)
    return signature + "{" + body + "}"


def native_path(name):
    return name if name == BINDING else DEST + name


def native_inputs():
    archive = ROOT.parent / ("linux-" + KERNEL + ".tar.gz")
    apk = (PACKAGE / "APKBUILD").read_text()
    expected = trace.one(r"^([0-9a-f]{128})  linux-postmarketos-mediatek-mt6878-" +
                         KERNEL + r"\.tar\.gz$", apk)
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != expected:
            raise ValueError("kernel archive checksum mismatch")
    # Apply the provider's actual package order, including parent-owned changes.
    patches = []
    for name in re.findall(r"^\s+(\S+\.patch)$", apk, re.M):
        data = (PACKAGE / name).read_bytes().decode("latin1")
        if re.search(r"^\+\+\+ b/drivers/pmdomain/mediatek/", data, re.M) or (
                "+++ b/" + BINDING) in data:
            patches.append(name)
    paths = {DEST + n for n in ("mtk-pm-domains.c", "mtk-pm-domains.h", "Makefile", "Kconfig")}
    paths.add(BINDING)
    for name in patches:
        paths.update(re.findall(r"^\+\+\+ b/(.+)$", (PACKAGE / name).read_bytes().decode("latin1"), re.M))
    files = {}
    prefix = "linux-" + KERNEL + "/"
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            path = member.name.removeprefix(prefix)
            if path in paths and member.isfile():
                files[path] = tar.extractfile(member).read()
    with tempfile.TemporaryDirectory(prefix="camisp-native-") as directory:
        tree = Path(directory)
        for path, content in files.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        for name in patches:
            applied = subprocess.run([
                "git", "apply", "--include=drivers/pmdomain/mediatek/*",
                "--include=include/dt-bindings/power/mediatek,mt6878-power.h",
                "--include=" + BINDING,
                str(PACKAGE / name)], cwd=tree, capture_output=True)
            if applied.returncode:
                raise ValueError(name + ": " + applied.stderr.decode())
        native = {n: (tree / native_path(n)).read_text()
                  for n in ("mtk-pm-domains.c", "mtk-pm-domains.h", "Makefile", "Kconfig", BINDING)}
    return native, {n: hashlib.sha256((PACKAGE / n).read_bytes()).hexdigest() for n in patches}


def vendor_inputs():
    repo = ROOT.parent / trace.VENDOR_REPO
    files = {}
    for path in ("drivers/soc/mediatek/mtk-scpsys-mt6878.c",
                 "drivers/soc/mediatek/mtk-scpsys.c", "arch/arm64/boot/dts/mediatek/mt6878.dts",
                 "drivers/misc/mediatek/vmm_spm/mtk-vmm-spm.c",
                 "drivers/misc/mediatek/vmm/mtk-vmm-notifier.c",
                 "drivers/soc/mediatek/mtk-mmdvfs-v3.c"):
        files[path] = subprocess.check_output(["git", "-C", str(repo), "show", VENDOR + ":" + path])
    for path in ("mtkcam/camsys/isp7sp/cam/mtk_cam.c",
                 "mtkcam/camsys/isp7sp/cam/mtk_cam-larb.c"):
        files["modules:" + path] = subprocess.check_output([
            "git", "-C", str(ROOT.parent / "android_kernel_modules_nothing_mt6878"),
            "show", MODULES + ":" + path])
    return files


def verify_vendor_contract(files):
    dts = files["arch/arm64/boot/dts/mediatek/mt6878.dts"].decode()
    soc = files["drivers/soc/mediatek/mtk-scpsys-mt6878.c"].decode()
    for name in ("cam-vcore", "isp-vcore"):
        if trace.one(re.escape(name) + r"-supply = <&(\w+)>;", dts) != "mt6319_6_vbuck1":
            raise ValueError("B4.1 CAM/ISP rail relationship drift")
    if dts.count("vmm-pmic-supply = <&mt6319_6_vbuck1>;") != 2:
        raise ValueError("B4.1 independent VMM/MMDVFS rail user drift")
    pmic = trace.body_after(dts, "mt6319_6: mt6319@6")
    buck = trace.body_after(pmic, "mt6319_6_vbuck1: 6-vbuck1")
    if "reg = <0x6 SPMI_USID>;" not in pmic or 'regulator-compatible = "vbuck1";' not in buck:
        raise ValueError("B4.1 USID-6 VBUCK1 identity drift")
    for parent, child in (("MM_INFRA", "CAM_VCORE"), ("MM_INFRA", "ISP_VCORE"), ("CAM_VCORE", "CAM_MAIN")):
        if f"{{MT6878_POWER_DOMAIN_{parent}, MT6878_POWER_DOMAIN_{child}}}" not in soc:
            raise ValueError("B4.1 native parent relationship drift")
    if "pm_runtime_resume_and_get(cam->dev)" not in files["modules:mtkcam/camsys/isp7sp/cam/mtk_cam.c"].decode():
        raise ValueError("pinned camera consumer runtime-PM route drift")


def payload(native, vendor):
    leaf = (POWER / "mt6878-cam-power.c").read_text()
    supplier = (POWER / "mt6878-vmm-supplier.c").read_text()
    leaf_sig = "int mt6878_cam_ctl_set(struct regmap *spm, unsigned int domain, bool on)\n"
    isp_leaf = function(leaf, leaf_sig)
    isp_leaf = replace_once(isp_leaf, "mt6878_cam_ctl_set", "mt6878_isp_vcore_ctl_set")
    isp_leaf = replace_once(isp_leaf,
        "domain != MT6878_POWER_DOMAIN_CAM_MAIN &&\n\t    domain != MT6878_POWER_DOMAIN_CAM_VCORE",
        "domain != MT6878_POWER_DOMAIN_ISP_VCORE")
    soc = vendor["drivers/soc/mediatek/mtk-scpsys-mt6878.c"].decode()
    isp = trace.body_after(soc, "[MT6878_POWER_DOMAIN_ISP_VCORE]")
    offset = int(trace.one(r"\.ctl_offs = (0x\w+)", isp), 16)
    isp_leaf = replace_once(isp_leaf, "offset = mt6878_cam_domain_data[domain].ctl_offs;",
                            f"offset = 0x{offset:04x};")
    supplier_sig = ("int mt6878_vmm_cam_ctl_set(struct mt6878_vmm_supplier *vmm,\n"
                    "\t\t\t   unsigned int domain, bool on)\n")
    isp_supplier = function(supplier, supplier_sig)
    isp_supplier = isp_supplier.replace("mt6878_vmm_cam_ctl_set", "mt6878_vmm_isp_vcore_ctl_set")
    isp_supplier = replace_once(isp_supplier,
        "domain != MT6878_POWER_DOMAIN_CAM_MAIN &&\n\t    domain != MT6878_POWER_DOMAIN_CAM_VCORE",
        "domain != MT6878_POWER_DOMAIN_ISP_VCORE")
    isp_supplier = replace_once(isp_supplier, "mt6878_cam_ctl_set(vmm->spm, domain, on)",
                                "mt6878_isp_vcore_ctl_set(vmm->spm, domain, on)")
    table = "static const struct scpsys_domain_data\nscpsys_vmm_data[MT6878_POWER_DOMAIN_NR] = {\n"
    for name in ("CAM_VCORE", "CAM_MAIN"):
        desc = trace.body_after(leaf, "[MT6878_POWER_DOMAIN_" + name + "]")
        desc = desc.replace(" | MTK_SCPD_DOMAIN_SUPPLY", "")
        table += "\t[MT6878_POWER_DOMAIN_" + name + "] = {" + desc + "},\n"
    table += ("\t[MT6878_POWER_DOMAIN_ISP_VCORE] = {\n\t\t.name = \"isp-vcore\",\n"
              "\t\t.sta_mask = GENMASK(31, 30),\n" +
              "".join(f"\t\t.{key} = 0x{offset:04x},\n" for key in
                      ("ctl_offs", "pwr_sta_offs", "pwr_sta2nd_offs")) + "\t\t.bp_cfg = {\n")
    for set_, clr, _, sta, mask in re.findall(
            r"BUS_PROT_IGN\(IFR_TYPE,\s*(0x\w+),\s*(0x\w+),\s*(0x\w+),\s*(0x\w+),\s*(\w+)\)", isp):
        definition = trace.one(r"^#define " + mask + r"\s+([^\n]+)", soc)
        table += ("\t\t\tBUS_PROT_WR_IGN(INFRA, " + definition + ",\n" +
                  f"\t\t\t\t\t{set_.lower()}, {clr.lower()}, {sta.lower()}),\n")
    table += "\t\t},\n\t\t.caps = MTK_SCPD_STATUS_IN_CTL,\n\t},\n};\n\n"
    result = {DEST + "native-vmm/" + n: (POWER / n).read_text()
              for n in ("mt6878-cam-power.h", "mt6878-vmm-supplier.h")}
    for name, code, extension in (("mt6878-cam-power.c", leaf, isp_leaf),
                                  ("mt6878-vmm-supplier.c", supplier, isp_supplier)):
        result[DEST + "native-vmm/" + name] = (
            code + '\n#include "mt6878-native-vmm.h"\n\n' + extension + "\n")
    result[DEST + "native-vmm/mt6878-native-vmm.h"] = (HERE / "mt6878-native-vmm.h").read_text()
    result[DEST + "native-vmm/Makefile"] = (
        "# SPDX-License-Identifier: GPL-2.0-only\n"
        "ccflags-y += -I$(srctree)/drivers/pmdomain/mediatek\n"
        "obj-y += mt6878-cam-power.o mt6878-vmm-supplier.o\n")
    result[DEST + "mt6878-native-vmm.inc"] = replace_once(
        (HERE / "mt6878-native-vmm.inc").read_text(),
        '#include "native-vmm/mt6878-native-vmm.h"\n',
        '#include "native-vmm/mt6878-native-vmm.h"\n\n' + table)
    code = native["mtk-pm-domains.c"]
    code = replace_once(code, "struct scpsys_domain {", "struct scpsys_vmm;\n\nstruct scpsys_domain {")
    code = replace_once(code, "\tstruct regmap *hwv;\n", "\tstruct regmap *hwv;\n"
                        "\tunsigned int vmm_id;\n\tint (*native_runtime_resume)(struct device *dev);\n")
    code = replace_once(code, "\tstruct genpd_onecell_data pd_data;\n",
                         "\tstruct genpd_onecell_data pd_data;\n\tstruct scpsys_vmm *vmm;\n")
    code = replace_once(code, "static struct\ngeneric_pm_domain *scpsys_add_one_domain",
                         '#include "mt6878-native-vmm.inc"\n\nstatic struct\n'
                         "generic_pm_domain *scpsys_add_one_domain")
    code = replace_once(code, "\tdomain_data = &scpsys->soc_data->domains_data[id];\n",
                         "\tdomain_data = &scpsys->soc_data->domains_data[id];\n"
                         "#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)\n"
                         "\tif (scpsys_vmm_domain(scpsys, id))\n\t\tdomain_data = &scpsys_vmm_data[id];\n"
                         "#endif\n")
    code = replace_once(code, "\tpd->scpsys = scpsys;\n", "\tpd->scpsys = scpsys;\n\tpd->vmm_id = id;\n")
    # Restrict replacements to add_one_domain, avoiding cleanup's modem branch.
    start = code.index("static struct\ngeneric_pm_domain *scpsys_add_one_domain")
    end = code.index("static int scpsys_add_subdomain", start)
    add = code[start:end]
    if "scpsys_vmm_observe_off(pd)" not in add:
        add = replace_once(add, "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n\t\tif (pd->num_clks",
                           "#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)\n"
                           "\tif (scpsys_vmm_domain(scpsys, id)) {\n"
                           "\t\tret = scpsys_vmm_observe_off(pd);\n"
                           "\t\tif (ret)\n\t\t\tgoto err_put_subsys_clocks;\n"
                           "\t} else\n#endif\n\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n\t\tif (pd->num_clks")
    add = replace_once(add, "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n\t\tpd->genpd.power_off",
                       "#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)\n"
                       "\tif (scpsys_vmm_domain(scpsys, id)) {\n"
                       "\t\tpd->genpd.power_off = scpsys_vmm_off;\n"
                       "\t\tpd->genpd.power_on = scpsys_vmm_on;\n"
                       "\t} else\n#endif\n\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n\t\tpd->genpd.power_off")
    add = replace_once(add, "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_KEEP_DEFAULT_OFF))\n",
                       "#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)\n"
                       "\tif (scpsys_vmm_domain(scpsys, id)) {\n"
                       "\t\tret = pm_genpd_init(&pd->genpd, NULL, true);\n"
                       "\t\tif (ret)\n\t\t\tgoto err_put_subsys_clocks;\n"
                       "\t\tpd->native_runtime_resume = pd->genpd.domain.ops.runtime_resume;\n"
                       "\t\tpd->genpd.domain.ops.runtime_resume = scpsys_vmm_resume;\n"
                       "\t\tpd->genpd.dev_ops.start = scpsys_vmm_start;\n"
                       "\t\tpd->genpd.dev_ops.stop = scpsys_vmm_stop;\n"
                       "\t} else\n#endif\n\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_KEEP_DEFAULT_OFF))\n")
    code = code[:start] + add + code[end:]
    code = replace_once(code, "\tfor_each_child_of_node(parent, child) {\n\t\tu32 id;\n",
                         "\tfor_each_child_of_node(parent, child) {\n\t\tu32 id;\n\n"
                         "\t\tif (scpsys->vmm && !of_device_is_available(child))\n\t\t\tcontinue;\n")
    start = code.index("static void scpsys_remove_one_domain")
    end = code.index("static void scpsys_domain_cleanup", start)
    cleanup = code[start:end]
    cleanup = replace_once(cleanup, "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n",
                           "#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)\n"
                           "\tif (scpsys_vmm_domain(pd->scpsys, pd->vmm_id)) {\n"
                           "\t\t/* Observed OFF; never force a camera domain OFF in cleanup. */\n"
                           "\t} else\n#endif\n\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n")
    code = code[:start] + cleanup + code[end:]
    code = replace_once(code, "\tret = -ENODEV;\n\tfor_each_available_child_of_node(np, node) {\n",
                         "\tret = scpsys_vmm_prepare(scpsys);\n\tif (ret)\n\t\treturn ret;\n\n"
                         "\tret = -ENODEV;\n\tfor_each_available_child_of_node(np, node) {\n")
    code = replace_once(code, "\tret = of_genpd_add_provider_onecell(np, &scpsys->pd_data);\n",
                         "\tret = scpsys_vmm_construct(scpsys);\n\tif (ret)\n\t\tgoto err_cleanup_domains;\n\n"
                         "\tret = of_genpd_add_provider_onecell(np, &scpsys->pd_data);\n")
    code = replace_once(code, "err_cleanup_domains:\n\tscpsys_domain_cleanup(scpsys);\n",
                         "err_cleanup_domains:\n\tif (scpsys_vmm_retain(scpsys, ret))\n\t\treturn 0;\n"
                         "\tif (scpsys_vmm_unlink(scpsys)) {\n"
                         "\t\tscpsys_vmm_retain(scpsys, ret);\n\t\treturn 0;\n\t}\n"
                         "\tscpsys_domain_cleanup(scpsys);\n")
    result[DEST + "mtk-pm-domains.c"] = code
    result[DEST + "Makefile"] = native["Makefile"] + "\nobj-$(CONFIG_MTK_MT6878_NATIVE_VMM) += native-vmm/\n"
    result[DEST + "Kconfig"] = replace_once(native["Kconfig"], "endmenu\n", """config MTK_MT6878_NATIVE_VMM
	bool "MT6878 native shared VMM integration candidate"
	depends on MTK_SCPSYS_PM_DOMAINS && REGULATOR && OF
	default n
	help
	  Construct shared VMM under the existing MM_INFRA domain for CAM_VCORE,
	  CAM_MAIN and ISP_VCORE. Requires matching board supplies and clocks,
	  quiescent firmware ownership and voltage policy. Inherited ON or any
	  independent rail consumer is rejected. No board nodes are enabled.
	  Do not also link the standalone camera research objects.

endmenu
""")
    binding = replace_once(native[BINDING], "\npatternProperties:\n", """
  cam-vcore-supply:
    description:
      Shared CAM/ISP VMM rail. Must reference the same regulator as
      isp-vcore-supply; both VCORE domains use one exclusive shared owner.

  isp-vcore-supply:
    description:
      Shared CAM/ISP VMM rail. Must reference the same regulator as
      cam-vcore-supply; per-domain supply ownership must be migrated together.

patternProperties:
""")
    result[BINDING] = replace_once(binding, "\nallOf:\n", """
allOf:
  - if:
      anyOf:
        - required: [cam-vcore-supply]
        - required: [isp-vcore-supply]
    then:
      properties:
        compatible:
          const: mediatek,mt6878-power-controller
      required:
        - cam-vcore-supply
        - isp-vcore-supply
""")
    return result


def patch_text(native, files):
    result = []
    for path, text in files.items():
        original = native.get(path.removeprefix(DEST), "")
        result.append("diff --git a/" + path + " b/" + path + "\n")
        if not original:
            result.append("new file mode 100644\n")
        result.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
                      fromfile="a/" + path if original else "/dev/null", tofile="b/" + path))
    return "".join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    native, patches = native_inputs()
    vendor = vendor_inputs()
    verify_vendor_contract(vendor)
    files = payload(native, vendor)
    binding = yaml.safe_load(files[BINDING])
    required_pair = {"cam-vcore-supply", "isp-vcore-supply"}
    if not required_pair <= binding["properties"].keys() or set(binding["allOf"][0]["then"]["required"]) != required_pair:
        raise ValueError("paired native binding schema drift")
    text = patch_text(native, files)
    evidence = dict(kernel_commit=KERNEL, vendor_commit=VENDOR, modules_commit=MODULES,
                    package_patch_sha256=patches,
                    native_input_sha256={n: hashlib.sha256(c.encode()).hexdigest() for n, c in native.items()},
                    vendor_input_sha256={n: hashlib.sha256(c).hexdigest() for n, c in vendor.items()},
                    baseline_payload_sha256={n: hashlib.sha256((POWER / n).read_bytes()).hexdigest()
                                             for n in ("mt6878-cam-power.c", "mt6878-cam-power.h",
                                                       "mt6878-vmm-supplier.c", "mt6878-vmm-supplier.h")},
                    payload_sha256={n: hashlib.sha256(c.encode()).hexdigest() for n, c in files.items()},
                    patch_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    activation="none: patch not packaged, Kconfig default n, no DT enablement")
    serialized = json.dumps(evidence, indent=2) + "\n"
    if args.write:
        (HERE / "native-provider.patch").write_text(text)
        (HERE / "evidence.json").write_text(serialized)
    if (HERE / "native-provider.patch").read_text() != text or (HERE / "evidence.json").read_text() != serialized:
        raise ValueError("native provider patch/evidence drift")
    with tempfile.TemporaryDirectory(prefix="camisp-native-apply-") as directory:
        tree = Path(directory)
        for n, c in native.items():
            target = tree / native_path(n)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(c)
        subprocess.run(["git", "apply", "--check", "--whitespace=error", str(HERE / "native-provider.patch")],
                       cwd=tree, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(HERE / "native-provider.patch")],
                       cwd=tree, check=True, capture_output=True)
        for path, c in files.items():
            if (tree / path).read_text() != c:
                raise ValueError("applied payload mismatch: " + path)
    print(f"Pinned packaged provider hunks and native patch apply verified; {len(files)} kernel files; no compilation")


if __name__ == "__main__":
    main()
