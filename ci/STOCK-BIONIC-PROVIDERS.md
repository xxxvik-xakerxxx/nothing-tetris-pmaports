# Selected B4.1 Bionic providers

`extract-stock-port-assets.py` now emits the five runtime providers in the same
`out/stock-port-assets` artifact as the existing vendor assets and system liblog.
The existing independently pinned two-part logical archive is downloaded once;
vendor.img and system.img are extracted together before archive cleanup. No
local runtime root, handset, second OTA, system mount or Android executable is
used. Existing manifest fields/vendor outputs remain; `bionic_runtime` records
the container provenance and its five provider rows also enter `files`.

Pins originate from `local/agent-results/mnl-runtime/REPORT.md` in the workspace,
not from newly calculated expected values at extraction time:

| Input | Size | SHA256 |
| --- | --- | --- |
| system.img (EROFS) | 1039855616 | ce53560d05e6caa8ad8c27a4c85eefbb93479b879e8c610be650be6b689108e6 |
| /system/apex/com.android.runtime.apex | 8372224 | f60104339cc839557d35caa922981cb4d37d87ee0d46a9db5e9264eda7092180 |
| apex_payload.img (ext4) | 8261632 | 3f5261a35da1c7bd5cbf8f8b74b935b94261580bae3dc904b75a2dc9d3741127 |

| Image source | Artifact path | SHA256 |
| --- | --- | --- |
| APEX /bin/linker64 | apex/com.android.runtime/bin/linker64 | 4a8dd94eb2d0e59184247892ba5232f7dcbe88eb8c5a43e3a9e4c9c4d4ba7844 |
| APEX /lib64/bionic/libc.so | apex/com.android.runtime/lib64/bionic/libc.so | 1e365bc2da9ca1e830801ce49f389e6e7fcbc0be7d82824924026af8751f8648 |
| APEX /lib64/bionic/libm.so | apex/com.android.runtime/lib64/bionic/libm.so | 25c852fca54f103e1a8ac2785a51ef2db2ea21ae9a89295d156ec63cbeb90e40 |
| APEX /lib64/bionic/libdl.so | apex/com.android.runtime/lib64/bionic/libdl.so | ec8a5f55630b6b41ad94b8bbdc6da308e36903709ce759bf2a3a59640715ae32 |
| system /system/lib64/libc++.so | system/lib64/libc++.so | 2267f93b8b3c9d1967f1833d5f71c7312213c43bb291250cf772800763037fb9 |

Each source/output is bounded, regular, exact-size and SHA-matched. EROFS reads
only the named APEX and libc++ via `dump.erofs --cat` with a child deadline;
no recursive system extraction. ZIP selection accepts exactly one regular,
unencrypted root-level apex_payload.img, checks its declared size and actual
bytes/CRC/hash, and never uses extractall/member names as output paths. Ext4
uses read-only debugfs stat/dump for four fixed files, with inode size/type
checks and command deadlines. No debug/HWASAN providers are selected. Outputs
are data mode0644; executable/sealed staging remains a separate owned step.

Prerequisites added to the existing CI extraction: Python standard zipfile
(no extra package), read-only debugfs/e2fsprogs, timeout; existing modern
dump.erofs --cat and pyelftools requirements remain. The parent owns workflow
changes. Run offline mechanics tests without images/network/native builds:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 ci/test-extract-stock-port-assets.py
```

The selected artifact root is now the source for **both** stock and Bionic
provider roots in downstream resource tests. Do not point tests at the stale
CI37898372984 local tree. This extraction does not supply the separately built
load-only `/probe`; that executable still needs its independent CI artifact
and pin before the executable resource producer can admit it. No INIT, loader
execution, properties or CCCI readiness is certified. Trust remains pinned
mirror archive identity/independent byte pins, not OEM/APEX signature checking.
