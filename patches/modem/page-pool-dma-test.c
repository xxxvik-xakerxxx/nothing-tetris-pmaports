/* Host test of the extracted vendor allocation function, not Linux DMA. */
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#define POOL_NUMBER 2
#ifndef PAGE_SIZE
#define PAGE_SIZE 4096
#endif
#define NET_SKB_PAD 64
#define PP_SIGNATURE 0x1234
#define GFP_ATOMIC 0
#define DMA_FROM_DEVICE 2
#define LOW_MEMORY_SKB -1
#define DMA_MAPPING_ERR -2
#define unlikely(x) (x)
#define CCCI_ERROR_LOG(...) ((void)0)
#define skb_data_size(skb) ((skb)->capacity)

struct page_pool { int unused; };
struct page { struct page_pool *pp; unsigned int pp_magic; };
struct sk_buff { char *data; unsigned int capacity; bool recyclable; };
static struct page_pool pool;
static struct page_pool *g_page_pool_arr[POOL_NUMBER] = { &pool, NULL };
static struct { void *dev; } controller;
static typeof(controller) *dpmaif_ctl = &controller;
static struct page test_page;
static struct sk_buff test_skb;
static char buffer[PAGE_SIZE];
static bool no_pool, no_page, no_skb, map_error;
static unsigned int requested_capacity, maps, frees, recycles, mapped_length;

static unsigned int ccci_dpmaif_page_pool_empty_index(void)
{
	return no_pool ? POOL_NUMBER : 0;
}

static struct page *page_pool_alloc_pages(struct page_pool *p, int flags)
{
	assert(p == &pool && flags == GFP_ATOMIC);
	return no_page ? NULL : &test_page;
}

static void *page_to_virt(struct page *page)
{
	assert(page == &test_page);
	return buffer;
}

static struct sk_buff *build_skb(void *data, unsigned int size)
{
	assert(data == buffer && size == PAGE_SIZE);
	test_skb = (struct sk_buff) { buffer, requested_capacity + NET_SKB_PAD, false };
	return no_skb ? NULL : &test_skb;
}

static void page_pool_recycle_direct(struct page_pool *p, struct page *page)
{
	assert(p == &pool && page == &test_page);
	recycles++;
}

static void skb_reserve(struct sk_buff *skb, unsigned int amount)
{
	assert(skb->capacity >= amount);
	skb->data += amount;
	skb->capacity -= amount;
}

static void skb_mark_for_recycle(struct sk_buff *skb)
{
	skb->recyclable = true;
}

static unsigned long long dma_map_single(void *dev, void *data, size_t size, int direction)
{
	assert(dev == controller.dev && data == test_skb.data);
	assert(direction == DMA_FROM_DEVICE);
	maps++;
	mapped_length = size;
	return map_error ? ULLONG_MAX : 0x10000;
}

static bool dma_mapping_error(void *dev, unsigned long long address)
{
	assert(dev == controller.dev);
	return address == ULLONG_MAX;
}

static void dev_kfree_skb_any(struct sk_buff *skb)
{
	assert(skb == &test_skb && skb->recyclable);
	frees++;
}

#include "allocation.h"

int main(void)
{
	const unsigned int capacities[] = { 0, 1024, 1500, 1664, 3712 };
	const unsigned int requests[] = { 1, 1024, 1500, 1664, 3712, 3713, UINT_MAX };
	unsigned int cases = 0;

	for (unsigned int c = 0; c < sizeof(capacities) / sizeof(capacities[0]); c++) {
		for (unsigned int r = 0; r < sizeof(requests) / sizeof(requests[0]); r++) {
			for (unsigned int failure = 0; failure < 5; failure++) {
				struct sk_buff *skb = NULL;
				unsigned long long address = 0;
				int result;

				requested_capacity = capacities[c];
				no_pool = failure == 1;
				no_page = failure == 2;
				no_skb = failure == 3;
				map_error = failure == 4;
				maps = frees = recycles = mapped_length = 0;
				result = skb_alloc_from_pool(&skb, &address, requests[r]);
				if (no_pool || no_page) {
					assert(result == LOW_MEMORY_SKB && maps == 0 && frees == 0 && recycles == 0);
				} else if (no_skb) {
					assert(result == LOW_MEMORY_SKB && maps == 0 && frees == 0 && recycles == 1);
				} else if (requests[r] > requested_capacity) {
					assert(result == LOW_MEMORY_SKB && !skb && maps == 0 && frees == 1);
				} else {
					assert(maps == 1 && mapped_length == requested_capacity);
					if (map_error)
						assert(result == DMA_MAPPING_ERR && !skb && frees == 1);
					else
						assert(result == 0 && skb == &test_skb && address == 0x10000 && frees == 0);
				}
				cases++;
			}
		}
	}
	printf("PASS: %u extracted allocation cases; host DMA recorder only\n", cases);
	return 0;
}
