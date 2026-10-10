/* SPDX-License-Identifier: GPL-2.0-only */
/* CI-only boundary fixture: exact production dispatchers, no hardware. */
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <sys/types.h>

#define IS_ENABLED(value) (value)
#define TAG "md"
#define CCCI_DEBUG_LOG(...) ((void)0)
#define container_of(ptr, type, member) \
	((type *)((char *)(ptr) - offsetof(type, member)))

struct kobject { int unused; };
struct attribute { int unused; };
struct ccci_modem { unsigned int hif_flag; };
struct ccci_md_attribute {
	struct attribute attr;
	struct ccci_modem *modem;
	ssize_t (*show)(struct ccci_modem *, char *);
	ssize_t (*store)(struct ccci_modem *, const char *, size_t);
};

static struct ccci_modem modem;
static struct ccci_modem *current_md;
static unsigned int gets, suspends, resumes, shows, stores;

static struct ccci_modem *ccci_get_modem(void)
{
	gets++;
	return current_md;
}

static void ccci_hif_suspend(unsigned int flags)
{
	assert(flags == modem.hif_flag);
	suspends++;
}

static void ccci_modem_restore_reg(struct ccci_modem *md)
{
	assert(md == &modem);
	resumes++;
}

static ssize_t show(struct ccci_modem *md, char *buf)
{
	assert(md == &modem && buf);
	shows++;
	return 17;
}

static ssize_t store(struct ccci_modem *md, const char *buf, size_t count)
{
	assert(md == &modem && buf && count == 1);
	stores++;
	return -EIO;
}

/* PRODUCTION */

int main(void)
{
	struct kobject obj = { 0 };
	struct ccci_md_attribute attr = { .modem = &modem, .show = show, .store = store };
	char buf[8] = { 0 };
	modem.hif_flag = 6;
	/* Unpublished, published and subsequently quarantined metadata states. */
	for (unsigned int state = 0; state < 3; state++) {
		/* Quarantine retains the published modem rather than clearing/freeing it. */
		current_md = state ? &modem : NULL;
		if (IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)) {
			assert(ccci_modem_syssuspend() == -EOPNOTSUPP);
			ccci_modem_sysresume();
			assert(ccci_md_attr_show(&obj, &attr.attr, buf) == -EOPNOTSUPP);
			assert(ccci_md_attr_store(&obj, &attr.attr, buf, 1) == -EOPNOTSUPP);
			assert(!gets && !suspends && !resumes && !shows && !stores);
		} else {
			assert(ccci_modem_syssuspend() == 0);
			ccci_modem_sysresume();
			assert(ccci_md_attr_show(&obj, &attr.attr, buf) == 17);
			assert(ccci_md_attr_store(&obj, &attr.attr, buf, 1) == -EIO);
		}
	}
	if (!IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)) {
		assert(gets == 6 && suspends == 2 && resumes == 2);
		assert(shows == 3 && stores == 3);
	}
	attr.show = NULL;
	attr.store = NULL;
	assert(ccci_md_attr_show(&obj, &attr.attr, buf) ==
		(IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER) ? -EOPNOTSUPP : 0));
	assert(ccci_md_attr_store(&obj, &attr.attr, buf, 0) ==
		(IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER) ? -EOPNOTSUPP : 0));
	puts("actual syscore/sysfs dispatch: PASS (no physical OFF or READY claim)");
	return 0;
}
