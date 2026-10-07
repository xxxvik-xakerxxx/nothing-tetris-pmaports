/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>

#define BIT(n) (1UL << (n))
struct clk { bool enabled; };
struct gpio_desc { bool active_low; int physical; };
struct pinctrl { int unused; };
struct pinctrl_state { bool on; };
struct regulator { int id; bool enabled; };
struct regulator_bulk_data { struct regulator *consumer; };

static struct gpio_desc reset;
static struct clk clock;
static int step, fail_at, releases, last_disabled, off_selected;
#ifdef TEST_CLOCK
#define STARTUP_CASES 13
static bool rate_owned, rounded_rate;
static int rate_puts;
#else
#define STARTUP_CASES 12
#endif
#ifdef TEST_CLEANUP
static int off_step, off_mask, first_off_error, dovdd_settled, last_enabled;
static bool disable_failed[4];

static int fail_off(void)
{
	int ret = (off_mask & (1 << off_step)) ? -200 - off_step : 0;

	off_step++;
	if (!first_off_error)
		first_off_error = ret;
	return ret;
}
#endif

static int fail(void)
{
	return ++step == fail_at ? -123 : 0;
}

static void gpiod_set_value_cansleep(struct gpio_desc *gpio, int logical)
{
	gpio->physical = logical ^ gpio->active_low;
	if (!logical) {
		assert(clock.enabled);
		releases++;
	}
}

#ifdef TEST_CLOCK
static int clk_set_rate_exclusive(struct clk *clk, unsigned long rate)
{
	assert(!clk->enabled && !rate_owned && rate == 24000000);
	int ret = fail();
	if (!ret)
		rate_owned = true;
	return ret;
}

static unsigned long clk_get_rate(struct clk *clk)
{
	assert(!clk->enabled && rate_owned);
	return rounded_rate ? 23999999 : 24000000;
}

static inline void clk_rate_exclusive_put(struct clk *clk)
{
	assert(!clk->enabled && rate_owned && off_selected);
	rate_owned = false;
	rate_puts++;
}
#else
static int clk_set_rate(struct clk *clk, unsigned long rate)
{
	assert(!clk->enabled && rate == 24000000);
	return fail();
}
#endif

static int regulator_set_voltage(struct regulator *reg, int min, int max)
{
	assert(reset.physical == 0 && !reg->enabled && min == max);
	return fail();
}

static int regulator_enable(struct regulator *reg)
{
	int ret = fail();
	assert(reset.physical == 0 && !reg->enabled);
	if (!ret)
		reg->enabled = true;
#ifdef TEST_CLEANUP
	if (!ret)
		last_enabled = reg->id;
#endif
	return ret;
}

static int regulator_disable(struct regulator *reg)
{
	assert(reset.physical == 0 && !clock.enabled && off_selected);
	assert(reg->enabled && reg->id < last_disabled);
	last_disabled = reg->id;
#ifdef TEST_CLEANUP
	int ret = fail_off();
	if (ret) {
		disable_failed[reg->id] = true;
		return ret;
	}
#endif
	reg->enabled = false;
	return 0;
}

static int pinctrl_select_state(struct pinctrl *pins, struct pinctrl_state *state)
{
	(void)pins;
	assert(reset.physical == 0);
	if (state->on) {
#ifdef TEST_CLEANUP
		assert(dovdd_settled);
#endif
		return fail();
	}
	assert(!clock.enabled);
	off_selected++;
#ifdef TEST_CLEANUP
	return fail_off();
#else
	return 0;
#endif
}

static int clk_prepare_enable(struct clk *clk)
{
	int ret = fail();
	assert(reset.physical == 0 && !clk->enabled);
	if (!ret)
		clk->enabled = true;
	return ret;
}

static void clk_disable_unprepare(struct clk *clk)
{
	assert(reset.physical == 0 && clk->enabled);
	clk->enabled = false;
}

