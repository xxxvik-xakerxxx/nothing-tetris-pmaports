/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "drivers.h"
#include "accel-mount-matrix.h"
#include "hf-abi.h"
#include <glib-unix.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>

#if G_BYTE_ORDER != G_LITTLE_ENDIAN
#error MediaTek HF backend requires little-endian ABI
#endif

typedef struct {
        int fd;
        guint watch, deadline;
        uint8_t sensor;
        uint32_t gain;
        gboolean enabled;
        int64_t timestamp;
        AccelVec3 *matrix;
        GUdevDevice *device;
} HfData;

static gboolean
hf_ready(void)
{
        g_autofree char *ready = NULL;
        return g_file_get_contents("/sys/module/sensorhub/parameters/firmware_ready",
                                   &ready, NULL, NULL) && g_str_equal(g_strstrip(ready), "Y");
}

static gboolean
hf_request(int fd, unsigned int number, uint8_t sensor, struct hf_packet *packet)
{
        memset(packet, 0, sizeof(*packet));
        packet->sensor = sensor;
        return ioctl(fd, _IOC(_IOC_READ | _IOC_WRITE, 'a', number, sizeof(*packet)), packet) == 0;
}

static int
hf_open_info(GUdevDevice *device, uint8_t sensor, struct hf_info *info)
{
        struct hf_packet packet;
        struct stat st;
        const char *path = g_udev_device_get_device_file(device);
        int fd;
        if (!path || !hf_ready())
                return -1;
        fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0)
                return -1;
        if (fstat(fd, &st) < 0 || !S_ISCHR(st.st_mode) ||
            !hf_request(fd, 8, 0, &packet) || !packet.payload[0] ||
            !hf_request(fd, 1, sensor, &packet) || !packet.payload[0] ||
            !hf_request(fd, 6, sensor, &packet))
                goto fail;
        memcpy(info, packet.payload, sizeof(*info));
        if (info->sensor != sensor || info->gain == 0)
                goto fail;
        return fd;
fail:
        close(fd);
        return -1;
}

static gboolean
hf_discover(GUdevDevice *device, uint8_t sensor)
{
        struct hf_info info;
        int fd;
        /* Opt-in ABI profile: never probe arbitrary character devices. */
        if (g_strcmp0(g_getenv("TETRIS_HF_BACKEND"), "1") ||
            g_strcmp0(g_udev_device_get_subsystem(device), "hf_manager") ||
            g_strcmp0(g_udev_device_get_name(device), "hf_manager"))
                return FALSE;
        fd = hf_open_info(device, sensor, &info);
        if (fd < 0)
                return FALSE;
        close(fd);
        return TRUE;
}

static void
hf_control(HfData *data, gboolean enabled)
{
        struct hf_command cmd = hf_make_command(data->sensor, enabled);
        ssize_t result = write(data->fd, &cmd, sizeof(cmd));
        /* Vendor write returns callback status 0 on success. Never retry. */
        if (result != 0 && result != sizeof(cmd))
                g_error("HF sensor %u control failed: %s", data->sensor, g_strerror(errno));
        data->enabled = enabled;
}

static gboolean
hf_first_sample_timeout(gpointer userdata)
{
        SensorDevice *sensor = userdata;
        HfData *data = sensor->priv;
        data->deadline = 0;
        g_error("HF sensor %u did not provide its first sample", data->sensor);
        return G_SOURCE_REMOVE;
}

