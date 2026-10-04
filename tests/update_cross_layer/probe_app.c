/* Host-only app entry point. The module and grants use the actual Runtime loader.
 * Product providers are unmodified; display/radio UI lives in separate UI tests. */
#include <RiscRuntimeV1.h>
#include <assert.h>
extern void integration_entry(const risc_runtime_api_v1*);
extern void integration_fini(void);
static const risc_runtime_api_v1* runtime;
__attribute__((visibility("default"))) int app_module_init(void) {
 runtime=risc_runtime_get_api(1);assert(runtime);assert(!runtime->confirm_boot());return 0;
}
__attribute__((visibility("default"))) void app_main(void){integration_entry(runtime);}
__attribute__((visibility("default"))) void app_module_fini(void){assert(!runtime->confirm_boot());integration_fini();}
