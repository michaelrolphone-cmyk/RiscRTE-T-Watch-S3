/* FT6336U is on its own pair, Wire1 in the LilyGO pin map. Separate capability
 * so the system bus and the touch bus cannot be bound to the same provider. */
#define TWATCH_I2C_SDA TWATCH_PIN_TOUCH_SDA
#define TWATCH_I2C_SCL TWATCH_PIN_TOUCH_SCL
#define TWATCH_I2C_ID "twatch-i2c-touch"
#define TWATCH_I2C_CAP "i2c.bus.touch"
#include "twatch_i2c_impl.h"
