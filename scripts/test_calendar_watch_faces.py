#!/usr/bin/env python3
"""Build guarded calendar tests, exhaustively check civil dates, and export QA sheets."""
from pathlib import Path
import ctypes
import datetime as dt
import hashlib
import os
import subprocess
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist/calendar-native'
OUT.mkdir(parents=True, exist_ok=True)
CC = os.environ.get('CC', 'cc')
FLAGS = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
         *['-I' + str(ROOT / path) for path in ('sdk/app', 'sdk/driver', 'include', '.')]]
SOURCE = ROOT / 'tests/watch_faces_calendar_test.c'
subprocess.run([CC, *FLAGS, '-fsanitize=undefined', '-fno-sanitize-recover=all',
                str(SOURCE), '-o', str(OUT / 'test')], check=True)
subprocess.run([str(OUT / 'test'), str(OUT)], check=True)
subprocess.run([CC, *FLAGS, '-shared', '-fPIC', str(SOURCE), '-o', str(OUT / 'calendar-test.so')], check=True)
lib = ctypes.CDLL(str(OUT / 'calendar-test.so'))
lib.calendar_date.argtypes = [ctypes.c_uint] * 4
lib.calendar_date.restype = ctypes.c_uint
lib.calendar_shift.argtypes = [ctypes.c_uint] * 3 + [ctypes.c_int]
lib.calendar_shift.restype = ctypes.c_uint
lib.calendar_render_frame.argtypes = [ctypes.c_void_p] + [ctypes.c_uint] * 10
lib.calendar_render_frame.restype = None

# Every supported RTC date, independently checked against Python's calendar.
date = dt.date(2000, 1, 1)
end = dt.date(2100, 1, 1)
count = 0
while date < end:
    year, month, day = date.year, date.month, date.day
    assert lib.calendar_date(year, month, day, 0) == (date.weekday() + 1) % 7, date
    assert lib.calendar_date(year, month, day, 1) == date.timetuple().tm_yday, date
    assert lib.calendar_date(year, month, day, 2) == date.isocalendar().week, date
    next_month = dt.date(year + (month == 12), month % 12 + 1, 1)
    assert lib.calendar_date(year, month, day, 3) == (next_month - dt.timedelta(days=1)).day, date
    for shift in range(-3, 4):
        expected = date + dt.timedelta(days=shift)
        assert lib.calendar_shift(year, month, day, shift) == expected.year * 10000 + expected.month * 100 + expected.day, (date, shift)
    count += 1
    date += dt.timedelta(days=1)
print(f'{count:,} RTC dates: Gregorian weekday/day-of-year/month length/ISO week and all seven ribbon dates match datetime')

NAMES = ('GRID', 'RIBBON', 'YEAR', '24H', 'AGENDA', 'DATE', 'DOTS', 'PROGRESS')
def decode(raw):
    rgb = bytearray()
    for i in range(0, len(raw), 2):
        value = raw[i] | raw[i + 1] << 8
        rgb.extend(((value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31))
    return Image.frombytes('RGB', (240, 240), bytes(rgb))

def frame(face, date=(2026, 10, 4), time=(10, 42, 18), valid=1, battery=84, hour_24=0):
    out = ctypes.create_string_buffer(240 * 240 * 2)
    lib.calendar_render_frame(out, face, *date, *time, valid, battery, hour_24)
    return out.raw

def sheet(frames):
    result = Image.new('RGB', (1020, 540), 'black')
    draw = ImageDraw.Draw(result)
    for face, raw in enumerate(frames):
        result.paste(decode(raw), (face % 4 * 255, face // 4 * 270))
        draw.text((face % 4 * 255 + 80, face // 4 * 270 + 250), NAMES[face], fill='white')
    return result

frames = [frame(face) for face in range(8)]
for face, raw in enumerate(frames):
    decode(raw).save(OUT / f'face-{face}.png')
    assert raw == (OUT / f'face-{face}.rgb565').read_bytes(), face
    # Every face updates its primary time; stale RTC fields never leak when invalid.
    assert raw != frame(face, time=(11, 42, 18)), face
    assert frame(face, valid=0) == frame(face, date=(2047, 8, 21), time=(20, 7, 38), valid=0), face
    assert frame(face, battery=0) != frame(face, battery=100), face
assert frame(3, hour_24=0) != frame(3, hour_24=1)
assert frame(4, hour_24=0) != frame(4, hour_24=1)
assert frame(3, time=(10, 42, 18)) != frame(3, time=(10, 43, 18))
assert frame(4, time=(10, 42, 18)) != frame(4, time=(10, 43, 18))
assert frame(6, time=(10, 42, 18)) != frame(6, time=(10, 42, 19))
# Both source types explicitly remain separate: reference mock events are never compiled.
calendar_source = (ROOT / 'apps/clock/faces/calendar_collection.inc').read_text()
for fake in ('STANDUP', 'LUNCH', 'REVIEW', 'GYM'):
    assert fake not in calendar_source
assert '"CALENDAR"' in calendar_source and '"UNAVAILABLE"' in calendar_source
reference = ROOT / 'apps/clock/faces/reference/Calendar + Time Watch Faces — 8 × 240×240.html'
assert reference.stat().st_size == 14333
assert hashlib.sha256(reference.read_bytes()).hexdigest() == '698c0101c2439e052d8a88a30f3c940aa31ac6cbb9eb5a82e61a737c4fb14944'

native = sheet(frames)
native.save(OUT / 'native-faces.png')
sheet([frame(face, valid=0, battery=255) for face in range(8)]).save(OUT / 'unset-faces.png')
sheet([frame(face, date=(2024, 2, 29), time=(23, 59, 59)) for face in range(8)]).save(OUT / 'leap-day-faces.png')
sheet([frame(face, date=(2000, 1, 1), time=(0, 0, 0)) for face in range(8)]).save(OUT / 'earliest-date-faces.png')
sheet([frame(face, date=(2099, 12, 31), time=(23, 59, 59)) for face in range(8)]).save(OUT / 'latest-date-faces.png')
source_sheet = ROOT / 'dist/calendar-reference/reference-0.png'
if source_sheet.exists():
    comparison = Image.new('RGB', (2040, 580), 'black')
    comparison.paste(Image.open(source_sheet).convert('RGB'), (0, 40))
    comparison.paste(native, (1020, 40))
    draw = ImageDraw.Draw(comparison)
    draw.text((20, 12), 'OWNER HTML REFERENCE  |  2026-10-04 10:42:18.250', fill='white')
    draw.text((1040, 12), 'NATIVE RGB565  |  SAME RTC, SETTINGS 12H  |  AGENDA UNAVAILABLE', fill='white')
    comparison.save(OUT / 'before-after-calendar.png')
print('Calendar source integrity, unknown state, live time/ruler/dot animation, battery updates and visual sheets passed')
