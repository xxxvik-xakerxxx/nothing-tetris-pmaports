// SPDX-License-Identifier: GPL-2.0-only
/* Reuse frozen resource mocks and actual controller without editing them. */
#define main frozen_resource_tests_main
#include "../sram-owner/test-sram-owner.c"
#undef main
#include "mt6878-gpueb-adoption.c"

int main(void)
{
	struct platform_device pdev = { .has_full = 1,
		.full = { GPUEB_SRAM_BASE, GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE - 1, IORESOURCE_MEM } };
	struct device wrong_parent = { 0 };
	struct resource gpr = { GPUEB_SRAM_BASE + GPUEB_GPR_OFFSET,
		GPUEB_SRAM_BASE + GPUEB_GPR_OFFSET + GPUEB_GPR_SIZE - 1, IORESOURCE_MEM };
	struct resource mbox = { GPUEB_SRAM_BASE + GPUEB_MBOX_OFFSET,
		GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE - 1, IORESOURCE_MEM };
	struct resource output = { 7, 8, 9 }, bad;
	struct mt6878_gpueb_adoption *parent;
	struct mt6878_gpueb_adopted_window *gpr_lease, *mbox_lease;
	int old_releases, old_unmaps;

	assert(!frozen_resource_tests_main());
	assert(PTR_ERR(mt6878_gpueb_adopt_parent(NULL)) == -EINVAL);
	assert(PTR_ERR(mt6878_gpueb_adopt_window(&pdev.dev, &gpr, GPUEB_WINDOW_GPR)) == -EPROBE_DEFER);
	pdev.has_full = 0;
	assert(PTR_ERR(mt6878_gpueb_adopt_parent(&pdev)) == -EINVAL);
	pdev.has_full = 1;
	parent = mt6878_gpueb_adopt_parent(&pdev);
	assert(!IS_ERR(parent));
	assert(PTR_ERR(mt6878_gpueb_adopt_parent(&pdev)) == -EBUSY);
	assert(PTR_ERR(mt6878_gpueb_adopt_window(&wrong_parent, &gpr, GPUEB_WINDOW_GPR)) == -EPROBE_DEFER);
	bad = gpr; bad.end -= 4;
	assert(PTR_ERR(mt6878_gpueb_adopt_window(&pdev.dev, &bad, GPUEB_WINDOW_GPR)) == -EINVAL);
	bad = gpr; bad.start -= 4; bad.end -= 4;
	assert(PTR_ERR(mt6878_gpueb_adopt_window(&pdev.dev, &bad, GPUEB_WINDOW_GPR)) == -EINVAL);
	assert(PTR_ERR(mt6878_gpueb_adopt_window(&pdev.dev, &mbox, GPUEB_WINDOW_GPR)) == -ERANGE);
	gpr_lease = mt6878_gpueb_adopt_window(&pdev.dev, &gpr, GPUEB_WINDOW_GPR);
	mbox_lease = mt6878_gpueb_adopt_window(&pdev.dev, &mbox, GPUEB_WINDOW_MBOX);
	assert(!IS_ERR(gpr_lease) && !IS_ERR(mbox_lease));
	assert(!mt6878_gpueb_adopted_resource(gpr_lease, &output));
	assert(output.start == gpr.start && output.end == gpr.end);
	assert(mt6878_gpueb_adoption_io_gate(gpr_lease) == -EOPNOTSUPP);
	old_releases = releases; old_unmaps = unmaps;
	assert(mt6878_gpueb_unadopt_parent(parent) == -EBUSY);
	assert(releases == old_releases && unmaps == old_unmaps);
	mt6878_gpueb_unadopt_window(gpr_lease);
	mt6878_gpueb_unadopt_window(mbox_lease);
	assert(!mt6878_gpueb_unadopt_parent(parent));
	assert(!adopted && !claim_active && !pdev.dev.refs);

	parent = mt6878_gpueb_adopt_parent(&pdev);
	assert(!IS_ERR(parent));
	gpr_lease = mt6878_gpueb_adopt_window(&pdev.dev, &gpr, GPUEB_WINDOW_GPR);
	assert(!IS_ERR(gpr_lease));
	assert(!mt6878_gpueb_adoption_unknown_start(parent));
	output = (struct resource){ 7, 8, 9 };
	assert(mt6878_gpueb_adopted_resource(gpr_lease, &output) == -ESHUTDOWN);
	assert(output.start == 7 && output.end == 8);
	assert(mt6878_gpueb_adoption_io_gate(gpr_lease) == -ESHUTDOWN);
	mt6878_gpueb_unadopt_window(gpr_lease);
	old_releases = releases; old_unmaps = unmaps;
	assert(mt6878_gpueb_unadopt_parent(parent) == -EBUSY);
	assert(adopted == parent && claim_active && pdev.dev.refs == 1);
	assert(releases == old_releases && unmaps == old_unmaps);
	/* Mock fixture disposal only, NEVER a production OFF/recovery path. */
	free(parent->sram->mapping);
	free(parent->sram);
	free(parent);
	adopted = NULL; claim_active = 0; pdev.dev.refs = 0;
	puts("Parent adoption + real frozen resource owner tests PASS; MMIO gate closed");
	return 0;
}
