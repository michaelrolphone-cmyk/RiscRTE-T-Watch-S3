#pragma once
#include "RiscRuntimeV1.h"
#include <string.h>
/* Optional suffix from RiscRTE Runtime0.1.11's canonical RiscRuntimeV1.h.
 * Existing frozen app SDK copies intentionally retain their ABI prefix. Read
 * only the appended function pointer after its published release-member end,
 * so legacy build lanes do not need incompatible duplicate header copies.
 * Deployment pins and tests verify this offset against the full Runtime SDK. */
static inline bool watch_confirm_paired_boot(const risc_runtime_api_v1* runtime) {
    bool (*confirm)(void)=NULL;
    const size_t offset=RISC_RUNTIME_CAPABILITIES_V1_SIZE;
    if(!runtime || runtime->api_version!=RISC_RUNTIME_API_V1 ||
       runtime->struct_size<offset+sizeof(confirm))return false;
    memcpy(&confirm,(const unsigned char*)runtime+offset,sizeof(confirm));
    return confirm && confirm();
}
