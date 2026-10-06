/* Bosch feature engine stays in the sensor across both CPU sleep modes.
 * Exact vendor source/images: vendor/SensorLib/PROVENANCE.json. Only double tap
 * is mapped to INT1; no MCU polling, touch filtering, or firmware board code. */
#include "../../vendor/SensorLib/bosch/bma4xx/bma423.h"
#include "../../vendor/SensorLib/bosch/bma4xx/bma456h.h"
static struct bma4_dev sensor;
/* Bosch BMA423: 0 is most sensitive, 7 is least. BMA456H uses a distinct
 * threshold scaling parameter (documented default 9; recommended 0..15).
 * These settings reduce sensitivity; they do not implement a custom equal-
 * magnitude/quiet-window classifier. */
enum { WAKE_BMA423_SENSITIVITY=3, WAKE_BMA456H_THRESHOLD=12 };
static bool wake_enrolled,wake_changed,wake_prepared,io_failed;
static const uint8_t saved_regs[]={BMA4_ACCEL_CONFIG_ADDR,BMA4_ACCEL_RANGE_ADDR,
    BMA4_POWER_CONF_ADDR,BMA4_POWER_CTRL_ADDR,BMA4_INT1_IO_CTRL_ADDR,BMA4_INT2_IO_CTRL_ADDR,
    BMA4_INTR_LATCH_ADDR,BMA4_INT_MAP_1_ADDR,BMA4_INT_MAP_2_ADDR,BMA4_INT_MAP_DATA_ADDR};
static uint8_t wake_saved[sizeof(saved_regs)];
/* Some vendor bulk loops overwrite an earlier error with a later success.
 * Latch transport failure for the complete operation and stop subsequent I/O.
 * Resume explicitly starts a fresh bounded rollback attempt. */
