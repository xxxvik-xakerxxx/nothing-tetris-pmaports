/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef MT6878_MD_MTK_CERT_H
#define MT6878_MD_MTK_CERT_H
#include <linux/types.h>
struct mt6878_md_signed_hashes {
	u8 header_sha256[32];
	u8 payload_sha256[32];
};
/* Exact B4.1 MTK delegated-key profile, not ordinary X.509. Fixed audited root
 * SPKI pin; no caller key/pin/digest authority. Inputs are accessible immutable
 * certificate/header bytes, NOT physical addresses. Allocates crypto contexts:
 * must run outside supplier/scope locks. Output copied only on full success,
 * retains no input pointers. Certs <=16KiB each; header exactly512 bytes.
 * This authenticates expected hashes/header, not installed payload or hardware
 * permission. No mapper, EMI/NS-access change, remoteproc start or AUTH callback.
 */
int mt6878_md_mtk_verify_header(const u8 *cert1, size_t cert1_size,
			      const u8 *cert2, size_t cert2_size,
			      const u8 *header, size_t header_size,
			      struct mt6878_md_signed_hashes *out);
#endif
