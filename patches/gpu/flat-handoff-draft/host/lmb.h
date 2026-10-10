#ifndef FLAT_HOST_LMB_H
#define FLAT_HOST_LMB_H
#include <stdint.h>
typedef uint64_t phys_addr_t;
typedef uint64_t phys_size_t;
#define LMB_NOMAP 2
#define LMB_NOOVERWRITE 4
#define LMB_NONOTIFY 8
enum lmb_mem_type { LMB_MEM_ALLOC_ADDR = 1, LMB_MEM_ALLOC_ANY, LMB_MEM_ALLOC_MAX };
int lmb_alloc_mem(enum lmb_mem_type, uint64_t, phys_addr_t *, phys_size_t, uint32_t);
long lmb_free(phys_addr_t, phys_size_t, uint32_t);
#endif
