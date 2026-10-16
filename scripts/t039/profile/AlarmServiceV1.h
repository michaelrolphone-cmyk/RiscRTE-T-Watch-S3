#ifndef UTILITIES_ALARM_SERVICE_V1_H
#define UTILITIES_ALARM_SERVICE_V1_H
/* Utilities-owned, opaque-to-Runtime ordinary provider capability. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ALARM_SERVICE_CAPABILITY "alarm.service"
#define ALARM_SERVICE_API_V1 1u
#define ALARM_STATUS_CUE_SUPPORTED 1u
#define ALARM_KIND_ALARM 1u
#define ALARM_KIND_COUNTDOWN 2u
#define ALARM_MODE_VIBRATE 1u
#define ALARM_MODE_SOUND 2u
#define ALARM_MODE_BOTH 3u
enum { ALARM_OK=0, ALARM_PENDING=1, ALARM_BUSY=-1, ALARM_INVALID=-2,
       ALARM_STALE=-3, ALARM_STORAGE=-4, ALARM_RTC=-5, ALARM_OUTPUT=-6,
       ALARM_EXHAUSTED=-7, ALARM_FOREGROUND=-8 };
enum { ALARM_STATE_LOADING, ALARM_STATE_READY, ALARM_STATE_ALERT,
       ALARM_STATE_DISMISSING, ALARM_STATE_BLOCKED,
       /* Additive copied status: non-modal output reservation, before open and
        * through cleanup. Updated clients must drain it without painting an
        * alarm overlay. Earlier clients reject unknown states safely. */
       ALARM_STATE_CUE };
enum { ALARM_SCHEDULE_OFF, ALARM_SCHEDULE_ARMED, ALARM_SCHEDULE_DUE,
       ALARM_SCHEDULE_DISMISSED, ALARM_SCHEDULE_EXPIRED };
typedef struct {
    uint32_t kind, revision, deadline, generation;
} alarm_token_v1;
typedef struct {
    uint32_t revision, deadline, state;
} alarm_schedule_status_v1;
typedef struct {
    uint32_t api_version, struct_size, state;
    int32_t error;
    uint32_t snapshot, rtc_seconds, mode, output_uncertain;
    alarm_schedule_status_v1 schedules[2];
    alarm_token_v1 occurrence;
    uint32_t recovery_until, remaining_ms;
    char label[24];
} alarm_status_v1;
typedef struct {
    uint32_t struct_size, snapshot, rtc_seconds, deadline;
    /* deadline=0 means no schedule. Decision is consumed immediately by the
       serialized caller, with no intervening service/writer call. */
} alarm_sleep_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    /* Memory-only copied values; caller sets struct_size. No retained pointers. */
    int32_t (*status)(void *, alarm_status_v1 *);
    /* One cooperative phase, at most two dependency calls (three with the DND
       preflight enabled). Explicit foreground
       safe point only; synchronous
       NVS has no hard latency guarantee. Never invoke from provider poll. */
    int32_t (*step)(void *);
    /* Memory-only hint; does not prove a writer commit. Also retries blocked
       storage/RTC reconciliation, without silently acknowledging an alert. */
    int32_t (*refresh)(void *);
    /* Queues exact-current dismissal. Fully dismissed only after status READY,
       matching schedule DISMISSED, safe output stop and verified durable ACK. */
    int32_t (*acknowledge)(void *, const alarm_token_v1 *);
    /* Starts/finishes a fresh reconciliation. PENDING means call step and retry.
       No suppression flag or retained sleep lease; service has no I/O poll. */
    int32_t (*prepare_sleep)(void *, alarm_sleep_v1 *);
    /* Failure-only cleanup while a foreground presentation is not settled.
       One stop/silence/close operation per call, no storage or output start.
       OK proves both outputs stopped, but does NOT acknowledge an occurrence.
       OUTPUT means retain the invocation/resources; no normal handoff. */
    int32_t (*stop_only)(void *);
} alarm_service_v1;
/* Optional append-only suffix. The original table remains an unchanged prefix,
   so existing clients and providers keep their source and binary layouts. */
#define ALARM_SERVICE_SLEEP_RESUME_SUPPORTED 1u
typedef struct {
    alarm_service_v1 base;
    /* Only the serialized sleep owner may call this, exactly once after native
       Light sleep returns OK, before another mutating service/writer call.
       Pass the unchanged successful prepare_sleep decision. A refusal must not
       call it. One RTC read rejects invalid/backward time, then reanchors the
       independent awake monotonic clock and starts full reconciliation. OK
       confirms this boundary only; due work still requires normal steps.
       STALE rejects a wrong, reused or invalidated decision without I/O. */
    int32_t (*resume_sleep)(void *, const alarm_sleep_v1 *);
} alarm_service_sleep_v1;
#define ALARM_SERVICE_SLEEP_V1_SIZE ((uint32_t)sizeof(alarm_service_sleep_v1))
#if defined(__cplusplus)
#define ALARM_STATIC_ASSERT static_assert
#else
#define ALARM_STATIC_ASSERT _Static_assert
#endif
ALARM_STATIC_ASSERT(sizeof(alarm_token_v1)==16,"alarm occurrence token ABI");
ALARM_STATIC_ASSERT(sizeof(alarm_status_v1)==104,"alarm copied status ABI");
ALARM_STATIC_ASSERT(sizeof(alarm_sleep_v1)==16,"alarm sleep decision ABI");
ALARM_STATIC_ASSERT(offsetof(alarm_service_sleep_v1,base)==0,"alarm sleep base prefix");
ALARM_STATIC_ASSERT(offsetof(alarm_service_sleep_v1,resume_sleep)==sizeof(alarm_service_v1),"alarm sleep suffix offset");
#if UINTPTR_MAX == UINT32_MAX
ALARM_STATIC_ASSERT(sizeof(alarm_service_v1)==36,"alarm service target ABI");
ALARM_STATIC_ASSERT(sizeof(alarm_service_sleep_v1)==40,"alarm sleep service target ABI");
#endif
#undef ALARM_STATIC_ASSERT
#endif
