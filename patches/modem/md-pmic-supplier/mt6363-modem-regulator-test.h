/* SPDX-License-Identifier: GPL-2.0-only */
/* Native KUnit fixtures use the actual callbacks/helpers and an uncached regmap.
 * The alias/status model tests software contracts, not electrical behavior.
 */
#if IS_REACHABLE(CONFIG_KUNIT)
#include <kunit/test.h>
#include <kunit/resource.h>

struct mt6363_md_fixture {
	u8 registers[0x2000];
	unsigned int reads, writes, fail_read, fail_write, last_read, last_write;
	bool drop_write, change_control;
	struct mutex lock;
	struct mt6363_md_state state;
	struct regulator_dev rdev;
};

static int mt6363_md_test_read(void *context, unsigned int reg, unsigned int *value)
{
	struct mt6363_md_fixture *fixture = context;

	fixture->reads++;
	fixture->last_read = reg;
	if (fixture->reads == fixture->fail_read)
		return -EIO;
	*value = fixture->registers[reg];
	return 0;
}

static int mt6363_md_test_write(void *context, unsigned int reg, unsigned int value)
{
	struct mt6363_md_fixture *fixture = context;
	const struct mt6363_md_info *info = fixture->state.info;
	unsigned int i;

	fixture->writes++;
	fixture->last_write = reg;
	if (fixture->writes == fixture->fail_write)
		return -EREMOTEIO;
	if (fixture->drop_write)
		return 0;
	if (reg == info->desc.enable_reg + 1)
		fixture->registers[info->desc.enable_reg] |= value;
	else if (reg == info->desc.enable_reg + 2)
		fixture->registers[info->desc.enable_reg] &= ~value;
	else
		fixture->registers[reg] = value;
	if (fixture->change_control)
		fixture->registers[info->op_en] = 1;
	/* Model the source HW_LP observation following a software LP request. */
	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		const struct mt6363_md_info *rail = &mt6363_md_rails[i];

		if (reg != rail->lp)
			continue;
		fixture->registers[rail->hw_lp] &= ~rail->hw_lp_mask;
		if (value & rail->lp_mask)
			fixture->registers[rail->hw_lp] |= 4;
	}
	return 0;
}

static const struct regmap_bus mt6363_md_test_bus = {
	.reg_read = mt6363_md_test_read,
	.reg_write = mt6363_md_test_write,
};

static void mt6363_md_test_map_exit(void *map)
{
	regmap_exit(map);
}

static struct mt6363_md_fixture *mt6363_md_test_fixture(struct kunit *test, unsigned int rail)
{
	static const struct regmap_config config = {
		.reg_bits = 16, .val_bits = 8, .max_register = 0x1fff,
		.cache_type = REGCACHE_NONE, .name = "mt6363-md-native-fixture",
	};
	struct mt6363_md_fixture *fixture;
	const struct mt6363_md_info *info = &mt6363_md_rails[rail];
	int ret;

	fixture = kunit_kzalloc(test, sizeof(*fixture), GFP_KERNEL);
	if (!fixture)
		return NULL;
	mutex_init(&fixture->lock);
	fixture->state.info = info;
	fixture->state.lock = &fixture->lock;
	fixture->rdev.desc = &info->desc;
	fixture->rdev.reg_data = &fixture->state;
	fixture->rdev.regmap = regmap_init(NULL, &mt6363_md_test_bus, fixture, &config);
	if (IS_ERR(fixture->rdev.regmap))
		return NULL;
	ret = kunit_add_action_or_reset(test, mt6363_md_test_map_exit, fixture->rdev.regmap);
	if (ret)
		return NULL;
	fixture->registers[info->op_en + 2] = 0x80;
	fixture->registers[info->op_en + 5] = 0x10;
	return fixture;
}

static void mt6363_md_voltage_test(struct kunit *test)
{
	static const int targets[] = { 700000, 800000, 800000 };
	static const int selectors[] = { 112, 128, 64 };
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, i);
		struct regulator_dev *rdev;
		int selector;

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		rdev = &fixture->rdev;
		selector = rdev->desc->ops->map_voltage(rdev, targets[i], targets[i]);
		KUNIT_EXPECT_EQ(test, selector, selectors[i]);
		KUNIT_EXPECT_EQ(test, rdev->desc->ops->list_voltage(rdev, selector), targets[i]);
		KUNIT_EXPECT_EQ(test,
			       rdev->desc->ops->list_voltage(rdev, rdev->desc->n_voltages - 1),
			       1193750);
		KUNIT_EXPECT_EQ(test, rdev->desc->ops->set_voltage_sel(rdev, selector), 0);
		KUNIT_EXPECT_EQ(test, rdev->desc->ops->get_voltage_sel(rdev), selector);
		KUNIT_EXPECT_EQ(test, fixture->last_write, rdev->desc->vsel_reg);
		KUNIT_EXPECT_EQ(test,
			       rdev->desc->ops->set_voltage_sel(rdev, rdev->desc->n_voltages),
			       -EINVAL);
		if (i < 2) {
			fixture->registers[rdev->desc->vsel_reg] = 192;
			KUNIT_EXPECT_EQ(test, mt6363_md_get_voltage_sel(rdev), -ERANGE);
		}
	}
}

