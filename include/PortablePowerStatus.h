#pragma once
#include "RiscBatteryGaugeV1.h"
/* Optional, layout-preserving status flags in board.battery@1 samples.
 * STATUS_VALID requires working battery detection and gates bits 3..7. Old providers leave it clear; clients must not
 * infer USB, charger enable, presence, completion or temperature from zeroes.
 * INPUT_READY means usable external power, not cable detection or wattage.
 * THERMAL_LIMIT means PMIC die regulation, never a measured cell temperature.
 * CHARGE_DONE comes from charger state, never from an estimated 100 percent.
 * No writes, policy setters, Runtime change or larger ABI table is involved. */
enum {
    PORTABLE_POWER_STATUS_VALID = 1u << 2,
    PORTABLE_POWER_INPUT_READY = 1u << 3,
    PORTABLE_POWER_CHARGER_ENABLED = 1u << 4,
    PORTABLE_POWER_CHARGE_DONE = 1u << 5,
    PORTABLE_POWER_BATTERY_PRESENT = 1u << 6,
    PORTABLE_POWER_THERMAL_LIMIT = 1u << 7
};
/* App-local read adapter; no runtime import. False clears every prior reading. */
bool portable_power_read(risc_battery_sample_v1 *out);
