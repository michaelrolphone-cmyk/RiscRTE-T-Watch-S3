#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "twatch_support.h"
#include "twatch_caps.h"
extern const uint8_t bma423_config_file[],bma456h_config_file[];
static uint8_t regs[256],feature[128],silicon;
static unsigned operations,fail_at,uploaded,reset_count,delay_total;
static unsigned force_feature_index,force_feature_mask,force_reg_index,force_reg_mask;
static unsigned final_read_index,final_read_xor;
static bool lose_sensitivity_write,alter_reserved_word;
static bool initialization_event,initialization_latched,fail_reset_always;
static const uint16_t tap_defaults[12]={6,9,130,6,6,8,80,0,0x44c,2,3,0};
static uint64_t fake_us,last_write_us;static bool write_wait,short_wait,clock_stalled;
static bool bus_live,pin_live,enrolled,held_line,fail_enroll,fail_withdraw,fail_gpio,wrong_status;
static tw_hw_i2c_device_v1 config_fixture;
static bool claim_bus(void*c,uint8_t address,uint64_t*out){(void)c;assert(address==25&&!bus_live);bus_live=true;*out=19;return true;}
static bool release_bus(void*c,uint64_t t){(void)c;assert(t==19);if(enrolled)return false;bus_live=false;return true;}
static bool transact(void*c,uint64_t t,const uint8_t*write,size_t wn,uint8_t*read,size_t rn,uint32_t ms){
 (void)c;assert(t==19&&bus_live&&wn&&ms&&wn<=33);
 /* All production raw/vendor writes, including uncertain failures, need the
  * Bosch suspend-mode450us minimum before the next bus access. Millisecond
  * clock resolution makes1ms the smallest observable compliant delay. */
 if(write_wait)assert(fake_us-last_write_us>=450);
 if(wn>1){write_wait=true;last_write_us=fake_us;}
 if(++operations==fail_at)return false;
 const uint8_t*p=write;uint8_t*q=read;unsigned reg=p[0];
 if(fail_reset_always && reg==0x7e && wn==2 && p[1]==0xb6)return false;
 if(rn){assert(wn==1);if(reg==0x5e){unsigned offset=2u*((unsigned)regs[0x5b]+((unsigned)regs[0x5c]<<4));assert(offset>=6144&&offset-6144+rn<=sizeof(feature));memcpy(q,feature+offset-6144,rn);}else{assert(reg+rn<=256);memcpy(q,regs+reg,rn);
  if(final_read_xor&&regs[0x56]==(silicon==0x13?0x20:1)&&reg<=final_read_index&&final_read_index<reg+rn)q[final_read_index-reg]^=(uint8_t)final_read_xor;
  if(reg==0x1c){regs[0x1c]=regs[0x1d]=0;initialization_latched=false;}}return true;}
 if(reg==0x7e && wn==2 && p[1]==0xb6){bool acknowledged=(regs[0x7c]&1)&&!(regs[0x7d]&5);memset(regs,0,sizeof(regs));memset(feature,0,sizeof(feature));regs[0]=silicon;regs[0x7c]=3;initialization_latched=false;uploaded=0;reset_count++;return acknowledged;}
 if(reg==0x5e){unsigned offset=2u*((unsigned)regs[0x5b]+((unsigned)regs[0x5c]<<4));if(!regs[0x59]){assert(offset==uploaded && wn==33);assert(!memcmp(p+1,(silicon==0x13?bma423_config_file:bma456h_config_file)+offset,wn-1));uploaded+=wn-1;}else{assert(offset>=6144&&offset-6144+wn-1<=sizeof(feature));memcpy(feature+offset-6144,p+1,wn-1);
  if(force_feature_mask)feature[force_feature_index]|=(uint8_t)force_feature_mask;
  if(lose_sensitivity_write){if(silicon==0x13)feature[0x38]=(uint8_t)((feature[0x38]&~0x0e)|14);else{feature[0x3e]=9;feature[0x3f]=0;}}
  if(alter_reserved_word&&silicon==0x16&&offset-6144<=0x3c&&0x3c<offset-6144+wn-1)feature[0x3c]^=1;
 }return true;}
 assert(reg+wn-1<=256);memcpy(regs+reg,p+1,wn-1);
 if(reg==0x56 && initialization_event)initialization_latched=true;
 if(force_reg_mask&&reg<=force_reg_index&&force_reg_index<reg+wn-1)regs[force_reg_index]|=(uint8_t)force_reg_mask;
 if(reg==0x59 && p[1]==1){assert(uploaded==6144);regs[0x2a]=wrong_status?0:1;regs[0x5b]=0;regs[0x5c]=0xc0;
  /* Documented feature defaults are not all zero. Seed real tap parameters;
   * reserved words and timing must survive a sensitivity-only update. */
  if(silicon==0x13)feature[0x38]=6; /* default sensitivity 3 */
  else for(unsigned i=0;i<12;i++){feature[0x3c+2*i]=(uint8_t)tap_defaults[i];feature[0x3d+2*i]=(uint8_t)(tap_defaults[i]>>8);}
 }
 return true;
}
static bool claim_pin(void*c,uint8_t pin,uint32_t flags,uint64_t*out){(void)c;assert(pin==14&&!pin_live&&flags==RISC_GPIO_INPUT);pin_live=true;*out=23;return true;}
static bool release_pin(void*c,uint64_t t){(void)c;assert(t==23);if(enrolled)return false;pin_live=false;return true;}
static bool gpio_write(void*c,uint64_t t,bool high){(void)c;(void)t;(void)high;return false;}
static bool gpio_read(void*c,uint64_t t,bool*out){(void)c;assert(t==23&&pin_live);*out=held_line||initialization_latched;return !fail_gpio;}
static int32_t enroll(void*c,uint64_t t,bool high,uint32_t mode){(void)c;assert(t==23&&high);if(mode){assert(mode==3);if(fail_enroll)return -7;enrolled=true;}else{if(fail_withdraw)return -5;enrolled=false;}return 0;}
static uint64_t now(void*c){(void)c;return fake_us/1000;}
static void sleep_ms(void*c,uint32_t ms){(void)c;assert(ms<1000);delay_total+=ms;if(!clock_stalled){fake_us+=(uint64_t)ms*1000-(short_wait?999:0);short_wait=false;}}
static const risc_i2c_bus_api_v1 bus_api={1,sizeof(bus_api),NULL,claim_bus,transact,release_bus};
static risc_gpio_bank_api_v1 gpio={.api_version=1,.struct_size=sizeof(gpio),.claim=claim_pin,.write=gpio_write,.read=gpio_read,.release=release_pin,.wake_source=enroll};
static const risc_platform_clock_api_v1 clock_port={1,sizeof(clock_port),NULL,now,sleep_ms};
#include "../drivers/twatch_imu/driver.c"
static bool start_fixture(void){
 const risc_hardware_device_v1 h={1,sizeof(h),7,"bosch,bma4xx","unspecified","peripheral.i2c",1,sizeof(config_fixture),&config_fixture};
 risc_provider_dependency_v1 deps[]={{"hardware.device",1,&h},{"i2c.bus",1,&bus_api},{"gpio.bank",1,&gpio},{"platform.clock",1,&clock_port}};
 return start(deps,4);
}
/* CPU Deep sleep resets provider RAM and ownership, not the powered sensor. */
static void fresh_cpu(void){
 bus=NULL;clock_api=NULL;claim=irq_claim=0;gpio_api=NULL;started=false;config=NULL;chip=0;
 sensor=(struct bma4_dev){0};wake_enrolled=wake_changed=wake_prepared=io_failed=observe_active=false;
 wake_value=0;memset(wake_saved,0,sizeof(wake_saved));wake_failure_code=0;
 bus_live=pin_live=enrolled=false;operations=0;
}
static void begin(uint8_t id){
 silicon=id;write_wait=short_wait=clock_stalled=false;fake_us=last_write_us=0;memset(regs,0,sizeof(regs));regs[0]=id;regs[0x7c]=3;operations=fail_at=uploaded=reset_count=delay_total=0;held_line=fail_enroll=fail_withdraw=fail_gpio=wrong_status=false;
 force_feature_index=force_feature_mask=force_reg_index=force_reg_mask=0;lose_sensitivity_write=alter_reserved_word=false;
 final_read_index=final_read_xor=0;
 initialization_event=initialization_latched=fail_reset_always=false;
 config_fixture=(tw_hw_i2c_device_v1){.struct_size=sizeof(config_fixture),.bus={.struct_size=sizeof(risc_hw_bus_v1),.instance_id=101,.kind=RISC_HW_BUS_I2C,.controller=0,.frequency_hz=100000,.sclk=-1,.mosi=-1,.miso=-1,.sda=10,.scl=11},.address=25,.irq=14,.irq_active_high=1,.irq_pull_up=0,.chip_id=id};
 assert(start_fixture());operations=0;
}
static void restored(void){assert(!enrolled&&!wake_changed&&!wake_prepared&&regs[0x40]==0xa8&&regs[0x41]==1&&regs[0x7c]==0&&regs[0x7d]==4);}
int main(void){
 for(unsigned variant=0;variant<2;variant++){uint8_t id=variant?0x16:0x13;
  /* Deep-wake reactivation must reset the still-powered detector safely.
   * Repeat with latched wake status and preserve the sensor across each CPU
   * reset. A cold fixture alone cannot catch this entry path. */
  begin(id);
  for(unsigned cycle=0;cycle<5;cycle++){
   assert(prepare_wake(NULL));assert(regs[0x7d]&4);regs[0x1c]=variant?1:0x20;initialization_latched=true;
   bool wake_line=false;assert(gpio_read(NULL,irq_claim,&wake_line) && wake_line);
   fresh_cpu();assert(initialization_latched && regs[0x1c]);assert(start_fixture());
   assert(!enrolled && started && regs[0x7d]==4 && !regs[0x1c]);
   assert(gpio_read(NULL,irq_claim,&wake_line) && !wake_line);
  }
  unsigned startup_count=operations;assert(quiesce());
  /* Startup must fail closed on every transport error, without accepting a
   * failed reset ACK. A later explicit activation may retry after cleanup. */
  for(unsigned failure=1;failure<=startup_count;failure++){
   begin(id);assert(prepare_wake(NULL));fresh_cpu();fail_at=failure;
   assert(!start_fixture() && !started && !bus_live && !pin_live && !enrolled);
   fail_at=0;assert(start_fixture());assert(quiesce());
  }
  /* CPU-only restart from ordinary sampling (APS off) has the same contract. */
  begin(id);assert(regs[0x7c]==0 && regs[0x7d]==4);fresh_cpu();assert(start_fixture());assert(quiesce());
  begin(id);assert(prepare_wake(NULL));fresh_cpu();fail_reset_always=true;
  assert(!start_fixture() && !started && !bus_live && !pin_live);
  fail_reset_always=false;assert(start_fixture());assert(quiesce());
  begin(id);fresh_cpu();clock_stalled=true;
  assert(!start_fixture() && operations==1 && !started && !bus_live && !pin_live);
  clock_stalled=false;assert(start_fixture());assert(quiesce());
  /* Verify the configured identity before any new power-state writes. */
  begin(id);fresh_cpu();regs[0]=variant?0x13:0x16;unsigned resets=reset_count;
  assert(!start_fixture() && operations==1 && reset_count==resets && !bus_live && !pin_live);
  /* The old running-state reset can physically succeed while losing ACK. */
  begin(id);sensor=(struct bma4_dev){.intf=BMA4_I2C_INTF,.bus_read=sensor_read,.bus_write=sensor_write,.delay_us=sensor_delay,.read_write_len=32};io_failed=false;
  assert(bma4_soft_reset(&sensor)==BMA4_E_COM_FAIL && io_failed && regs[0x7c]==3 && !regs[0x7d] && !regs[0x41]);
  io_failed=false;assert(quiesce());
  begin(id);assert(prepare_wake(NULL));unsigned count=operations;assert(enrolled&&wake_prepared&&uploaded==6144&&regs[0x55]==1&&regs[0x53]==0x0a&&regs[0x56]==(variant?1:0x20)&&!regs[0x57]&&!regs[0x58]);
  if(variant){assert(!regs[0x28]&&regs[0x29]==0x20);for(unsigned i=0;i<12;i++)assert(((uint16_t)feature[0x3c+2*i]|((uint16_t)feature[0x3d+2*i]<<8))==(i==1?12:tap_defaults[i]));}
  else assert((feature[0x38]&0x1f)==0x07&&!feature[0x3a]&&!(feature[0x37]&0x38)&&!(feature[3]&0xe0));
  unsigned before=operations;assert(prepare_wake(NULL)&&operations==before);bool pending=true;assert(wake_pending(NULL,&pending)&&!pending);held_line=true;assert(wake_pending(NULL,&pending)&&pending&&operations==before);held_line=false;
  assert(resume_wake(NULL));restored();before=operations;assert(resume_wake(NULL)&&operations==before);assert(quiesce());
  begin(id);initialization_event=true;assert(prepare_wake(NULL));assert(!initialization_latched);
  initialization_latched=true;bool actual=false;before=operations;
  assert(wake_pending(NULL,&actual)&&actual&&initialization_latched&&operations==before);
  assert(resume_wake(NULL));restored();assert(quiesce());
  /* Every physical transfer can fail; bulk firmware loops must not hide one. */
  for(unsigned failure=1;failure<=count;failure++){begin(id);fail_at=failure;assert(!prepare_wake(NULL));assert(operations==failure);fail_at=0;assert(resume_wake(NULL));restored();assert(prepare_wake(NULL));assert(resume_wake(NULL));restored();assert(quiesce());}
  begin(id);assert(prepare_wake(NULL));operations=0;assert(resume_wake(NULL));unsigned cleanup_count=operations;assert(quiesce());
  for(unsigned failure=1;failure<=cleanup_count;failure++){begin(id);assert(prepare_wake(NULL));operations=0;fail_at=failure;assert(!resume_wake(NULL)&&enrolled);fail_at=0;assert(resume_wake(NULL));restored();assert(quiesce());}
  begin(id);held_line=true;assert(!prepare_wake(NULL)&&enrolled);assert(resume_wake(NULL));restored();assert(quiesce());
  begin(id);fail_reset_always=true;assert(!prepare_wake(NULL)&&enrolled&&wake_error(NULL)==742);assert(!resume_wake(NULL)&&enrolled);fail_reset_always=false;assert(resume_wake(NULL));restored();assert(quiesce());
  begin(id);wrong_status=true;assert(!prepare_wake(NULL)&&enrolled);wrong_status=false;assert(resume_wake(NULL));restored();assert(quiesce());
  begin(id);fail_gpio=true;assert(!prepare_wake(NULL));fail_gpio=false;assert(resume_wake(NULL));restored();assert(quiesce());
  begin(id);fail_enroll=true;assert(!prepare_wake(NULL)&&!operations&&!enrolled);fail_enroll=false;assert(quiesce());
  begin(id);assert(prepare_wake(NULL));fail_withdraw=true;assert(!resume_wake(NULL)&&enrolled&&!wake_changed);assert(!quiesce()&&bus_live&&pin_live);fail_withdraw=false;assert(resume_wake(NULL));restored();assert(quiesce());
  begin(id);short_wait=true;assert(prepare_wake(NULL));short_wait=true;assert(resume_wake(NULL));restored();assert(quiesce());
  begin(id);clock_stalled=true;assert(!prepare_wake(NULL)&&enrolled);assert(!resume_wake(NULL)&&enrolled);clock_stalled=false;assert(resume_wake(NULL));restored();assert(quiesce());
  begin(id);lose_sensitivity_write=true;assert(!prepare_wake(NULL)&&enrolled);lose_sensitivity_write=false;assert(resume_wake(NULL));restored();assert(prepare_wake(NULL));assert(resume_wake(NULL));assert(quiesce());
  if(variant){
   begin(id);alter_reserved_word=true;assert(!prepare_wake(NULL)&&enrolled);alter_reserved_word=false;assert(resume_wake(NULL));restored();assert(quiesce());
   for(unsigned i=0;i<16;i++)if(i!=13){begin(id);force_reg_index=0x28+i/8;force_reg_mask=1u<<(i%8);assert(!prepare_wake(NULL)&&enrolled);force_reg_mask=0;assert(resume_wake(NULL));restored();assert(quiesce());}
  }else{
   const unsigned indices[]={0x3a,0x37,0x37,0x37,3,3,3,0x38};const unsigned bits[]={1,8,16,32,32,64,128,16};
   for(unsigned i=0;i<sizeof(indices)/sizeof(indices[0]);i++){begin(id);force_feature_index=indices[i];force_feature_mask=bits[i];assert(!prepare_wake(NULL)&&enrolled);force_feature_mask=0;assert(resume_wake(NULL));restored();assert(quiesce());}
  }
  for(unsigned i=0;i<8;i++)if((1u<<i)!=(variant?1u:32u)){begin(id);force_reg_index=0x56;force_reg_mask=1u<<i;assert(!prepare_wake(NULL)&&enrolled);force_reg_mask=0;assert(resume_wake(NULL));restored();assert(quiesce());}
  const unsigned read_indices[]={0x57,0x58,0x53,0x53,0x53,0x53,0x55};const unsigned read_bits[]={1,128,2,8,4,16,1};
  for(unsigned i=0;i<sizeof(read_indices)/sizeof(read_indices[0]);i++){begin(id);final_read_index=read_indices[i];final_read_xor=read_bits[i];assert(!prepare_wake(NULL)&&enrolled);final_read_xor=0;assert(resume_wake(NULL));restored();assert(prepare_wake(NULL));assert(resume_wake(NULL));assert(quiesce());}
  /* Every encoded setting uses actual vendor semantics and readback; the
   * observation suffix never acknowledges an ordinary prepared sleep. */
  for(unsigned value=0;value<=(variant?15u:7u);value++){
   begin(id);twatch_tap_info_v1 info={.struct_size=sizeof(info)};
   assert(tap_info(NULL,&info) && info.profile==(variant?2u:1u) && info.minimum==0 && info.maximum==(variant?15u:7u));
   assert(!tap_configure(NULL,(uint16_t)(info.maximum+1)) && !operations);
   assert(tap_configure(NULL,(uint16_t)value) && prepare_wake(NULL));
   assert((variant?(unsigned)feature[0x3e]:(unsigned)((feature[0x38]&14)>>1))==value);
   twatch_tap_observation_v1 sample={.struct_size=sizeof(sample)};
   assert(!tap_observe(NULL,&sample) && !tap_configure(NULL,0));
   assert(resume_wake(NULL));restored();
   assert(tap_observe_begin(NULL,(uint16_t)value));
   regs[0x1c]=variant?1:0x20;regs[3]=0x80;
   regs[0x12]=0;regs[0x13]=0x40;regs[0x14]=0;regs[0x15]=0xc0;regs[0x16]=0;regs[0x17]=0x20;
   assert(tap_observe(NULL,&sample) && sample.double_tap && sample.sample_ready &&
       sample.x_mg==1000 && sample.y_mg==-1000 && sample.z_mg==500 && !regs[0x1c]);
   regs[3]=0;assert(tap_observe(NULL,&sample) && !sample.double_tap && !sample.sample_ready && !sample.x_mg);
   assert(resume_wake(NULL));restored();assert(!observe_active && !tap_observe(NULL,&sample));assert(quiesce());
  }
  begin(id);assert(tap_observe_begin(NULL,0));regs[3]=0x80;
  twatch_tap_observation_v1 sample={.struct_size=sizeof(sample)};
  operations=0;assert(tap_observe(NULL,&sample));unsigned observed_transfers=operations;
  assert(resume_wake(NULL));assert(quiesce());
  for(unsigned failure=1;failure<=observed_transfers;failure++){
   begin(id);assert(tap_observe_begin(NULL,0));regs[3]=0x80;operations=0;fail_at=failure;
   sample=(twatch_tap_observation_v1){.struct_size=sizeof(sample),.x_mg=123};
   assert(!tap_observe(NULL,&sample) && sample.x_mg==123 && enrolled && observe_active);
   fail_at=0;assert(resume_wake(NULL));restored();assert(!observe_active);assert(quiesce());
  }
  printf("BMA%u fresh-CPU retained-sensor startup: 5 Deep cycles, %u activation transfers fault-injected PASS\n",variant?456:423,startup_count);
  printf("BMA%u actual Bosch image/configuration: %u preparation transfers, %u rollback transfers fault-injected, retry/held IRQ/cleanup PASS\n",variant?456:423,count,cleanup_count);
 }
}
