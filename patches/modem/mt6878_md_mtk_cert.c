// SPDX-License-Identifier: GPL-2.0-or-later
/* Profile adapted from U-Boot bffec9306e7c40a432d79deefb450230c2ee2360,
 * board/mediatek/mt6878/tetris_scp_security.c. Kernel ASN.1 decoder provides
 * structure walking; this consumer restricts it to canonical bounded DER.
 */
#include <linux/asn1_decoder.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <crypto/algapi.h>
#include "mt6878_md_mtk_fields.asn1.h"
#include "mt6878_md_pss32.h"
#include "mt6878_md_mtk_cert.h"

#define MD_CERT_MAX 16384
#define MD_FIELDS_MAX 48

struct md_der_field {
	const u8 *data;
	size_t size, header;
	u8 tag;
};
struct md_der_fields {
	struct md_der_field fields[MD_FIELDS_MAX];
	size_t count;
};
struct md_der_cert {
	struct md_der_field tbs, spki, raw_key, signature;
	struct md_der_fields body;
};
struct md_der_work {
	struct md_der_cert root, leaf;
	struct md_der_fields scratch, integers;
};

static const u8 md_mtk_root_pin[32] = {
	0xe1, 0xb5, 0x23, 0x5d, 0x94, 0x11, 0x47, 0x3a,
	0x35, 0x8c, 0x75, 0x4f, 0x84, 0x84, 0x38, 0x01,
	0xb9, 0x1f, 0x05, 0xb8, 0xfb, 0x9d, 0xc4, 0x86,
	0x33, 0x93, 0xe3, 0x78, 0xe4, 0x1a, 0x11, 0x5e,
};

static int md_der_header(const u8 *p, size_t size, size_t *header)
{
	size_t count, length = 0, i;

	if (size < 2 || (p[0] & 31) == 31)
		return -EINVAL;
	if (p[1] < 128) {
		*header = 2;
		return p[1] == size - 2 ? 0 : -EINVAL;
	}
	count = p[1] & 127;
	if (!count || count > 2 || count + 2 > size || !p[2])
		return -EINVAL;
	for (i = 0; i < count; i++)
		length = (length << 8) | p[2 + i];
	*header = count + 2;
	if (length < 128 || (count == 2 && length < 256) || length != size - *header)
		return -EINVAL;
	return 0;
}

int mt6878_md_mtk_note_field(void *context, size_t hdrlen, unsigned char tag,
			   const void *value, size_t vlen)
{
	struct md_der_fields *out = context;
	struct md_der_field *field;
	const u8 *data = (const u8 *)value - hdrlen;
	size_t header;

	if (out->count == MD_FIELDS_MAX || hdrlen > MD_CERT_MAX ||
	    vlen > MD_CERT_MAX - hdrlen ||
	    md_der_header(data, hdrlen + vlen, &header) || header != hdrlen)
		return -EINVAL;
	field = &out->fields[out->count++];
	field->data = data;
	field->size = hdrlen + vlen;
	field->header = header;
	field->tag = tag;
	return 0;
}

static int md_der_sequence(const u8 *data, size_t size, struct md_der_fields *out)
{
	size_t header;
	int ret;

	memset(out, 0, sizeof(*out));
	if (!data || size > MD_CERT_MAX || md_der_header(data, size, &header) || data[0] != 0x30)
		return -EINVAL;
	ret = asn1_ber_decoder(&mt6878_md_mtk_fields_decoder, out, data, size);
	return ret > 0 ? -EPROTO : ret;
}

static bool md_field_bytes(const struct md_der_field *field, const u8 *data, size_t size)
{
	return field->size == size && !memcmp(field->data, data, size);
}

static bool md_field_equal(const struct md_der_field *a, const struct md_der_field *b)
{
	return md_field_bytes(a, b->data, b->size);
}

static int md_bits(const struct md_der_field *field, size_t size, const u8 **out)
{
	if (field->tag != 3 || field->size - field->header != size + 1 || field->data[field->header])
		return -EINVAL;
	*out = field->data + field->header + 1;
	return 0;
}

