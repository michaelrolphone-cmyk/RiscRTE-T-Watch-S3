#!/usr/bin/env python3
"""Application policy and real driver timed suffixes; no target/device access."""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'dist/hybrid-sleep';out.mkdir(parents=True,exist_ok=True)
 exe=out/'policy'
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')],str(ROOT/'tests/hybrid_policy_test.c'),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
