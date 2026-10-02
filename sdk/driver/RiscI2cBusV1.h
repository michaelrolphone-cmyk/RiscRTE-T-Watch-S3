#pragma once
#include "RiscProviderV2.h"
#ifdef __cplusplus
extern "C" {
#endif
#define RISC_I2C_BUS_API_V1 1u
#define RISC_I2C_BUS_CAPABILITY "i2c.bus"
typedef struct {
    uint32_t api_version;
    uint32_t struct_size;
    void *context;
    bool (*claim_device)(void *context, uint8_t address, uint64_t *claim);
    bool (*transact)(void *context, uint64_t claim,
                     const uint8_t *write_bytes, size_t write_length,
                     uint8_t *read_bytes, size_t read_length,
                     uint32_t timeout_ms);
    bool (*release_device)(void *context, uint64_t claim);
} risc_i2c_bus_api_v1;
#ifdef __cplusplus
}
#endif