static int md_pss_profile(const struct md_der_field *field)
{
	static const u8 pss[] = {
		0x30, 0x41, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d,
		0x01, 0x01, 0x0a, 0x30, 0x34, 0xa0, 0x0f, 0x30, 0x0d,
		0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02,
		0x01, 0x05, 0x00, 0xa1, 0x1c, 0x30, 0x1a, 0x06, 0x09,
		0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x08,
		0x30, 0x0d, 0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65,
		0x03, 0x04, 0x02, 0x01, 0x05, 0x00, 0xa2, 0x03, 0x02, 0x01, 0x20,
	};
	static const u8 trailer[] = { 0xa3, 3, 2, 1, 1 };
	u8 explicit_pss[sizeof(pss) + sizeof(trailer)];

	if (md_field_bytes(field, pss, sizeof(pss)))
		return 0;
	memcpy(explicit_pss, pss, sizeof(pss));
	explicit_pss[1] += sizeof(trailer);
	explicit_pss[14] += sizeof(trailer);
	memcpy(explicit_pss + sizeof(pss), trailer, sizeof(trailer));
	return md_field_bytes(field, explicit_pss, sizeof(explicit_pss)) ? 0 : -EINVAL;
}

static int md_spki(struct md_der_work *work, struct md_der_cert *cert)
{
	static const u8 algorithm[] = { 0x30, 0x0d, 6, 9, 0x2a, 0x86, 0x48, 0x86,
		0xf7, 0x0d, 1, 1, 1, 5, 0 };
	static const u8 exponent[] = { 2, 3, 1, 0, 1 };
	struct md_der_fields *fields = &work->scratch, *integers = &work->integers;
	const struct md_der_field *modulus;
	const u8 *raw;
	size_t size;

	if (md_der_sequence(cert->spki.data, cert->spki.size, fields) || fields->count != 2 ||
	    !md_field_bytes(&fields->fields[0], algorithm, sizeof(algorithm)))
		return -EINVAL;
	size = fields->fields[1].size - fields->fields[1].header;
	if (!size || md_bits(&fields->fields[1], size - 1, &raw) ||
	    md_der_sequence(raw, size - 1, integers) || integers->count != 2)
		return -EINVAL;
	modulus = &integers->fields[0];
	if (modulus->tag != 2 || modulus->size - modulus->header != 257 ||
	    modulus->data[modulus->header] || !(modulus->data[modulus->header + 1] & 0x80) ||
	    !(modulus->data[modulus->size - 1] & 1) ||
	    !md_field_bytes(&integers->fields[1], exponent, sizeof(exponent)))
		return -EINVAL;
	cert->raw_key.data = raw;
	cert->raw_key.size = size - 1;
	return 0;
}

static int md_parse_cert(struct md_der_work *work, const u8 *data, size_t size,
			 struct md_der_cert *cert)
{
	static const u8 legacy[] = { 0x30, 0x0d, 6, 9, 0x2a, 0x86, 0x48, 0x86,
		0xf7, 0x0d, 1, 1, 0x0b, 5, 0 };
	struct md_der_fields *envelope = &work->scratch;
	const u8 *signature;
	size_t i, j;
	int ret;

	memset(cert, 0, sizeof(*cert));
	ret = md_der_sequence(data, size, envelope);
	if (ret || envelope->count != 3 || md_pss_profile(&envelope->fields[1]) ||
	    md_bits(&envelope->fields[2], 256, &signature))
		return ret ? ret : -EINVAL;
	cert->tbs = envelope->fields[0];
	cert->signature = envelope->fields[2];
	ret = md_der_sequence(cert->tbs.data, cert->tbs.size, &cert->body);
	if (ret || cert->body.count < 7 || (cert->body.count - 7) % 2)
		return ret ? ret : -EINVAL;
	if (!md_field_equal(&cert->body.fields[2], &envelope->fields[1]) &&
	    !md_field_bytes(&cert->body.fields[2], legacy, sizeof(legacy)))
		return -EINVAL;
	cert->spki = cert->body.fields[6];
	ret = md_spki(work, cert);
	if (ret)
		return ret;
	for (i = 7; i < cert->body.count; i += 2) {
		if (cert->body.fields[i].tag != 6)
			return -EINVAL;
		for (j = 7; j < i; j += 2)
			if (md_field_equal(&cert->body.fields[i], &cert->body.fields[j]))
				return -EINVAL;
	}
	return 0;
}

static const struct md_der_field *md_metadata(const struct md_der_cert *cert, u8 group, u8 item)
{
	u8 oid[] = { 6, 7, 0x60, 0x86, 0x76, 0x93, 0x16, group, item };
	size_t i;

	for (i = 7; i < cert->body.count; i += 2)
		if (md_field_bytes(&cert->body.fields[i], oid, sizeof(oid)))
			return &cert->body.fields[i + 1];
	return NULL;
}

