/* SPDX-License-Identifier: GPL-2.0-only */
#include <dlfcn.h>
#include <string.h>
#include <unistd.h>

static void message(const char *text)
{
    size_t left = strlen(text);
    while (left) {
        ssize_t used = write(STDOUT_FILENO, text, left);
        if (used <= 0)
            _exit(3);
        text += used;
        left -= (size_t)used;
    }
}

int main(int argc, char **argv)
{
    if (argc != 2 || strcmp(argv[1], "/vendor/lib64/libmnl.so"))
        _exit(2);
    if (!dlopen(argv[1], RTLD_NOW | RTLD_LOCAL)) {
        const char *error = dlerror();
        message("LOAD_FAILED: ");
        message(error ? error : "no loader diagnostic");
        message("\n");
        _exit(1);
    }
    message("LOAD_OK: no vendor API called; no dlclose or destructors\n");
    _exit(0);
}
