import errno
import hashlib
import os
import tempfile
import unittest
from b41_mipc_sealed_stage import SealedStage, seal_provider


class StageTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "memfd_create"), "Linux memfd required; run in CI")
    def test_external_writer_cannot_change_copy(self):
        with tempfile.TemporaryFile() as source:
            source.write(b"provider")
            source.flush()
            fd = seal_provider(source.fileno(), hashlib.sha256(b"provider").hexdigest())
            try:
                os.pwrite(source.fileno(), b"modified", 0)
                self.assertEqual(os.pread(fd, 8, 0), b"provider")
                with self.assertRaises(OSError):
                    os.pwrite(fd, b"X", 0)
                with self.assertRaises(OSError):
                    os.ftruncate(fd, 0)
            finally:
                os.close(fd)

    @unittest.skipUnless(hasattr(os, "memfd_create"), "Linux memfd required; run in CI")
    def test_changed_source_is_not_authorized(self):
        with tempfile.TemporaryFile() as source:
            source.write(b"changed")
            source.flush()
            with self.assertRaises(OSError) as caught:
                seal_provider(source.fileno(), hashlib.sha256(b"original").hexdigest())
            self.assertEqual(caught.exception.errno, errno.EBADMSG)

    def test_incomplete_closure_never_stages(self):
        class Missing:
            def require_closure(self):
                raise OSError(errno.ENODATA, "actual liblog absent")
        with self.assertRaises(OSError) as caught:
            SealedStage(Missing())
        self.assertEqual(caught.exception.errno, errno.ENODATA)


if __name__ == "__main__":
    unittest.main()
