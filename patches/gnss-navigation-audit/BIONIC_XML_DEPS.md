# Real Bionic XML dependency build

`gnss-bionic-xml.yml` closes the target-library dependency of the existing
XML/ADC backend fixtures. Builds run only in GitHub CI; no local C build,
vendor engine call, phone installation or firmware execution is performed.
The existing sealed load-only probe and its provider policy remain unchanged.

## Inputs

- Same Android NDK r27d/API28 ARM64 compiler as the published callback adapters.
  The official archive has the existing independent size/SHA1 pin; its resolved
  SHA256 is retained as additional build evidence, not a new independent pin.
- OpenSSL 3.5.9 source archive SHA256
  `603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a`,
  from the [official release](https://github.com/openssl/openssl/releases/tag/openssl-3.5.9).
  Build follows the release's
  [Android configuration](https://github.com/openssl/openssl/blob/openssl-3.5.9/NOTES-ANDROID.md).
- libxml2 2.15.4 source archive SHA256
  `98087fd181d9070724f3fbc65c7377db03038eb92bd882374daff44940138821`,
  from the [official checksum](https://download.gnome.org/sources/libxml2/2.15/libxml2-2.15.4.sha256sum).
  Its official CMake project uses the actual NDK Android toolchain.
- Independently pinned public B4.1 XML, libmnl ELF and mnld ELF from stock
  selection CI `38048111345`; they are read as data only.

Source downloads, archive shape and extraction are bounded. No host include
or library substitutions, generated successful XML/EVP stubs, NDK import stubs
or arbitrary local development prefix are admitted. Actual headers and shared
libraries are built together from the source pins. The manifest retains the
commands, installed-file hashes, architecture, required defined exports and
complete immediate DT_NEEDED dependencies. Host ELF/GLIBC and unexpected
dependencies fail the build.

## Scope

The real API28 `libxml2.so` and `libcrypto.so` then link both complete standalone
XML and ADC fixtures with `--no-undefined`. Dependency libraries and output
executables are checked as ARM64; vendor-engine dependencies are prohibited.
This is target build/link evidence, not target execution or satellite fix.
Native ASan/UBSan execution remains independently recorded in CI `38052531292`.

The artifact contains the development prefix, compiler/source/asset/binary
manifests and first build failure log. It is a CI fixture dependency artifact,
not a postmarketOS package or replacement for the stock Bionic provider chain.
New libraries must not be silently inserted into the frozen sealed probe root.
Actual pre-engine XML reader/SET ordering, legitimate Android host services,
exclusive RX, ADC producer/diagnostic endpoint and bounded engine shutdown
remain necessary before runtime integration.

The initial dependency build and both complete fixture links passed
[CI 38065279869](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38065279869)
at `7963a021db54c0f14c5e70196f0c25d2f06c0dd4`. Downloaded manifests confirm
actual API28 ARM64 libraries, defined exports and Bionic-only dependency closure.
Neither target fixture was executed. Later backend changes need their own run.
