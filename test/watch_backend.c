/* Exact Watch provider with unchanged strict I2C/GPIO fixture. */
#include "hid_watch_touch_backend.c"
const risc_touch_api_v1 *scene_timing_touch_api(void) {
    const risc_driver_v2 *driver=t5_driver_get(2);assert(driver);return driver->capability;
}
const risc_touch_api_v1 *scene_timing_touch_start(void) {return hid_watch_touch_start();}
bool scene_timing_touch_quiesce(void) {return provider->quiesce();}
void scene_timing_touch_stop(void) {provider->stop();assert(!bus_owned&&!gpio_owned);}