/* Private helper has a pin argument for isolated synthetic CI coverage; the
 * only public wrapper supplies the compiled audited pin, never a DT argument.
 */
static int md_mtk_verify_pin(const u8 *cert1, size_t size1, const u8 *cert2, size_t size2,
			     const u8 *header, size_t header_size,
			     struct mt6878_md_signed_hashes *out, const u8 pin[32])
{
	static const u8 zero_bits[] = { 3, 2, 0, 0 };
	static const u8 items[][2] = { { 2, 6 }, { 2, 8 }, { 4, 2 } };
	struct md_der_work *work;
	struct mt6878_md_pss32 *root = NULL, *leaf = NULL;
	struct mt6878_md_signed_hashes verified;
	const struct md_der_field *field;
	const u8 *expected;
	u8 hash[32];
	size_t i;
	int ret;

	if (!cert1 || !cert2 || !size1 || !size2 || size1 > MD_CERT_MAX || size2 > MD_CERT_MAX ||
	    !header || header_size != 512 || !out || !pin)
		return -EINVAL;
	work = kzalloc(sizeof(*work), GFP_KERNEL);
	if (!work)
		return -ENOMEM;
	ret = md_parse_cert(work, cert1, size1, &work->root);
	if (!ret)
		ret = md_parse_cert(work, cert2, size2, &work->leaf);
	if (ret)
		goto out;
	root = mt6878_md_pss32_create(work->root.raw_key.data, work->root.raw_key.size);
	if (IS_ERR(root)) {
		ret = PTR_ERR(root);
		goto out;
	}
	ret = mt6878_md_pss32_sha256(root, work->root.spki.data, work->root.spki.size, hash);
	if (ret)
		goto out;
	if (crypto_memneq(hash, pin, sizeof(hash))) {
		ret = -EKEYREJECTED;
		goto out;
	}
	field = md_metadata(&work->root, 1, 2);
	if (!field || !md_field_equal(field, &work->leaf.spki)) {
		ret = -EKEYREJECTED;
		goto out;
	}
	ret = mt6878_md_pss32_verify(root, work->root.tbs.data, work->root.tbs.size,
		work->root.signature.data + work->root.signature.header + 1, 256);
	if (ret)
		goto out;
	leaf = mt6878_md_pss32_create(work->leaf.raw_key.data, work->leaf.raw_key.size);
	if (IS_ERR(leaf)) {
		ret = PTR_ERR(leaf);
		goto out;
	}
	ret = mt6878_md_pss32_verify(leaf, work->leaf.tbs.data, work->leaf.tbs.size,
		work->leaf.signature.data + work->leaf.signature.header + 1, 256);
	if (ret)
		goto out;
	for (i = 0; i < ARRAY_SIZE(items); i++) {
		field = md_metadata(&work->leaf, items[i][0], items[i][1]);
		if (!field || !md_field_bytes(field, zero_bits, sizeof(zero_bits))) {
			ret = -EPROTONOSUPPORT;
			goto out;
		}
	}
	field = md_metadata(&work->leaf, 2, 4);
	if (!field || md_bits(field, 32, &expected)) {
		ret = -EINVAL;
		goto out;
	}
	memcpy(verified.header_sha256, expected, 32);
	ret = mt6878_md_pss32_sha256(leaf, header, header_size, hash);
	if (ret)
		goto out;
	if (crypto_memneq(hash, expected, sizeof(hash))) {
		ret = -EKEYREJECTED;
		goto out;
	}
	field = md_metadata(&work->leaf, 2, 1);
	if (!field || md_bits(field, 32, &expected)) {
		ret = -EINVAL;
		goto out;
	}
	memcpy(verified.payload_sha256, expected, 32);
	*out = verified;
	ret = 0;
out:
	mt6878_md_pss32_destroy(leaf);
	mt6878_md_pss32_destroy(root);
	memzero_explicit(hash, sizeof(hash));
	memzero_explicit(&verified, sizeof(verified));
	kfree_sensitive(work);
	return ret;
}

int mt6878_md_mtk_verify_header(const u8 *cert1, size_t cert1_size,
			      const u8 *cert2, size_t cert2_size,
			      const u8 *header, size_t header_size,
			      struct mt6878_md_signed_hashes *out)
{
	return md_mtk_verify_pin(cert1, cert1_size, cert2, cert2_size, header, header_size,
		out, md_mtk_root_pin);
}
EXPORT_SYMBOL_GPL(mt6878_md_mtk_verify_header);
MODULE_LICENSE("GPL");
