#pragma once
/* Proposed generic HCI packet capability. See docs/CAPABILITY_BACKFILL.md. */
#include "RiscProviderV2.h"
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*send)(void *, uint8_t packet_type, const uint8_t *packet, size_t length);
    /* 1 packet, 0 no packet, -1 I/O/invalid packet/capacity. Capacity >=1028. */
    int32_t (*next)(void *, uint8_t *packet_type, uint8_t *packet, size_t capacity, size_t *length);
} risc_bluetooth_hci_v1;
