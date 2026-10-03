/* Integrated ESP32-S3 BLE HCI transport. Host protocols belong above this ELF. */
#include "twatch_support.h"
#include "RiscBluetoothHciV1.h"
static const twatch_hci_controller_v1 *hw;
static uint64_t session;
static bool started;
static bool send_packet(void *c, uint8_t type, const uint8_t *p, size_t n) {
    (void)c;
    if (!started || !p)
        return false;
    if (type == 1) {
        if (n < 3 || n > 258 || n != (size_t)p[2] + 3)
            return false;
    } else if (type == 2) {
        if (n < 4 || n > 1028 || n != 4u + p[2] + ((size_t)p[3] << 8))
            return false;
    } else
        return false;
    return hw->send(hw->context, session, type, p, n, 20);
}
static int32_t next_packet(void *c, uint8_t *type, uint8_t *p, size_t cap, size_t *length) {
    (void)c;
    if (length)
        *length = 0;
    if (!started || !type || !p || !length || cap < 1028)
        return -1;
    if (!hw->receive(hw->context, session, type, p, 1028, length, 0))
        return -1;
    if (!*length)
        return 0;
    size_t n = *length;
    bool valid = false;
    if (*type == 4)
        valid = n >= 2 && n <= 257 && n == 2u + p[1];
    if (*type == 2)
        valid = n >= 4 && n <= 1028 && n == 4u + p[2] + ((size_t)p[3] << 8);
    if (!valid) {
        *length = 0;
        return -1;
    }
    return 1;
}
static bool quiesce(void) {
    if (session) {
        if (!hw->close(hw->context, session))
            return false;
        session = 0;
    }
    started = false;
    hw = NULL;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started || session)
        return false;
    const risc_hw_radio_v1 *config =
        tw_config(d, n, "espressif,esp32s3-ble", "radio.integrated", sizeof(*config));
    if (!config || config->unit || config->features != 1)
        return false;
    hw = tw_dep(d, n, "platform.hci.controller", sizeof(*hw));
    if (!hw || !hw->open || !hw->send || !hw->receive || !hw->close)
        return false;
    if (!hw->open(hw->context, config->unit, &session) || !session)
        return false;
    started = true;
    return true;
}
static const risc_bluetooth_hci_v1 api = {1, sizeof(api), NULL, send_packet, next_packet};
TW_DRIVER("twatch-ble", "bluetooth.hci", 1, api)
