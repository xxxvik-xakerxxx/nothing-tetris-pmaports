#!/usr/bin/env python3
"""Keep wakeup-source APIs while vetoing sleep during the retained MD experiment."""
import difflib
import hashlib
from pathlib import Path
import argparse

PATCH = "0187-native-modem-wakeup-sleep-veto.patch"
HEADER = "drivers/pmdomain/mediatek/mt6878-modem-adopt.h"
SLEEP_API = ("SUSPEND", "PM_SLEEP", "PM_SLEEP_SMP", "HOTPLUG_CPU")
VETO = """
/* Boot-lifetime diagnostic veto; wakeup-source accounting stays available. */
static int mt6878_md_sleep_veto(struct notifier_block *nb,
                              unsigned long event, void *unused)
{
\tif (event == PM_SUSPEND_PREPARE || event == PM_HIBERNATION_PREPARE ||
\t    event == PM_RESTORE_PREPARE)
\t\treturn notifier_from_errno(-EBUSY);
\treturn NOTIFY_DONE;
}

static struct notifier_block mt6878_md_sleep_notifier = {
\t.notifier_call = mt6878_md_sleep_veto,
\t.priority = INT_MAX,
};
"""


def patched_header(parent):
    before = parent.frozen("patches/modem/md-pm-integration/mt6878-modem-adopt.h").decode()
    after = parent.change_once(before, "#include <linux/delay.h>\n",
                               "#include <linux/delay.h>\n#include <linux/suspend.h>\n#include <linux/limits.h>\n#include <linux/cpu.h>\n")
    after = parent.change_once(after, "static struct mt6878_md_adoption *mt6878_md_first_off_owner;\n",
                               "static struct mt6878_md_adoption *mt6878_md_first_off_owner;\n" + VETO)
    after = parent.change_once(after,
        "if (IS_ENABLED(CONFIG_CPU_IDLE) || IS_ENABLED(CONFIG_PM_SLEEP) ||\n"
        "\t    IS_ENABLED(CONFIG_SUSPEND) || IS_ENABLED(CONFIG_HIBERNATION) ||",
        "if (IS_ENABLED(CONFIG_CPU_IDLE) || !IS_ENABLED(CONFIG_PM_SLEEP) ||\n"
        "\t    !IS_ENABLED(CONFIG_SUSPEND) || IS_ENABLED(CONFIG_HIBERNATION) ||")
    after = parent.change_once(after, "IS_ENABLED(CONFIG_HOTPLUG_CPU) || IS_ENABLED(CONFIG_MTK_DVFSRC)",
                               "!IS_ENABLED(CONFIG_HOTPLUG_CPU) || IS_ENABLED(CONFIG_MTK_DVFSRC)")
    after = parent.change_once(after,
        "\tu32 value;\n\tunsigned int i;\n\tint ret;\n\n\tmutex_lock(&mt6878_md_first_off_lock);",
        "\tu32 value;\n\tunsigned int i;\n\tint ret;\n\tbool transition_locked = false;\n\n"
        "\tmutex_lock(&mt6878_md_first_off_lock);")
    after = parent.change_once(after,
        "\tret = mt6878_md_first_off_profile(pd);\n\tif (!ret)\n"
        "\t\tret = mt6878_md_adopt_revalidate(pd, owner);",
        "\t/* Never wait behind a concurrent suspend/reboot that may wait for probe. */\n"
        "\tif (!mutex_trylock(&system_transition_mutex)) {\n\t\tret = -EBUSY;\n\t\tgoto out;\n\t}\n"
        "\ttransition_locked = true;\n\tret = mt6878_md_first_off_profile(pd);\n\tif (!ret)\n"
        "\t\tret = mt6878_md_adopt_revalidate(pd, owner);")
    after = parent.change_once(after,
        "\t/* Non-devm owner and references survive every failure after the first write. */",
        "\t/* Install under the transition lock before any hardware write. Retain\n"
        "\t * the static notifier through success, failure and provider teardown.\n\t */\n"
        "\tret = register_pm_notifier(&mt6878_md_sleep_notifier);\n\tif (ret)\n\t\tgoto out;\n\n"
        "\t/* PM_SLEEP_SMP selects HOTPLUG_CPU. Retain its API but prohibit\n"
        "\t * CPU up/down through the real boot-lifetime hotplug-disable owner.\n\t */\n"
        "\tcpu_hotplug_disable();\n\n"
        "\t/* Non-devm owner and references survive every failure after the first write. */")
    after = parent.change_once(after,
        "\tmt6878_md_first_off_owner = owner;\n\tfor (i = 0; i < 3; i++) {",
        "\tmt6878_md_first_off_owner = owner;\n"
        "\tif (!cpumask_equal(cpu_online_mask, cpu_present_mask)) {\n"
        "\t\tret = -EBUSY;\n\t\tgoto fault;\n\t}\n\tfor (i = 0; i < 3; i++) {")
    after = parent.change_once(after,
        "out:\n\tmutex_unlock(&mt6878_md_first_off_lock);\n\treturn ret;\n}",
        "out:\n\tif (transition_locked)\n\t\tmutex_unlock(&system_transition_mutex);\n"
        "\tmutex_unlock(&mt6878_md_first_off_lock);\n\treturn ret;\n}")
    return before, after


