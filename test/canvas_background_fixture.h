/* Declared host doubles for the canvas-only background clients. No physical
 * Contexts acquisition or BLE broadcasting is qualified by this fixture. */
#include "ContextsServiceV1.h"
#include "TelemetryBroadcastV1.h"
static bool canvas_ctx_pause(void*c){(void)c;return true;}
static bool canvas_ctx_step(void*c,const contexts_policy_v1*p){(void)c;(void)p;return true;}
static bool canvas_ctx_status(void*c,contexts_status_v1*s){(void)c;*s=(contexts_status_v1){.struct_size=sizeof(*s),.state=CONTEXTS_OFF};return true;}
static bool canvas_ctx_request(void*c,uint32_t s){(void)c;(void)s;return true;}
static bool canvas_ctx_export(void*c,uint32_t s,uint32_t k,uint32_t i,const void*b,uint32_t n){(void)c;(void)s;(void)k;(void)i;(void)b;(void)n;return false;}
static bool canvas_ctx_finish(void*c,uint32_t s,uint32_t r){(void)c;(void)s;(void)r;return true;}
static int32_t canvas_ctx_label(void*c,uint32_t s,uint32_t i,contexts_label_v1*out){(void)c;(void)s;(void)i;(void)out;return 0;}
static bool canvas_ctx_claim(void*c,uint32_t s,uint32_t i,const char*n,uint32_t g){(void)c;(void)s;(void)i;(void)n;(void)g;return false;}
static bool canvas_ctx_result(void*c,uint32_t s,uint32_t g,uint32_t r){(void)c;(void)s;(void)g;(void)r;return true;}
static const contexts_service_v1 canvas_ctx={.api_version=1,.struct_size=sizeof(canvas_ctx),.step=canvas_ctx_step,.pause=canvas_ctx_pause,.status=canvas_ctx_status,.request_export=canvas_ctx_request,.begin_export=canvas_ctx_request,.export_record=canvas_ctx_export,.finish_export=canvas_ctx_finish,.label=canvas_ctx_label,.claim_preset=canvas_ctx_claim,.preset_result=canvas_ctx_result,.capture_audio=canvas_ctx_pause};
static bool canvas_bt_step(void*c,bool allow,const telemetry_broadcast_policy_v1*p){(void)c;(void)allow;(void)p;return true;}
static bool canvas_bt_status(void*c,telemetry_broadcast_status_v1*s){(void)c;*s=(telemetry_broadcast_status_v1){.struct_size=sizeof(*s),.state=TELEMETRY_BROADCAST_OFF};return true;}
static int32_t canvas_bt_enum(void*c,uint32_t i,risc_telemetry_field_v1*f){(void)c;(void)i;(void)f;return 0;}
static int32_t canvas_bt_read(void*c,uint32_t i,int32_t*v){(void)c;(void)i;(void)v;return 0;}
static const telemetry_broadcast_v1 canvas_bt={1,sizeof(canvas_bt),NULL,canvas_bt_step,canvas_ctx_pause,canvas_bt_status,canvas_bt_enum,canvas_bt_read};
