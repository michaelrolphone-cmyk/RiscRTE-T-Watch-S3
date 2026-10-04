#!/usr/bin/env python3
"""Compare every supported RTC hour to independent host IANA ZoneInfo rules."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
data=subprocess.check_output([str(ROOT/'dist/crown-tests/display-time'),'oracle'])
source=timezone(timedelta(hours=8)); denver=ZoneInfo('America/Denver')
rtc=datetime(2000,1,1,0,37,49,tzinfo=source);end=datetime(2100,1,1,tzinfo=source)
pos=0
while rtc<end:
    local=rtc.astimezone(denver)
    expected=(bytes((1,local.year>>8,local.year&255,local.month,local.day,
                     (local.weekday()+1)%7,local.hour,local.minute,local.second))
              if local.year>=2000 else bytes(9))
    actual=data[pos:pos+9]
    assert actual==expected,(rtc.isoformat(),local.isoformat(),actual,expected)
    rtc+=timedelta(hours=1);pos+=9
assert pos==len(data)
policy=json.loads((ROOT/'apps/clock/time-policy.json').read_text())
assert policy['rtc_basis']['utc_offset_minutes']==480
assert policy['display_zone']=='America/Denver' and policy['writes_rtc'] is False
print(f'Denver conversion matches independent ZoneInfo for {pos//9:,} RTC hours (2000–2099)')
