# Main-owned opt-in wiring

Main integrated the six GPU C/H files and opt-in board/Kconfig/Makefile wiring
in actual U-Boot commit 94ead1146c93fef603db5c85820f2fb04c559c10, available at
https://github.com/xxxvik-xakerxxx/u-boot.git. This frozen draft matches those
six production files; the dedicated gpueb-flat workflow verifies each with cmp.
Default is n and mutually exclusive with existing GPUEB transform diagnostic:
there must be one transform, not diagnostic erase followed by a second decrypt.
Existing SCP secure profile/slot/crypto context checks remain authoritative.

## Capture in the existing crypto window

In tetris_scp_prepare.c, after its SCP members have been authenticated/transformed
and before the service page is unmapped, call under the new opt-in guard:

```c
gpueb_capture_ret = tetris_gpueb_flat_capture_slot_a(dev, &crypto,
    &tetris_scp_security_hw_ops, root_pin);
```

This uses exactly the current bounded gpueb_a GPT/direct-block-read loader.
Do not add crypto init/unlock, bypass profile selection, or return early and skip
existing SCP secure handoff/cleanup. Numeric capture failure is fatal to the
eventual diagnostic boot; do not describe failed retention as successful.
Both the crypto ops pointer retained in the handle and security ops are existing
static board objects, not local/temporary callback tables.

## Publish after final Linux DT edits

Current board_prep_linux is called from ARM bootm preparation after
image_setup_libfdt, which has already applied FIT overlays and shrunk the FDT.
Therefore do NOT assume it still has spare capacity. At the very END of
board_prep_linux, after its remaining devinfo/connsys/modem fixups, call:

```c
ret = tetris_gpueb_flat_publish_final(images);
if (ret)
    panic("Tetris: GPUEB analysis retention failed: %d\n", ret);
```

Guard that call with CONFIG_TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC. It copies
the final images->ft_addr DT into a newly LMB-reserved blob with actual 4 KiB
headroom, adds that blob's own header memreserve, then publishes the payload
reservation atomically. Only after success does it update images->ft_addr and
ft_len; ft_addr is a borrowed virtual pointer, not a physical address. Cache
maintenance uses the new mapped virtual pointer. The successful final mapping
stays alive through Linux handoff; only a failed owned mapping is unmapped and
freed. The borrowed old pointer is never mapped again or unmapped here.
Kernel handoff must use those updated fields. No further fixups may
operate on the old working_fdt pointer. Existing old DT reservation is not freed.
Failure leaves the old final DT intact, erases/discards pending plaintext and
requires recovery boot if any release itself fails. No GPUEB hardware is started.

## Minimal public CI asset config

Existing ci/extract-stock-port-assets.py downloads image-logical archives and
extracts vendor files; gpueb.img is NOT in that vendor image selection.
Use the SAME smaller public image-firmware archive as ci/extract-stock-modem.py.
Readonly listing of the independently hash-verified cached archive confirms its
exact member is `gpueb.img` (no path prefix), size 532480 bytes.

```sh
python3 patches/gpu/flat-handoff-draft/extract_factory_gpueb.py \
    --out out/factory-gpueb
export TETRIS_GPUEB_FACTORY_CONTAINER="$PWD/out/factory-gpueb/gpueb.img"
sh patches/gpu/flat-handoff-draft/run-native-ci.sh
```

Set TETRIS_UBOOT_TREE to the reviewed source checkout and CI=true; extractor
also requires GITHUB_ACTIONS=true. If the modem job retains its archive, pass
--archive /actual/CI/archive/path instead of downloading again. Download URL:
https://github.com/spike0en/nothing_archive/releases/download/Tetris_B4.1-260415-1709/Tetris_B4.1-260415-1709-image-firmware.7z
Archive: 59168898 bytes; SHA256
2336875d0b1e7364f87690701706e0d8cd7149bcf8f05c6d295f6082cf949811.
Member: 532480 bytes; SHA256
58c337b0e713d643a1cb129fd444bce0b8bc00e38877c3f242ac9a7f5901ba22.
Extractor rejects duplicates/links/unsafe paths/wrong sizes or hashes, verifies
the actual root/cert/header/RV33 ciphertext contract, writes PROVENANCE.json.
No handset upload, raw firmware commit, decryption or execution is involved.

Native build uses -Wall -Wextra -Werror for our security/crypto/layout/fixture/
publisher units. Unused-warning exceptions apply only to upstream ASN.1
compiler/decoder and generated ASN.1 TU, compiled separately. Positive plaintext
producer test remains explicitly skipped until authentic factory plaintext exists;
factory and phone-a signed plaintext hashes are different. ARM smoke now includes
the actual hook object; full opt-in image link and module modpost remain main gates.
