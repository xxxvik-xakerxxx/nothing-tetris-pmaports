#define _POSIX_C_SOURCE 200809L
#include "download_linux.h"

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/* Linker-wrapped syscalls: this fixture never opens, reads or writes hardware. */
static unsigned int query_calls, write_calls, read_calls, fragment_calls;
static unsigned int pending_sequence;
static int pending, injected_error, injection_kind, clock_error, flags;
static uint64_t ticks;
static struct b41_mvcd_bootstrap_inputs fields;
static struct b41_bootstrap_session session;
static struct b41_download owner;
static const uint8_t name[] = "test";

int __wrap_clock_gettime(clockid_t id, struct timespec *time);
int __wrap_fcntl(int fd, int command, ...);
int __wrap_fstat(int fd, struct stat *st);
int __wrap_ioctl(int fd, unsigned long command, ...);
ssize_t __wrap_write(int fd, const void *data, size_t size);
ssize_t __wrap_read(int fd, void *data, size_t size);

int __wrap_clock_gettime(clockid_t id, struct timespec *time)
{
    assert(id == CLOCK_MONOTONIC);
    if (clock_error) {
        errno = EIO;
        return -1;
    }
    ++ticks;
    time->tv_sec = 0;
    time->tv_nsec = (long)ticks;
    return 0;
}

int __wrap_fcntl(int fd, int command, ...)
{
    assert(fd == 7 && command == F_GETFL);
    return flags;
}

int __wrap_fstat(int fd, struct stat *st)
{
    assert(fd == 7);
    memset(st, 0, sizeof(*st));
    st->st_mode = 0020000; /* Fixture-only S_IFCHR, hidden by strict POSIX headers. */
    return 0;
}

static int inject(int kind)
{
    if (injection_kind != kind)
        return 0;
    errno = injected_error;
    clock_error = 1; /* Later clock failure must not replace the first syscall error. */
    return 1;
}

int __wrap_ioctl(int fd, unsigned long command, ...)
{
    va_list args;

    assert(fd == 7);
    va_start(args, command);
    if (command == 23u || command == 24u) {
        struct b41_bootstrap_boot_info *info = va_arg(args, struct b41_bootstrap_boot_info *);

        ++query_calls;
        va_end(args);
        if (inject(1))
            return -1;
        *info = (struct b41_bootstrap_boot_info){0x1234, 0x5678, 0x9abc, 0x1357, 3};
        return 0;
    }
    assert(command == 25u || command == 26u);
    unsigned long argument = va_arg(args, unsigned long);
    va_end(args);
    assert(argument == fragment_calls);
    ++fragment_calls;
    if (inject(3))
        return -1;
    assert(!pending);
    pending_sequence = (unsigned int)argument + 1u;
    pending = 1;
    return 0;
}

ssize_t __wrap_write(int fd, const void *data, size_t size)
{
    const uint8_t *bytes = data;

    assert(fd == 7 && size == 116 && bytes[4] == 8 && bytes[6] == 0x1a);
    ++write_calls;
    if (inject(2))
        return -1;
    assert(write_calls == 1 && !pending); /* No extra per-fragment wire write. */
    pending_sequence = 0;
    pending = 1;
    return (ssize_t)size;
}

ssize_t __wrap_read(int fd, void *data, size_t size)
{
    uint8_t *bytes = data;
    size_t payload = pending_sequence == 0 ? 4u : 2u;
    size_t frame_size = payload + 10u;
    unsigned int sum = 0;

    assert(fd == 7 && size == 2048);
    ++read_calls;
    if (inject(4))
        return -1;
    if (!pending) {
        errno = EAGAIN;
        return -1;
    }
    memset(bytes, 0, frame_size);
    bytes[0] = 0xaa;
    bytes[1] = 0xf0;
    bytes[2] = (uint8_t)(payload + 4u);
    bytes[4] = pending_sequence == 0 ? 0x31 : 0x32;
    bytes[5] = 0xfe;
    bytes[6] = (uint8_t)pending_sequence;
    bytes[7] = (uint8_t)(pending_sequence >> 8);
    for (size_t i = 2; i < payload + 6u; ++i)
        sum += bytes[i];
    bytes[frame_size - 4u] = (uint8_t)sum;
    bytes[frame_size - 3u] = (uint8_t)(sum >> 8);
    bytes[frame_size - 2u] = 0xaa;
    bytes[frame_size - 1u] = 0x0f;
    pending = 0;
    return (ssize_t)frame_size;
}

static void init(void)
{
    memset(&fields, 0, sizeof(fields));
    memset(&session, 0, sizeof(session));
    memset(&owner, 0, sizeof(owner));
    fields.context_mode_13 = 0xff;
    fields.context_hz_18 = 26000000u;
    fields.context_baud_1c = 921600u;
    fields.context_chip_30 = UINT32_C(0xffff6725);
    fields.feature_name = name;
    fields.feature_name_size = sizeof(name);
    fields.secondary_fd_6edeec = -1;
    session.gps0_fd = 7;
    session.selectors.secure_download_7178b8_33e = 1;
    session.fields = &fields;
    query_calls = write_calls = read_calls = fragment_calls = 0;
    pending = injection_kind = injected_error = clock_error = 0;
    ticks = 0;
    flags = O_RDWR | O_NONBLOCK;
}

int main(void)
{
    for (unsigned int cw = 0; cw <= 1u; ++cw) {
        init();
        session.selectors.dsp_selector_717cb0 = (uint8_t)cw;
        assert(b41_download_linux_begin(&owner, &session, 1000) == 0);
        assert(b41_download_linux_begin(&owner, &session, 1000) == -EALREADY);
        while (owner.stage != B41_DOWNLOAD_ACKS_COMPLETE)
            assert(b41_download_linux_step(&owner) == 0);
        assert(query_calls == 1 && write_calls == 1 && fragment_calls == 3 && read_calls == 4);
        assert(owner.session == NULL);
        session.gps0_fd = -1;
        session.fields = NULL;
        clock_error = 1;
        assert(b41_download_linux_step(&owner) == 0);
    }
    init();
    flags = O_RDWR;
    assert(b41_download_linux_begin(&owner, &session, 1000) == -EINVAL);
    assert(query_calls == 0);
    init();
    assert(b41_download_linux_begin(&owner, &session, 0) == -ETIMEDOUT);
    assert(query_calls == 0);
    init();
    fields.feature_name = NULL;
    assert(b41_download_linux_begin(&owner, &session, 1000) != 0);
    assert(query_calls == 0);
    for (int kind = 1; kind <= 4; ++kind) {
        init();
        injection_kind = kind;
        injected_error = ENXIO;
        int result = b41_download_linux_begin(&owner, &session, 1000);
        while (result == 0)
            result = b41_download_linux_step(&owner);
        assert(result == -ENXIO && owner.first_error == -ENXIO);
        assert(b41_download_linux_begin(&owner, &session, 1000) == -ENXIO);
        assert(b41_download_linux_step(&owner) == -ENXIO);
        assert(query_calls == 1 && write_calls <= 1 && fragment_calls <= 1 && read_calls <= 1);
    }
    return 0;
}
