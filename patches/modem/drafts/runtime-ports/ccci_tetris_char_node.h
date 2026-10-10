/* SPDX-License-Identifier: GPL-2.0-only */
/* Included in ccci_core.c, where the actual CCCI dev_class is owned. */
#include <linux/cdev.h>

int ccci_tetris_publish_char(struct cdev **owned,
		const struct file_operations *fops, const char *name, dev_t number)
{
	struct cdev *cdev;
	struct device *device;
	int ret;

	if (!owned || *owned || !fops || !name)
		return -EINVAL;
	if (IS_ERR_OR_NULL(dev_class))
		return -ENODEV;
	cdev = cdev_alloc();
	if (!cdev)
		return -ENOMEM;
	cdev->owner = fops->owner;
	cdev->ops = fops;
	ret = cdev_add(cdev, number, 1);
	if (ret) {
		kobject_put(&cdev->kobj);
		return ret;
	}
	device = device_create(dev_class, NULL, number, NULL, "%s", name);
	if (IS_ERR(device)) {
		ret = PTR_ERR(device);
		cdev_del(cdev);
		return ret;
	}
	*owned = cdev;
	return 0;
}

/* Removes publication, NOT port storage. Open files may still reference it. */
void ccci_tetris_unpublish_char(struct cdev **owned, dev_t number)
{
	if (!owned || !*owned)
		return;
	device_destroy(dev_class, number);
	cdev_del(*owned);
	*owned = NULL;
}
