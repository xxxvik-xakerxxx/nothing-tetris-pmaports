/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_LIBRARY_ASSOCIATION_H
#define B41_LIBRARY_ASSOCIATION_H
#include <elf.h>
#include <stddef.h>
#include <stdint.h>
#define B41_LIBRARY_FILE_SIZE 7299184u
#define B41_LIBRARY_IMAGE_END 0x90ffc0u
struct b41_library_view {
    uintptr_t base;
    const Elf64_Phdr *phdr;
    size_t phnum;
    const void *registration_symbol;
};
struct b41_library_association {
    uintptr_t base, xml_global, chip_global;
    size_t extent;
};
/* Read-only association, NEVER authentication or load/engine authorization.
 * The existing trusted immutable staging gate must SHA256-pin the complete ELF
 * and Bionic closure before loading. This verifies exact ELF/build-id/phdr shape,
 * file-backed immutable segments, symbol offset, and relocated global pointers.
 * View must come from the legitimate loader; its readable mapped spans must
 * remain valid. No loaded or retained resource is closed/freed here.
 * Failure leaves out untouched. Zero means association only, not native init.
 */
int b41_library_associate(const void *file, size_t length,
    const struct b41_library_view *view, struct b41_library_association *out);
#endif
