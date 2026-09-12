// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

struct device { const char *of_node; };
struct mtk_ddp_comp { unsigned int id; };
struct drm_dsc_config { unsigned int bpp; };
struct mtk_crtc {
	struct device *mmsys_dev;
	int ddp_comp_nr;
	struct mtk_ddp_comp **ddp_comp;
};
struct event { char type; unsigned int id; };
static struct event events[64];
static unsigned int count;
static const struct drm_dsc_config *expected_dsc;
static bool of_device_is_compatible(const char *node, const char *name)
{
	return !strcmp(node, name);
}
static void record(char type, struct mtk_ddp_comp *comp)
{
	assert(count < 64);
	events[count++] = (struct event){ type, comp->id };
}
static void mtk_ddp_comp_bgclr_in_on(struct mtk_ddp_comp *comp) { record('B', comp); }
static void mtk_ddp_comp_dsc_config(struct mtk_ddp_comp *comp,
	const struct drm_dsc_config *dsc, void *pkt)
{
	assert(dsc == expected_dsc && !pkt);
	record('D', comp);
}
static void mtk_ddp_comp_config(struct mtk_ddp_comp *comp, unsigned int w,
	unsigned int h, unsigned int hz, unsigned int bpc, void *pkt)
{
	assert(w == 1080 && h == 2400 && hz == 60 && bpc == 8 && !pkt);
	record('C', comp);
}
static void mtk_ddp_comp_start(struct mtk_ddp_comp *comp) { record('S', comp); }
static void run(struct mtk_crtc *mtk_crtc, const struct drm_dsc_config *dsc)
{
	unsigned int width = 1080, height = 2400, vrefresh = 60, bpc = 8;
	int i;
#include "start-order-source.h"
}
int main(void)
{
	struct mtk_ddp_comp comps[6], *ptrs[6];
	struct device device;
	struct mtk_crtc crtc = { .mmsys_dev = &device, .ddp_comp = ptrs };
	struct drm_dsc_config dsc = { 8 };
	unsigned int soc, n, compression, pass, i, k, cases = 0;
	for (i = 0; i < 6; i++) { comps[i].id = i; ptrs[i] = &comps[i]; }
	for (soc = 0; soc < 2; soc++) {
		device.of_node = soc ? "mediatek,mt6878-mmsys0" : "mediatek,mt8192-mmsys";
		for (n = 5; n <= 6; n++) {
			crtc.ddp_comp_nr = n;
			for (compression = 0; compression < 2; compression++) {
				expected_dsc = compression ? &dsc : NULL;
				for (pass = 0; pass < 3; pass++) {
					count = 0;
					run(&crtc, expected_dsc);
					k = 0;
					for (i = 0; i < n; i++) {
						if (i) { assert(events[k].type == 'B' && events[k].id == i); k++; }
						assert(events[k].type == 'D' && events[k].id == i); k++;
						assert(events[k].type == 'C' && events[k].id == i); k++;
						if (!soc) { assert(events[k].type == 'S' && events[k].id == i); k++; }
					}
					if (soc) for (i = 0; i < n; i++) {
						assert(events[k].type == 'S' && events[k].id == i); k++;
					}
					assert(k == count);
					cases++;
				}
			}
		}
	}
	printf("PASS: %u actual-source startup traces; other SoC ordering preserved\n", cases);
	return 0;
}