static int8_t sensor_read(uint8_t reg,uint8_t *data,uint32_t n,void *c){
    (void)c;if(io_failed || !data || !n || n>128)return -1;
    if(!read_reg(reg,data,n)){io_failed=true;return -1;}return 0;
}
static int8_t sensor_write(uint8_t reg,const uint8_t *data,uint32_t n,void *c){
    (void)c;if(io_failed || !data || !n || n>32)return -1;
    uint8_t bytes[33];bytes[0]=reg;for(uint32_t i=0;i<n;i++)bytes[i+1]=data[i];
    if(!bus->transact(bus->context,claim,bytes,n+1,NULL,0,30)){io_failed=true;(void)sensor_wait_us(450);return -1;}return 0;
}
static void sensor_delay(uint32_t us,void *c){
    (void)c;if(!sensor_wait_us(us))io_failed=true;
}
static bool wake_pending(void *context,bool *pending){
    (void)context;if(!started || !wake_prepared || !pending)return false;
    bool level=false;if(!gpio_api->read(gpio_api->context,irq_claim,&level))return false;
    *pending=level==config->irq_active_high;return true;
}
static bool reset_before_wake(void);
static bool resume_wake(void *context){
    (void)context;if(!wake_enrolled && !wake_changed)return true;
    if(!started || !claim || !irq_claim)return false;
    if(wake_changed){
        io_failed=false;
        if(!sensor_wait_us(450))return false; /* Guard uncertain prior bus completion. */
        /* Reset is the documented disable/ack boundary for both feature engines.
         * This provider exposes no independent feature setters. Restore its
         * exact sampled register state only after reset succeeds. */
        if(!reset_before_wake())return false;
        if(!sensor_wait_us(20000))return false;
        for(size_t i=0;i<sizeof(saved_regs);i++)if(!write_reg(saved_regs[i],wake_saved[i]))return false;
        for(size_t i=0;i<sizeof(saved_regs);i++){uint8_t value=0;if(!read_reg(saved_regs[i],&value,1) || value!=wake_saved[i])return false;}
        wake_changed=wake_prepared=false;
    }
    /* No resource is released until sensor rollback is verified. The runtime
     * enrollment remains an app-exit barrier across a failed attempt/retry. */
    if(wake_enrolled){
        if(gpio_api->wake_source(gpio_api->context,irq_claim,config->irq_active_high,0)!=0)return false;
        wake_enrolled=false;
    }
    return true;
}
static uint32_t wake_failure_code;
static bool wake_failure(uint32_t code){wake_failure_code=code;return false;}
static uint32_t wake_error(void *context){(void)context;return wake_failure_code;}
static bool reset_before_wake(void){
    /* Bosch reset ACK preconditions: stop accel/aux, then enable APS. A
     * running normal-mode reset may take effect before its I2C data ACK. */
    uint8_t power[2]={0},observed[2]={0};
    if(!sensor_wait_us(450))return wake_failure(749);
    if(bma4_read_regs(BMA4_POWER_CONF_ADDR,power,2,&sensor)!=BMA4_OK || io_failed)return wake_failure(742);
    power[1]&=(uint8_t)~(BMA4_ACCEL_ENABLE_MSK|BMA4_MAG_ENABLE_MSK);
    power[0]|=BMA4_ADVANCE_POWER_SAVE_MSK;
    if(bma4_write_regs(BMA4_POWER_CTRL_ADDR,&power[1],1,&sensor)!=BMA4_OK ||
       bma4_write_regs(BMA4_POWER_CONF_ADDR,&power[0],1,&sensor)!=BMA4_OK || io_failed)return wake_failure(742);
    if(bma4_read_regs(BMA4_POWER_CONF_ADDR,observed,2,&sensor)!=BMA4_OK ||
       observed[0]!=power[0] || observed[1]!=power[1] || io_failed)return wake_failure(747);
    int8_t result=bma4_soft_reset(&sensor);
    if(result!=BMA4_OK)return wake_failure(740u+(unsigned)(result<0?-result:result));
    return io_failed?wake_failure(749):true;
}
static bool prepare_wake(void *context){
    wake_failure_code=0;
    (void)context;if(!started || !irq_claim)return wake_failure(__LINE__);
    if(wake_enrolled || wake_changed)return wake_prepared;
    if(gpio_api->struct_size<RISC_GPIO_BANK_WAKE_SOURCE_V1_SIZE || !gpio_api->wake_source)return wake_failure(__LINE__);
    if(gpio_api->wake_source(gpio_api->context,irq_claim,config->irq_active_high,RISC_WAKE_SET_LIGHT|RISC_WAKE_SET_DEEP)!=0)return wake_failure(__LINE__);
    wake_enrolled=true;
    for(size_t i=0;i<sizeof(saved_regs);i++)if(!read_reg(saved_regs[i],&wake_saved[i],1))return wake_failure(__LINE__);
    sensor=(struct bma4_dev){0};sensor.intf=BMA4_I2C_INTF;sensor.bus_read=sensor_read;
    sensor.bus_write=sensor_write;sensor.delay_us=sensor_delay;sensor.read_write_len=32;
    io_failed=false;wake_changed=true;
    if(!reset_before_wake())return false;
    if(!sensor_wait_us(20000))return wake_failure(__LINE__);
    if(chip==BMA423_CHIP_ID){
        if(bma423_init(&sensor)!=BMA4_OK)return wake_failure(__LINE__);
        sensor.config_size=BMA423_CONFIG_FILE_SIZE;
        if(bma423_write_config_file(&sensor)!=BMA4_OK)return wake_failure(__LINE__);
        if(bma423_feature_enable(BMA423_STEP_CNTR|BMA423_ANY_MOTION|BMA423_NO_MOTION|BMA423_ACTIVITY|BMA423_TILT|BMA423_WAKEUP,0,&sensor)!=BMA4_OK ||
           bma423_step_detector_enable(0,&sensor)!=BMA4_OK || bma423_anymotion_enable_axis(BMA423_ALL_AXIS_DIS,&sensor)!=BMA4_OK ||
           bma423_tap_selection(0,&sensor)!=BMA4_OK || /* 0 is DOUBLE, not single. */
           bma423_wakeup_set_sensitivity(WAKE_BMA423_SENSITIVITY,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
    }else{
        if(bma456h_init(&sensor)!=BMA4_OK || bma456h_write_config_file(&sensor)!=BMA4_OK ||
           bma456h_feature_enable(UINT16_MAX,0,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
        struct bma456h_multitap_settings wanted={0},observed={0};
        if(bma456h_tap_get_parameter(&wanted,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
        wanted.tap_sens_thres=WAKE_BMA456H_THRESHOLD;
        if(bma456h_tap_set_parameter(&wanted,&sensor)!=BMA4_OK ||
           bma456h_tap_get_parameter(&observed,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
        /* Preserve and verify the complete vendor parameter object, including
         * reserved words, axis selection and existing gesture timing. */
        const uint8_t *a=(const uint8_t *)&wanted,*b=(const uint8_t *)&observed;
        for(size_t i=0;i<sizeof(wanted);i++)if(a[i]!=b[i])return wake_failure(__LINE__);
    }
    /* Manufacturer tap example: >=200 Hz, 2g, AVG2, CIC mode. Keep sensor
     * powered, use APS, and retain this config through terminal CPU Deep. */
    const struct bma4_accel_config accel={.odr=BMA4_OUTPUT_DATA_RATE_200HZ,.range=BMA4_ACCEL_RANGE_2G,
        .bandwidth=BMA4_ACCEL_OSR2_AVG2,.perf_mode=BMA4_CIC_AVG_MODE};
    const struct bma4_int_pin_config interrupt={.edge_ctrl=BMA4_LEVEL_TRIGGER,
        .lvl=config->irq_active_high?BMA4_ACTIVE_HIGH:BMA4_ACTIVE_LOW,.od=BMA4_PUSH_PULL,
        .output_en=BMA4_OUTPUT_ENABLE,.input_en=BMA4_INPUT_DISABLE};
    if(io_failed || bma4_set_accel_config(&accel,&sensor)!=BMA4_OK || bma4_set_accel_enable(BMA4_ENABLE,&sensor)!=BMA4_OK ||
       bma4_set_interrupt_mode(BMA4_LATCH_MODE,&sensor)!=BMA4_OK ||
       bma4_set_int_pin_config(&interrupt,BMA4_INTR1_MAP,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
    uint16_t status=0;
    /* Ack stale status before enabling any gesture. Events after this boundary
     * stay latched; pending/final CPU admission never reads-to-clear status. */
    if(bma4_read_int_status(&status,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
    if(chip==BMA423_CHIP_ID){
        if(bma423_feature_enable(BMA423_WAKEUP,1,&sensor)!=BMA4_OK ||
           bma423_map_interrupt(BMA4_INTR1_MAP,BMA423_WAKEUP_INT,1,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
        uint8_t feature[BMA423_FEATURE_SIZE];
        if(bma4_read_regs(BMA4_FEATURE_CONFIG_ADDR,feature,sizeof(feature),&sensor)!=BMA4_OK ||
           (feature[BMA423_WAKEUP_OFFSET]&(BMA423_WAKEUP_EN_MSK|BMA423_TAP_SEL_MSK|BMA423_WAKEUP_SENS_MSK))!=
               (BMA423_WAKEUP_EN_MSK|(WAKE_BMA423_SENSITIVITY<<BMA423_WAKEUP_SENS_POS)) ||
           (feature[BMA423_TILT_OFFSET]&BMA423_TILT_EN_MSK) ||
           (feature[BMA423_STEP_CNTR_OFFSET+1]&(BMA423_STEP_CNTR_EN_MSK|BMA423_ACTIVITY_EN_MSK|BMA423_STEP_DETECTOR_EN_MSK)) ||
           (feature[BMA423_ANY_NO_MOTION_OFFSET+3]&BMA423_ANY_NO_MOTION_AXIS_EN_MSK))return wake_failure(__LINE__);
    }else{
        if(bma456h_feature_enable(BMA456H_DOUBLE_TAP_EN,1,&sensor)!=BMA4_OK ||
           bma456h_map_interrupt(BMA4_INTR1_MAP,BMA456H_TAP_OUT_INT,1,&sensor)!=BMA4_OK)return wake_failure(__LINE__);
        uint8_t enabled[2];
        if(bma4_read_regs(BMA456H_FEAT_EN_ADDR1,enabled,2,&sensor)!=BMA4_OK || enabled[0] || enabled[1]!=BMA456H_DOUBLE_TAP_EN_MSK)return wake_failure(__LINE__);
    }
    uint8_t maps[3]={0},control=0,latch=0;
    if(io_failed || !read_reg(BMA4_INT_MAP_1_ADDR,maps,3) ||
       maps[0]!=(chip==BMA423_CHIP_ID?BMA423_WAKEUP_INT:BMA456H_TAP_OUT_INT) || maps[1] || maps[2] ||
       !read_reg(BMA4_INT1_IO_CTRL_ADDR,&control,1) || control!=(uint8_t)(BMA4_OUTPUT_ENABLE<<3 | (config->irq_active_high?1u:0u)<<1) ||
       !read_reg(BMA4_INTR_LATCH_ADDR,&latch,1) || latch!=BMA4_LATCH_MODE)return wake_failure(__LINE__);
    /* Enabling/configuring the feature engine can itself leave a latched
     * interrupt. Establish the sleep arm boundary only after configuration and
     * readback are complete. Events after this ACK remain latched for wake. */
    if(bma4_read_int_status(&status,&sensor)!=BMA4_OK || io_failed)return wake_failure(__LINE__);
    bool level=false;
    if(!gpio_api->read(gpio_api->context,irq_claim,&level) || level==config->irq_active_high)return wake_failure(__LINE__);
    wake_prepared=true;return true;
}
