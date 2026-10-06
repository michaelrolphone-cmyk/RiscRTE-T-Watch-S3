#!/usr/bin/env python3
import os,subprocess
from pathlib import Path
from imu_sources import extra_sources
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'dist/test-motion-wake';out.parent.mkdir(exist_ok=True)
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-unused-function','-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),str(ROOT/'tests/motion_wake_test.c'),*extra_sources('twatch-imu'),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
if __name__=='__main__':main()
