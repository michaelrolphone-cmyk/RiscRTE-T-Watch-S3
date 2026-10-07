#include "twatch_support.h"
#include "twatch_caps.h"
#include "RiscDisplayOutputV1.h"
#include "RiscBluetoothHciV1.h"
_Static_assert(sizeof(void *) == 4, "target pointers");
_Static_assert(sizeof(risc_provider_dependency_v1) == 12, "dependency ABI");
_Static_assert(sizeof(risc_driver_v2) == 36, "provider ABI");
_Static_assert(offsetof(risc_driver_v2, quiesce) == 32, "quiesce ABI");
_Static_assert(sizeof(risc_driver_poll_v2) == 48, "poll suffix ABI");
_Static_assert(sizeof(risc_hardware_device_v1) == 40, "hardware envelope ABI");
_Static_assert(offsetof(risc_hardware_device_v1, config) == 36, "hardware config pointer ABI");
_Static_assert(sizeof(risc_hw_bus_v1) == 40, "hardware bus ABI");
_Static_assert(sizeof(garden_gpio_v1) == 68, "shared GPIO ABI");
_Static_assert(sizeof(garden_spi_v1) == 36, "shared SPI ABI");
_Static_assert(sizeof(twatch_i2c_controller_v1) == 24, "raw I2C ABI");
_Static_assert(sizeof(tw_hw_i2c_device_v1) == 56, "I2C device config ABI");
_Static_assert(sizeof(tw_hw_audio_v1) == 16, "audio config ABI");
_Static_assert(sizeof(risc_i2c_bus_api_v1) == 24, "canonical I2C ABI");
_Static_assert(sizeof(risc_battery_sample_v1) == 4, "battery sample ABI");
_Static_assert(offsetof(twatch_pmu_api_v1, key_events) == sizeof(risc_battery_gauge_api_v1),
               "PMU append-only prefix");

_Static_assert(offsetof(garden_gpio_v1,light_sleep)==36,"raw GPIO append-only prefix");
_Static_assert(sizeof(risc_light_sleep_result_v1)==8,"sleep result ABI");

_Static_assert(offsetof(garden_gpio_v1,deep_sleep)==40,"raw deep append-only");
_Static_assert(offsetof(garden_gpio_v1,deep_sleep_hold)==44,"raw hold append-only");

_Static_assert(offsetof(garden_gpio_v1,light_sleep_for)==48,"raw timer append-only");
_Static_assert(TWATCH_PMU_DEEP_SLEEP_SIZE==36,"old PMU Deep ABI size preserved");

#include "../drivers/twatch_wifi/WifiApi.h"
_Static_assert(GARDEN_RADIO_PREFIX_V1_SIZE==44,"radio legacy prefix unchanged");
_Static_assert(GARDEN_RADIO_SCAN_V1_SIZE==56,"radio scan suffix target size");
_Static_assert(sizeof(garden_radio_scan_entry_v1)==37,"bounded copied AP entry");
_Static_assert(sizeof(garden_radio_scan_result_v1)==600,"bounded AP scan snapshot");
_Static_assert(WIFI_PREFIX_V1_SIZE==40,"Wi-Fi legacy prefix unchanged");
_Static_assert(WIFI_MANAGEMENT_V1_SIZE==56,"Wi-Fi management suffix target size");

_Static_assert(offsetof(garden_gpio_v1,wake_source)==56,"GPIO old prefix");
_Static_assert(TWATCH_PMU_TIMED_DEEP_SLEEP_SIZE==48,"PMU old timed prefix");
_Static_assert(TWATCH_MOTION_SAMPLE_SIZE==20,"motion sample prefix");

_Static_assert(offsetof(twatch_radio_api_v2,profile_info)==36,"LoRa v2 prefix unchanged");
_Static_assert(sizeof(twatch_lora_profile_info_v1)==16,"LoRa profile information ABI");
_Static_assert(offsetof(tw_hw_lora_v2,base)==0,"LoRa config v1 prefix unchanged");
_Static_assert(offsetof(tw_hw_lora_v2,allowed_profiles)==sizeof(tw_hw_lora_v1),"LoRa config profile suffix");

_Static_assert(TWATCH_MOTION_WAKE_SIZE==32,"motion wake prefix unchanged");
_Static_assert(TWATCH_MOTION_DIAGNOSTIC_SIZE==36,"motion diagnostic prefix unchanged");
_Static_assert(TWATCH_MOTION_TAP_SIZE==52,"motion observation suffix size");
_Static_assert(sizeof(twatch_tap_info_v1)==12,"motion info ABI");
_Static_assert(sizeof(twatch_tap_observation_v1)==12,"motion observation ABI");