def patch_text(parent):
    before, after = patched_header(parent)
    return ("From: Tetris port maintainers\n"
            "Subject: [DIAGNOSTIC PATCH] keep PM wakeup sources, veto actual sleep\n\n"
            "PM_SLEEP=n makes wakeup_source_register return NULL. Sensorhub fails\n"
            "ENOMEM and conninfra dereferences its absent wake lock. Keep the APIs;\n"
            "retain a PM prepare veto and exclude concurrent system transitions.\n\n"
            "diff --git a/" + HEADER + " b/" + HEADER + "\n" +
            "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        fromfile="a/" + HEADER, tofile="b/" + HEADER)))


def extend(parent, tree, native, revision):
    package = tree / parent.KERNEL
    apk = (package / "APKBUILD").read_text()
    apk = parent.change_once(apk, "pkgrel=" + native["kernel_package"].split("-r")[1] + "\n",
                             f"pkgrel={revision}\n")
    apk = parent.change_once(apk, "\t0184-native-modem-single-ack.patch\n",
                             "\t0184-native-modem-single-ack.patch\n\t" + PATCH + "\n")
    excluded = tuple(symbol for symbol in parent.DISABLED if symbol not in SLEEP_API)
    apk = parent.change_once(apk, "\tfor _symbol in " + " ".join(parent.DISABLED) + "; do\n",
                             "\tfor _symbol in " + " ".join(excluded) + "; do\n")
    apk = parent.change_once(apk, "\tfor _symbol in " + " ".join(parent.ENABLED) + "; do\n",
                             "\tfor _symbol in " + " ".join(parent.ENABLED + SLEEP_API) + "; do\n")
    config = package / "config-postmarketos-mediatek-mt6878.aarch64"
    configured = config.read_text()
    for symbol in SLEEP_API:
        configured = parent.change_once(configured, "# CONFIG_" + symbol + " is not set\n",
                                         "CONFIG_" + symbol + "=y\n")
    data = patch_text(parent).encode()
    destination = package / PATCH
    if destination.exists() or destination.is_symlink():
        raise ValueError("wakeup extension already staged")
    destination.write_bytes(data)
    (package / "APKBUILD").write_text(apk)
    config.write_text(configured)
    native["kernel_package"] = f"7.2.1-r{revision}"
    native["changes"][PATCH] = hashlib.sha256(data).hexdigest()
    native["wakeup_source_apis_enabled"] = True
    native["sleep_policy"] = "permanent PM prepare veto before MD writes; transition mutex trylock"
    native["hotplug_policy"] = "boot-lifetime cpu_hotplug_disable before writes; all present CPUs required online"
    return native


def check_kernel(kernel):
    kconfig = (kernel / "kernel/power/Kconfig").read_text()
    selected = kconfig.split("config PM_SLEEP_SMP\n", 1)[1].split("\nconfig ", 1)[0]
    if "depends on PM_SLEEP" not in selected or "select HOTPLUG_CPU" not in selected:
        raise ValueError("pinned sleep/hotplug Kconfig dependency changed")
    cpu = (kernel / "kernel/cpu.c").read_text()
    disable = cpu.split("void cpu_hotplug_disable(void)\n", 1)[1].split("\n}", 1)[0]
    positions = [disable.index(token) for token in (
        "cpu_maps_update_begin();", "cpu_hotplug_disabled++;", "cpu_maps_update_done();")]
    if positions != sorted(positions) or "EXPORT_SYMBOL_GPL(cpu_hotplug_disable);" not in cpu:
        raise ValueError("pinned CPU hotplug owner changed")
    wakeup = (kernel / "include/linux/pm_wakeup.h").read_text()
    stub = wakeup.split("static inline struct wakeup_source *wakeup_source_register", 1)[1].split("\n}", 1)[0]
    if "return NULL;" not in stub:
        raise ValueError("pinned disabled wakeup-source ABI changed")
    suspend = (kernel / "kernel/power/suspend.c").read_text()
    prepare = suspend.split("static int suspend_prepare(suspend_state_t state)\n", 1)[1].split("\n}", 1)[0]
    if prepare.index("pm_notifier_call_chain_robust") >= prepare.index("suspend_freeze_processes"):
        raise ValueError("PM veto must run before process/device suspension")
    print("Pinned PM wakeup, sleep/hotplug dependency and pre-freeze veto contracts pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-kernel", type=Path, required=True)
    check_kernel(parser.parse_args().check_kernel)
