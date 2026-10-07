/* Same actual SleepDiagnostics.cpp + existing Runtime Arduino USB shim linkage
 * as hid_runtime_diagnostics.cpp. This test never opens a hardware serial port. */
#include "ports/esp32s3/SleepDiagnostics.h"
#include <Arduino.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>

static const char *const expected[]={
    "SDR app enter",
    "SDR acquire begin",
    "SDR acquire ok=1",
    "SDR capture rc=4 pairs=256",
    "SDR detail stage=4 rc=4 ready=0 cleanup=1",
    "SDR dump clk=00000040 start=44 end=44 cycles=2400010",
    "SDR cleanup ok=1",
    "SDR app exit"
};
static void verify_lines(const std::string& output,bool replay,unsigned first) {
    size_t after=0;
    for (unsigned i=first;i<sizeof(expected)/sizeof(*expected);++i) {
        const std::string line=(replay?std::string("text="):std::string())+expected[i]+"\n";
        const size_t at=output.find(line,after);
        assert(at!=std::string::npos);after=at+line.size();
        assert(output.find(line,after)==std::string::npos);
    }
}
static void save(const char *directory,const char *name,const std::string& output) {
    std::ofstream file(std::string(directory)+"/"+name);assert(file.good());file<<output;file.close();assert(file.good());
}
static void replay(void) {
    Serial.input="diag\n";
    for (unsigned i=0;i<200;++i) RiscDiagnostics::poll();
    assert(Serial.input.empty());
    assert(Serial.output.find("RTE_DIAG end\n")!=std::string::npos);
}
extern "C" void waterfall_serial_start(const char *mode) {
    Serial.connected=std::strcmp(mode,"absent")!=0;
    Serial.space=std::strcmp(mode,"full")==0?0:256;
    RiscDiagnostics::start();assert(Serial.timeout==0);
}
extern "C" void waterfall_serial_line(const char *line) { RiscDiagnostics::line(line); }
extern "C" void waterfall_serial_finish(const char *directory,const char *mode) {
    const bool live=std::strcmp(mode,"connected")==0;
    if (live) { assert(Serial.writes==8);verify_lines(Serial.output,false,0); }
    else { assert(Serial.writes==0 && Serial.output.empty()); }
    save(directory,"live-usb.txt",Serial.output);

    /* app_main has returned and both grants are released. Exercise an actual
     * disconnect/reconnect and one-byte TX capacity against journal replay. */
    Serial.connected=false;RiscDiagnostics::poll();
    Serial.connected=true;Serial.space=1;Serial.output.clear();
    Serial.input="diag\n";
    for (unsigned i=0;i<1500;++i) RiscDiagnostics::poll();
    assert(Serial.output.find("RTE_DIAG begin schema=1 events=1 messages=8 event_lost=0 message_lost=0\n")==0);
    assert(Serial.output.find("RTE_DIAG end\n")!=std::string::npos);
    verify_lines(Serial.output,true,0);save(directory,"post-return-replay.txt",Serial.output);

    /* The main.cpp idle marker is logged if runtime.run itself returns. Its
     * ninth message evicts app-enter, leaving the failure detail and cleanup. */
    Serial.space=256;Serial.output.clear();
    waterfall_serial_line("RTE_BOOT state=idle reason=app-returned");
    Serial.output.clear();replay();verify_lines(Serial.output,true,1);
    assert(Serial.output.find("text=SDR app enter\n")==std::string::npos);
    assert(Serial.output.find("message_lost=1\n")!=std::string::npos);
    assert(Serial.output.find("text=RTE_BOOT state=idle reason=app-returned\n")!=std::string::npos);
    save(directory,"post-idle-replay.txt",Serial.output);
    std::puts("Runtime logger: live/absent/full USB, post-return reconnect, 1-byte replay, and idle marker PASS");
}
