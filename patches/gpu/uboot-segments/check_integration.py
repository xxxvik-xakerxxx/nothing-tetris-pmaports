#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Check the integrated inspection contract without patching or executing C."""
import argparse
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
DEFAULT_TREE = HERE.parents[3] / "u-boot-mt6878"
BASE = "fdb0ee2994c62b6220e35dd1f75bbeee6e7d6f3a"
BOARD = Path("board/mediatek/mt6878")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_sources(read):
    """Read checkout or git-object text through the same fail-closed checks."""
    code = read(BOARD / "tetris_gpueb_prepare.c")
    header = read(BOARD / "tetris_gpueb_prepare.h")
    makefile = read(BOARD / "Makefile")
    call = "ret = tetris_gpueb_inspect_segments(staging, size, &result.segments);"
    require(code.count("tetris_gpueb_inspect_segments(") == 1 and call in code,
            "segment inspector must consume the verified primary exactly once")
    require(header.count('#include "tetris_gpueb_segments.h"') == 1 and
            header.count("struct tetris_gpueb_segment_info segments;") == 1,
            "missing or duplicate segment report ABI")
    ordered = re.compile(
        r"ret = tetris_scp_crypto_decrypt\(crypto, staging, size, capacity, 1,\s*"
        r"metadata\.wrapped, metadata\.ciphertext, metadata\.plaintext\);\s*"
        r"if \(ret\)\s*goto out;\s*"
        r"ret = tetris_gpueb_describe_plain\(staging, size, &result\.plain\);\s*"
        r"if \(!ret\)\s*" + re.escape(call) + r"\s*if \(!ret\) \{\s*"
        r"memcpy\(result\.plaintext_sha256, metadata\.plaintext, 32\);\s*"
        r"\*report = result;\s*attempt->state = TETRIS_GPUEB_PREPARE_DONE;\s*\}"
    )
    require(ordered.search(code), "inspection/publication must follow verified decryption")
    require(re.search(
        r"out:\s*wipe\(staging, capacity\);\s*ops->flush\(staging, capacity\);\s*"
        r"wipe\(&metadata, sizeof\(metadata\)\);\s*wipe\(&result, sizeof\(result\)\);\s*"
        r"return ret;", code), "full-capacity erasure and first error must survive")
    require(makefile.count("tetris_gpueb_segments.o") == 1 and re.search(
        r"^obj-\$\(CONFIG_TETRIS_SCP_SECURITY\) \+= tetris_gpueb_segments\.o$",
        makefile, re.M), "segment object must remain in the existing security owner")
    for name in ("tetris_gpueb_segments.c", "tetris_gpueb_segments.h"):
        require(read(BOARD / name) == (HERE / name).read_text(),
                f"{name}: review copy drift; reconcile before native CI")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = parser.parse_args()
    try:
        check_sources(lambda path: (args.tree / path).read_text())
    except (OSError, ValueError) as error:
        parser.exit(1, f"GPUEB integration failed: {error}\n")
    print("GPUEB inspection integration verified; no upload/start permission")


if __name__ == "__main__":
    main()
