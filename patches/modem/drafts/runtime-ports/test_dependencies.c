/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#define PAGE_SIZE 4096
#define SZ_64K 65536
#define U64_MAX UINT64_MAX
#define EPROBE_DEFER 517
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define READ_ONCE(a) (a)
#define CCIF_HIF_ID 1
#define DPMAIF_HIF_ID 2
#define DL_FLAG_AUTOREMOVE_CONSUMER 16
struct device_node { int id, enabled, refs; };
struct device { struct device_node *of_node; bool bound; int refs; };
struct platform_device { struct device dev; };
struct device_link { int id; };
static struct device_node nodes[3];
static struct platform_device pdevs[2], consumer;
static struct device_link links[2];
static void *ccci_hif[3], *ccci_hif_op[3];
static u8 raw[32];
static int length, present, missing, link_fault, link_count;
static u64 get_unaligned_le64(const void *p)
{
	const u8 *b = p;
	u64 value = 0;
	unsigned int i;
	for (i = 0; i < 8; i++)
		value |= (u64)b[i] << (i * 8);
	return value;
}
static u32 get_unaligned_le32(const void *p)
{
	const u8 *b = p;
	return (u32)b[0] | (u32)b[1] << 8 | (u32)b[2] << 16 | (u32)b[3] << 24;
}
static const void *of_get_property(struct device_node *node, const char *key, int *len)
{
	assert(node == consumer.dev.of_node && !strcmp(key, "ccci,modem_info_v2"));
	*len = length;
	return present ? raw : NULL;
}
static void of_node_put(struct device_node *node)
{
	assert(node && node->refs > 0);
	node->refs--;
}
static struct device_node *of_node_get(struct device_node *node)
{
	node->refs++;
	return node;
}
static struct device_node *next_node(struct device_node *previous, const char *compatible)
{
	int start = previous ? (int)(previous - nodes) + 1 : 0;
	int id = !strcmp(compatible, "mediatek,dpmaif") ? 1 : 0;
	int i;
	if (previous)
		of_node_put(previous);
	for (i = start; i < 3; i++) {
		if (nodes[i].id == id)
			return of_node_get(&nodes[i]);
	}
	return NULL;
}
#define for_each_compatible_node(node, type, compat) \
	for ((node) = next_node(NULL, compat); (node); (node) = next_node(node, compat))
static bool of_device_is_available(struct device_node *node) { return node->enabled; }
static struct platform_device *of_find_device_by_node(struct device_node *node)
{
	if (missing == node->id + 1)
		return NULL;
	pdevs[node->id].dev.refs++;
	return &pdevs[node->id];
}
static bool device_is_bound(struct device *dev) { return dev->bound; }
static void put_device(struct device *dev) { assert(dev->refs > 0); dev->refs--; }
static struct device_link *device_link_add(struct device *c, struct device *s, unsigned int flags)
{
	int id = s == &pdevs[0].dev ? 0 : 1;
	assert(c == &consumer.dev && flags == DL_FLAG_AUTOREMOVE_CONSUMER);
	if (link_fault == id + 1)
		return NULL;
	link_count++;
	links[id].id = id;
	return &links[id];
}
/* PRODUCTION */
static void reset(void)
{
	unsigned int i;
	memset(raw, 0, sizeof(raw));
	raw[2] = 1;
	raw[9] = 32;
	raw[16] = 2;
	raw[20] = 21;
	present = 1;
	length = 32;
	missing = link_fault = link_count = 0;
	memset(nodes, 0, sizeof(nodes));
	nodes[0].id = 0;
	nodes[1].id = 1;
	nodes[2].id = -1;
	for (i = 0; i < 2; i++) {
		nodes[i].enabled = 1;
		pdevs[i].dev.bound = true;
		pdevs[i].dev.refs = 0;
		ccci_hif[i + 1] = &links[i];
		ccci_hif_op[i + 1] = &links[i];
	}
	consumer.dev.of_node = &nodes[2];
}
static void expect(int error)
{
	int i;
	assert(tetris_ccci_dependencies(&consumer) == error);
	for (i = 0; i < 3; i++)
		assert(!nodes[i].refs);
	assert(!pdevs[0].dev.refs && !pdevs[1].dev.refs);
	if (!error)
		assert(link_count == 2);
	/* Fake driver-core failed-probe cleanup, not production driver teardown. */
	if (error)
		link_count = 0;
}
int main(void)
{
	int i;
	reset(); expect(0);
	reset(); present = 0; expect(-ENODATA);
	reset(); length = 31; expect(-EBADMSG);
	for (i = 0; i < 8; i++) {
		reset();
		switch (i) {
		case 0: raw[2] = 0; break;
		case 1: raw[0] = 1; break;
		case 2: raw[8] = 75; raw[9] = 0; break;
		case 3: raw[10] = 2; break;
		case 4: raw[12] = 1; break;
		case 5: raw[16] = 1; break;
		case 6: raw[20] = 20; break;
		case 7: raw[24] = 1; break;
		}
		expect(-EBADMSG);
	}
	reset(); raw[28] = 1; expect(-EBADMSG);
	reset(); memset(raw, 0xff, 8); raw[0] = 0; raw[1] = 0xf0; expect(-EBADMSG);
	reset(); nodes[0].enabled = 0; expect(-ENODEV);
	reset(); nodes[2].id = 0; nodes[2].enabled = 1; expect(-EINVAL);
	for (i = 0; i < 2; i++) {
		reset(); missing = i + 1; expect(-EPROBE_DEFER);
		reset(); pdevs[i].dev.bound = false; expect(-EPROBE_DEFER);
		reset(); ccci_hif[i + 1] = NULL; expect(-EPROBE_DEFER);
		reset(); ccci_hif_op[i + 1] = NULL; expect(-EPROBE_DEFER);
		reset(); link_fault = i + 1; expect(-ENOMEM);
	}
	reset(); ccci_hif_op[2] = NULL; expect(-EPROBE_DEFER);
	assert(!link_count);
	return 0;
}
