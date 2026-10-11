# Native CCD Worker

The mapped worker owns process-local work/message DMA-buffer mappings and uses
the existing native CQ composer. Registration and retirement use the explicit
generation/token ABI in `mt6878-ccd-retire-uapi.h`, not stock libccd emulation.
It does not enable a sensor, power domain, IRQ or DMA engine.

A clean protocol DESTROY may precede kernel retirement. A following step queries
retirement but returns `ESHUTDOWN` without falsely recording composition failure
when the query still returns `EAGAIN`. Only an actual matching retirement ticket
permits ACK and subsequent mapping release. Cache/composition failures remain
terminal and prevent release; closing a session alone is not hardware OFF.

Main CI compiles/links the real worker, mapped owner and existing composer path
and runs fault fixtures. Native C builds run only in GitHub Actions. Hardware
capture and the kernel bus/controller integration remain unverified; these files
are not installed as a camera service or used to claim working capture.
