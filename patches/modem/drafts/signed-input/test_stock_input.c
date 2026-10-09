/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Real factory input and public fixed-pin verifier: no private trust override. */
static void reset_faults(void)
{
	assert(!live);
	fail_stage = allocations = hash_calls = hash_fault = rsa_fault = rsa_calls = 0;
	maxsize_fault = digestsize_fault = short_output = snapshot_fault = firmware_fault = 0;
	hash_error = -EIO;
}
static void rejected(const u8 *data, size_t size, u64 capacity, int expected)
{
	struct mt6878_md_fw_metadata *owner = (void *)(uintptr_t)1;
	int ret = mt6878_md_fw_prepare(data, size, capacity, &owner);
	assert(ret < 0 && (!expected || ret == expected));
	assert(!owner && !live);
}
static void expected_digest(const u8 *data, size_t size, const u8 expected[32])
{
	u8 hash[32];
	unsigned int written;
	assert(EVP_Digest(data, size, hash, &written, EVP_sha256(), NULL) == 1 && written == 32);
	assert(!memcmp(hash, expected, 32));
}
static void expected_identity(const u8 *data, size_t size,
			      const struct mt6878_md_fw_identity *identity)
{
	const u8 *check;
	assert(identity->source_size == size);
	for (unsigned int i = 0; i < MT6878_MD_FW_MEMBERS; i++) {
		const struct mt6878_md_fw_member_identity *member = &identity->member[i];
		size_t cursor;
		struct md_fw_part cert;
		assert(member->header_offset <= size && size - member->header_offset >= 512);
		assert(member->payload_offset == member->header_offset + 512);
		assert(member->stored_size <= size - member->payload_offset);
		expected_digest(data + member->header_offset, 512, member->header_sha256);
		expected_digest(data + member->payload_offset, member->stored_size, member->payload_sha256);
		cursor = (member->payload_offset + member->stored_size + 15) & ~(size_t)15;
		assert(!md_fw_next(data, size, &cursor, &cert));
		expected_digest(data + cert.payload, cert.size, member->cert1_sha256);
		assert(!md_fw_next(data, size, &cursor, &cert));
		expected_digest(data + cert.payload, cert.size, member->cert2_sha256);
	}
	check = data + identity->member[0].payload_offset + identity->member[0].stored_size - 512;
	assert(identity->memory_size == md_fw_word(check + 172));
	assert(identity->logical_image_size == md_fw_word(check + 176));
	assert(identity->dsp_offset == md_fw_word(check + 184));
	assert(identity->dsp_capacity == md_fw_word(check + 188));
	assert(identity->region_count == md_fw_word(check + 192));
	for (u32 i = 0; i < identity->region_count; i++) {
		assert(identity->region_offset[i] == md_fw_word(check + 196 + 8 * i));
		assert(identity->region_size[i] == md_fw_word(check + 200 + 8 * i));
	}
}
static void test_existing_loader_placement(struct mt6878_md_fw_metadata *owner,
					 u8 *data, const struct mt6878_md_fw_identity *identity)
{
	struct tetris_modem_boot_plan plan, expected = { 0 }, untouched;
	u8 saved[512], *allocation, *window;
	const u8 *rom = data + identity->member[0].payload_offset;
	size_t size = identity->memory_size;
	int hashes = hash_calls, rsa = rsa_calls, refs = live;

	assert(!tetris_modem_plan_layout(rom, identity->member[0].stored_size,
		identity->member[2].stored_size, size, &expected.layout));
	assert(!tetris_modem_plan_smem_rom_b41(rom, identity->member[0].stored_size,
		identity->member[2].stored_size, size, 1, &expected.smem_inputs, &expected.smem));
	allocation = malloc(size + 2);
	assert(allocation);
	window = allocation + 1;
	allocation[0] = 0xfd;
	allocation[size + 1] = 0xfe;
	if (identity->dsp_offset > identity->member[0].stored_size)
		window[identity->member[0].stored_size] = 0xc7;
	if (size > identity->dsp_offset + identity->member[2].stored_size)
		window[size - 1] = 0xc8;
	memcpy(saved, rom, sizeof(saved));
	memset(data + identity->member[0].payload_offset, 0xa5, sizeof(saved));
	assert(!mt6878_md_fw_place_b41(owner, window, size, 1, &plan));
	memcpy(data + identity->member[0].payload_offset, saved, sizeof(saved));
	assert(!memcmp(&plan.layout, &expected.layout, sizeof(plan.layout)));
	assert(!memcmp(&plan.smem_inputs, &expected.smem_inputs, sizeof(plan.smem_inputs)));
	assert(!memcmp(&plan.smem, &expected.smem, sizeof(plan.smem)));
	expected_digest(window, identity->member[0].stored_size, identity->member[0].payload_sha256);
	expected_digest(window + identity->dsp_offset, identity->member[2].stored_size,
		identity->member[2].payload_sha256);
	assert(allocation[0] == 0xfd && allocation[size + 1] == 0xfe);
	if (identity->dsp_offset > identity->member[0].stored_size)
		assert(window[identity->member[0].stored_size] == 0xc7);
	if (size > identity->dsp_offset + identity->member[2].stored_size)
		assert(window[size - 1] == 0xc8);
	assert(hash_calls == hashes && rsa_calls == rsa && live == refs);
	memset(&plan, 0xa5, sizeof(plan));
	untouched = plan;
	window[0] = 0xab;
	window[identity->dsp_offset] = 0xcd;
	assert(mt6878_md_fw_place_b41(owner, window, size - 1, 1, &plan) == -ERANGE);
	assert(mt6878_md_fw_place_b41(owner, window, size, 99, &plan) == -EINVAL);
	assert(mt6878_md_fw_place_b41(owner, window, SIZE_MAX, 1, &plan) == -EINVAL);
	assert(mt6878_md_fw_place_b41(owner, window, size, 1,
		(struct tetris_modem_boot_plan *)window) == -EINVAL);
	assert(mt6878_md_fw_place_b41(owner, owner->verified_source,
		identity->source_size, 1, &plan) == -EINVAL);
	assert(window[0] == 0xab && window[identity->dsp_offset] == 0xcd);
	assert(!memcmp(&plan, &untouched, sizeof(plan)));
	assert(hash_calls == hashes && rsa_calls == rsa && live == refs);
	free(allocation);
}
int main(int argc, char **argv)
{
	struct mt6878_md_fw_metadata *owner;
	struct mt6878_md_fw_identity baseline, copy;
	struct device dev = { 0 };
	FILE *file;
	long length;
	u8 *data;
	u8 slice[512], expected_slice[512];
	int complete_hashes;
	const int faults[] = { 1, 21, 22, 23, 24, 44, 47, 67, 69 };
	const char *filename;

	assert(argc == 1 || argc == 2);
	filename = argc == 2 ? argv[1] : getenv("MT6878_MD_STOCK_INPUT");
	assert(filename && *filename);
	file = fopen(filename, "rb");
	assert(file && !fseek(file, 0, SEEK_END));
	length = ftell(file);
	assert(length > 0 && (unsigned long)length <= MD_SOURCE_MAX);
	assert(!fseek(file, 0, SEEK_SET));
	data = malloc((size_t)length);
	assert(data && fread(data, 1, (size_t)length, file) == (size_t)length);
	assert(!fclose(file));
	reset_faults();
	assert(!mt6878_md_fw_prepare(data, length, UINT32_MAX, &owner));
	assert(!mt6878_md_fw_snapshot(owner, &baseline));
	complete_hashes = hash_calls;
	assert(rsa_calls == 6 && complete_hashes == 69);
	assert(live == 2 && baseline.memory_size && baseline.consumed_size <= (u64)length);
	expected_identity(data, length, &baseline);
	assert(mt6878_md_fw_get(owner) == owner);
	mt6878_md_fw_put(owner);
	for (unsigned int i = 0; i < MT6878_MD_FW_MEMBERS; i++) {
		size_t offset = baseline.member[i].payload_offset;
		assert(baseline.member[i].stored_size >= sizeof(slice));
		memcpy(expected_slice, data + offset, sizeof(slice));
		memset(data + offset, 0xa5, sizeof(slice));
		assert(!mt6878_md_fw_copy_payload(owner, i, 0, slice, sizeof(slice)));
		assert(!memcmp(slice, expected_slice, sizeof(slice)));
		memcpy(data + offset, expected_slice, sizeof(slice));
		assert(!mt6878_md_fw_snapshot(owner, &copy) && !memcmp(&baseline, &copy, sizeof(copy)));
	}
	memset(slice, 0xa5, sizeof(slice));
	memcpy(expected_slice, slice, sizeof(slice));
	assert(mt6878_md_fw_copy_payload(owner, 3, 0, slice, sizeof(slice)) == -EINVAL);
	assert(mt6878_md_fw_copy_payload(owner, 0, baseline.member[0].stored_size,
		slice, 1) == -ERANGE);
	assert(mt6878_md_fw_copy_payload(owner, 0, SIZE_MAX, slice, 1) == -ERANGE);
	assert(mt6878_md_fw_copy_payload(owner, 0, 0, slice, SIZE_MAX) == -ERANGE);
	assert(mt6878_md_fw_copy_payload(owner, 0, 0, NULL, 1) == -EINVAL);
	assert(mt6878_md_fw_copy_payload(owner, 0, 0, slice, 0) == -EINVAL);
	assert(mt6878_md_fw_copy_payload(owner, 0, 0, (void *)owner->verified_source, 1) == -EINVAL);
	assert(mt6878_md_fw_copy_payload(owner, 0, 0, owner, 1) == -EINVAL);
	assert(!memcmp(slice, expected_slice, sizeof(slice)));
	test_existing_loader_placement(owner, data, &baseline);
	mt6878_md_fw_put(owner);
	assert(!live && !mt6878_md_fw_get(NULL));
	reset_faults();
	rejected(data, length, baseline.memory_size - 1, -ERANGE);
	reset_faults();
	rejected(data, baseline.consumed_size - 16, UINT32_MAX, 0);
	for (unsigned int i = 0; i < MT6878_MD_FW_MEMBERS; i++) {
		size_t offsets[] = { baseline.member[i].header_offset + 40,
			baseline.member[i].payload_offset,
			baseline.member[i].payload_offset + baseline.member[i].stored_size - 1 };
		for (unsigned int j = 0; j < ARRAY_SIZE(offsets); j++) {
			reset_faults();
			data[offsets[j]] ^= 1;
			rejected(data, length, UINT32_MAX, -EKEYREJECTED);
			data[offsets[j]] ^= 1;
		}
	}
	for (unsigned int i = 0; i < ARRAY_SIZE(faults); i++) {
		reset_faults();
		hash_fault = faults[i];
		rejected(data, length, UINT32_MAX, -EIO);
		assert(hash_calls == hash_fault);
	}
	reset_faults();
	hash_fault = 1;
	hash_error = 1;
	rejected(data, length, UINT32_MAX, -EPROTO);
	reset_faults();
	rsa_fault = -ETIMEDOUT;
	rejected(data, length, UINT32_MAX, -ETIMEDOUT);
	reset_faults();
	snapshot_fault = 1;
	rejected(data, length, UINT32_MAX, -ENOMEM);
	reset_faults();
	fail_stage = FAIL_CONTEXT;
	rejected(data, length, UINT32_MAX, -ENOMEM);
	reset_faults();
	fail_stage = FAIL_SHA;
	rejected(data, length, UINT32_MAX, -ENOENT);
	reset_faults();
	digestsize_fault = 1;
	rejected(data, length, UINT32_MAX, -EPROTO);
	reset_faults();
	fixture_firmware.data = data;
	fixture_firmware.size = length;
	snapshot_fault = 1; /* request uses the immutable firmware blob, no snapshot alloc. */
	assert(!mt6878_md_fw_request(&dev, "fixture-stock", UINT32_MAX, &owner));
	assert(firmware_releases == 0 && live == 1);
	assert(mt6878_md_fw_get(owner) == owner);
	mt6878_md_fw_put(owner);
	assert(firmware_releases == 0);
	assert(!mt6878_md_fw_copy_payload(owner, 0, 0, slice, sizeof(slice)));
	assert(!memcmp(slice, data + baseline.member[0].payload_offset, sizeof(slice)));
	mt6878_md_fw_put(owner);
	assert(firmware_releases == 1 && !live);
	reset_faults();
	firmware_fault = -ENOENT;
	assert(mt6878_md_fw_request(&dev, "fixture-stock", UINT32_MAX, &owner) == -ENOENT);
	assert(!owner && firmware_releases == 1 && !live);
	reset_faults();
	data[baseline.member[0].payload_offset] ^= 1;
	assert(mt6878_md_fw_request(&dev, "fixture-stock", UINT32_MAX, &owner) == -EKEYREJECTED);
	assert(!owner && firmware_releases == 2 && !live);
	free(data);
	puts("factory signed-input public-root crypto/lifetime/fault checks PASS; no hardware admission");
	return 0;
}
