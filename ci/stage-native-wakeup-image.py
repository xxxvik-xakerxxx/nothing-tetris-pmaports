#!/usr/bin/env python3
"""Keep wakeup-source APIs while vetoing sleep during the retained MD experiment."""
import difflib
import hashlib
from pathlib import Path

PATCH = "0187-native-modem-wakeup-sleep-veto.patch"
HEADER = "drivers/pmdomain/mediatek/mt6878-modem-adopt.h"
SLEEP_API = ("SUSPEND", "PM_SLEEP", "PM_SLEEP_SMP")
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
                               "#include <linux/delay.h>\n#include <linux/suspend.h>\n#include <linux/limits.h>\n")
    after = parent.change_once(after, "static struct mt6878_md_adoption *mt6878_md_first_off_owner;\n",
                               "static struct mt6878_md_adoption *mt6878_md_first_off_owner;\n" + VETO)
    after = parent.change_once(after,
        "if (IS_ENABLED(CONFIG_CPU_IDLE) || IS_ENABLED(CONFIG_PM_SLEEP) ||\n"
        "\t    IS_ENABLED(CONFIG_SUSPEND) || IS_ENABLED(CONFIG_HIBERNATION) ||",
        "if (IS_ENABLED(CONFIG_CPU_IDLE) || !IS_ENABLED(CONFIG_PM_SLEEP) ||\n"
        "\t    !IS_ENABLED(CONFIG_SUSPEND) || IS_ENABLED(CONFIG_HIBERNATION) ||")
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
        "\t/* Non-devm owner and references survive every failure after the first write. */")
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
    native["sleep_policy"] = "permanent PM prepare veto registered before MD writes; transition mutex trylock"
    return native
