#!/usr/bin/env python3
"""Source-only regressions for native fixture ordering and cleanup coverage."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("owner", Path(__file__).with_name("check_transport_owner.py"))
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class FixtureTests(unittest.TestCase):
    def test_atomic_before_every_extracted_user(self):
        source = owner.EXTRA
        definition = source.index("static void atomic_set(")
        for consumer in ("wdt.c", "ccif-irq.c", "ccif-start.c", "dpmaif-start.c", "ccci_tetris_owner.c"):
            self.assertLess(definition, source.index(f'#include "{consumer}"'))

    def test_cleanup_only_guarded_states(self):
        source = owner.EXTRA
        self.assertIn("mt6878_md_cleanup(&pd);assert(!calls && !pd.md_owned && !pd.md_error)", source)
        self.assertIn("mt6878_md_cleanup(&pd);assert(!calls && maps[0].words[0xe00/4]==inherited)", source)
        self.assertIn("if(pd.md_error){", source)
        self.assertIn("assert(calls==fault && pd.md_error==first_fault)", source)

    def test_no_warning_relaxation(self):
        source = Path(owner.__file__).read_text()
        self.assertNotIn("-Wno-unused-function", source)
        self.assertIn('"-Wall", "-Wextra", "-Werror"', source)
        owner.check_delimiters(owner.EXTRA)


if __name__ == "__main__":
    unittest.main()
