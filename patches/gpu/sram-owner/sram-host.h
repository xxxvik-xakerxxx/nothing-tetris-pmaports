/* SPDX-License-Identifier: GPL-2.0-only */
/* CI fixture dependencies only; NEVER linked into a kernel. */
#ifndef GPUEB_SRAM_HOST_H
#define GPUEB_SRAM_HOST_H
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#define __iomem
#define GFP_KERNEL 0
#define IORESOURCE_MEM 0x200U
#define EXPORT_SYMBOL_GPL(symbol)
#define MODULE_LICENSE(value)
#define ERR_PTR(error) ((void *)(intptr_t)(error))
#define PTR_ERR(pointer) ((long)(intptr_t)(pointer))
#define IS_ERR(pointer) ((uintptr_t)(pointer) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(pointer) (!(pointer) || IS_ERR(pointer))
struct device { unsigned int refs; };
struct resource { uint64_t start, end; unsigned long flags; };
struct mutex { pthread_mutex_t value; };
static inline void mutex_init(struct mutex *lock)
{
	assert(!pthread_mutex_init(&lock->value, NULL));
}
static inline void mutex_lock(struct mutex *lock)
{
	assert(!pthread_mutex_lock(&lock->value));
}
static inline void mutex_unlock(struct mutex *lock)
{
	assert(!pthread_mutex_unlock(&lock->value));
}
static inline unsigned long resource_type(const struct resource *res)
{
	return res->flags & 0x1f00U;
}
static inline const char *dev_name(struct device *parent)
{
	assert(parent);
	return "CI-no-hardware";
}
static inline struct device *get_device(struct device *parent)
{
	parent->refs++;
	return parent;
}
static inline void put_device(struct device *parent)
{
	assert(parent->refs);
	parent->refs--;
}
static void *kzalloc(size_t bytes, int flags);
static void kfree(void *pointer);
static struct resource *request_mem_region(uint64_t start, uint64_t size, const char *name);
static void release_mem_region(uint64_t start, uint64_t size);
static void *ioremap(uint64_t start, uint64_t size);
static void iounmap(void *mapping);
#endif
