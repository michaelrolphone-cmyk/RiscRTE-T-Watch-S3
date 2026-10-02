#pragma once
/* LILYGO T-Watch-S3 (ASIN B0GPQ3TGLM), not the Plus.
 * Pins from LilyGoLib docs/hardware/lilygo-t-watch-s3.md and
 * arduino-esp32 variants/lilygo_twatch_s3/pins_arduino.h.
 * This tree has not been run on a watch. */
#define TWATCH_PIN_I2C_SDA 10u
#define TWATCH_PIN_I2C_SCL 11u
#define TWATCH_PIN_TOUCH_SDA 39u
#define TWATCH_PIN_TOUCH_SCL 40u
#define TWATCH_PIN_TOUCH_INT 16u
#define TWATCH_PIN_RTC_INT 17u
#define TWATCH_PIN_IMU_INT 14u
#define TWATCH_PIN_PMU_INT 21u
#define TWATCH_PIN_I2S_BCLK 48u
#define TWATCH_PIN_I2S_WCLK 15u
#define TWATCH_PIN_I2S_DOUT 46u
#define TWATCH_PIN_LORA_SCK 3u
#define TWATCH_PIN_LORA_MISO 4u
#define TWATCH_PIN_LORA_MOSI 1u
#define TWATCH_PIN_LORA_RST 8u
#define TWATCH_PIN_LORA_BUSY 7u
#define TWATCH_PIN_LORA_CS 5u
#define TWATCH_PIN_LORA_IRQ 9u
#define TWATCH_PIN_LCD_CS 12u
#define TWATCH_PIN_LCD_MOSI 13u
#define TWATCH_PIN_LCD_SCK 18u
#define TWATCH_PIN_LCD_DC 38u
#define TWATCH_PIN_LCD_BL 45u
#define TWATCH_PIN_MIC_SCK 44u
#define TWATCH_PIN_MIC_DAT 47u
#define TWATCH_PIN_IR 2u
#define TWATCH_PIN_BOOT 0u
#define TWATCH_I2C_AXP2101 0x34u
#define TWATCH_I2C_BMA423 0x19u
#define TWATCH_I2C_PCF8563 0x51u
#define TWATCH_I2C_DRV2605 0x5Au
#define TWATCH_I2C_FT6336 0x38u
#define TWATCH_LCD_W 240u
#define TWATCH_LCD_H 240u
#define TWATCH_BATTERY_MAH 470u
/* XPowersLib AXP2101 charge-current code. 4 is 100 mA. 5 is 125 mA.
 * LilyGO requires below 130 mA. This package hardcodes 100 mA. */
#define TWATCH_AXP_CHG_100MA 4u
