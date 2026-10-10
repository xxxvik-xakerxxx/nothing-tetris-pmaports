"""Linux sealed provider copies; no loader, engine or modem operations."""
import errno
import fcntl
import hashlib
import os
import re
import stat


def seal_provider(source, expected_sha):
    """Verify the sealed copy, not source stats, against an independent pin."""
    if not hasattr(os, "memfd_create"):
        raise OSError(errno.ENOSYS, "Linux sealing unavailable")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("independent SHA256 required")
    size = os.fstat(source).st_size
    if not stat.S_ISREG(os.fstat(source).st_mode) or not 0 < size <= 64 * 1024 * 1024:
        raise OSError(errno.EINVAL, "bounded regular provider required")
    fd = os.memfd_create("b41-mipc-provider", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        offset = 0
        while offset < size:
            chunk = os.pread(source, min(65536, size - offset), offset)
            if not chunk:
                raise OSError(errno.ESTALE, "source truncated during staging")
            written = 0
            while written < len(chunk):
                count = os.write(fd, chunk[written:])
                if count <= 0:
                    raise OSError(errno.EIO, "short staging write")
                written += count
            offset += len(chunk)
        seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals != seals:
            raise OSError(errno.EPERM, "staging not immutable")
        digest = hashlib.sha256()
        offset = 0
        while offset < size:
            chunk = os.pread(fd, min(65536, size - offset), offset)
            if not chunk:
                raise OSError(errno.EIO, "short sealed read")
            digest.update(chunk)
            offset += len(chunk)
        if digest.hexdigest() != expected_sha:
            raise OSError(errno.EBADMSG, "sealed provider SHA256 mismatch")
        return fd
    except BaseException:
        os.close(fd)
        raise


class SealedStage:
    """Owns copies until moved into the sole parent C supervisor."""
    def __init__(self, resources):
        self.descriptors = {}
        self._moved = False
        resources.require_closure()
        try:
            for name, image in resources.images.items():
                self.descriptors[name] = seal_provider(resources.descriptors[name], image["sha256"])
        except BaseException:
            self.close()
            raise

    def move(self):
        if self._moved or not self.descriptors:
            raise OSError(errno.EINVAL, "stage already consumed")
        result = self.descriptors
        self.descriptors = {}
        self._moved = True
        return result

    def close(self):
        descriptors, self.descriptors = self.descriptors, {}
        first = None
        for fd in descriptors.values():
            try:
                os.close(fd)
            except OSError as error:
                first = first or error
        if first:
            raise first
