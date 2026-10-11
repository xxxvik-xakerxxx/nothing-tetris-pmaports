#!/usr/bin/env python3
"""Generate a fail-closed patch from pinned Git blobs and balanced C spans."""
import argparse
from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
MODULES = Path(os.environ.get("TETRIS_MODULES_TREE", str(
    ROOT / "upstream/connectivity-modules" if (ROOT / "upstream/connectivity-modules").exists()
    else ROOT.parent / "android_kernel_modules_nothing_mt6878")))
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
PATCH = PACKAGE / "1008-vendor-gnss-bound-data-link-read.patch.vendor"
BASE = "connectivity/gps/data_link/"
DEVICE = BASE + "linux/gps_each_device.c"
LINK = BASE + "gps_each_link.c"
DMA = BASE + "lib/gps_dl_dma_buf.c"
DEVICE_H = BASE + "linux/inc/gps_each_device.h"
DMA_H = BASE + "lib/inc/gps_dl_dma_buf.h"
STATUS_H = BASE + "lib/inc/gps_dl_base.h"
SOURCES = (DEVICE, LINK, DMA)
FUNCTIONS = {DEVICE: "gps_each_device_read", LINK: "gps_each_link_read_with_timeout",
             DMA: "gdl_dma_buf_get"}


@dataclass(frozen=True)
class Span:
    start: int
    end: int

    def text(self, source):
        return source[self.start:self.end]


def source(path, modules=MODULES):
    return subprocess.check_output(
        ["git", "-C", str(modules), "show", f"{PIN}:{path}"]
    ).decode("utf-8")


def mask_c(text):
    # Preserve offsets/newlines while hiding comments and quoted delimiters.
    pattern = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m[0]),
                  text, flags=re.S)


def balanced_end(masked, start, opening="{", closing="}"):
    if masked[start] != opening:
        raise ValueError("span does not start at opening delimiter")
    depth = 0
    for offset in range(start, len(masked)):
        if masked[offset] == opening:
            depth += 1
        elif masked[offset] == closing:
            depth -= 1
            if depth == 0:
                return offset + 1
    raise ValueError("unbalanced source span")


def function_span(text, name):
    masked = mask_c(text)
    definitions = []
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", masked):
        paren = masked.index("(", match.start())
        end = balanced_end(masked, paren, "(", ")")
        body = end
        while body < len(masked) and masked[body].isspace():
            body += 1
        if body < len(masked) and masked[body] == "{":
            start = masked.rfind("\n", 0, match.start()) + 1
            definitions.append(Span(start, balanced_end(masked, body)))
    if len(definitions) != 1:
        raise ValueError(f"expected one definition of {name}: {len(definitions)}")
    return definitions[0]


def unique_span(text, expected, within):
    start = text.find(expected, within.start, within.end)
    if start < 0 or text.find(expected, start + 1, within.end) >= 0:
        raise ValueError(f"source drift or ambiguous span: {expected!r}")
    return Span(start, start + len(expected))


def declaration(text, keyword, name):
    masked = mask_c(text)
    matches = list(re.finditer(r"\b" + keyword + r"\s+" + name + r"\s*\{", masked))
    if len(matches) != 1:
        raise ValueError(f"expected one {keyword} {name}")
    match = matches[0]
    end = balanced_end(masked, masked.index("{", match.start()))
    if masked[end] != ";":
        raise ValueError("declaration missing semicolon")
    return text[match.start():end + 1]


def fixture_types(modules=MODULES):
    chunks = []
    for path, keyword, names in (
        (STATUS_H, "enum", ("GDL_RET_STATUS",)),
        (DMA_H, "enum", ("gps_dl_dma_dir",)),
        (DMA_H, "struct", ("gdl_dma_buf_entry", "gps_dl_dma_buf")),
        (DEVICE_H, "struct", ("gps_each_device_cfg", "gps_each_device"))):
        text = source(path, modules)
        for name in names:
            chunks.append(declaration(text, keyword, name) + "\n")
    for path, name in ((DEVICE_H, "GPS_DATA_PATH_BUF_MAX"),
                       (DMA_H, "GPS_DL_DMA_BUF_ENTRY_ARRAY_MAX"),
                       (BASE + "lib/inc/gps_dl_time_tick.h", "GPS_DL_RW_NO_TIMEOUT")):
        matches = re.findall(r"^#define\s+" + name + r"\b[^\n]*", source(path, modules), re.M)
        if len(matches) != 1:
            raise ValueError(f"ambiguous macro {name}")
        chunks.insert(0, matches[0] + "\n")
    dma = source(DMA, modules)
    match = re.search(r"^#define GDL_COUNT_DATA[^\n]*\n[^\n]*", dma, re.M)
    if not match:
        raise ValueError("missing DMA count macro")
    chunks.insert(0, match[0] + "\n")
    return "".join(chunks)


def edit_spans(text, edits):
    previous = len(text) + 1
    for span, replacement in sorted(edits, key=lambda item: item[0].start, reverse=True):
        if span.end > previous:
            raise ValueError("overlapping edits")
        text = text[:span.start] + replacement + text[span.end:]
        previous = span.start
    return text