static void mt6363_md_enable_test(struct kunit *test)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, i);
		const struct regulator_desc *desc;

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		desc = fixture->rdev.desc;
		fixture->registers[desc->enable_reg] = 0x80;
		KUNIT_EXPECT_EQ(test, mt6363_md_enable(&fixture->rdev), 0);
		KUNIT_EXPECT_EQ(test, desc->ops->is_enabled(&fixture->rdev), 1);
		KUNIT_EXPECT_EQ(test, fixture->last_write, desc->enable_reg + 1);
		KUNIT_EXPECT_EQ(test, fixture->registers[desc->enable_reg],
			       0x80 | desc->enable_mask);
		KUNIT_EXPECT_TRUE(test, fixture->state.owns_enable);
		KUNIT_EXPECT_EQ(test, mt6363_md_disable(&fixture->rdev), 0);
		KUNIT_EXPECT_EQ(test, desc->ops->is_enabled(&fixture->rdev), 0);
		KUNIT_EXPECT_EQ(test, fixture->last_write, desc->enable_reg + 2);
		KUNIT_EXPECT_EQ(test, fixture->registers[desc->enable_reg], 0x80);
		fixture->registers[desc->enable_reg] |= desc->enable_mask;
		fixture->writes = 0;
		KUNIT_EXPECT_EQ(test, mt6363_md_enable(&fixture->rdev), 0);
		KUNIT_EXPECT_FALSE(test, fixture->state.owns_enable);
		KUNIT_EXPECT_EQ(test, mt6363_md_disable(&fixture->rdev), -EBUSY);
		KUNIT_EXPECT_EQ(test, fixture->writes, 0U);
	}
}

static void mt6363_md_ownership_test(struct kunit *test)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, i);
		const struct mt6363_md_info *info;

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		info = fixture->state.info;
		fixture->state.registering = true;
		KUNIT_EXPECT_EQ(test, mt6363_md_set_voltage_sel(&fixture->rdev, 64), -EOPNOTSUPP);
		KUNIT_EXPECT_EQ(test, mt6363_md_enable(&fixture->rdev), -EOPNOTSUPP);
		KUNIT_EXPECT_EQ(test, fixture->reads, 0U);
		fixture->state.registering = false;
		fixture->registers[info->op_en] = 1;
		KUNIT_EXPECT_EQ(test, mt6363_md_set_voltage_sel(&fixture->rdev, 64), -EBUSY);
		KUNIT_EXPECT_EQ(test, mt6363_md_is_enabled(&fixture->rdev), -EBUSY);
		fixture->registers[info->op_en] = 0;
		if (info->sshub_en) {
			fixture->registers[info->sshub_en] = 1;
			KUNIT_EXPECT_EQ(test, mt6363_md_get_voltage_sel(&fixture->rdev), -EBUSY);
			KUNIT_EXPECT_EQ(test, mt6363_md_enable(&fixture->rdev), -EBUSY);
		}
		KUNIT_EXPECT_EQ(test, fixture->writes, 0U);
	}
}

static void mt6363_md_mode_test(struct kunit *test)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, i);
		const struct mt6363_md_info *info;

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		info = fixture->state.info;
		fixture->registers[info->lp] = 0x80;
		KUNIT_EXPECT_EQ(test, mt6363_md_set_mode(&fixture->rdev, REGULATOR_MODE_IDLE), 0);
		KUNIT_EXPECT_EQ(test, mt6363_md_get_mode(&fixture->rdev),
			       (unsigned int)REGULATOR_MODE_IDLE);
		KUNIT_EXPECT_EQ(test, fixture->last_read, (unsigned int)info->hw_lp);
		KUNIT_EXPECT_EQ(test, fixture->registers[info->lp], 0x80 | info->lp_mask);
		KUNIT_EXPECT_EQ(test, mt6363_md_set_mode(&fixture->rdev, REGULATOR_MODE_NORMAL), 0);
		KUNIT_EXPECT_EQ(test, fixture->registers[info->lp], 0x80);
		fixture->writes = 0;
		KUNIT_EXPECT_EQ(test, mt6363_md_set_mode(&fixture->rdev, REGULATOR_MODE_FAST),
			       -EOPNOTSUPP);
		KUNIT_EXPECT_EQ(test, mt6363_md_set_load(&fixture->rdev, 100000), -EOPNOTSUPP);
		if (info->fccm) {
			fixture->registers[info->fccm] = info->fccm_mask;
			KUNIT_EXPECT_EQ(test, mt6363_md_get_mode(&fixture->rdev),
				       (unsigned int)REGULATOR_MODE_FAST);
			KUNIT_EXPECT_EQ(test,
				       mt6363_md_set_mode(&fixture->rdev, REGULATOR_MODE_NORMAL),
				       -EOPNOTSUPP);
		}
		KUNIT_EXPECT_EQ(test, fixture->writes, 0U);
	}
}

