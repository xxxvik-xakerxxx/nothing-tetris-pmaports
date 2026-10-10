/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdint.h>
#include <sys/types.h>
struct kobject { int unused; };
struct file_operations { void *owner; };
struct cdev { struct kobject kobj; void *owner; const struct file_operations *ops; };
struct device { int unused; };
static struct device published;
static void *dev_class;
static int fault, live, nodes, deletes, kputs;
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
static struct cdev *cdev_alloc(void)
{
	if (fault == 1)
		return NULL;
	live++;
	return calloc(1, sizeof(struct cdev));
}
static int cdev_add(struct cdev *cdev, dev_t number, unsigned int count)
{
	assert(cdev && number == 123 && count == 1);
	return fault == 2 ? -EIO : 0;
}
static void kobject_put(struct kobject *kobj)
{
	kputs++;
	live--;
	free(kobj);
}
static void cdev_del(struct cdev *cdev)
{
	deletes++;
	live--;
	free(cdev);
}
static struct device *device_create(void *class, void *parent, dev_t number,
		void *data, const char *format, const char *name)
{
	assert(class && !parent && !data && number == 123 && format && name);
	if (fault == 3)
		return (void *)(intptr_t)-ENOSPC;
	nodes++;
	return &published;
}
static void device_destroy(void *class, dev_t number)
{
	assert(class && number == 123 && nodes == 1);
	nodes--;
}
/* PRODUCTION */
int main(void)
{
	struct cdev *owned = NULL;
	const struct file_operations fops = { .owner = &published };
	int i;

	assert(ccci_tetris_publish_char(&owned, &fops, "test", 123) == -ENODEV);
	dev_class = &published;
	assert(ccci_tetris_publish_char(NULL, &fops, "test", 123) == -EINVAL);
	assert(ccci_tetris_publish_char(&owned, NULL, "test", 123) == -EINVAL);
	assert(ccci_tetris_publish_char(&owned, &fops, NULL, 123) == -EINVAL);
	for (i = 1; i <= 3; i++) {
		fault = i;
		assert(ccci_tetris_publish_char(&owned, &fops, "test", 123) ==
		       (i == 1 ? -ENOMEM : i == 2 ? -EIO : -ENOSPC));
		assert(!owned && !live && !nodes);
	}
	assert(kputs == 1 && deletes == 1);
	fault = 0;
	assert(!ccci_tetris_publish_char(&owned, &fops, "test", 123));
	assert(owned->owner == fops.owner && owned->ops == &fops);
	assert(ccci_tetris_publish_char(&owned, &fops, "test", 123) == -EINVAL);
	ccci_tetris_unpublish_char(&owned, 123);
	ccci_tetris_unpublish_char(&owned, 123);
	assert(!owned && !live && !nodes && deletes == 2);
	return 0;
}
