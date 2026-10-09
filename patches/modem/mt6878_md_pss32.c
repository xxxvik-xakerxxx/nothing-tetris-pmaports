// SPDX-License-Identifier: GPL-2.0-or-later
/* Padding adaptation: Copyright (c) 2013, Google Inc. */
/* Fixed B4.1 RSA2048/PSS-SHA256/MGF1-SHA256/salt32. Padding steps derived
 * from U-Boot bffec9306e7c40a432d79deefb450230c2ee2360,
 * lib/rsa/rsa-verify.c:mask_generation_function1, compute_hash_prime,
 * padding_pss_verify_with_salt. Preserve first hash failure (upstream ignores
 * the two helper returns); reject positive errors, never auto-detect salt.
 */
#include <crypto/akcipher.h>
#include <crypto/algapi.h>
#include <crypto/hash.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/module.h>
#include <linux/scatterlist.h>
#include <linux/slab.h>
#include <linux/string.h>
#include "mt6878_md_pss32.h"

#define MD_RSA_BYTES 256
#define MD_HASH_BYTES 32
#define MD_DB_BYTES (MD_RSA_BYTES - MD_HASH_BYTES - 1)
#define MD_PAD_BYTES (MD_DB_BYTES - MD_HASH_BYTES - 1)

struct mt6878_md_pss32 {
	struct crypto_akcipher *rsa;
	struct crypto_shash *sha;
	struct shash_desc *desc;
	struct akcipher_request *request;
	u8 signature[MD_RSA_BYTES], em[MD_RSA_BYTES];
};

static int md_crypto_error(int error)
{
	return error > 0 ? -EPROTO : error;
}

void mt6878_md_pss32_destroy(struct mt6878_md_pss32 *ctx)
{
	if (IS_ERR_OR_NULL(ctx))
		return;
	if (ctx->request)
		akcipher_request_free(ctx->request);
	kfree_sensitive(ctx->desc);
	if (ctx->sha)
		crypto_free_shash(ctx->sha);
	if (ctx->rsa)
		crypto_free_akcipher(ctx->rsa);
	kfree_sensitive(ctx);
}
EXPORT_SYMBOL_GPL(mt6878_md_pss32_destroy);

struct mt6878_md_pss32 *mt6878_md_pss32_create(const u8 *key, size_t length)
{
	static const u8 prefix[] = { 0x30, 0x82, 1, 0x0a, 2, 0x82, 1, 1, 0 };
	static const u8 exponent[] = { 2, 3, 1, 0, 1 };
	struct mt6878_md_pss32 *ctx;
	int ret;

