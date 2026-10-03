#include "mock.h"
const risc_driver_v2 *first_get(uint32_t);
const risc_driver_v2 *second_get(uint32_t);
int main(void) {
    tw_hw_i2c_controller_v1 a = {.struct_size = sizeof(a),
                                 .bus = {.struct_size = sizeof(risc_hw_bus_v1),
                                         .kind = 2,
                                         .instance_id = 101,
                                         .controller = 0,
                                         .frequency_hz = 100000,
                                         .sda = 10,
                                         .scl = 11,
                                         .sclk = -1,
                                         .mosi = -1,
                                         .miso = -1}};
    tw_hw_i2c_controller_v1 b = a;
    b.bus.instance_id = 102;
    b.bus.controller = 1;
    b.bus.sda = 39;
    b.bus.scl = 40;
    risc_hardware_device_v1 e = {
        1, sizeof(e), 2, "espressif,esp32s3-i2c", "unspecified", "controller.i2c",
        1, sizeof(a), &a};
    risc_provider_dependency_v1 deps[] = {{"hardware.device", 1, &e},
                                          {"platform.i2c.controller", 1, &m_i2c}};
    const risc_driver_v2 *first = first_get(2), *second = second_get(2);
    assert(first != second && first->start(deps, 2));
    risc_hardware_device_v1 other = e;
    other.instance_id = 3;
    other.config = &b;
    risc_provider_dependency_v1 second_deps[] = {{"hardware.device", 1, &other},
                                                 {"platform.i2c.controller", 1, &m_i2c}};
    assert(second->start(second_deps, 2));
    const risc_i2c_bus_api_v1 *x = first->capability, *y = second->capability;
    uint64_t one, two;
    assert(x->claim_device(NULL, 0x34, &one));
    assert(y->claim_device(NULL, 0x34, &two));
    assert(!first->quiesce() && !second->quiesce());
    assert(y->release_device(NULL, two));
    assert(second->quiesce());
    assert(m_live == 1);
    uint8_t tx[] = {0x20, 0x33}, rx;
    assert(x->transact(NULL, one, tx, 2, NULL, 0, 20));
    assert(x->transact(NULL, one, tx, 1, &rx, 1, 20) && rx == 0x33);
    assert(x->release_device(NULL, one));
    assert(first->quiesce());
    assert(m_live == 0);
    return 0;
}
