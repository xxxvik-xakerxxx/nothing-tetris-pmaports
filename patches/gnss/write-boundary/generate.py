#!/usr/bin/env python3
"""Stage a deterministic TX extension against pinned, package-stacked blobs."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location(
    "gnss_read_spans", HERE.parent / "read-boundary/generate.py")
read = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = read
spec.loader.exec_module(read)
PIN, MODULES, PACKAGE, BASE = read.PIN, read.MODULES, read.PACKAGE, read.BASE
DEVICE, LINK, DMA = read.DEVICE, read.LINK, read.DMA
LINK_H = BASE + "inc/gps_each_link.h"
SOURCES = (DEVICE, LINK, LINK_H)
PATCH = HERE / "1009-vendor-gnss-nonblocking-data-link-write.patch.vendor"
Span, function_span, unique_span = read.Span, read.function_span, read.unique_span
HELPER = "gps_each_link_write_with_options"
PROTOTYPE = ("int " + HELPER + "(enum gps_dl_link_id_enum link_id,\n"
             "\tunsigned char *buf, unsigned int len, bool wait_tx_done, bool nonblocking)")
OLD_SIGNATURE = ("int gps_each_link_write_with_opt(enum gps_dl_link_id_enum link_id,\n"
                 "\tunsigned char *buf, unsigned int len, bool wait_tx_done)")
WRAPPER = (OLD_SIGNATURE + "\n{\n"
           "\treturn " + HELPER + "(link_id, buf, len, wait_tx_done, false);\n}\n\n")
ZERO_DEVICE = "\tif (!count)\n\t\treturn 0;\n\n"
BOUND = "\tif (count > sizeof(dev->o_buf))\n\t\tcount = sizeof(dev->o_buf);\n"
ZERO_LINK = "\tif (nonblocking && !len)\n\t\treturn 0;\n\n"
QUEUED = "\t\t\tif (nonblocking)\n\t\t\t\treturn 0;\n"
UNAVAILABLE = "\t\t\tif (nonblocking)\n\t\t\t\treturn -EAGAIN;\n\n"


def source(path, modules=MODULES):
    return read.source(path, modules)


def stack():
    patches = sorted(PACKAGE.glob("100[1-8]-*.patch.vendor"))
    if [p.name[:4] for p in patches] != [str(n) for n in range(1001, 1009)]:
        raise ValueError("expected exactly package patches 1001..1008")
    manifest = json.loads((HERE / "STAGING.json").read_text())
    actual = {p.name: hashlib.sha512(p.read_bytes()).hexdigest() for p in patches}
    if manifest["connectivity_commit"] != PIN or manifest["prerequisite_sha512"] != actual:
        raise ValueError("prerequisite stack or source pin drifted")
    return patches


def checked(argv, cwd):
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(cwd).parent), LC_ALL="C")
    result = subprocess.run(argv, cwd=cwd, env=env, text=True,
                            capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError(f"{argv}:\n{result.stdout}{result.stderr}")
    return result.stdout + result.stderr


def populate(directory, modules=MODULES):
    """Match package preparation, including its existing clock CRLF cleanup."""
    paths = set(SOURCES) | {DMA, read.DEVICE_H, read.DMA_H, read.STATUS_H}
    added = set()
    for patch in stack():
        text = patch.read_text()
        paths.update(re.findall(r"^--- a/(.+)$", text, re.M))
        added.update(re.findall(r"^--- /dev/null\n\+\+\+ b/(.+)$", text, re.M))
    for path in sorted(paths - added):
        dest = Path(directory) / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source(path, modules))
    for patch in stack():
        if patch.name.startswith("1005-"):
            clock = Path(directory) / (BASE + "linux/gps_dl_linux_clock_mng.c")
            clock.write_bytes(clock.read_bytes().replace(b"\r\n", b"\n"))
        output = checked([os.environ.get("TETRIS_GNU_PATCH", "patch"),
                          "--batch", "--fuzz=0", "-p1", "-i", str(patch)], directory)
        if re.search(r"fuzz", output, re.I):
            raise ValueError(output)


def stacked(modules=MODULES):
    with tempfile.TemporaryDirectory(prefix="stack-", dir=HERE) as directory:
        populate(directory, modules)
        result = {p: (Path(directory) / p).read_bytes().decode() for p in (*SOURCES, DMA)}
        manifest = json.loads((HERE / "STAGING.json").read_text())
        actual = {p: hashlib.sha512(t.encode()).hexdigest() for p, t in result.items()}
        if manifest["stacked_source_sha512"] != actual:
            raise ValueError("exact package-stacked source drifted")
        return result


def transform(path, text):
    if path == DEVICE:
        span = function_span(text, "gps_each_device_write")
        body = span.text(text)
        if "if (!count)" in body or "O_NONBLOCK" in body:
            raise ValueError("device write already patched or drifted")
        dev = unique_span(text, "\tdev = (struct gps_each_device *)filp->private_data;\n", span)
        old_bound = unique_span(text,
            "\t\tif (count > GPS_DATA_PATH_BUF_MAX) {\n"
            '\t\t\tGDL_LOGXW_DRW(link_id, "len = %ld is too long", count);\n'
            "\t\t\tcopy_size = GPS_DATA_PATH_BUF_MAX;\n"
            "\t\t} else\n\t\t\tcopy_size = count;", span)
        call = unique_span(text,
            "\t\t\tretval = gps_each_link_write(link_id, &dev->o_buf[0], copy_size);", span)
        return read.edit_spans(text, [
            (Span(dev.start, dev.start), ZERO_DEVICE),
            (Span(dev.end, dev.end), BOUND),
            (old_bound, "\t\tcopy_size = count;"),
            (call, "\t\t\tif (filp->f_flags & O_NONBLOCK)\n"
             "\t\t\t\tretval = " + HELPER + "(link_id,\n"
             "\t\t\t\t\t&dev->o_buf[0], copy_size, true, true);\n"
             "\t\t\telse\n\t" + call.text(text))])
    if path == LINK:
        if HELPER in read.mask_c(text):
            raise ValueError("link write already patched or drifted")
        span = function_span(text, "gps_each_link_write_with_opt")
        signature = unique_span(text, OLD_SIGNATURE, span)
        lookup = unique_span(text, "\tstruct gps_each_link *p = gps_dl_link_get(link_id);", span)
        valid = unique_span(text, "\tif (NULL == p)", span)
        event = unique_span(text, "\t\t\tgps_dl_link_event_send(GPS_DL_EVT_LINK_WRITE, link_id);\n", span)
        unavailable = unique_span(text, "\t\t\t/* TODO: */", span)
        return read.edit_spans(text, [
            (signature, WRAPPER + PROTOTYPE),
            (lookup, "\tstruct gps_each_link *p;"),
            (Span(valid.start, valid.start), ZERO_LINK + "\tp = gps_dl_link_get(link_id);\n"),
            (Span(event.end, event.end), QUEUED),
            (Span(unavailable.start, unavailable.start), UNAVAILABLE)])
    if path == LINK_H:
        if HELPER in read.mask_c(text):
            raise ValueError("write declaration already patched or drifted")
        decl = unique_span(text, OLD_SIGNATURE + ";\n", Span(0, len(text)))
        return read.edit_spans(text, [(Span(decl.end, decl.end),
            "/* nonblocking skips capacity and completion waits for this call only. */\n"
            + PROTOTYPE + ";\n")])
    raise ValueError(f"out-of-scope source: {path}")


HEADER = """Subject: [PATCH] gps: add per-call nonblocking data-link TX

