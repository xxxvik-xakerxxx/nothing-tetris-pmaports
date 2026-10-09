/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Appended to real kernel decoder + production PSS32/MTK profile in CI. */
static void reset_faults(void)
{
	fail_stage = allocations = hash_calls = hash_fault = rsa_fault = rsa_calls = 0;
	maxsize_fault = digestsize_fault = short_output = 0;
	hash_error = -EIO;
}
static void output_untouched(const struct mt6878_md_signed_hashes *out)
{
	const u8 *p = (const u8 *)out;
	for (size_t i = 0; i < sizeof(*out); i++)
		assert(p[i] == 0xa5);
}
static int synthetic_verify(const u8 *a, size_t an, const u8 *b, size_t bn,
			    const u8 *header, struct mt6878_md_signed_hashes *out)
{
	return md_mtk_verify_pin(a, an, b, bn, header, 512, out, fixture_pin);
}
int main(void)
{
	struct mt6878_md_signed_hashes out;
	u8 bad[MD_CERT_MAX + 1], header[512];
	struct md_der_work *work;
	int ret;

	reset_faults();
	memset(&out, 0xa5, sizeof(out));
	assert(mt6878_md_mtk_verify_header(fixture_root, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, 512, &out) == -EKEYREJECTED);
	output_untouched(&out);
	assert(!live); /* Public root pin is NEVER replaced by synthetic CI pin. */
	reset_faults();
	assert(!synthetic_verify(fixture_root, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, &out));
	assert(!memcmp(out.header_sha256, fixture_header_hash, 32));
	assert(!memcmp(out.payload_sha256, fixture_payload_hash, 32));
	assert(hash_calls == 20 && rsa_calls == 2 && !live);
	assert(mt6878_md_mtk_verify_header(NULL, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, 512, &out) == -EINVAL);
	assert(mt6878_md_mtk_verify_header(fixture_root, MD_CERT_MAX + 1, fixture_leaf,
		sizeof(fixture_leaf), fixture_header, 512, &out) == -EINVAL);
	assert(mt6878_md_mtk_verify_header(fixture_root, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, 511, &out) == -EINVAL);
	assert(mt6878_md_mtk_verify_header(fixture_root, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, 512, NULL) == -EINVAL);
	assert(!live);
	/* Reject every truncation through the actual generated kernel ASN.1 engine. */
	for (size_t n = 0; n < sizeof(fixture_root); n++) {
		reset_faults(); memset(&out, 0xa5, sizeof(out));
		assert(synthetic_verify(fixture_root, n, fixture_leaf, sizeof(fixture_leaf),
			fixture_header, &out) != 0);
		output_untouched(&out); assert(!live);
	}
	for (size_t n = 0; n < sizeof(fixture_leaf); n++) {
		reset_faults(); memset(&out, 0xa5, sizeof(out));
		assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_leaf, n,
			fixture_header, &out) != 0);
		output_untouched(&out); assert(!live);
	}
	for (int n = 1; n <= 20; n++) {
		reset_faults(); hash_fault = n; memset(&out, 0xa5, sizeof(out));
		assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_leaf,
			sizeof(fixture_leaf), fixture_header, &out) == -EIO);
		assert(hash_calls == n && !live); output_untouched(&out);
	}
	reset_faults(); hash_fault = 1; hash_error = 1;
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, &out) == -EPROTO && !live);
	reset_faults(); fail_stage = FAIL_CONTEXT; memset(&out, 0xa5, sizeof(out));
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, &out) == -ENOMEM && !live);
	output_untouched(&out);
	reset_faults(); rsa_fault = -ETIMEDOUT;
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, &out) == -ETIMEDOUT && !live);
	assert(rsa_calls == 1);
	reset_faults();
	memcpy(bad, fixture_root, sizeof(fixture_root)); bad[sizeof(fixture_root) - 1] ^= 1;
	assert(synthetic_verify(bad, sizeof(fixture_root), fixture_leaf, sizeof(fixture_leaf),
		fixture_header, &out) == -EKEYREJECTED && !live);
	memcpy(bad, fixture_leaf, sizeof(fixture_leaf)); bad[sizeof(fixture_leaf) - 1] ^= 1;
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), bad, sizeof(fixture_leaf),
		fixture_header, &out) == -EKEYREJECTED && !live);
	memcpy(header, fixture_header, 512); header[1] ^= 1;
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_leaf, sizeof(fixture_leaf),
		header, &out) == -EKEYREJECTED && !live);
	assert(synthetic_verify(fixture_wrong_delegation, sizeof(fixture_wrong_delegation), fixture_leaf,
		sizeof(fixture_leaf), fixture_header, &out) == -EKEYREJECTED && !live);
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_transformed,
		sizeof(fixture_transformed), fixture_header, &out) == -EPROTONOSUPPORT && !live);
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_duplicate_oid,
		sizeof(fixture_duplicate_oid), fixture_header, &out) == -EINVAL && !live);
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_missing_digest,
		sizeof(fixture_missing_digest), fixture_header, &out) == -EINVAL && !live);
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_bad_bits,
		sizeof(fixture_bad_bits), fixture_header, &out) == -EINVAL && !live);
	assert(!synthetic_verify(fixture_explicit_root, sizeof(fixture_explicit_root), fixture_explicit_leaf,
		sizeof(fixture_explicit_leaf), fixture_header, &out) && !live);
	assert(synthetic_verify(fixture_root, sizeof(fixture_root), fixture_salt64,
		sizeof(fixture_salt64), fixture_header, &out) == -EKEYREJECTED && !live);
	/* Noncanonical DER/SPKI/table bounds tested before crypto. */
	work = calloc(1, sizeof(*work)); assert(work);
	for (size_t i = 0; i < sizeof(fixture_leaf); i++) {
		memcpy(bad, fixture_leaf, sizeof(fixture_leaf)); bad[i] ^= 0x80;
		ret = md_parse_cert(work, bad, sizeof(fixture_leaf), &work->leaf);
		assert(ret <= 0); /* Parser success is not signature/trust success. */
	}
	const u8 indefinite[] = { 0x30, 0x80, 0, 0 };
	const u8 nonminimal[] = { 0x30, 0x81, 1, 0 };
	assert(md_parse_cert(work, indefinite, sizeof(indefinite), &work->leaf) == -EINVAL);
	assert(md_parse_cert(work, nonminimal, sizeof(nonminimal), &work->leaf) == -EINVAL);
	assert(md_parse_cert(work, fixture_many_fields, sizeof(fixture_many_fields), &work->leaf) == -EINVAL);
	memcpy(bad, fixture_leaf, sizeof(fixture_leaf)); bad[sizeof(fixture_leaf)] = 0;
	assert(md_parse_cert(work, bad, sizeof(fixture_leaf) + 1, &work->leaf) == -EINVAL);
	assert(md_parse_cert(work, bad, MD_CERT_MAX + 1, &work->leaf) == -EINVAL);
	free(work);
	assert(!live);
	puts("production MTK DER + real kernel ASN.1 + PSS32 crypto fault tests PASS");
	return 0;
}
