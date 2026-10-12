/* SPDX-License-Identifier: GPL-2.0-only */
/* CI-only dependencies for the ACTUAL reset/SRAM adapters. No hardware. */
#ifndef GPUEB_RESET_HOST_H
#define GPUEB_RESET_HOST_H
#include "sram-host.h"
#include "mt6878-gpueb-sram-core.h"
#include <string.h>
#include <stdbool.h>
typedef uint64_t resource_size_t;
typedef pthread_mutex_t spinlock_t;
#define BIT(n) (1U << (n))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define READ_ONCE(x) (x)
#define IRQ_TYPE_LEVEL_HIGH 4U
#define IRQF_ONESHOT 1U
#define IRQF_NO_AUTOEN 2U
#define MT6878_POWER_DOMAIN_MFG0_SHUTDOWN 0U
enum { IRQ_NONE, IRQ_HANDLED };
typedef int irqreturn_t;
struct irq_data { int disabled; };
struct platform_device { struct device dev; unsigned int num_resources;
	struct resource *resource; };
struct of_phandle_args { unsigned int args_count, args[1]; struct device_node *np; };
static struct module fixture_module;
#define THIS_MODULE (&fixture_module)
static struct irq_data fixture_irq_data;
static unsigned int fixture_masks, fixture_syncs;
static void fixture_barrier(void);
#define mb() fixture_barrier()
#define spin_lock_init(lock) assert(!pthread_mutex_init((lock), NULL))
#define spin_lock_irqsave(lock, flags) do { (flags) = 0; assert(!pthread_mutex_lock(lock)); } while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(flags); assert(!pthread_mutex_unlock(lock)); } while (0)
static inline int try_module_get(struct module *module)
{
	if (module) module->refs++;
	return 1;
}
static inline void module_put(struct module *module)
{
	if (module) { assert(module->refs); module->refs--; }
}
static inline struct irq_data *irq_get_irq_data(int irq)
{
	assert(irq == 273);
	return &fixture_irq_data;
}
static inline int irqd_irq_disabled(struct irq_data *data) { return data->disabled; }
static inline void disable_irq_nosync(int irq)
{
	assert(irq == 273); fixture_masks++; fixture_irq_data.disabled = 1;
}
static inline void synchronize_irq(int irq) { assert(irq == 273); fixture_syncs++; }
/* Unused platform bring-up dependencies deliberately abort, not fake success. */
static inline int of_property_count_u32_elems(struct device_node *node, const char *name)
{ (void)node; (void)name; abort(); }
static inline int of_property_read_u32(struct device_node *node, const char *name, u32 *value)
{ (void)node; (void)name; (void)value; abort(); }
static inline int of_property_read_u32_index(struct device_node *node, const char *name,
		unsigned int index, u32 *value)
{ (void)node; (void)name; (void)index; (void)value; abort(); }
static inline int of_device_is_available(struct device_node *node)
{ (void)node; abort(); }
static inline int of_device_is_compatible(struct device_node *node, const char *name)
{ (void)node; (void)name; abort(); }
static inline int of_count_phandle_with_args(struct device_node *node,
		const char *name, const char *cells)
{ (void)node; (void)name; (void)cells; abort(); }
static inline int of_parse_phandle_with_args(struct device_node *node, const char *name,
		const char *cells, int index, struct of_phandle_args *args)
{ (void)node; (void)name; (void)cells; (void)index; (void)args; abort(); }
static inline void of_node_put(struct device_node *node) { (void)node; abort(); }
static inline struct resource *platform_get_resource_byname(struct platform_device *dev,
		unsigned long type, const char *name)
{ (void)dev; (void)type; (void)name; abort(); }
static inline int platform_get_irq_byname(struct platform_device *dev, const char *name)
{ (void)dev; (void)name; abort(); }
static inline unsigned int irq_get_trigger_type(int irq) { (void)irq; abort(); }
static inline int pm_runtime_get_if_in_use(struct device *dev) { (void)dev; abort(); }
static inline void pm_runtime_put_noidle(struct device *dev) { (void)dev; abort(); }
static inline int request_threaded_irq(int irq, irqreturn_t (*primary)(int, void *),
		irqreturn_t (*thread)(int, void *), unsigned long flags,
		const char *name, void *context)
{ (void)irq; (void)primary; (void)thread; (void)flags; (void)name; (void)context; abort(); }
static inline void free_irq(int irq, void *context) { (void)irq; (void)context; abort(); }
static inline uint64_t resource_size(const struct resource *res)
{ return res->end - res->start + 1; }
#endif
