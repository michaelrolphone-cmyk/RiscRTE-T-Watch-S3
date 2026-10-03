#!/usr/bin/env python3
from pathlib import Path
import os,subprocess
root=Path(__file__).resolve().parents[1];out=root/'dist/test-navigation'
subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=undefined',*['-I'+str(root/p) for p in ('sdk/driver','include','.')],str(root/'tests/navigation_test.c'),'-o',str(out)],check=True)
subprocess.run([str(out)],check=True)