static void mt6363_md_first_errno_test(struct kunit *test)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, i);

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		fixture->fail_write = 1;
		KUNIT_EXPECT_EQ(test, mt6363_md_set_voltage_sel(&fixture->rdev, 64), -EREMOTEIO);
		KUNIT_EXPECT_EQ(test, mt6363_md_enable(&fixture->rdev), -EREMOTEIO);
		KUNIT_EXPECT_EQ(test, mt6363_md_set_mode(&fixture->rdev, REGULATOR_MODE_IDLE),
			       -EREMOTEIO);
		KUNIT_EXPECT_EQ(test, fixture->writes, 1U);
		fixture = mt6363_md_test_fixture(test, i);
		KUNIT_ASSERT_NOT_NULL(test, fixture);
		fixture->drop_write = true;
		KUNIT_EXPECT_EQ(test, mt6363_md_set_voltage_sel(&fixture->rdev, 64), -EIO);
		KUNIT_EXPECT_EQ(test, mt6363_md_disable(&fixture->rdev), -EIO);
		KUNIT_EXPECT_EQ(test, fixture->writes, 1U);
		fixture = mt6363_md_test_fixture(test, i);
		KUNIT_ASSERT_NOT_NULL(test, fixture);
		fixture->change_control = true;
		KUNIT_EXPECT_EQ(test, mt6363_md_set_voltage_sel(&fixture->rdev, 64), -EBUSY);
		KUNIT_EXPECT_EQ(test, mt6363_md_enable(&fixture->rdev), -EBUSY);
		KUNIT_EXPECT_EQ(test, fixture->writes, 1U);
	}
}

static void mt6363_md_read_fault_test(struct kunit *test)
{
	unsigned int i, fault;

	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, i);
		unsigned int reads;

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		KUNIT_EXPECT_EQ(test, mt6363_md_get_voltage_sel(&fixture->rdev), 0);
		reads = fixture->reads;
		for (fault = 1; fault <= reads; fault++) {
			fixture->reads = 0;
			fixture->fail_read = fault;
			KUNIT_EXPECT_EQ(test, mt6363_md_get_voltage_sel(&fixture->rdev), -EIO);
			KUNIT_EXPECT_EQ(test, fixture->reads, fault);
			KUNIT_EXPECT_EQ(test, fixture->writes, 0U);
		}
		fixture->reads = 0;
		fixture->fail_read = 1;
		KUNIT_EXPECT_EQ(test, mt6363_md_get_mode(&fixture->rdev), (unsigned int)-EIO);
	}
}

static void mt6363_md_unavailable_test(struct kunit *test)
{
	struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, 0);
	struct platform_device *pdev = kunit_kzalloc(test, sizeof(*pdev), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	KUNIT_ASSERT_NOT_NULL(test, pdev);
	KUNIT_EXPECT_EQ(test, mt6363_md_register(pdev, fixture->rdev.regmap), 0);
	KUNIT_EXPECT_EQ(test, fixture->reads, 0U);
	KUNIT_EXPECT_EQ(test, fixture->writes, 0U);
}

static void mt6363_md_writer_read_fault_test(struct kunit *test)
{
	unsigned int i, fault;

	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		struct mt6363_md_fixture *fixture = mt6363_md_test_fixture(test, i);
		unsigned int reads;

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		KUNIT_ASSERT_EQ(test, mt6363_md_set_voltage_sel(&fixture->rdev, 64), 0);
		reads = fixture->reads;
		for (fault = 1; fault <= reads; fault++) {
			fixture = mt6363_md_test_fixture(test, i);
			KUNIT_ASSERT_NOT_NULL(test, fixture);
			fixture->fail_read = fault;
			KUNIT_EXPECT_EQ(test, mt6363_md_set_voltage_sel(&fixture->rdev, 64), -EIO);
			KUNIT_EXPECT_EQ(test, fixture->reads, fault);
			if (fixture->writes) {
				KUNIT_EXPECT_EQ(test, mt6363_md_enable(&fixture->rdev), -EIO);
				KUNIT_EXPECT_EQ(test, fixture->reads, fault);
				KUNIT_EXPECT_EQ(test, fixture->writes, 1U);
			}
		}
	}
}

static struct kunit_case mt6363_md_cases[] = {
	KUNIT_CASE(mt6363_md_voltage_test),
	KUNIT_CASE(mt6363_md_enable_test),
	KUNIT_CASE(mt6363_md_ownership_test),
	KUNIT_CASE(mt6363_md_mode_test),
	KUNIT_CASE(mt6363_md_first_errno_test),
	KUNIT_CASE(mt6363_md_read_fault_test),
	KUNIT_CASE(mt6363_md_unavailable_test),
	KUNIT_CASE(mt6363_md_writer_read_fault_test),
	{ }
};

static struct kunit_suite mt6363_md_suite = {
	.name = "mt6363-native-modem-regulator",
	.test_cases = mt6363_md_cases,
};
kunit_test_suite(mt6363_md_suite);
#endif
