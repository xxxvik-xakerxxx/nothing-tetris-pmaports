/* SPDX-License-Identifier: GPL-2.0-or-later */
#define main existing_ccci_tests
#include "tetris_ccci_handoff.c"
#undef main

static void set_stock48(struct fixture *fixture, u8 *raw, int len)
{
	require(!fdt_setprop(fixture->fdt, modem_node(fixture),
		"ccci,modem_info_v2", raw, len), "set stock48 descriptor");
}

int main(void)
{
	struct fixture fixture;
	u8 raw[64] = { 0 };
	const void *prefix;
	int len, ret;

	existing_ccci_tests();
	fixture_init(&fixture, true, false);
	prefix = fdt_getprop(fixture.fdt, modem_node(&fixture), "ccci,modem_info_v2", &len);
	require(prefix && len == 32, "existing fixture has exact prefix");
	memcpy(raw, prefix, 32);
	put_le32(raw + 16, 3);
	set_stock48(&fixture, raw, 48);
#ifdef EXPECT_OLD_REJECTION
	require(observe(&fixture, &ret) == TETRIS_CCCI_BAD_DESCRIPTOR_SIZE && ret < 0,
		"baseline rejects the actual stock property length");
	puts("PASS: baseline stock48 length rejection reproduced");
#else
	int failure = observe(&fixture, &ret);
	if (failure != TETRIS_CCCI_OK || ret)
		fprintf(stderr, "stock48 failure=%d ret=%d\n", failure, ret);
	require(failure == TETRIS_CCCI_OK && !ret,
		"zero-tail stock48 accepted");
	for (int i = 32; i < 48; i++) {
		raw[i] = 1;
		set_stock48(&fixture, raw, 48);
		fixture.map_calls = 0;
		require(observe(&fixture, &ret) != TETRIS_CCCI_OK && ret < 0 && !fixture.map_calls,
			"each nonzero extension byte rejected before mapping");
		raw[i] = 0;
	}
	for (int size = 33; size <= 64; size++) {
		if (size == 48)
			continue;
		set_stock48(&fixture, raw, size);
		require(observe(&fixture, &ret) == TETRIS_CCCI_BAD_DESCRIPTOR_SIZE && ret < 0,
			"noncanonical extension length rejected");
	}
	for (unsigned int version = 0; version <= 4; version++) {
		if (version == 3)
			continue;
		put_le32(raw + 16, version);
		set_stock48(&fixture, raw, 48);
		require(observe(&fixture, &ret) != TETRIS_CCCI_OK && ret < 0,
			"stock48 is exclusive to version three");
	}
	put_le32(raw + 16, 3);
	put_le32(raw + 12, 1);
	set_stock48(&fixture, raw, 48);
	require(observe(&fixture, &ret) == TETRIS_CCCI_BAD_DESCRIPTOR_STATUS && ret < 0,
		"prefix errors still rejected");
	puts("PASS: stock48 positive and 52 negative extension/prefix cases");
#endif
	return 0;
}
