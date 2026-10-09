/* SPDX-License-Identifier: GPL-2.0-or-later */
/* CI-only kernel API doubles backed by real OpenSSL BN/SHA256. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <openssl/bn.h>
#include <openssl/evp.h>
typedef unsigned char u8;
#define GFP_KERNEL 0
#define CRYPTO_ALG_ASYNC 0x80
#define EXPORT_SYMBOL_GPL(x)
#define MODULE_LICENSE(x)
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
enum { FAIL_NONE, FAIL_CONTEXT, FAIL_RSA, FAIL_KEY, FAIL_SHA, FAIL_DESC, FAIL_REQUEST };
static int fail_stage, live, allocations, hash_calls, hash_fault, hash_error, rsa_fault, rsa_calls;
static int maxsize_fault, digestsize_fault, short_output;
struct crypto_akcipher { BIGNUM *n, *e; };
struct crypto_shash { int unused; };
struct shash_desc { struct crypto_shash *tfm; };
struct scatterlist { void *data; unsigned int size; };
struct akcipher_request {
	struct crypto_akcipher *tfm;
	struct scatterlist *src, *dst;
	unsigned int src_len, dst_len;
};
static void *allocate(size_t size)
{
	void *p = calloc(1, size);
	assert(p);
	live++;
	return p;
}
static void *kzalloc(size_t size, int flags)
{
	(void)flags;
	allocations++;
	if ((allocations == 1 && fail_stage == FAIL_CONTEXT) ||
	    (allocations == 2 && fail_stage == FAIL_DESC))
		return NULL;
	return allocate(size);
}
static void kfree_sensitive(void *p)
{
	if (p) {
		live--;
		free(p);
	}
}
static void memzero_explicit(void *p, size_t size) { memset(p, 0, size); }
static int crypto_memneq(const void *a, const void *b, size_t n) { return memcmp(a, b, n) != 0; }
static struct crypto_akcipher *crypto_alloc_akcipher(const char *name, int type, int mask)
{
	assert(!strcmp(name, "rsa-generic") && type == 0 && mask == CRYPTO_ALG_ASYNC);
	return fail_stage == FAIL_RSA ? ERR_PTR(-ENOENT) : allocate(sizeof(struct crypto_akcipher));
}
static void crypto_free_akcipher(struct crypto_akcipher *r)
{
	BN_free(r->n);
	BN_free(r->e);
	kfree_sensitive(r);
}
static int crypto_akcipher_set_pub_key(struct crypto_akcipher *r, const void *key, size_t size)
{
	if (fail_stage == FAIL_KEY)
		return -EBADMSG;
	assert(size == 270);
	r->n = BN_bin2bn((const u8 *)key + 9, 256, NULL);
	r->e = BN_new();
	assert(r->n && r->e && BN_set_word(r->e, 65537));
	return 0;
}
static unsigned int crypto_akcipher_maxsize(struct crypto_akcipher *r)
{
	assert(r->n);
	return maxsize_fault ? 255 : 256;
}
static struct crypto_shash *crypto_alloc_shash(const char *name, int type, int mask)
{
	assert(!strcmp(name, "sha256-lib") && !type && !mask);
	return fail_stage == FAIL_SHA ? ERR_PTR(-ENOENT) : allocate(sizeof(struct crypto_shash));
}
static void crypto_free_shash(struct crypto_shash *s) { kfree_sensitive(s); }
static unsigned int crypto_shash_digestsize(struct crypto_shash *s)
{
	assert(s);
	return digestsize_fault ? 31 : 32;
}
static size_t crypto_shash_descsize(struct crypto_shash *s) { assert(s); return 0; }
static int crypto_shash_digest(struct shash_desc *s, const void *data, size_t size, void *out)
{
	unsigned int written;
	assert(s->tfm);
	hash_calls++;
	if (hash_calls == hash_fault)
		return hash_error;
	assert(EVP_Digest(data, size, out, &written, EVP_sha256(), NULL) == 1 && written == 32);
	return 0;
}
static struct akcipher_request *akcipher_request_alloc(struct crypto_akcipher *r, int flags)
{
	(void)flags;
	if (fail_stage == FAIL_REQUEST)
		return NULL;
	struct akcipher_request *q = allocate(sizeof(*q));
	q->tfm = r;
	return q;
}
static void akcipher_request_free(struct akcipher_request *r) { kfree_sensitive(r); }
static void sg_init_one(struct scatterlist *s, void *data, unsigned int size)
{
	s->data = data;
	s->size = size;
}
static void akcipher_request_set_crypt(struct akcipher_request *r, struct scatterlist *src,
				       struct scatterlist *dst, unsigned int slen, unsigned int dlen)
{
	r->src = src;
	r->dst = dst;
	r->src_len = slen;
	r->dst_len = dlen;
}
static int crypto_akcipher_encrypt(struct akcipher_request *r)
{
	int ret = 0;
	rsa_calls++;
	if (rsa_fault)
		return rsa_fault;
	BIGNUM *sig = BN_bin2bn(r->src->data, r->src_len, NULL), *em = BN_new();
	BN_CTX *ctx = BN_CTX_new();
	assert(sig && em && ctx && r->dst_len == 256);
	if (BN_cmp(sig, r->tfm->n) >= 0)
		ret = -EINVAL;
	else {
		assert(BN_mod_exp(em, sig, r->tfm->e, r->tfm->n, ctx));
		assert(BN_bn2binpad(em, r->dst->data, 256) == 256);
		if (short_output)
			r->dst_len = 255;
	}
	BN_free(sig);
	BN_free(em);
	BN_CTX_free(ctx);
	return ret;
}
/* PRODUCTION_INSERT */
/* VECTORS_INSERT */
static void reset_faults(void)
{
	fail_stage = allocations = hash_calls = hash_fault = rsa_fault = rsa_calls = 0;
	maxsize_fault = digestsize_fault = short_output = 0;
	hash_error = -EIO;
}
int main(void)
{
	struct mt6878_md_pss32 *ctx;
	u8 bad_key[270], hash[32], bad_sig[256];
	reset_faults();
	for (int stage = FAIL_CONTEXT; stage <= FAIL_REQUEST; stage++) {
		reset_faults();
		fail_stage = stage;
		ctx = mt6878_md_pss32_create(vector_key, sizeof(vector_key));
		assert(IS_ERR(ctx) && !live);
	}
	reset_faults(); maxsize_fault = 1;
	assert(PTR_ERR(mt6878_md_pss32_create(vector_key, sizeof(vector_key))) == -EPROTO && !live);
	reset_faults(); digestsize_fault = 1;
	assert(PTR_ERR(mt6878_md_pss32_create(vector_key, sizeof(vector_key))) == -EPROTO && !live);
	reset_faults();
	for (int index = 0; index < 5; index++) {
		memcpy(bad_key, vector_key, 270);
		switch (index) {
		case 0: bad_key[0] ^= 1; break;
		case 1: bad_key[9] &= 0x7f; break;
		case 2: bad_key[264] &= 0xfe; break;
		case 3: bad_key[269] = 3; break;
		case 4: bad_key[8] = 1; break;
		}
		assert(PTR_ERR(mt6878_md_pss32_create(bad_key, 270)) == -EINVAL && !live);
	}
	assert(PTR_ERR(mt6878_md_pss32_create(vector_key, 269)) == -EINVAL);
	ctx = mt6878_md_pss32_create(vector_key, sizeof(vector_key));
	assert(!IS_ERR(ctx));
	assert(!mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_signature, 256));
	assert(hash_calls == 9 && rsa_calls == 1);
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_salt64, 256) == -EKEYREJECTED);
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_v15, 256) == -EKEYREJECTED);
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_signature, 255) == -EINVAL);
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, 16385, vector_signature, 256) == -EINVAL);
	memcpy(bad_sig, vector_signature, 256); bad_sig[30] ^= 1;
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), bad_sig, 256) != 0);
	assert(mt6878_md_pss32_verify(ctx, (const u8 *)"wrong", 5, vector_signature, 256) == -EKEYREJECTED);
	memset(bad_sig, 255, 256);
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), bad_sig, 256) == -EINVAL);
	for (int fault = 1; fault <= 9; fault++) {
		reset_faults(); hash_fault = fault;
		assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_signature, 256) == -EIO);
		assert(hash_calls == fault && rsa_calls == (fault > 1));
	}
	reset_faults(); hash_fault = 2; hash_error = 1;
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_signature, 256) == -EPROTO);
	reset_faults(); rsa_fault = -ETIMEDOUT;
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_signature, 256) == -ETIMEDOUT);
	assert(hash_calls == 1 && rsa_calls == 1);
	reset_faults(); short_output = 1;
	assert(mt6878_md_pss32_verify(ctx, vector_tbs, sizeof(vector_tbs), vector_signature, 256) == -EPROTO);
	reset_faults();
	assert(!mt6878_md_pss32_sha256(ctx, vector_tbs, sizeof(vector_tbs), hash));
	memcpy(ctx->em, vector_em, 256);
	assert(!md_pss32_encoded(ctx, hash));
	for (int i = 0; i < 5; i++) {
		memcpy(ctx->em, vector_em, 256);
		switch (i) {
		case 0: ctx->em[255] ^= 1; break;
		case 1: ctx->em[0] |= 128; break;
		case 2: ctx->em[1] ^= 1; break;
		case 3: ctx->em[190] ^= 1; break;
		case 4: ctx->em[223] ^= 1; break;
		}
		assert(md_pss32_encoded(ctx, hash) == -EKEYREJECTED);
	}
	assert(mt6878_md_pss32_sha256(ctx, vector_tbs, 64U * 1024 * 1024 + 1, hash) == -EINVAL);
	mt6878_md_pss32_destroy(ctx);
	mt6878_md_pss32_destroy(NULL);
	assert(!live);
	puts("production PSS32 + OpenSSL raw RSA/SHA256 fault tests PASS");
	return 0;
}
