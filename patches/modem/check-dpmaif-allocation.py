#!/usr/bin/env python3
"""Evaluate actual vendor Kbuild selection; no kernel compilation or hardware."""
from pathlib import Path
import subprocess
import sys
import tempfile


PROBE = """
.PHONY: allocation-probe
allocation-probe:
	@printf '%s\\n' 'flags=$(ccflags-y)' 'module=$(ccci_dpmaif-y)' 'builtin=$(ccci_hif_all-y)' 'selected=$(obj-m) $(obj-y)'
"""
OLD_POOL = """ifeq ($(CONFIG_PAGE_POOL), y)
ccflags-y += -DRX_PAGE_POOL
ccci_dpmaif-y += ccci_dpmaif_page_pool.o
endif
"""


def validate(makefile, driver, pool):
    output = subprocess.check_output([
        "make", "--no-print-directory", "-s", "-f", str(makefile), "-f", "-",
        "allocation-probe", f"CONFIG_MTK_ECCCI_DRIVER={driver}",
        f"CONFIG_PAGE_POOL={pool}", "DEVICE_MODULES_PATH=/source"],
        input=PROBE, text=True)
    fields = dict(line.split("=", 1) for line in output.splitlines())
    assert "-DRX_PAGE_POOL" not in fields["flags"], output
    assert "ccci_dpmaif_page_pool.o" not in output, output
    if driver in ("m", "y"):
        objects = fields["module" if driver == "m" else "builtin"].split()
        assert {"ccci_dpmaif_bat.o", "ccci_dpmaif_com.o"} <= set(objects), output
        selected = "ccci_dpmaif.o" if driver == "m" else "ccci_hif_all.o"
        assert selected in fields["selected"].split(), output
    else:
        assert not fields["module"] and not fields["builtin"], output
        assert not fields["selected"].strip(), output


def main():
    makefile = Path(sys.argv[1]).resolve()
    for driver in ("m", "y", "n", ""):
        for pool in ("y", "n", ""):
            validate(makefile, driver, pool)
    with tempfile.TemporaryDirectory() as directory:
        mutant = Path(directory) / "Makefile"
        text = makefile.read_text()
        marker = "obj-$(CONFIG_MTK_ECCCI_DRIVER) += ccci_dpmaif.o"
        assert text.count(marker) == 1
        mutant.write_text(text.replace(marker, OLD_POOL + marker))
        try:
            validate(mutant, "m", "y")
        except AssertionError:
            pass
        else:
            raise AssertionError("unsafe automatic vendor pool selection was accepted")
    print("PASS: 12 DPMAIF Kbuild selections; unsafe pool mutant rejected")


if __name__ == "__main__":
    main()