def transform(path, text):
    if path == DEVICE:
        read = function_span(text, "gps_each_device_read")
        if "if (!count)" in read.text(text) or "O_NONBLOCK" in read.text(text):
            raise ValueError("device read already patched or drifted")
        dev = unique_span(text,
            "\tdev = (struct gps_each_device *)filp->private_data;\n", read)
        call = unique_span(text,
            "\tretlen = gps_each_link_read(link_id, &dev->i_buf[0], count);", read)
        return edit_spans(text, [
            (Span(dev.start, dev.start), "\tif (!count)\n\t\treturn 0;\n\n"),
            (Span(dev.end, dev.end),
             "\tif (count > sizeof(dev->i_buf))\n\t\tcount = sizeof(dev->i_buf);\n"),
            (call, "\tif (filp->f_flags & O_NONBLOCK)\n"
             "\t\tretlen = gps_each_link_read_with_timeout(link_id,\n"
             "\t\t\t&dev->i_buf[0], count, 0, NULL);\n"
             "\telse\n\t\tretlen = gps_each_link_read(link_id, &dev->i_buf[0], count);")
        ])
    if path == LINK:
        read = function_span(text, "gps_each_link_read_with_timeout")
        if "if (timeout_usec == 0)" in read.text(text):
            raise ValueError("link read already patched or drifted")
        branch = unique_span(text, "} else if (gdl_ret == GDL_FAIL_NODATA) {", read)
        masked = mask_c(text)
        body = text.index("{", branch.start)
        nodata = Span(body, balanced_end(masked, body))
        log = unique_span(text,
            '\t\t\tGDL_LOGXD_DRW(link_id, "gdl_dma_buf_get no data and wait");', nodata)
        return edit_spans(text, [(Span(log.start, log.start),
            "\t\t\tif (timeout_usec == 0)\n\t\t\t\treturn -EAGAIN;\n\n")])
    if path == DMA:
        read = function_span(text, "gdl_dma_buf_get")
        if "gdl_dma_buf_set_data_entry(p_dma, NULL)" in read.text(text):
            raise ValueError("DMA get already patched or drifted")
        copy = unique_span(text,
            "\tgdl_ret = gdl_dma_buf_entry_to_buf(p_entry, p_buf, buf_len, p_data_len);", read)
        branch = unique_span(text, "\tif (GDL_OKAY != gdl_ret) {",
                             Span(copy.end, read.end))
        body = text.index("{", branch.start)
        failure = Span(branch.start, balanced_end(mask_c(text), body))
        expected = ("\tif (GDL_OKAY != gdl_ret) {\n"
            "\t\t/* TODO: 210819: handling gdl_ret case to avoid FAIL_BUSY next time\n"
            "\t\t * the cause is th buf_len < data_len\n\t\t *\n"
            "\t\t * directly set p_entry->read_index = p_entry->write_index may be not a good solution,\n"
            "\t\t * due to it drops the data\n\t\t *\n\t\t */\n"
            "\t\treturn gdl_ret;\n\t}")
        if failure.text(text) != expected:
            raise ValueError("DMA copy failure branch drifted")
        return edit_spans(text, [(failure,
            "\tif (GDL_OKAY != gdl_ret) {\n"
            "\t\t/* Release the reader without consuming the failed entry. */\n"
            "\t\tgdl_dma_buf_set_data_entry(p_dma, NULL);\n"
            "\t\treturn gdl_ret;\n\t}")])
    raise ValueError(f"out-of-scope production source: {path}")


HEADER = """Subject: [PATCH] gps: bound data-link reads and honor O_NONBLOCK

Base: NothingOSS/android_kernel_modules_nothing_mt6878
Commit: e96f60dc081ae3525ef43d4bcf0ee5ee97e53835

Bound size_t count to the actual device input array before passing it to
the unsigned-int DMA reader. Return zero without touching the link for
an empty read. Use zero timeout for O_NONBLOCK, and return -EAGAIN on
GDL_FAIL_NODATA before either IRQ or polling waits.

Release acquired DMA reader ownership if entry-to-buffer copy fails, using
the existing locked NULL completion API without consuming queued data.
Return the first copy error even if cleanup encounters changed ownership.

Keep the blocking wrapper and existing error mappings. This does not
implement finite IRQ timeouts or serialize concurrent device readers.

"""


def generate(modules=MODULES):
    chunks = [HEADER]
    for path in SOURCES:
        original = source(path, modules)
        fixed = transform(path, original)
        chunks.append(f"diff --git a/{path} b/{path}\n")
        chunks.extend(difflib.unified_diff(original.splitlines(True),
            fixed.splitlines(True), fromfile="a/" + path, tofile="b/" + path, n=3))
    return "".join(chunks)


def fixture(modules=MODULES, originals=False):
    """Real function bodies; harness supplies only kernel/HAL boundaries."""
    chunks = ["/* SPDX-License-Identifier: GPL-2.0 */\n",
              f"/* Extracted MediaTek sources at {PIN}; CI-only. */\n"]
    for path, names in (
        (DMA, ("gdl_dma_buf_get_data_entry_inner", "gdl_dma_buf_get_data_entry",
               "gdl_dma_buf_set_data_entry_inner", "gdl_dma_buf_set_data_entry",
               "gdl_dma_buf_entry_to_buf", "gdl_dma_buf_get")),
        (LINK, ("gps_each_link_read_with_timeout", "gps_each_link_read")),
        (DEVICE, ("gps_each_device_read",))):
        text = source(path, modules)
        if path in SOURCES and not originals:
            text = transform(path, text)
        for name in names:
            span = function_span(text, name)
            line = text[:span.start].count("\n") + 1
            chunks.append(f'#line {line} "{path}"\n{span.text(text)}\n\n')
    return "".join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", "--modules", dest="modules", type=Path, default=MODULES)
    parser.add_argument("--write", action="store_true", help="write new generated vendor patch")
    args = parser.parse_args()
    expected = generate(args.modules)
    if args.write:
        PATCH.write_text(expected)
        print(f"generated {PATCH.name}")
    elif PATCH.read_text() != expected:
        raise SystemExit("staged patch differs from pinned generator")
    else:
        print("PASS: deterministic pinned production patch")


if __name__ == "__main__":
    main()
