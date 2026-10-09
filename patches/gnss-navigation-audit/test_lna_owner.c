/* SPDX-License-Identifier: GPL-2.0-only */
/* CI shim runs the actual patched parser/cache on synthetic OF nodes.
 * This is not a kernel lifetime, GPIO or hardware test.
 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "gps_dl_lna_metadata.h"

struct device_node {
	const char *compatible;
	int available, refs, state_index, phandle_count, pinmux_count, read_error;
	unsigned int mux;
	struct device_node *parent, *state, *children, *next;
};
struct device { struct device_node *of_node; };
enum { GPS_DL_L1_LNA_DSP_CTRL };
static int control;
static void *g_gps_dl_pinctrl_ptr = &control;
static void *g_gps_dl_pinctrl_state_struct_list[] = { &control };
#define IS_ERR_OR_NULL(ptr) (!(ptr))
#define DEFINE_MUTEX(name) pthread_mutex_t name = PTHREAD_MUTEX_INITIALIZER
#define mutex_lock(lock) ((void)pthread_mutex_lock(lock))
#define mutex_unlock(lock) ((void)pthread_mutex_unlock(lock))
#define GDL_LOGW_INI(...) ((void)0)
static int of_device_is_available(struct device_node *n) { return n && n->available; }
static int of_device_is_compatible(struct device_node *n, const char *s)
{ return n && n->compatible && !strcmp(n->compatible, s); }
static int of_property_match_string(struct device_node *n, const char *p, const char *s)
{
	assert(!strcmp(p, "pinctrl-names") && !strcmp(s, "gps_l1_lna_dsp_ctrl"));
	return n->state_index;
}
static int of_property_count_u32_elems(struct device_node *n, const char *p)
{ return !strcmp(p, "pinmux") ? n->pinmux_count : n->phandle_count; }
static struct device_node *of_parse_phandle(struct device_node *n, const char *p, int index)
{
	assert(!strcmp(p, "pinctrl-2") && index == 0);
	if (n->state) ++n->state->refs;
	return n->state;
}
static void of_node_put(struct device_node *n)
{ if (n) { assert(n->refs > 0); --n->refs; } }
static int of_property_read_u32(struct device_node *n, const char *p, unsigned int *v)
{
	assert(!strcmp(p, "pinmux"));
	if (n->read_error) return n->read_error;
	*v = n->mux;
	return 0;
}
static struct device_node *next_child(struct device_node *state, struct device_node *old)
{
	struct device_node *n = old ? old->next : state->children;
	of_node_put(old);
	while (n && !n->available) n = n->next;
	if (n) ++n->refs;
	return n;
}
#define for_each_available_child_of_node(state, child) \
	for ((child) = next_child(state, NULL); (child); (child) = next_child(state, child))
#include "lna-owner-under-test.inc"

int main(void)
{
	struct device_node pio = {.compatible = "mediatek,mt6878-pinctrl", .available = 1};
	struct device_node group = {.available = 1, .pinmux_count = 1, .mux = (143u << 8) | 2};
	struct device_node state = {.available = 1, .parent = &pio, .children = &group};
	struct device_node gps = {.compatible = "mediatek,mt6878-gps", .available = 1,
		.state_index = 2, .phandle_count = 1, .state = &state};
	struct device owner = {.of_node = &gps}, second = {.of_node = &gps};
	int second_control;
	unsigned int pin = 0xa5a5a5a5;
	assert(gps_dl_get_lna_pin(&pin) == -ENODEV && pin == 0xa5a5a5a5);
	gps_dl_lna_metadata_init(&owner);
	assert(gps_dl_get_lna_pin(&pin) == 0 && pin == 143);
	assert(!state.refs && !group.refs);
	gps_dl_lna_metadata_remove(&owner);
	assert(gps_dl_get_lna_pin(&pin) == -ENODEV);
	for (unsigned int order = 0; order < 2; ++order) {
		gps_dl_lna_metadata_init(&owner);
		assert(gps_dl_get_lna_pin(&pin) == 0 && pin == 143);
		/* A second successful probe changes the singleton driver globals. */
		g_gps_dl_pinctrl_ptr = &second_control;
		gps_dl_lna_metadata_init(&second);
		pin = 0xa5a5a5a5;
		assert(gps_dl_get_lna_pin(&pin) == -EBUSY && pin == 0xa5a5a5a5);
		gps_dl_lna_metadata_init(&owner);
		gps_dl_lna_metadata_init(&second);
		assert(gps_dl_get_lna_pin(&pin) == -EBUSY && pin == 0xa5a5a5a5);
		gps_dl_lna_metadata_remove(order ? &owner : &second);
		assert(gps_dl_get_lna_pin(&pin) == -EBUSY && pin == 0xa5a5a5a5);
		gps_dl_lna_metadata_init(order ? &second : &owner);
		assert(gps_dl_get_lna_pin(&pin) == -EBUSY && pin == 0xa5a5a5a5);
		gps_dl_lna_metadata_remove(order ? &second : &owner);
		assert(gps_dl_get_lna_pin(&pin) == -EBUSY && pin == 0xa5a5a5a5);
		/* Removing both owners is not enough: unrelated/global state may persist. */
		gps_dl_lna_metadata_init(&owner);
		assert(gps_dl_get_lna_pin(&pin) == -EBUSY && pin == 0xa5a5a5a5);
		gps_dl_lna_metadata_remove(&owner);
		/* Simulate the driver-wide unregister barrier, not a normal re-probe. */
		gps_dl_lna_metadata_reset();
		g_gps_dl_pinctrl_ptr = &control;
		assert(gps_dl_get_lna_pin(&pin) == -ENODEV && pin == 0xa5a5a5a5);
		gps_dl_lna_metadata_init(&owner);
		assert(gps_dl_get_lna_pin(&pin) == 0 && pin == 143);
		gps_dl_lna_metadata_remove(&owner);
	}

	for (unsigned int fault = 0; fault < 12; ++fault) {
		struct device_node bad_group = group, bad_state = state, bad_gps = gps, bad_pio = pio;
		struct device bad_owner = {.of_node = &bad_gps};
		struct device_node duplicate = group;
		bad_gps.state = &bad_state;
		bad_state.parent = &bad_pio;
		bad_state.children = &bad_group;
		int expected = -EINVAL;
		switch (fault) {
		case 0: bad_owner.of_node = NULL; expected = -ENODEV; break;
		case 1: bad_gps.state_index = -1; expected = -ENODATA; break;
		case 2: bad_gps.phandle_count = 2; break;
		case 3: bad_gps.state = NULL; expected = -ENODATA; break;
		case 4: bad_pio.compatible = "wrong-controller"; break;
		case 5: bad_state.children = NULL; expected = -ENODATA; break;
		case 6: bad_group.pinmux_count = 2; break;
		case 7: bad_group.next = &duplicate; break;
		case 8: bad_group.mux = (143u << 8); break; /* GPIO function, not DSP LNA */
		case 9: bad_group.read_error = -EIO; expected = -EIO; break;
		case 10: bad_gps.compatible = "wrong-soc"; expected = -EOPNOTSUPP; break;
		case 11: bad_pio.available = 0; break;
		}
		pin = 0xa5a5a5a5;
		gps_dl_lna_metadata_init(&bad_owner);
		assert(gps_dl_get_lna_pin(&pin) == expected && pin == 0xa5a5a5a5);
		assert(!bad_state.refs && !bad_group.refs && !duplicate.refs);
		gps_dl_lna_metadata_remove(&bad_owner);
	}
	g_gps_dl_pinctrl_ptr = NULL;
	gps_dl_lna_metadata_init(&owner);
	assert(gps_dl_get_lna_pin(&pin) == -ENODEV);
	gps_dl_lna_metadata_remove(&owner);
	assert(gps_dl_get_lna_pin(NULL) == -EINVAL);
	puts("PASS: actual patched parser/cache, twelve invalid-record cases, conflict latch/both removal orders/no reinit revival/clean lifecycle");
	return 0;
}
