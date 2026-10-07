#ifndef PORTABLE_MOTION_TAP_V1_H
#define PORTABLE_MOTION_TAP_V1_H
/* Append-only motion.accel@1 contract. Encoded tap settings are not g values.
 * Configuration is invocation-local; the application owns persistent policy.
 * Both sleep and observation preparation must be paired with resume_wake,
 * including failures. Observation is only legal in an explicit awake session. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define TWATCH_MOTION_API_V1 1u
#define TWATCH_MOTION_CAPABILITY "motion.accel"
typedef struct { int16_t x,y,z; } twatch_accel_sample_v1;
typedef struct {
    uint32_t struct_size;
    uint16_t profile,minimum,maximum,default_value;
    /* Larger encoded values are less sensitive for these supported profiles. */
} twatch_tap_info_v1;
enum { TWATCH_TAP_BMA423=1, TWATCH_TAP_BMA456H=2 };
typedef struct {
    uint32_t struct_size;
    bool double_tap,sample_ready;
    int16_t x_mg,y_mg,z_mg;
} twatch_tap_observation_v1;
typedef struct {
    uint32_t api_version,struct_size;
    void *context;
    bool (*read)(void *,twatch_accel_sample_v1 *);
    bool (*chip_id)(void *,uint8_t *);
    bool (*prepare_wake)(void *);
    bool (*wake_pending)(void *,bool *);
    bool (*resume_wake)(void *);
    uint32_t (*wake_error)(void *);
    bool (*tap_info)(void *,twatch_tap_info_v1 *);
    bool (*tap_configure)(void *,uint16_t value);
    bool (*tap_observe_begin)(void *,uint16_t value);
    /* Reads/acknowledges the selected hardware double-tap status. Never call
     * in sleep preparation: wake_pending remains a non-acknowledging read. */
    bool (*tap_observe)(void *,twatch_tap_observation_v1 *);
} twatch_motion_api_v1;
#define TWATCH_MOTION_SAMPLE_SIZE offsetof(twatch_motion_api_v1,prepare_wake)
#define TWATCH_MOTION_WAKE_SIZE offsetof(twatch_motion_api_v1,wake_error)
#define TWATCH_MOTION_DIAGNOSTIC_SIZE offsetof(twatch_motion_api_v1,tap_info)
#define TWATCH_MOTION_TAP_SIZE sizeof(twatch_motion_api_v1)
static inline bool portable_motion_tap_valid(const twatch_motion_api_v1 *a) {
    return a && a->api_version==1 && a->struct_size>=TWATCH_MOTION_TAP_SIZE &&
        a->tap_info && a->tap_configure && a->tap_observe_begin && a->tap_observe && a->resume_wake;
}

#if UINTPTR_MAX == UINT32_MAX && !defined(__cplusplus)
_Static_assert(TWATCH_MOTION_SAMPLE_SIZE==20,"motion sample prefix ABI");
_Static_assert(TWATCH_MOTION_WAKE_SIZE==32,"motion wake prefix ABI");
_Static_assert(TWATCH_MOTION_DIAGNOSTIC_SIZE==36,"motion diagnostic prefix ABI");
_Static_assert(TWATCH_MOTION_TAP_SIZE==52,"motion observation suffix ABI");
#endif

#endif
