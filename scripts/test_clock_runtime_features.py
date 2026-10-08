#!/usr/bin/env python3
"""Production Watch feature client and actual Runtime/CPU/dlopen, never hardware."""
import argparse,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--sanitize',action='store_true');a=p.parse_args();runtime=a.runtime.resolve()
 flags=['-g','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers']
 if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
 inc=['-I'+str(runtime/x) for x in ('src','sdk/app','sdk/driver','sdk/hardware','lib/ArduinoJson/src','test/drivers/stubs')]
 app_inc=['-I'+str(ROOT/x) for x in ('include','sdk/driver','sdk/app')]+inc
 env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'}
 def run(cmd):subprocess.run(list(map(str,cmd)),check=True,env=env,timeout=180)
 with tempfile.TemporaryDirectory(prefix='watch-runtime-features-') as tmp:
  out=Path(tmp)
  run(['cc','-std=c11',*flags,*app_inc,'-fno-pie','-no-pie',ROOT/'tests/clock_runtime_features_test.c','-o',out/'client']);run([out/'client'])
  for name,source in [('default',ROOT/'tests/runtime_features_runtime/app.c'),('deep',runtime/'test/fixtures/deep_sleep_provider.c')]:
   run(['cc','-std=c11',*flags,*(app_inc if name=='default' else inc),'-fPIC','-fvisibility=hidden','-shared',source,'-o',out/(name+'.elf')])
  sources=[runtime/x for x in ('src/bootstrap/Json.cpp','src/bootstrap/Board.cpp','src/bootstrap/Runtime.cpp','src/runtime/drivers/ProviderGraphV2.cpp','src/runtime/drivers/ProviderModuleV2.cpp','src/ports/esp32s3/CpuPort.cpp')]
  run(['c++','-std=c++17',*flags,*inc,'-rdynamic','-fno-pie','-no-pie',*sources,ROOT/'tests/runtime_features_runtime/host.cpp','-ldl','-o',out/'test']);run([out/'test',out])
if __name__=='__main__':main()
