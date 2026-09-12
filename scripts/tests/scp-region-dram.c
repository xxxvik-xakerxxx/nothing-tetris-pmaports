/* SPDX-License-Identifier: GPL-2.0 */
/* Included after the actual vendor structure and patched validator. */
struct dram_case {
	const char *name;
	u32 start;
	u32 size;
	u32 required;
	int expected;
};

int main(void)
{
	static const struct dram_case cases[] = {
		{ "optional absent", 0, 0, 0, 0 },
		{ "required absent", 0, 0, 1, -EINVAL },
		{ "optional aligned", 0x100000, 1024, 0, 0 },
		{ "required aligned", 0x100000, 1024, 1, 0 },
		{ "unaligned size", 0x100000, 1025, 1, 0 },
		{ "minimum size", 0x100000, 1, 0, 0 },
		{ "missing start", 0, 1024, 0, -EINVAL },
		{ "missing size", 0x100000, 0, 0, -EINVAL },
		{ "single range wraps with flag off", 0xfffffc00, 2048, 0, -EINVAL },
		{ "backup span wraps", 0xfffff000, 1024, 1, -EINVAL },
		{ "backup span wraps with flag off", 0xfffff000, 1024, 0, -EINVAL },
		{ "rounding crosses address limit", 0xffffe001, 1025, 1, -EINVAL },
		{ "last nonwrapping end", 0xffffefff, 1024, 1, 0 },
		{ "rounding overflow", 0x100000, 0xfffffc01, 0, -EINVAL },
		{ "multiplication overflow", 0x100000, 0x40000000, 1, -EINVAL },
		{ "rounding triggers multiplication overflow", 0x100000, 0x3ffffc01, 0, -EINVAL },
		{ "signed predicate boundary", 0x100000, 0x80000000, 0, -EINVAL },
		{ "maximum u32 size", 0x100000, UINT32_MAX, 1, -EINVAL },
	};
	unsigned int failures = 0;

	for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
		struct scp_region_info_st before;
		int result;

		scp_region_info_copy = (struct scp_region_info_st) {
			.struct_size = sizeof(scp_region_info_copy),
			.ap_loader_start = 0x200000,
			.ap_loader_size = 4096,
			.ap_firmware_start = 0x300000,
			.ap_firmware_size = 8192,
			.ap_dram_start = cases[i].start,
			.ap_dram_size = cases[i].size,
		};
		scpreg.scp_dram_region = cases[i].required;
		before = scp_region_info_copy;
		result = scp_region_info_validate();
		if (result != cases[i].expected ||
		    memcmp(&before, &scp_region_info_copy, sizeof(before))) {
			fprintf(stderr, "FAIL %s: got %d expected %d\n",
				cases[i].name, result, cases[i].expected);
			failures++;
		}
	}
	printf("%zu DRAM cases, %u failures\n",
	       sizeof(cases) / sizeof(cases[0]), failures);
	return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}