Base: NothingOSS/android_kernel_modules_nothing_mt6878
Commit: e96f60dc081ae3525ef43d4bcf0ee5ee97e53835
Prerequisite: package vendor patches 1001 through 1008, in order

Add an explicit nonblocking option, retaining write_with_opt's wait_tx_done
contract via a wrapper with nonblocking=false. O_NONBLOCK queues once and
returns before polling completion, or returns -EAGAIN on NOSPACE/BUSY/NOENTRY
before the capacity wait. Keep other error mappings and blocking behavior.

Return zero-length device writes before any access or recording; bound count
to sizeof(o_buf) before narrowing/recording. The new nonblocking link entry
also returns zero for len=0 before lookup. No poll readiness ABI is added.

Staged only: no package activation or hardware validation.

"""


def generate(modules=MODULES, baseline=None):
    baseline = stacked(modules) if baseline is None else baseline
    chunks = [HEADER]
    for path in SOURCES:
        old, new = baseline[path], transform(path, baseline[path])
        chunks.append(f"diff --git a/{path} b/{path}\n")
        chunks.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                      fromfile="a/" + path, tofile="b/" + path, n=3))
    return "".join(chunks)


def fixture_types(modules=MODULES):
    dma = source(DMA, modules)
    matches = re.findall(r"^#define GDL_COUNT_FREE[^\n]*\n[^\n]*", dma, re.M)
    if len(matches) != 1:
        raise ValueError("missing/ambiguous DMA free macro")
    return read.fixture_types(modules) + matches[0] + "\n"


def fixture(modules=MODULES, originals=False, baseline=None):
    baseline = stacked(modules) if baseline is None else baseline
    chunks = ["/* SPDX-License-Identifier: GPL-2.0 */\n",
              f"/* Actual package-stacked sources at {PIN}; CI-only. */\n"]
    chunks.append((OLD_SIGNATURE if originals else PROTOTYPE) + ";\n")
    for path, names in (
        (DMA, ("gdl_dma_buf_get_free_entry_inner", "gdl_dma_buf_get_free_entry",
               "gdl_dma_buf_set_free_entry_inner", "gdl_dma_buf_set_free_entry",
               "gdl_dma_buf_buf_to_entry", "gdl_dma_buf_put")),
        (LINK, ((HELPER,) if not originals else ()) +
               ("gps_each_link_write_with_opt", "gps_each_link_write")),
        (DEVICE, ("gps_each_device_write",))):
        text = baseline[path]
        if path in SOURCES and not originals:
            text = transform(path, text)
        for name in names:
            span = function_span(text, name)
            line = text[:span.start].count("\n") + 1
            chunks.append(f'#line {line} "{path}"\n{span.text(text)}\n\n')
    return "".join(chunks)


def mutations(fixed):
    cases = {
        "without-zero-device": (ZERO_DEVICE, ""),
        "without-bound": (BOUND, ""),
        "without-dispatch": ("filp->f_flags & O_NONBLOCK", "0"),
        "without-capacity-guard": (UNAVAILABLE, ""),
        "without-completion-guard": (QUEUED, ""),
        "without-zero-link": (ZERO_LINK, ""),
        "legacy-made-nonblocking": ("wait_tx_done, false);", "wait_tx_done, true);"),
        "legacy-forced-completion": ("wait_tx_done, false);", "true, false);")}
    results = {}
    for name, (needle, replacement) in cases.items():
        if fixed.count(needle) != 1:
            raise ValueError(f"mutation span drift: {name}")
        results[name] = fixed.replace(needle, replacement, 1)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", "--modules", dest="modules", type=Path, default=MODULES)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = generate(args.modules)
    if args.write:
        PATCH.write_text(expected)
        print(f"generated {PATCH.name}; sha512={hashlib.sha512(PATCH.read_bytes()).hexdigest()}")
    elif PATCH.read_text() != expected:
        raise SystemExit("staged patch differs from pinned stacked generator")
    else:
        print("PASS: deterministic pinned stacked production patch")


if __name__ == "__main__":
    main()
