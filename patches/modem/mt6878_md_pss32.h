/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef MT6878_MD_PSS32_H
#define MT6878_MD_PSS32_H
#include <linux/types.h>
struct mt6878_md_pss32;
/* Caller authenticates SPKI/delegation separately. Key is exact canonical
 * PKCS#1 RSAPublicKey DER (270 bytes), RSA2048/exponent65537 only, NOT SPKI.
 * Allocate/free and signature verification outside supplier/scope locks.
 * One caller per context, immutable input buffers throughout each call.
 * No RAM mapping, trust-pin choice, firmware request or hardware permission.
 */
struct mt6878_md_pss32 *mt6878_md_pss32_create(const u8 *key, size_t length);
void mt6878_md_pss32_destroy(struct mt6878_md_pss32 *ctx);
int mt6878_md_pss32_verify(struct mt6878_md_pss32 *ctx,
			 const u8 *tbs, size_t tbs_size,
			 const u8 *signature, size_t signature_size);
/* Hash primitive only, never a successful AUTH verdict. Accessible immutable
 * bytes <=64MiB must be supplied by the owner; this does not read physical RAM.
 */
int mt6878_md_pss32_sha256(struct mt6878_md_pss32 *ctx,
			 const u8 *bytes, size_t size, u8 digest[32]);
#endif
