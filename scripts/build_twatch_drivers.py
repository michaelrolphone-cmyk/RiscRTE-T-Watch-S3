
#!/usr/bin/env python3
"""Build T-Watch-S3 driver ELFs. Requires xtensa-esp32s3-elf-gcc."""
import shutil, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
cc = shutil.which("xtensa-esp32s3-elf-gcc")
if not cc:
    sys.exit("xtensa-esp32s3-elf-gcc not on PATH")
drivers = [
    ("twatch_gpio", "drivers/twatch_gpio/driver.c"),
    ("twatch_i2c", "drivers/twatch_i2c/i2c_main.c"),
    ("twatch_i2c_touch", "drivers/twatch_i2c_touch/i2c_main.c"),
    ("twatch_pmu", "drivers/twatch_pmu/driver.c"),
    ("twatch_panel", "drivers/twatch_panel/driver.c"),
    ("twatch_touch", "drivers/twatch_touch/driver.c"),
    ("twatch_imu", "drivers/twatch_imu/driver.c"),
    ("twatch_rtc", "drivers/twatch_rtc/driver.c"),
    ("twatch_haptic", "drivers/twatch_haptic/driver.c"),
    ("twatch_button", "drivers/twatch_button/driver.c"),
    ("twatch_lora", "drivers/twatch_lora/driver.c"),
    ("twatch_speaker", "drivers/twatch_speaker/driver.c"),
    ("twatch_mic", "drivers/twatch_mic/driver.c"),
]
for name, src in drivers:
    out = root / "dist" / name
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "driver.elf"
    cmd = [cc, "-shared", "-fPIC", "-fvisibility=hidden", "-nostdlib", "-mlongcalls",
           "-Os", "-ffreestanding", "-fno-builtin",
           f"-I{root / 'sdk' / 'driver'}", f"-I{root / 'include'}",
           f"-Wl,--version-script={root / 'exports.map'}",
           "-Wl,-soname,driver.elf", str(root / src), "-o", str(elf)]
    print(" ".join(cmd))
    subprocess.check_call(cmd)
    subprocess.check_call(["xtensa-esp32s3-elf-nm", "-D", str(elf)])
print("built", len(drivers), "ELFs under dist/")