	if (!key || length != 270 || memcmp(key, prefix, sizeof(prefix)) ||
	    !(key[9] & 0x80) || !(key[264] & 1) ||
	    memcmp(key + 265, exponent, sizeof(exponent)))
		return ERR_PTR(-EINVAL);
	ctx = kzalloc(sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return ERR_PTR(-ENOMEM);
	/* Exact software raw RSA, no pkcs1pad, hardware PM or async fallback. */
	ctx->rsa = crypto_alloc_akcipher("rsa-generic", 0, CRYPTO_ALG_ASYNC);
	if (IS_ERR(ctx->rsa)) {
		ret = PTR_ERR(ctx->rsa);
		ctx->rsa = NULL;
		goto fail;
	}
	ret = md_crypto_error(crypto_akcipher_set_pub_key(ctx->rsa, key, length));
	if (ret)
		goto fail;
	if (crypto_akcipher_maxsize(ctx->rsa) != MD_RSA_BYTES) {
		ret = -EPROTO;
		goto fail;
	}
	/* Exact pinned kernel software/library driver (not older sha256-generic). */
	ctx->sha = crypto_alloc_shash("sha256-lib", 0, 0);
	if (IS_ERR(ctx->sha)) {
		ret = PTR_ERR(ctx->sha);
		ctx->sha = NULL;
		goto fail;
	}
	if (crypto_shash_digestsize(ctx->sha) != MD_HASH_BYTES) {
		ret = -EPROTO;
		goto fail;
	}
	ctx->desc = kzalloc(sizeof(*ctx->desc) + crypto_shash_descsize(ctx->sha), GFP_KERNEL);
	if (!ctx->desc) {
		ret = -ENOMEM;
		goto fail;
	}
	ctx->desc->tfm = ctx->sha;
	ctx->request = akcipher_request_alloc(ctx->rsa, GFP_KERNEL);
	if (!ctx->request) {
		ret = -ENOMEM;
		goto fail;
	}
	return ctx;
fail:
	mt6878_md_pss32_destroy(ctx);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_md_pss32_create);

int mt6878_md_pss32_sha256(struct mt6878_md_pss32 *ctx,
			 const u8 *bytes, size_t size, u8 digest[32])
{
	int ret;

	if (IS_ERR_OR_NULL(ctx) || !bytes || !digest || !size || size > 64U * 1024 * 1024)
		return -EINVAL;
	ret = md_crypto_error(crypto_shash_digest(ctx->desc, bytes, size, digest));
	if (ret)
		memzero_explicit(digest, MD_HASH_BYTES);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_pss32_sha256);

static int md_pss32_encoded(struct mt6878_md_pss32 *ctx, const u8 hash[32])
{
	u8 db[MD_DB_BYTES], mask[MD_HASH_BYTES], seed[MD_HASH_BYTES + 4];
	u8 prime_input[8 + MD_HASH_BYTES + MD_HASH_BYTES] = { 0 };
	u8 prime[MD_HASH_BYTES];
	const u8 *h = ctx->em + MD_DB_BYTES;
	unsigned int offset, i, count;
	int ret;

	if (ctx->em[MD_RSA_BYTES - 1] != 0xbc || (ctx->em[0] & 0x80))
		return -EKEYREJECTED;
	memcpy(seed, h, MD_HASH_BYTES);
	/* MGF1(H,223), counter encoded big-endian. Exactly seven hashes. */
	for (offset = 0, count = 0; offset < MD_DB_BYTES; offset += MD_HASH_BYTES, count++) {
		seed[32] = count >> 24;
		seed[33] = count >> 16;
		seed[34] = count >> 8;
		seed[35] = count;
		ret = mt6878_md_pss32_sha256(ctx, seed, sizeof(seed), mask);
		if (ret)
			goto out;
		for (i = 0; i < MD_HASH_BYTES && offset + i < MD_DB_BYTES; i++)
			db[offset + i] = ctx->em[offset + i] ^ mask[i];
	}
	db[0] &= 0x7f; /* emBits=2047, modulus is strictly 2048 bits. */
	ret = -EKEYREJECTED;
	for (i = 0; i < MD_PAD_BYTES; i++)
		if (db[i])
			goto out;
	if (db[MD_PAD_BYTES] != 1)
		goto out;
	memcpy(prime_input + 8, hash, MD_HASH_BYTES);
	memcpy(prime_input + 8 + MD_HASH_BYTES, db + MD_PAD_BYTES + 1, MD_HASH_BYTES);
	ret = mt6878_md_pss32_sha256(ctx, prime_input, sizeof(prime_input), prime);
	if (!ret && crypto_memneq(h, prime, MD_HASH_BYTES))
		ret = -EKEYREJECTED;
out:
	memzero_explicit(db, sizeof(db));
	memzero_explicit(mask, sizeof(mask));
	memzero_explicit(seed, sizeof(seed));
	memzero_explicit(prime_input, sizeof(prime_input));
	memzero_explicit(prime, sizeof(prime));
	return ret;
}

int mt6878_md_pss32_verify(struct mt6878_md_pss32 *ctx,
			 const u8 *tbs, size_t tbs_size,
			 const u8 *signature, size_t signature_size)
{
	struct scatterlist src, dst;
	u8 hash[MD_HASH_BYTES];
	int ret;

	if (IS_ERR_OR_NULL(ctx) || !tbs || !tbs_size || tbs_size > 16384 ||
	    !signature || signature_size != MD_RSA_BYTES)
		return -EINVAL;
	ret = mt6878_md_pss32_sha256(ctx, tbs, tbs_size, hash);
	if (ret)
		return ret;
	memcpy(ctx->signature, signature, MD_RSA_BYTES);
	memset(ctx->em, 0, MD_RSA_BYTES);
	sg_init_one(&src, ctx->signature, MD_RSA_BYTES);
	sg_init_one(&dst, ctx->em, MD_RSA_BYTES);
	akcipher_request_set_crypt(ctx->request, &src, &dst, MD_RSA_BYTES, MD_RSA_BYTES);
	ret = md_crypto_error(crypto_akcipher_encrypt(ctx->request));
	if (!ret && ctx->request->dst_len != MD_RSA_BYTES)
		ret = -EPROTO;
	if (!ret)
		ret = md_pss32_encoded(ctx, hash);
	memzero_explicit(hash, sizeof(hash));
	memzero_explicit(ctx->signature, MD_RSA_BYTES);
	memzero_explicit(ctx->em, MD_RSA_BYTES);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_pss32_verify);
MODULE_LICENSE("GPL");
