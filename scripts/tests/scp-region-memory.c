/* SPDX-License-Identifier: GPL-2.0 */
/* Actual patched helpers are compiled above this harness. No device access. */
static unsigned int checks, failures;

#define CHECK(condition) do { \
	checks++; \
	if (!(condition)) { \
		fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); \
		failures++; \
	} \
} while (0)

static void setup(u32 base, u32 cores, u32 secure)
{
	scpreg.core_nums = cores;
	scpreg.secure_dump = secure;
	scpreg.scp_dram_region = 1;
	scp_region_info_copy = (struct scp_region_info_st) {
		.struct_size = sizeof(scp_region_info_copy),
		.ap_loader_start = base,
		.ap_loader_size = 0x2000,
		.ap_firmware_start = base + 0x2000,
		.ap_firmware_size = 0x100000,
		.ap_dram_start = base + 0x700000,
		.ap_dram_size = 0x924740,
		.ap_dram_backup_start = base + 0x700000 + 0x924800,
	};
}

int main(void)
{
	const u32 bases[] = { 0xb8000000, 0xa4000000 };
	struct scp_region_info_st before;

	for (size_t i = 0; i < sizeof(bases) / sizeof(bases[0]); i++) {
		setup(bases[i], 2, 1);
		before = scp_region_info_copy;
		CHECK(scp_region_info_validate() == 0);
		CHECK(scp_region_dram_map_size() == 0x924800);
		CHECK(scp_region_memory_validate(bases[i], 0x2300000) == 0);
		CHECK(!memcmp(&before, &scp_region_info_copy, sizeof(before)));
		/* The old unconditional four-bank mapping exceeded this reservation. */
		CHECK(!scp_region_contains(bases[i], 0x2300000,
			bases[i] + 0x700000, 4 * 0x924800));

		setup(bases[i], 1, 0);
		CHECK(scp_region_info_validate() == 0);
		CHECK(scp_region_dram_map_size() == 2 * 0x924800);
		CHECK(scp_region_memory_validate(bases[i], 0x2300000) == 0);

		setup(bases[i], 2, 0);
		CHECK(scp_region_info_validate() == -EINVAL);
		CHECK(scp_region_dram_map_size() == 0);
		scp_region_info_copy.ap_dram_backup_start += 0x924800;
		CHECK(scp_region_info_validate() == 0);
		CHECK(scp_region_dram_map_size() == 3 * 0x924800);
		CHECK(scp_region_memory_validate(bases[i], 0x2300000) == 0);
		CHECK(scp_region_memory_validate(bases[i], 0x2200000) == -ERANGE);
	}

	setup(bases[0], 0, 0);
	CHECK(scp_region_info_validate() == -EINVAL);
	scpreg.core_nums = 3;
	CHECK(scp_region_info_validate() == -EINVAL);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_dram_backup_start = scp_region_info_copy.ap_dram_start;
	CHECK(scp_region_info_validate() == -EINVAL);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_dram_backup_start = 0xba300000;
	CHECK(scp_region_info_validate() == 0);
	CHECK(scp_region_memory_validate(bases[0], 0x2300000) == -ERANGE);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_dram_backup_start = 0xfffff000;
	CHECK(scp_region_info_validate() == -EINVAL);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_dram_size = 0x80000000;
	CHECK(scp_region_info_validate() == -EINVAL);
	scp_region_info_copy.ap_dram_size = UINT32_MAX;
	CHECK(scp_region_info_validate() == -EINVAL);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_loader_start--;
	CHECK(scp_region_memory_validate(bases[0], 0x2300000) == -ERANGE);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_firmware_start = 0xba2ff000;
	CHECK(scp_region_memory_validate(bases[0], 0x2300000) == -ERANGE);
	setup(bases[0], 2, 1);
	CHECK(scp_region_memory_validate(bases[0], 0) == -ERANGE);
	CHECK(scp_region_memory_validate(0x100000000ULL, 0x2300000) == -ERANGE);
	CHECK(scp_region_contains(0x1000, 0x1000, 0x1800, 0x800));
	CHECK(!scp_region_contains(0x1000, 0x1000, 0x1800, 0x801));
	CHECK(!scp_region_contains(0x1000, 0x1000, 0x2000, 1));
	CHECK(!scp_region_contains(0x1000, 0x1000, 0x1800, 0));
	setup(0x1000, 2, 0);
	scp_region_info_copy.ap_dram_start = 0x100000;
	scp_region_info_copy.ap_dram_size = 0x60000000;
	scp_region_info_copy.ap_dram_backup_start = 0xc0100000;
	CHECK(scp_region_info_validate() == -EINVAL);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_dram_start = 0xfffffc00;
	scp_region_info_copy.ap_dram_size = 1025;
	CHECK(scp_region_info_validate() == -EINVAL);
	setup(bases[0], 2, 1);
	scp_region_info_copy.ap_dram_start = 0;
	scp_region_info_copy.ap_dram_size = 0;
	scp_region_info_copy.ap_dram_backup_start = 0;
	CHECK(scp_region_info_validate() == -EINVAL);
	scpreg.scp_dram_region = 0;
	CHECK(scp_region_info_validate() == 0);
	CHECK(scp_region_memory_validate(bases[0], 0x2300000) == 0);
	printf("%u memory checks, %u failures\n", checks, failures);
	return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
