/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_library_association.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void rejected(const unsigned char *file, size_t size,
    const struct b41_library_view *view, int expected)
{
    struct b41_library_association out, before;
    memset(&out, 0xa5, sizeof(out));
    memcpy(&before, &out, sizeof(out));
    assert(b41_library_associate(file, size, view, &out) == expected);
    assert(!memcmp(&before, &out, sizeof(out)));
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *fp = fopen(argv[1], "rb");
    assert(fp);
    unsigned char *file = malloc(B41_LIBRARY_FILE_SIZE);
    unsigned char *image = calloc(1, B41_LIBRARY_IMAGE_END);
    assert(file && image);
    assert(fread(file, 1, B41_LIBRARY_FILE_SIZE, fp) == B41_LIBRARY_FILE_SIZE);
    assert(fgetc(fp) == EOF && !ferror(fp));
    assert(fclose(fp) == 0);
    Elf64_Phdr phdr[10];
    memcpy(phdr, file + 64, sizeof(phdr));
    for (unsigned i = 0; i < 10; ++i) {
        if (phdr[i].p_type != PT_LOAD) continue;
        assert(phdr[i].p_offset + phdr[i].p_filesz <= B41_LIBRARY_FILE_SIZE);
        assert(phdr[i].p_vaddr + phdr[i].p_memsz <= B41_LIBRARY_IMAGE_END);
        memcpy(image + phdr[i].p_vaddr, file + phdr[i].p_offset, phdr[i].p_filesz);
    }
    uintptr_t base = (uintptr_t)image, target = base + 0x7178b8;
    memcpy(image + 0x6e6660, &target, sizeof(target));
    target = base + 0x6f2dac;
    memcpy(image + 0x6e6610, &target, sizeof(target));
    struct b41_library_view view = {base, phdr, 10, image + 0x52f9d0};
    struct b41_library_association out;
    assert(!b41_library_associate(file, B41_LIBRARY_FILE_SIZE, &view, &out));
    assert(out.base == base && out.xml_global == base + 0x7178b8);
    assert(out.chip_global == base + 0x6f2dac && out.extent == B41_LIBRARY_IMAGE_END);
    rejected(file, B41_LIBRARY_FILE_SIZE - 1, &view, -ENOEXEC);
    file[0x298] ^= 1;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ENOEXEC);
    file[0x298] ^= 1;
    file[EI_CLASS] = ELFCLASS32;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ENOEXEC);
    file[EI_CLASS] = ELFCLASS64;
    view.phnum = 9;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ENOEXEC);
    view.phnum = 10;
    phdr[0].p_align ^= 1;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ESTALE);
    phdr[0].p_align ^= 1;
    image[0x1000] ^= 1;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ESTALE);
    image[0x1000] ^= 1;
    image[0x4f0100] ^= 1;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ESTALE);
    image[0x4f0100] ^= 1;
    view.registration_symbol = image + 0x52f9d4;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ESTALE);
    view.registration_symbol = image + 0x52f9d0;
    image[0x6e6660] ^= 1;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ESTALE);
    image[0x6e6660] ^= 1;
    image[0x6e6610] ^= 1;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ESTALE);
    image[0x6e6610] ^= 1;
    /* Non-GOT writable state is allowed to differ after legitimate relocation. */
    image[0x718000] ^= 1;
    assert(!b41_library_associate(file, B41_LIBRARY_FILE_SIZE, &view, &out));
    view.base = UINTPTR_MAX - B41_LIBRARY_IMAGE_END + 1;
    rejected(file, B41_LIBRARY_FILE_SIZE, &view, -ERANGE);
    free(image); free(file);
    puts("B41 library association: immutable image, aliases, drift and failure atomicity pass");
    return 0;
}
