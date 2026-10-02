
#!/usr/bin/env python3
"""Host check: manifests, exported symbol, and exclusive pin claims."""
import json, re, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
pins = {
    "TWATCH_PIN_I2C_SDA": 10, "TWATCH_PIN_I2C_SCL": 11,
    "TWATCH_PIN_TOUCH_SDA": 39, "TWATCH_PIN_TOUCH_SCL": 40,
    "TWATCH_PIN_TOUCH_INT": 16, "TWATCH_PIN_PMU_INT": 21,
    "TWATCH_PIN_I2S_BCLK": 48, "TWATCH_PIN_I2S_WCLK": 15, "TWATCH_PIN_I2S_DOUT": 46,
    "TWATCH_PIN_LORA_SCK": 3, "TWATCH_PIN_LORA_MISO": 4, "TWATCH_PIN_LORA_MOSI": 1,
    "TWATCH_PIN_LORA_RST": 8, "TWATCH_PIN_LORA_BUSY": 7, "TWATCH_PIN_LORA_CS": 5,
    "TWATCH_PIN_LCD_CS": 12, "TWATCH_PIN_LCD_MOSI": 13, "TWATCH_PIN_LCD_SCK": 18,
    "TWATCH_PIN_LCD_DC": 38, "TWATCH_PIN_LCD_BL": 45, "TWATCH_PIN_BOOT": 0,
}
owners = {}
errors = []
for manifest in sorted((root / "drivers").glob("*/manifest.json")):
    data = json.loads(manifest.read_text())
    for key in ("id", "version", "driver_abi", "provides", "product_asin"):
        if key not in data:
            errors.append(f"{manifest}: missing {key}")
    if data.get("driver_abi") != 2 or data.get("product_asin") != "B0GPQ3TGLM":
        errors.append(f"{manifest}: abi/asin")
    if data.get("status") != "derived-unverified-on-device":
        errors.append(f"{manifest}: status must stay unverified until a watch run")
    sources = list(manifest.parent.glob("*.c")) + list(manifest.parent.glob("*.h"))
    text = "\n".join(p.read_text() for p in sources)
    if "twatch_i2c_impl.h" in text:
        text += (root / "include" / "twatch_i2c_impl.h").read_text()
    if "t5_driver_get" not in text:
        errors.append(f"{manifest.parent}: no t5_driver_get")
    if "TWATCH_AXP_CHG" in text and "125" in text and "hardcoded" not in text:
        errors.append("charge current must not be raised in source")
    for name, pin in pins.items():
        if name in text:
            owners.setdefault(pin, set()).add(manifest.parent.name)
for pin, who in owners.items():
    if len(who) > 1:
        errors.append(f"GPIO {pin} claimed by {sorted(who)}")
if "4u" not in (root / "include" / "twatch_pins.h").read_text():
    errors.append("100 mA charge code missing")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"ok {len(list((root/'drivers').glob('*/manifest.json')))} drivers, pins exclusive")
