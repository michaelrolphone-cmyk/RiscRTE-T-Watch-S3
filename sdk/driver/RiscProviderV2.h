#pragma once
/* Vendored from michaelrolphone-cmyk/RiscRTE-Drivers @ cb0bd49d1fdd002c639c81437dce9fb0e3055d5b
 * sdk/driver/RiscProviderV2.h. Do not fork the ABI. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define RISC_PROVIDER_DRIVER_ABI_V2 2u
typedef struct {
    const char *capability_id;
    uint32_t api_version;
    const void *api;
} risc_provider_dependency_v1;
typedef struct {
    uint32_t abi_version;
    uint32_t struct_size;
    const char *driver_id;
    const char *capability_id;
    uint32_t capability_api;
    const void *capability;
    bool (*start)(const risc_provider_dependency_v1 *dependencies, size_t count);
    void (*stop)(void);
    bool (*quiesce)(void);
} risc_driver_v2;
typedef struct {
    risc_driver_v2 base;
    bool (*last_error)(char *destination, size_t capacity);
} risc_driver_diagnostics_v2;
#define RISC_DRIVER_V2_BASE_SIZE offsetof(risc_driver_v2, quiesce)
typedef const risc_driver_v2 *(*risc_driver_get_v2_fn)(uint32_t abi);
const risc_driver_v2 *t5_driver_get(uint32_t abi);
#ifdef __cplusplus
}
#endif
