#include <assert.h>
#include "../drivers/twatch_board/driver.c"
int main(void) {
    const risc_driver_v2 *d = t5_driver_get(2);
    risc_hardware_board_identity_v2 b = {2, sizeof(b), "lilygo-t-watch-s3", "unknown"};
    risc_provider_dependency_v1 dep = {"platform.board", 2, &b};
    assert(!d->start(&dep, 1));
    b.revision = "sx1262-915-bma423";
    assert(d->start(&dep, 1));
    const risc_hardware_catalog_v1 *c = d->capability;
    assert(c->manifest_size > 1000 && c->manifest_json[0] == '{');
    assert(!d->start(&dep, 1));
    assert(d->quiesce());
    b.revision = "sx1280-2400-bma456h";
    assert(d->start(&dep, 1));
    assert(d->quiesce());
    return 0;
}
