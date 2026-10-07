#!/usr/bin/env python3
"""Exercise the patched clock callback from pinned B4.1; CI compiles the fixture."""
import argparse
from pathlib import Path
import subprocess
import tempfile

COMMIT = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
SOURCE = "connectivity/gps/data_link/linux/gps_dl_linux_clock_mng.c"
SIGNATURE = "int gps_dl_clock_mng_get_platform_clock(void)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    parser.add_argument("--apply-only", action="store_true")
    args = parser.parse_args()
    original = subprocess.check_output(
        ["git", "-C", str(args.tree), "show", f"{COMMIT}:{SOURCE}"], text=True)
    patch = (Path(__file__).resolve().parents[1] /
             "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/"
             "1005-vendor-gnss-propagate-clock-read-error.patch.vendor")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / SOURCE
        source.parent.mkdir(parents=True)
        source.write_text(original)
        result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)],
                                cwd=root, check=True, capture_output=True, text=True)
        if "offset" in result.stdout or "fuzz" in result.stdout:
            raise ValueError(result.stdout)
        fixed = source.read_text()
        start = fixed.index(SIGNATURE)
        callback = fixed[start:fixed.index("\n}", start) + 2]
        if args.apply_only:
            print("GNSS clock patch applies without offset/fuzz; no compilation performed")
            return
        harness = r'''
#include <assert.h>
#include <stdio.h>
#define DCXO_DIGCLK_ELR 0x7f4
#define GDL_LOGE(...) ((void)0)
#define GDL_LOGW(...) ((void)0)
struct regmap { int unused; };
static struct regmap map;
static int missing, error, calls;
static unsigned int value;
static struct regmap *gps_dl_clock_mng_get_regmap(void) { return missing ? NULL : &map; }
static int regmap_read(struct regmap *m, unsigned int reg, unsigned int *out)
{
    assert(m == &map && reg == DCXO_DIGCLK_ELR);
    calls++;
    if (error) return error;
    *out = value;
    return 0;
}
CALLBACK
int main(void)
{
    missing = 1;
    assert(gps_dl_clock_mng_get_platform_clock() == -1 && calls == 0);
    missing = 0;
    for (value = 0; value < 256; value++) {
        calls = 0;
        assert(gps_dl_clock_mng_get_platform_clock() == (int)(value & 1));
        assert(calls == 1);
    }
    for (error = -1; error >= -133; error--) {
        calls = 0;
        assert(gps_dl_clock_mng_get_platform_clock() == error && calls == 1);
    }
    puts("PASS: 256 clock selectors, 133 errors, missing regmap");
}
'''
        test = root / "test.c"
        test.write_text(harness.replace("CALLBACK", callback))
        binary = root / "test"
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(test), "-o", str(binary)]
        subprocess.run(command, check=True)
        subprocess.run([str(binary)], check=True)
        mutant = callback.replace("return retval;", "return 0;", 1)
        test.write_text(harness.replace("CALLBACK", mutant))
        subprocess.run(command, check=True)
        result = subprocess.run([str(binary)], cwd=root, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            raise ValueError("test accepted swallowed regmap error")
        print("PASS: rejected swallowed-error mutant")


if __name__ == "__main__":
    main()
