#include <stddef.h>
#include <stdint.h>
void *map_sysmem(uint64_t address, unsigned long size);
void unmap_sysmem(const void *pointer);
uint64_t map_to_sysmem(const void *pointer);
