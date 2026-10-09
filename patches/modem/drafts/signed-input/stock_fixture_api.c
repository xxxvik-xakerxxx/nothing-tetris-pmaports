/* SPDX-License-Identifier: GPL-2.0-or-later */
/* CI-only ordinary-memory/firmware doubles; crypto remains real. */
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { unsigned int value; } refcount_t;
static void refcount_set(refcount_t *r, unsigned int value) { r->value = value; }
static int refcount_inc_not_zero(refcount_t *r)
{
	if (!r->value)
		return 0;
	r->value++;
	return 1;
}
static int refcount_dec_and_test(refcount_t *r)
{
	assert(r->value);
	return --r->value == 0;
}
static int snapshot_fault, firmware_fault, firmware_releases;
static void *kvmalloc(size_t size, int flags)
{
	(void)flags;
	return snapshot_fault ? NULL : allocate(size);
}
static void kvfree(const void *p) { kfree_sensitive((void *)p); }
struct device { int unused; };
struct firmware { const u8 *data; size_t size; };
static struct firmware fixture_firmware;
static int request_firmware(const struct firmware **out, const char *name, struct device *dev)
{
	assert(dev && !strcmp(name, "fixture-stock"));
	if (firmware_fault)
		return firmware_fault;
	*out = &fixture_firmware;
	return 0;
}
static void release_firmware(const struct firmware *firmware)
{
	assert(firmware == &fixture_firmware);
	firmware_releases++;
}
