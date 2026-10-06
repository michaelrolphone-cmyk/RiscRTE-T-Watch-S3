from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def extra_sources(driver):
 return [str(ROOT/'vendor/SensorLib/bosch/bma4xx'/n) for n in ('bma4.c','bma423.c','bma456h.c')] if driver=='twatch-imu' else []
