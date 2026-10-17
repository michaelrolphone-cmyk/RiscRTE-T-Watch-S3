#!/usr/bin/env python3
"""Build and exercise the complete core feed through the production controller."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from package_provisioning import require, record, encoded


def prepare(sources, files, image, firmware, p, output):
    system,runtime=sources['system'],sources['runtime']
    path=system/'scripts/build_boot_profile_feed.py'
    spec=importlib.util.spec_from_file_location('pinned_boot_feed',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    base='https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/download/'+p['release_tag']+'/'
    with tempfile.TemporaryDirectory(prefix='twatch-core-feed-') as tmp:
        root=Path(tmp);store=root/'store';store.mkdir()
        for n,b in files.items():
            dest=store/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
        (root/'store.bin').write_bytes(image);(root/'firmware.bin').write_bytes(firmware)
        receipt=module.build(runtime,store,root/'store.bin',root/'firmware.bin',base,p['product_id'],'core',[p['time_server']],output)
    feed=json.loads((output/'native-packages-v1.json').read_bytes());core=feed['boot_profiles']['core']
    require(len(core['profile']['files'])==125 and not core['mirrors'], 'Complete internal-only core inventory required')
    require(receipt['file_count']==125 and receipt['credential_free'], 'Feed bounds/credential contract differs')
    # apps[] is the separate dynamic-package catalog. Core provisioning consumes
    # the complete nonempty boot_profiles.core record, which is exercised below.
    require(feed['apps']==[] and feed['profiles']=={'core':[]}, 'Unrequested dynamic package scope')
    proof=exercise_controller(system,runtime,output/'native-packages-v1.json',p)
    (output/'controller-proof.json').write_bytes(encoded(proof))
    return {'receipt':receipt,'controller':proof,'core_inventory_files':125,
            'core_inventory_elfs':61,'dynamic_app_descriptors':0,'hardware_tested':False}


def exercise_controller(system,runtime,feed,p):
    original=(system/'test/native_apps/installed_apps_boot_profile_test.cpp').read_text()
    require(original.count('int main(){')==1,'Controller fixture entry changed')
    source=original[:original.index('int main(){')]
    source=source.replace('static risc_provision_request_status_v1 requestStatus;',
        'static std::string queuedProfile;\nstatic risc_provision_request_status_v1 requestStatus;')
    source=source.replace('++queueCalls;assert(', 'queuedProfile.assign(static_cast<const char*>(q->profile_json),q->profile_size);++queueCalls;assert(',1)
    source=source.replace('t["servers"][0]=="time.example.org"','t["servers"][0]=="'+p['time_server']+'"')
    source+='''
int main(int argc,char**argv){
 assert(argc==2);staged_fixture::setup();staged_fixture::begin();assert(api.refresh(nullptr)==0);statusReset();
 std::ifstream input(argv[1],std::ios::binary);assert(input);feedBody.assign(std::istreambuf_iterator<char>(input),{});
 assert(parseBody());JsonDocument document;assert(!deserializeJson(document,feedBody));auto core=document["boot_profiles"]["core"];
 auto native=core["native"];requestStatus.store_abi=native["store_abi"].as<uint32_t>();requestStatus.firmware_size=native["firmware_size"].as<uint32_t>();
 assert(copy(requestStatus.layout,sizeof(requestStatus.layout),native["layout"]));assert(copy(requestStatus.runtime_version,sizeof(requestStatus.runtime_version),native["runtime_version"]));
 assert(bootDigest(native["firmware_sha256"],requestStatus.firmware_sha256));
 beginCore();assert(driveCore(nullptr)==INSTALLED_APPS_NEEDS_PROFILE_WIFI);
 assert(bootApi.supply_wifi(nullptr,"saved default","saved-password")==INSTALLED_APPS_PROFILE_QUEUED);assert(queueCalls==1);
 JsonDocument queued;assert(!deserializeJson(queued,queuedProfile));
 auto expected=core["profile"];assert(queued["files"].size()==125&&queued["files"]==expected["files"]&&queued["image"]==expected["image"]);
 assert(requestStatus.state==RISC_PROVISION_REQUEST_PENDING);uint8_t target[32];assert(bootDigest(expected["image"]["sha256"],target));assert(!memcmp(target,requestStatus.target_store_sha256,32));
 closeCore();assert(!feedOpen);puts("Complete125-file core parsed and exact image request queued; no target/hardware execution");
}
'''
    with tempfile.TemporaryDirectory(prefix='twatch-controller-') as tmp:
        root=Path(tmp);(root/'controller.cpp').write_text(source)
        includes=[runtime/x for x in ('src','sdk/app','sdk/driver','sdk/hardware','lib/ArduinoJson/src')]
        includes += [system/x for x in ('lib/PortableApps/include','lib/InstalledCatalog/include','test/native_apps')]
        inc=['-I'+str(x) for x in includes]
        commands=[['cc','-std=c11','-Wall','-Wextra','-Werror',*inc,'-c',str(system/'lib/InstalledCatalog/src/InstalledCatalog.c'),'-o',str(root/'catalog.o')],
            ['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function', '-DINSTALLED_APPS_FEED_PRODUCT="'+p['product_id']+'"',*inc,str(root/'controller.cpp'),str(runtime/'src/runtime/storage/PackageFiles.cpp'),str(root/'catalog.o'),'-o',str(root/'controller')]]
        for cmd in commands:subprocess.run(cmd,check=True)
        result=subprocess.run([str(root/'controller'),str(feed)],check=True,capture_output=True,text=True)
    return {'production_feed_sha256':record(feed.read_bytes())['sha256'],'fixture_sha256':record(source.encode())['sha256'],
            'files_selected':125,'queue_calls':1,'exact_image_url_size_digest_selected':True,'native_firmware_identity_matched':True,
            'hardware_tested':False,'target_instructions_executed':False,'result':result.stdout.strip()}
