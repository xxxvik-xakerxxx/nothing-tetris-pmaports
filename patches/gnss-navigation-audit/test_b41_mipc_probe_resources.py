"""Pinned executable admission evidence; never execute the probe or library."""
import errno
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from b41_mipc_probe_resources import ProbeResources, PROBE_SHA, MNL_SHA
from test_b41_mipc_provider_resources import STOCK, BIONIC


class ProbeTests(unittest.TestCase):
    def test_actual_independent_executable_pins(self):
        for relative, pin in (("probe", PROBE_SHA), ("vendor/lib64/libmnl.so", MNL_SHA)):
            data = (BIONIC / relative).read_bytes()
            self.assertEqual(data[:4], b"\x7fELF")
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin)

    def test_seal_failure_retains_first_with_both_cleanup_faults(self):
        base = Mock(close=Mock(side_effect=OSError(errno.EIO, "base close")))
        with patch("b41_mipc_probe_resources.LoaderResources", return_value=base), \
                patch("b41_mipc_probe_resources.os.open", return_value=77), \
                patch("b41_mipc_probe_resources.seal_provider", side_effect=OSError(errno.EBADMSG, "bad pin")), \
                patch("b41_mipc_probe_resources.os.close", side_effect=OSError(errno.EIO, "source close")):
            with self.assertRaises(OSError) as caught:
                ProbeResources(STOCK, BIONIC)
        self.assertEqual(caught.exception.errno, errno.EBADMSG)
        self.assertIn("source close", caught.exception.__notes__[0])
        self.assertIn("base close", caught.exception.__notes__[1])

    def test_adapter_retains_frozen_policy_and_deadline(self):
        source = Path(__file__).with_name("b41_mipc_sealed_isolate.c").read_text()
        self.assertIn('#include "mnl-isolate.c"', source)
        self.assertIn('if (filter())', source)
        self.assertNotIn('mount(root, root,', source)
        self.assertNotIn('mnl_run(', source)
        self.assertNotIn('mipc_init(', source)
        self.assertLess(source.index('return -ETIMEDOUT'), source.index('unshare(CLONE_NEWNET'))

    @unittest.skipUnless(hasattr(os, "memfd_create"), "Linux sealing required in CI")
    def test_actual_twelve_sealed_descriptors_transfer(self):
        owned = ProbeResources(STOCK, BIONIC)
        descriptors = owned.move()
        try:
            self.assertEqual(len(descriptors), 12)
            for index, pin in ((10, PROBE_SHA), (11, MNL_SHA)):
                fd = descriptors[index]
                data = os.pread(fd, os.fstat(fd).st_size, 0)
                self.assertEqual(hashlib.sha256(data).hexdigest(), pin)
                self.assertEqual(os.fstat(fd).st_mode & 0o777, 0o555 if index == 10 else 0o444)
                with self.assertRaises(OSError):
                    os.pwrite(fd, b"X", 0)
            with self.assertRaises(OSError):
                owned.move()
            owned.close()
            self.assertTrue(all(os.fstat(fd).st_size for fd in descriptors))
        finally:
            for fd in descriptors:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