static gboolean
hf_read(int fd, GIOCondition condition, gpointer userdata)
{
        SensorDevice *sensor = userdata;
        HfData *data = sensor->priv;
        struct hf_event events[128];
        ssize_t bytes;
        if (condition & (G_IO_ERR | G_IO_HUP | G_IO_NVAL) || !hf_ready())
                g_error("HF sensor transport lost");
        bytes = read(fd, events, sizeof(events));
        if (bytes < 0 && (errno == EAGAIN || errno == EINTR))
                return G_SOURCE_CONTINUE;
        if (bytes <= 0 || bytes % sizeof(events[0]))
                g_error("Invalid HF sensor event stream");
        for (size_t i = 0; i < (size_t) bytes / sizeof(events[0]); i++) {
                struct hf_event *event = &events[i];
                if (event->sensor != data->sensor || event->action != 0)
                        continue;
                if (!hf_valid_data(event, data->sensor, data->timestamp))
                        g_error("HF sensor timestamp regressed");
                data->timestamp = event->timestamp;
                g_clear_handle_id(&data->deadline, g_source_remove);
                if (data->sensor == 1) {
                        AccelReadings values;
                        AccelVec3 v = { event->words[0], event->words[1], event->words[2] };
                        if (!apply_mount_matrix(data->matrix, &v))
                                g_error("HF mount matrix failed");
                        values.accel_x = v.x; values.accel_y = v.y; values.accel_z = v.z;
                        set_accel_scale(&values.scale, 1.0 / data->gain);
                        sensor->callback_func(sensor, &values, sensor->user_data);
                } else if (data->sensor == 5) {
                        LightReadings values = { .uses_lux = TRUE };
                        if (event->words[0] < 0)
                                g_error("Negative HF light reading");
                        values.level = (double)event->words[0] / data->gain;
                        sensor->callback_func(sensor, &values, sensor->user_data);
                } else {
                        ProximityReadings values;
                        if (event->words[0] < 0)
                                g_error("Negative HF proximity reading");
                        values.is_near = event->words[0] == 0 ? PROXIMITY_NEAR_TRUE : PROXIMITY_NEAR_FALSE;
                        sensor->callback_func(sensor, &values, sensor->user_data);
                }
        }
        return G_SOURCE_CONTINUE;
}

static void
hf_set_polling(SensorDevice *sensor, gboolean enabled)
{
        HfData *data = sensor->priv;
        if (data->enabled == enabled)
                return;
        g_clear_handle_id(&data->watch, g_source_remove);
        g_clear_handle_id(&data->deadline, g_source_remove);
        if (enabled) {
                struct hf_info info;
                data->fd = hf_open_info(data->device, data->sensor, &info);
                if (data->fd < 0 || info.gain != data->gain)
                        g_error("HF sensor identity changed or transport unavailable");
                data->timestamp = 0;
        }
        hf_control(data, enabled);
        if (enabled) {
                data->watch = g_unix_fd_add(data->fd, G_IO_IN | G_IO_ERR | G_IO_HUP,
                                           hf_read, sensor);
                data->deadline = g_timeout_add_seconds(5, hf_first_sample_timeout, sensor);
        } else {
                /* A fresh client on the next claim cannot replay queued old samples. */
                close(data->fd);
                data->fd = -1;
        }
}

static SensorDevice *
hf_open(GUdevDevice *device, uint8_t id)
{
        struct hf_info info;
        int fd = hf_open_info(device, id, &info);
        SensorDevice *sensor;
        HfData *data;
        if (fd < 0)
                return NULL;
        sensor = g_new0(SensorDevice, 1);
        data = g_new0(HfData, 1);
        close(fd);
        data->fd = -1; data->sensor = id; data->gain = info.gain;
        data->device = g_object_ref(device);
        data->matrix = setup_mount_matrix(device);
        sensor->priv = data;
        sensor->name = g_strndup(info.name, sizeof(info.name));
        return sensor;
}

static void
hf_close(SensorDevice *sensor)
{
        HfData *data = sensor->priv;
        hf_set_polling(sensor, FALSE);
        g_object_unref(data->device);
        g_free(data->matrix);
        g_free(data);
        g_free(sensor);
}

#define HF_DRIVER(label, id, kind) \
static gboolean label##_discover(GUdevDevice *d) { return hf_discover(d, id); } \
static SensorDevice *label##_open(GUdevDevice *d) { return hf_open(d, id); } \
SensorDriver label = { .driver_name = "MediaTek HF " #label, .type = kind, \
        .discover = label##_discover, .open = label##_open, \
        .set_polling = hf_set_polling, .close = hf_close };

HF_DRIVER(mtk_hf_accel, 1, DRIVER_TYPE_ACCEL)
HF_DRIVER(mtk_hf_light, 5, DRIVER_TYPE_LIGHT)
HF_DRIVER(mtk_hf_proximity, 8, DRIVER_TYPE_PROXIMITY)
