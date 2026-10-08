#!/usr/bin/env python3
"""Apply to pinned vendor source; execute actual patched functions in CI only."""
import argparse
from pathlib import Path
import subprocess
import tempfile

PIN = "ee2be53cb75670b548948636a0db1d1ff112bf12"
SOURCE = "drivers/misc/mediatek/ccci_util/ccci_util_md_mem.c"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    patch = here.parents[1] / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0173-vendor-ccci-smem-map-span.patch.vendor"
    source = subprocess.check_output(["git", "-C", str(args.repository), "show",
                                      PIN + ":" + SOURCE], text=True)
    with tempfile.TemporaryDirectory(prefix="tetris-smem-") as temporary:
        work = Path(temporary)
        target = work / SOURCE
        target.parent.mkdir(parents=True)
        target.write_text(source)
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=work, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=work, check=True)
        text = target.read_text()
        begin = text.index("static int map_and_update_tbl(")
        end = text.index("static void smem_layout_dump(", begin)
        (work / "smem-map-functions.h").write_text(text[begin:end])
        if args.check_only:
            print("PASS: mapping patch applies to exact B4.1 source; no compilation")
            return
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-I", str(work), str(here / "smem-map-test.c"),
                        "-o", str(work / "test")], check=True)
        subprocess.run([str(work / "test")], check=True)


if __name__ == "__main__":
    main()
