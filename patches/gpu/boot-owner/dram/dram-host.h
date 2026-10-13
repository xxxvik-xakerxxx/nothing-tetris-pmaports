/* SPDX-License-Identifier: GPL-2.0-only */
/* Private CI mocks only; not used by the ARM64 kernel object. */
#ifndef GPUEB_DRAM_HOST_H
#define GPUEB_DRAM_HOST_H
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
typedef uint32_t u32;
typedef uint64_t phys_addr_t;
#define PAGE_SIZE 4096UL
#define GFP_KERNEL 0
#define ERR_PTR(error) ((void *)(intptr_t)(error))
#define PTR_ERR(pointer) ((long)(intptr_t)(pointer))
#define IS_ERR(pointer) ((uintptr_t)(pointer) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(pointer) (!(pointer) || IS_ERR(pointer))
struct device { unsigned int refs; };
struct mutex { pthread_mutex_t value; };
static inline void mutex_init(struct mutex *lock)
{ assert(!pthread_mutex_init(&lock->value, NULL)); }
static inline void mutex_lock(struct mutex *lock)
{ assert(!pthread_mutex_lock(&lock->value)); }
static inline void mutex_unlock(struct mutex *lock)
{ assert(!pthread_mutex_unlock(&lock->value)); }
static inline struct device *get_device(struct device *parent)
{ parent->refs++; return parent; }
static inline void put_device(struct device *parent)
{ assert(parent->refs); parent->refs--; }
static void *kzalloc(size_t bytes, int flags);
static void kfree(void *pointer);
struct cma { int fixture_only; };
struct page { phys_addr_t fixture_physical; };
static struct cma *dev_get_cma_area(struct device *parent);
static struct page *cma_alloc(struct cma *area, unsigned long count,
		unsigned int align, bool no_warn);
static bool cma_release(struct cma *area, const struct page *page, unsigned long count);
static inline phys_addr_t page_to_phys(const struct page *page)
{ return page->fixture_physical; }
#endif