static void usleep_range(unsigned long min, unsigned long max)
{
	assert(min > 0 && max >= min);
#ifdef TEST_CLEANUP
	if (last_enabled == 3 && !clock.enabled && min >= 1000)
		dovdd_settled = 1;
#endif
}

/* Extracted verbatim from the patched driver, not a copied power model. */
#include "identity-under-test.h"

int main(void)
{
	struct pinctrl pins = {0};
	struct pinctrl_state on = {.on = true}, off = {0};
	struct regulator regs[IMX882_NUM_SUPPLIES];
	struct imx882_identity sensor = {
		.xclk = &clock, .reset = &reset, .pinctrl = &pins,
		.mclk_4ma = &on, .mclk_off = &off,
	};

	for (int scenario = 0; scenario <
#ifdef TEST_CLEANUP
	     STARTUP_CASES * 32
#else
	     STARTUP_CASES
#endif
	     ; scenario++) {
		int failure = scenario % STARTUP_CASES;
		unsigned long enabled = 0;
		bool clock_enabled = false;
		int ret;

		/* GPIOD_OUT_HIGH on an active-low descriptor acquires physical low. */
		reset = (struct gpio_desc){.active_low = true, .physical = 0};
		clock.enabled = false;
		step = releases = off_selected = 0;
		last_disabled = IMX882_NUM_SUPPLIES;
		fail_at = failure;
#ifdef TEST_CLOCK
		rounded_rate = failure == 12;
		rate_owned = false;
		rate_puts = 0;
		assert(!sensor.rate_exclusive);
#endif
#ifdef TEST_CLEANUP
		off_mask = scenario / STARTUP_CASES;
		off_step = first_off_error = dovdd_settled = 0;
		last_enabled = -1;
		for (int i = 0; i < 4; i++)
			disable_failed[i] = false;
#endif
		for (int i = 0; i < IMX882_NUM_SUPPLIES; i++) {
			regs[i] = (struct regulator){.id = i};
			sensor.supplies[i].consumer = &regs[i];
			assert(imx882_supply_names[i]);
		}
		ret = imx882_power_on(&sensor, &enabled, &clock_enabled);
#ifdef TEST_CLOCK
		assert(ret == (rounded_rate ? -EINVAL : failure ? -123 : 0));
		assert(step == (rounded_rate ? 1 : failure ? failure : 11));
		if (rounded_rate)
			assert(!enabled && !clock_enabled);
#else
		assert(ret == (failure ? -123 : 0));
		assert(step == (failure ? failure : 11));
#endif
		assert(releases == (failure ? 0 : 1));
		assert(reset.physical == (failure ? 0 : 1));
		if (!failure)
			assert(enabled == 15 && clock_enabled);
#ifdef TEST_CLEANUP
		ret = imx882_power_off(&sensor, enabled, clock_enabled);
		assert(ret == first_off_error);
		assert(off_step == 1 + __builtin_popcountl(enabled));
#else
		imx882_power_off(&sensor, enabled, clock_enabled);
#endif
		assert(reset.physical == 0 && !clock.enabled && off_selected == 1);
#ifdef TEST_CLOCK
		assert(!rate_owned && !sensor.rate_exclusive);
		assert(rate_puts == (failure == 1 ? 0 : 1));
#endif
		for (int i = 0; i < IMX882_NUM_SUPPLIES; i++)
#ifdef TEST_CLEANUP
			assert(regs[i].enabled == disable_failed[i]);
#else
			assert(!regs[i].enabled);
#endif
	}
#ifdef TEST_CLOCK
	puts("PASS: 416 startup/shutdown combinations, exclusive clock balance and rounding rejection");
#elif defined(TEST_CLEANUP)
	puts("PASS: 384 startup/shutdown combinations, first error and DOVDD settling");
#else
	puts("PASS: success + 11 power-on failures; reset and reverse shutdown");
#endif
	return 0;
}
