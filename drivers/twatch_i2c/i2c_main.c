/* Bit-banged system I2C. AXP2101, BMA423, PCF8563 and DRV2605 share GPIO10/11.
 * Do not load i2c-esp32s3-v2: that ELF owns the T5S3 pin pair. */
#define TWATCH_I2C_SDA TWATCH_PIN_I2C_SDA
#define TWATCH_I2C_SCL TWATCH_PIN_I2C_SCL
#define TWATCH_I2C_ID "twatch-i2c"
#define TWATCH_I2C_CAP RISC_I2C_BUS_CAPABILITY
#include "twatch_i2c_impl.h"
