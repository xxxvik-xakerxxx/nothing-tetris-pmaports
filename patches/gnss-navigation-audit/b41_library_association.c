/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_library_association.h"
#include <errno.h>
#include <string.h>
_Static_assert(sizeof(Elf64_Phdr) == 56 && sizeof(Elf64_Ehdr) == 64, "ELF64 ABI");
static const struct load_shape {
    uint64_t offset, address, filesz, memsz;
    unsigned flags;
} loads[] = {
    {0, 0, 0x4efc5c, 0x4efc5c, PF_R},
    {0x4f0000, 0x4f0000, 0x1f5c80, 0x1f5c80, PF_R | PF_X},
    {0x6e6000, 0x6e6000, 0x3538, 0x3538, PF_R | PF_W},
    {0x6e9538, 0x6ea538, 0x5d68, 0x225a88, PF_R | PF_W},
};
int b41_library_associate(const void *data, size_t length,
    const struct b41_library_view *v, struct b41_library_association *out)
{
    static const uint8_t build_id[16] = {0x31,0x94,0xdb,0x35,0x24,0x67,0x6a,0x9b,
        0x81,0xa4,0x9e,0x75,0x6f,0xcd,0x41,0xd8};
    const uint8_t *file = data;
    Elf64_Ehdr header;
    Elf64_Phdr phdr[10];
    uintptr_t target;
    unsigned n = 0;
    if (!data || !v || !out || !v->phdr || !v->base) return -EINVAL;
    if (length != B41_LIBRARY_FILE_SIZE || v->phnum != 10) return -ENOEXEC;
    if (sizeof(uintptr_t) != 8 || v->base > UINTPTR_MAX - B41_LIBRARY_IMAGE_END)
        return -ERANGE;
    memcpy(&header, file, sizeof(header));
    if (memcmp(header.e_ident, ELFMAG, SELFMAG) || header.e_ident[EI_CLASS] != ELFCLASS64 ||
        header.e_ident[EI_DATA] != ELFDATA2LSB || header.e_machine != EM_AARCH64 ||
        header.e_type != ET_DYN || header.e_phoff != 64 || header.e_phnum != 10 ||
        header.e_phentsize != 56 || memcmp(file + 0x298, build_id, sizeof(build_id)))
        return -ENOEXEC;
    memcpy(phdr, file + 64, sizeof(phdr));
    if (memcmp(phdr, v->phdr, sizeof(phdr))) return -ESTALE;
    for (unsigned i = 0; i < 10; ++i) {
        if (phdr[i].p_type != PT_LOAD) continue;
        if (n == 4) return -ENOEXEC;
        const struct load_shape *s = &loads[n++];
        if (phdr[i].p_offset != s->offset || phdr[i].p_vaddr != s->address ||
            phdr[i].p_filesz != s->filesz || phdr[i].p_memsz != s->memsz ||
            phdr[i].p_flags != s->flags || phdr[i].p_align != 4096) return -ENOEXEC;
        /* Only immutable file-backed spans: relocated writable sections differ. */
        if (!(phdr[i].p_flags & PF_W) && memcmp((const void *)(v->base + s->address),
            file + s->offset, (size_t)s->filesz)) return -ESTALE;
    }
    if (n != 4 || (uintptr_t)v->registration_symbol != v->base + 0x52f9d0) return -ESTALE;
    memcpy(&target, (const void *)(v->base + 0x6e6660), sizeof(target));
    if (target != v->base + 0x7178b8) return -ESTALE;
    memcpy(&target, (const void *)(v->base + 0x6e6610), sizeof(target));
    if (target != v->base + 0x6f2dac) return -ESTALE;
    struct b41_library_association result = {v->base, v->base + 0x7178b8,
        v->base + 0x6f2dac, B41_LIBRARY_IMAGE_END};
    *out = result;
    return 0;
}
