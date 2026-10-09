# Stock camera composer asset gate

0117/0118 are frozen for main's compile-only/native CI. This evidence file
does not change their generated patches or activate a service/driver.

## Named candidates, explicitly historical

Local `local/stock-b41/evolution-device`, blob-list commit
`e5938ea8fb1de42e2f85036d8b5374486b457a40`, `proprietary-files.txt` line 1:
`All unpinned blobs are extracted from Tetris_B4.0-260225-1904_4.0`.
The directory name is NOT evidence that these blobs match B4.1 sources.

That list names:

- `vendor/bin/hw/camerahalserver`
- `vendor/bin/hw/mt6878/camerahalserver`
- `vendor/etc/init/camerahalserver.rc`
- `vendor/etc/vintf/manifest/manifest_cameraprovider.xml`
- `vendor/etc/vintf/manifest/manifest_isphal.xml`
- `vendor/lib64/libccd.so` and `vendor/lib64/mt6878/libccd.so`
- `vendor/lib64/libispinterpreter_mtkcam.so` and its `mt6878/` variant
- `vendor/lib64/libispfeature_mtkcam.v4l2.so` and its `mt6878/` variant
- `vendor/lib64/libcam.halisp.imp.v4l2.so`, `libcam.halisp.v4l2.so`,
  `libcam.halisp.TopCtrlMgr.so`, and their `mt6878/` variants
- IMX882 / IMX882TXD `ISP_mapping.db` and `ISP_param.db`, including `mt6878/`
  variants under `vendor/bin/crossbuild/DataSet/SQLiteModule/db/tuning_DB`.

These are named extraction candidates, NOT a proven DT_NEEDED chain or proof
that libispinterpreter generates CAMSV CQs. No standalone `ccd` executable is
listed. Composition may be hosted inside the camera HAL process, but that is
an inference until the matching ELF/init data establishes it.

Workspace inventory found no actual camerahalserver/libccd/libispinterpreter
ELFs, camerahalserver.rc, vendor/super image or OTA payload to inspect. No phone,
SSH, binary execution or network extraction was performed.

## Exact next input for main

Obtain those named files from the actual matching installed vendor release,
not the historical blob-list, and record release identity and SHA256 hashes.
Need the camera init and VINTF files to establish the chosen executable/service,
ELF interpreter, ELF machine and DT_NEEDED recursively to establish dependencies,
and static disassembly/import/call evidence for dlopen libraries and the caller
of CCD MASTER/WORKER ioctls. A library filename alone is not that evidence.
Capture CQ output-format/stride/register templates and verified ABI version
before attempting service integration with native Linux queues. Do not run
the Android service blindly against enabled camera hardware.

DONE IRQ: the exact ISP7SP vendor handler reads status and never writes it.
The named WCLR field belongs to the CQ interrupt register, not DONE status.
Neither source supplies a documented DONE read-clear/W1C rule. Required input
is matching chip documentation or controlled masked-source live evidence by
main; 0118 must keep its no-guessed-ack gate until then.

The sensor SCP firmware is not a substitute for this AP CCD composition path.
No working capture-engine claim is justified by the frozen native tests.
