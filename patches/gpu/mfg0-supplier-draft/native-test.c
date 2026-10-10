// SPDX-License-Identifier: GPL-2.0-only
/* Compile the actual draft TU; substitute kernel APIs, not the transaction. */
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <errno.h>
#include <stdio.h>
#define GPUEB_MFG0_HOST_TEST
#define GFP_KERNEL 0
/* Packaged 0018 binding, not the vendor DT's separately numbered enum. */
#define MT6878_POWER_DOMAIN_MFG0_SHUTDOWN 6
#define EXPORT_SYMBOL_GPL(symbol)
#define MODULE_DESCRIPTION(text)
#define MODULE_LICENSE(text)
#define IS_ERR_OR_NULL(pointer) (!(pointer))
#define lockdep_assert_held(lock) assert(*(lock))
struct task_struct { int id; };
struct module { int refs; };
struct device_node { int refs; };
struct device_driver { bool suppress_bind_attrs; struct module *owner; };
struct device {
	bool mutex, bound, enabled, active;
	int usage, refs;
	void *pm_domain;
	struct device_node *of_node;
	struct device_driver *driver;
};
struct platform_device { struct device dev; };
struct of_phandle_args { unsigned int args_count, args[1]; struct device_node *np; };
static struct task_struct task1, task2, *current = &task1;
static struct module self, owner;
static struct device_node node;
#define THIS_MODULE (&self)
static int alloc_fail, module_fail, module_calls, domains, parse_error;
static int resume_error, resume_calls, noidle_calls;
static bool profile, resume_active;
static void *kzalloc(size_t bytes, int flags)
{ (void)flags; return alloc_fail ? NULL : calloc(1, bytes); }
static void kfree(void *p) { free(p); }
static bool device_trylock(struct device *d)
{ if (d->mutex) return false; d->mutex = true; return true; }
static void device_unlock(struct device *d) { assert(d->mutex); d->mutex = false; }
static bool device_is_bound(struct device *d) { return d->bound; }
static bool pm_runtime_enabled(struct device *d) { return d->enabled; }
static bool pm_runtime_active(struct device *d) { return d->active; }
static int of_count_phandle_with_args(struct device_node *np, const char *a, const char *b)
{ (void)np; (void)a; (void)b; return domains; }
static int of_parse_phandle_with_args(struct device_node *np, const char *a,
	const char *b, int index, struct of_phandle_args *out)
{
	(void)np; (void)a; (void)b; (void)index;
	if (parse_error) return parse_error;
	out->args_count = 1; out->args[0] = MT6878_POWER_DOMAIN_MFG0_SHUTDOWN;
	out->np = &node; node.refs++; return 0;
}
static bool of_device_is_compatible(struct device_node *np, const char *compatible)
{ (void)np; (void)compatible; return profile; }
static void of_node_put(struct device_node *np) { assert(np->refs > 0); np->refs--; }
static bool try_module_get(struct module *m)
{
	module_calls++;
	if (module_fail == module_calls)
		return false;
	if (m)
		m->refs++;
	return true;
}
static void module_put(struct module *m) { if (m) { assert(m->refs > 0); m->refs--; } }
static struct device *get_device(struct device *d) { d->refs++; return d; }
static void put_device(struct device *d) { assert(d->refs > 0); d->refs--; }
static int pm_runtime_get_sync(struct device *d)
{
	assert(d->mutex && d->refs && owner.refs && self.refs);
	d->usage++;
	resume_calls++;
	if (resume_active)
		d->active = true;
	return resume_error;
}
static void pm_runtime_put_noidle(struct device *d)
{ assert(d->usage > 0); d->usage--; noidle_calls++; }
#include "mt6878-gpueb-mfg0.c"

/* Fixture combines the split production calls; no exported shortcut can
 * bypass bound-parent SRAM ownership in the real control caller. */
static int acquire(struct platform_device *p, struct mt6878_gpueb_mfg0 **out)
{
	int ret = mt6878_gpueb_mfg0_prepare(p, out);
	return ret ? ret : mt6878_gpueb_mfg0_resume(*out);
}

static struct platform_device parent;
static struct device_driver driver = { .suppress_bind_attrs = true, .owner = &owner };
static void baseline(void)
{
	assert(!self.refs && !owner.refs && !node.refs);
	parent = (struct platform_device){ .dev = { .bound = true, .enabled = true,
		.pm_domain = &parent, .of_node = &node, .driver = &driver } };
	alloc_fail = module_fail = parse_error = resume_error = resume_calls = noidle_calls = 0;
	module_calls = 0;
	domains = 1; profile = resume_active = true; current = &task1;
}

