#include "twatch_support.h"
#include "board_catalogs.h"
static bool started;
static risc_hardware_catalog_v1 api = {1, sizeof(api), NULL, NULL, NULL, 0};
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started || !d || n != 1 || !twatch_equal(d[0].capability_id, "platform.board") ||
        d[0].api_version != 2 || !d[0].api)
        return false;
    const risc_hardware_board_identity_v2 *b = d[0].api;
    if (b->api_version != 2 || b->struct_size < sizeof(*b))
        return false;
    for (size_t i = 0; i < sizeof(catalogs) / sizeof(catalogs[0]); i++)
        if (twatch_equal(b->board_id, catalogs[i].board_id) &&
            twatch_equal(b->revision, catalogs[i].revision)) {
            api = catalogs[i];
            started = true;
            return true;
        }
    return false;
}
static bool quiesce(void) {
    started = false;
    api = (risc_hardware_catalog_v1){1, sizeof(api), NULL, NULL, NULL, 0};
    return true;
}
TW_DRIVER("twatch-board", "hardware.catalog", 1, api)
