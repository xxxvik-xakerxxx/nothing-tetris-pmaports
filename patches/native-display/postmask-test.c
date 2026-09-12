// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
#define BIT(n) (1U << (n))
struct cmdq_pkt { int unused; };
struct cmdq_client_reg { int unused; };
struct mtk_ddp_comp_dev {
	void *regs;
	struct cmdq_client_reg cmdq_reg;
};
struct device { const char *of_node; struct mtk_ddp_comp_dev *priv; };
static u32 words[1024];
static unsigned int offsets[16], writes;
static void *dev_get_drvdata(struct device *dev) { return dev->priv; }
static bool of_device_is_compatible(const char *node, const char *name)
{
	return !strcmp(node, name);
}
static void writel(u32 value, void *address)
{
	uintptr_t offset = (uintptr_t)address - (uintptr_t)words;
	assert(offset < sizeof(words) && offset % 4 == 0 && writes < 16);
	offsets[writes++] = offset;
	words[offset / 4] = value;
}
#define writel_relaxed writel
static void mtk_ddp_write(struct cmdq_pkt *pkt, unsigned int value,
	struct cmdq_client_reg *cmdq, void *regs, unsigned int offset)
{
	writel(value, (char *)regs + offset);
}
static void mtk_ddp_write_mask(struct cmdq_pkt *pkt, unsigned int value,
	struct cmdq_client_reg *cmdq, void *regs, unsigned int offset, unsigned int mask)
{
	mtk_ddp_write(pkt, (words[offset / 4] & ~mask) | (value & mask), cmdq, regs, offset);
}
#include "postmask-source.h"

int main(void)
{
	struct mtk_ddp_comp_dev priv = { .regs = words };
	struct device dev = { .priv = &priv };
	struct cmdq_pkt packet;
	unsigned int soc, queued, pass, configurations = 0;
	for (soc = 0; soc < 2; soc++) {
		dev.of_node = soc ? "mediatek,mt6878-disp-postmask" : "mediatek,mt8192-disp-postmask";
		for (queued = 0; queued < 2; queued++) {
			for (pass = 0; pass < 2; pass++) {
				unsigned int width = pass ? 720 : 1080, height = pass ? 1600 : 2400;
				memset(words, 0, sizeof(words));
				words[8 / 4] = 0x917;
				words[0x24 / 4] = 0x80000001;
				words[0x100 / 4] = 0x12345678;
				words[0x104 / 4] = 0x87654321;
				writes = 0;
				mtk_postmask_config(&dev, width, height, 60, 8, queued ? &packet : NULL);
				assert(words[0] == 0);
				assert(words[0x20 / 4] == (soc ? 0x147U : 1U));
				assert(words[0x30 / 4] == (width << 16 | height));
				assert(words[8 / 4] == (soc ? 0U : 0x917U));
				assert(words[0x24 / 4] == (soc ? 0x80000003U : 0x80000001U));
				assert(writes == (soc ? 4U : 2U));
				if (soc) assert(offsets[0] == 8 && offsets[1] == 0x24);
				assert(offsets[writes - 2] == 0x30 && offsets[writes - 1] == 0x20);
				mtk_postmask_start(&dev);
				assert(words[0] == 1 && offsets[writes - 1] == 0);
				mtk_postmask_stop(&dev);
				assert(words[0] == 0 && offsets[writes - 1] == 0);
				if (soc) assert(offsets[writes - 2] == 8);
				assert(words[0x100 / 4] == 0x12345678 && words[0x104 / 4] == 0x87654321);
				configurations++;
			}
		}
	}
	printf("PASS: %u POSTMASK lifecycle configurations; other SoC unchanged\n", configurations);
	return 0;
}
