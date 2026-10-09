#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Deterministic caller migration on exact frozen input; no shared-tree edits."""
import argparse
import difflib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_gpueb_owner_boundary import patched_source
from test_gpueb_session import MAILBOX, DRIVER
from test_supply_inventory import PATCHES, ROOT, new_file
from test_gpueb_power import require_exact_application


def replace_one(source, old, new):
    if source.count(old) != 1:
        raise ValueError("migration input changed: " + old[:90])
    return source.replace(old, new, 1)


def mailbox_source():
    kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
        ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
    text = (PATCHES / "0120-mailbox-mediatek-mt6878-gpueb-session.patch").read_text()
    chunk = "--- a/" + MAILBOX
    fragment = chunk + text.split(chunk, 1)[1].split("diff --git ", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / MAILBOX
        path.parent.mkdir(parents=True)
        path.write_text((kernel / MAILBOX).read_text())
        result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"], cwd=tmp,
                                input=fragment, text=True, capture_output=True)
        require_exact_application(result)
        return path.read_text()


def migrate_mailbox(source):
    source = replace_one(source, "#include <linux/platform_device.h>",
                         "#include <linux/platform_device.h>\n"
                         "#include <linux/soc/mediatek/mt6878-gpueb-adoption.h>")
    source = replace_one(source, "\tconst u8 num_channels;", "\tconst u8 num_channels;\n\tbool parent_owned;")
    source = replace_one(source, "\t.num_channels = 11,", "\t.num_channels = 11,\n\t.parent_owned = true,")
    source = replace_one(source, "static int mtk_gpueb_mbox_probe(struct platform_device *pdev)",
                         "static void mtk_gpueb_put_adopted_window(void *data)\n"
                         "{\n\tmt6878_gpueb_unadopt_window(data);\n}\n\n"
                         "static int mtk_gpueb_mbox_probe(struct platform_device *pdev)")
    source = replace_one(source, "\tebm->irq = platform_get_irq(pdev, 0);", """\t/* MT6878 SRAM must come from the explicit real remoteproc parent.
\t * No fallback to an overlapping independent claim, and no clock/MMIO
\t * operations until the real power/boot owner gate is implemented.
\t */
\tif (ebm->v->parent_owned) {
\t\tstruct mt6878_gpueb_adopted_window *window;
\t\tstruct resource *resource;
\t\tint ret;

\t\tresource = platform_get_resource(pdev, IORESOURCE_MEM, 0);
\t\twindow = mt6878_gpueb_adopt_window(pdev->dev.parent, resource,
\t\t\t\t\t\t GPUEB_WINDOW_MBOX);
\t\tif (IS_ERR(window))
\t\t\treturn PTR_ERR(window);
\t\tret = devm_add_action_or_reset(ebm->dev,
\t\t\t\t\t     mtk_gpueb_put_adopted_window, window);
\t\tif (ret)
\t\t\treturn ret;
\t\tret = mt6878_gpueb_adoption_io_gate(window);
\t\t/* The candidate gate always refuses: no actual MMIO backend yet.
\t\t * Never fall through to devm_platform_ioremap_resource for MT6878.
\t\t */
\t\treturn ret ? ret : -EOPNOTSUPP;
\t}

\tebm->irq = platform_get_irq(pdev, 0);""")
    return source


def migrate_session(source):
    source = replace_one(source, "#include <linux/soc/mediatek/mt6878-gpueb-session.h>",
                         "#include <linux/soc/mediatek/mt6878-gpueb-session.h>\n"
                         "#include <linux/soc/mediatek/mt6878-gpueb-adoption.h>")
    source = replace_one(source, "\tstruct resource *gpr_claim, *shared_claim;",
                         "\tstruct resource *shared_claim;\n"
                         "\tstruct mt6878_gpueb_adopted_window *gpr_lease;")
    source = replace_one(source, "\tif (s->gpr_claim)\n\t\trelease_mem_region(s->gpr_claim->start, resource_size(s->gpr_claim));",
                         "\tmt6878_gpueb_unadopt_window(s->gpr_lease);")
    start = source.index('\tres = platform_get_resource_byname(pdev, IORESOURCE_MEM, "gpueb_gpr_base");')
    end = source.index("\ts->boot_attempted = true;", start)
    source = source[:start] + """\tres = platform_get_resource_byname(pdev, IORESOURCE_MEM, "gpueb_gpr_base");
\ts->gpr_lease = mt6878_gpueb_adopt_window(s->rproc->dev.parent, res,
\t\t\t\t\t       GPUEB_WINDOW_GPR);
\tif (IS_ERR(s->gpr_lease)) {
\t\tret = PTR_ERR(s->gpr_lease);
\t\ts->gpr_lease = NULL;
\t\tgoto fail;
\t}
\t/* Parent lease replaces the conflicting GPR claim. Resource ownership
\t * alone is NOT permission to map/touch powered hardware or start GPUEB.
\t * The candidate gate is closed until an actual owner supplies that path.
\t */
\tret = mt6878_gpueb_adoption_io_gate(s->gpr_lease);
\tif (ret)
\t\tgoto fail;
\tret = -EOPNOTSUPP;
\tgoto fail;
""" + source[end:]
    # Keep the protocol implementation below the closed boundary for review;
    # enabling its path requires a separate real owner/transport migration.
    return source


def inputs_and_outputs():
    mailbox, session = mailbox_source(), patched_source()
    return {MAILBOX: (mailbox, migrate_mailbox(mailbox)),
            DRIVER: (session, migrate_session(session))}


def migration_patch():
    result = "From: Tetris Linux bring-up\nSubject: [CANDIDATE] adopt MT6878 SRAM parent leases; hardware gate closed\n\n"
    for path, (before, after) in inputs_and_outputs().items():
        result += "diff --git a/" + path + " b/" + path + "\n"
        result += "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                             "a/" + path, "b/" + path, n=3))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--session-header", type=Path)
    args = parser.parse_args()
    if args.stage:
        for path, (_, code) in inputs_and_outputs().items():
            output = args.stage / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(code)
    else:
        print(migration_patch(), end="")
    if args.session_header:
        args.session_header.write_text(new_file(
            (PATCHES / "0120-mailbox-mediatek-mt6878-gpueb-session.patch").read_text(),
            "include/linux/soc/mediatek/mt6878-gpueb-session.h"))