/* Fixture disposal after checking deliberate production quarantine. This is
 * not a production OFF proof or an API available to the hardware caller.
 */
static void fixture_dispose(struct mt6878_gpueb_mfg0 *scope)
{
	assert(scope && !parent.dev.mutex && parent.dev.usage == 1);
	free(scope); parent.dev.usage = parent.dev.refs = 0;
	self.refs = owner.refs = 0;
}

int main(void)
{
	struct mt6878_gpueb_mfg0 *scope, *again;
	int error;
	baseline();
	assert(acquire(NULL, &scope) == -EINVAL && scope == NULL);
	assert(acquire(&parent, NULL) == -EINVAL);
	assert(mt6878_gpueb_mfg0_prepare(&parent, &scope) == 0 && scope);
	assert(parent.dev.mutex && resume_calls == 0 && parent.dev.usage == 0);
	assert(mt6878_gpueb_mfg0_finish(&scope) == 0 && !scope);
	assert(!parent.dev.mutex && noidle_calls == 0 && !self.refs && !owner.refs);
	for (int fault = 0; fault < 8; fault++) {
		baseline();
		switch (fault) {
		case 0: alloc_fail = 1; error = -ENOMEM; break;
		case 1: parent.dev.mutex = true; error = -EBUSY; break;
		case 2: parent.dev.bound = false; error = -ENODEV; break;
		case 3: domains = 2; error = -EINVAL; break;
		case 4: parse_error = -ENOENT; error = -ENOENT; break;
		case 5: profile = false; error = -EINVAL; break;
		case 6: module_fail = 1; error = -ENODEV; break;
		default: module_fail = 2; error = -ENODEV;
		}
		assert(acquire(&parent, &scope) == error && scope == NULL);
		assert(!resume_calls && !parent.dev.refs && !self.refs && !owner.refs && !node.refs);
	}
	baseline();
	assert(acquire(&parent, &scope) == 0 && scope);
	assert(resume_calls == 1 && parent.dev.usage == 1 && parent.dev.mutex);
	assert(acquire(&parent, &again) == -EBUSY && again == NULL);
	current = &task2;
	assert(mt6878_gpueb_mfg0_finish(&scope) == -EPERM && scope);
	current = &task1;
	assert(mt6878_gpueb_mfg0_finish(&scope) == 0 && scope == NULL);
	assert(noidle_calls == 1 && !parent.dev.usage && parent.dev.active && !parent.dev.mutex);
	assert(!self.refs && !owner.refs && !parent.dev.refs);
	baseline();
	parent.dev.active = true;
	parent.dev.usage = 2;
	resume_error = 1; /* Already-active get_sync is a successful acquisition. */
	assert(acquire(&parent, &scope) == 0);
	assert(parent.dev.usage == 3);
	assert(mt6878_gpueb_mfg0_finish(&scope) == 0 && scope == NULL);
	assert(parent.dev.usage == 2 && parent.dev.active);
	assert(mt6878_gpueb_mfg0_finish(&scope) == -EINVAL);
	for (int failure = 0; failure < 2; failure++) {
		baseline();
		resume_error = failure ? 0 : -ETIMEDOUT;
		resume_active = false;
		error = failure ? -EHOSTDOWN : -ETIMEDOUT;
		assert(acquire(&parent, &scope) == error && scope);
		assert(mt6878_gpueb_mfg0_finish(&scope) == error && scope);
		assert(resume_calls == 1 && noidle_calls == 0 && !parent.dev.mutex);
		assert(parent.dev.usage == 1 && parent.dev.refs && self.refs && owner.refs);
		current = &task2;
		assert(mt6878_gpueb_mfg0_resume(scope) == error);
		assert(mt6878_gpueb_mfg0_finish(&scope) == error && scope);
		assert(resume_calls == 1 && noidle_calls == 0);
		current = &task1;
		fixture_dispose(scope);
	}
	baseline();
	assert(acquire(&parent, &scope) == 0);
	current = &task2;
	assert(mt6878_gpueb_mfg0_quarantine(scope, -EIO) == -EPERM);
	assert(parent.dev.mutex && scope->first_error == 0);
	current = &task1;
	assert(mt6878_gpueb_mfg0_quarantine(scope, -EIO) == -EIO);
	assert(!parent.dev.mutex && scope->task == NULL);
	assert(mt6878_gpueb_mfg0_resume(scope) == -EIO && resume_calls == 1);
	assert(mt6878_gpueb_mfg0_finish(&scope) == -EIO && noidle_calls == 0);
	fixture_dispose(scope);
	puts("GPUEB MFG0 transaction/fault fixture PASS (no hardware)");
	return 0;
}
