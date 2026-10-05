/* Persist through the actual application writer, including exact readback. */
#include <assert.h>
#include <stdio.h>
#include "points_writer.h"
static const char *directory;
static int32_t get(void *c,const char *key,void *buffer,uint32_t capacity,uint32_t *size) {
    (void)c;char path[1024];snprintf(path,sizeof(path),"%s/%s",directory,key);*size=0;
    FILE *f=fopen(path,"rb");if(!f)return RISC_KEY_VALUE_NOT_FOUND;
    *size=(uint32_t)fread(buffer,1,capacity,f);assert(!ferror(f));fclose(f);return 0;
}
static int32_t put(void *c,const char *key,const void *buffer,uint32_t size) {
    (void)c;char path[1024];snprintf(path,sizeof(path),"%s/%s",directory,key);
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(buffer,1,size,f)==size);assert(!fclose(f));return 0;
}
int main(int argc,char **argv) {
    assert(argc==3);directory=argv[1];const risc_key_value_v1 kv={1,sizeof(kv),NULL,get,put};
    points_writer writer={0};assert(points_writer_load(&writer,&kv)==ALARM_OK);
    points_config config={.revision=1};assert(alarm_calendar_seconds(2026,10,4,8,0,0,&config.created));
    config.points[0]=(points_item){.kind=POINTS_LUNCH,.enabled=1,.weekdays=127,.hour=13,.duration_minutes=30};
    if(!strcmp(argv[2],"flags"))config.points[0].notify_end=config.points[0].warn3=1;
    if(!strcmp(argv[2],"custom")) {
        config.points[0].kind=POINTS_CUSTOM_1;config.points[0].notify_end=config.points[0].warn3=1;
        points_meta meta={.revision=1};meta.custom[0].color=3;memcpy(meta.custom[0].name,"STUDY",6);
        assert(points_writer_save_meta(&writer,&kv,&meta)==ALARM_OK);
    }
    assert(points_writer_save(&writer,&kv,&config)==ALARM_OK);
    puts("Actual app writer: config committed and exact-readback verified");
}
