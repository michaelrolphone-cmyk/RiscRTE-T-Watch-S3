/* Compatibility GPIO bank over the shared raw GPIO owner. No MMIO bypass. */
#include "twatch_support.h"
static const garden_gpio_v1 *hw;
static bool started;
static uint64_t serial;
static struct {
    uint64_t token, raw;
    uint32_t flags;
} slots[48];
static bool claim_pin(void *c, uint8_t pin, uint32_t flags, uint64_t *out) {
    (void)c;
    if (out)
        *out = 0;
    if (!started || !out || !tw_pin(pin) || serial == UINT64_MAX || !(flags & 3) || flags & ~7u)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (!slots[i].token) {
            uint64_t raw = 0;
            if (!hw->claim(hw->context, pin, (flags & RISC_GPIO_OUTPUT) != 0, false,
                           (flags & RISC_GPIO_PULLUP) != 0, &raw) ||
                !raw)
                return false;
            slots[i].token = ++serial;
            slots[i].raw = raw;
            slots[i].flags = flags;
            *out = serial;
            return true;
        }
    return false;
}
static bool write_pin(void *c, uint64_t t, bool value) {
    (void)c;
    if (!started || !t)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token == t && slots[i].flags & RISC_GPIO_OUTPUT)
            return hw->write(hw->context, slots[i].raw, value);
    return false;
}
static bool read_pin(void *c, uint64_t t, bool *value) {
    (void)c;
    if (!started || !t || !value)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token == t)
            return hw->read(hw->context, slots[i].raw, value);
    return false;
}
static bool release_pin(void *c, uint64_t t) {
    (void)c;
    if (!started || !t)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token == t) {
            if (!hw->release(hw->context, slots[i].raw))
                return false;
            slots[i].token = slots[i].raw = 0;
            return true;
        }
    return false;
}
static int32_t light_sleep(void *c,uint64_t token,bool high,risc_light_sleep_result_v1 *out) {
    (void)c;
    if (!started || !token || !out || out->struct_size<sizeof(*out)) return RISC_LIGHT_SLEEP_INVALID;
    if (hw->struct_size<GARDEN_GPIO_LIGHT_SLEEP_V1_SIZE || !hw->light_sleep) return RISC_LIGHT_SLEEP_UNSUPPORTED;
    for(size_t i=0;i<48;i++)if(slots[i].token==token) {
        if (!(slots[i].flags&RISC_GPIO_INPUT) || (slots[i].flags&RISC_GPIO_OUTPUT)) return RISC_LIGHT_SLEEP_INVALID;
        return hw->light_sleep(hw->context,slots[i].raw,high,out);
    }
    return RISC_LIGHT_SLEEP_INVALID;
}
static int32_t deep_sleep(void *c,uint64_t token,bool high) {
    (void)c;
    if (!started || !token) return RISC_DEEP_SLEEP_INVALID;
    if (hw->struct_size<GARDEN_GPIO_DEEP_SLEEP_V1_SIZE || !hw->deep_sleep) return RISC_DEEP_SLEEP_UNSUPPORTED;
    for(size_t i=0;i<48;i++)if(slots[i].token==token) {
        if (!(slots[i].flags&RISC_GPIO_INPUT) || (slots[i].flags&RISC_GPIO_OUTPUT)) return RISC_DEEP_SLEEP_INVALID;
        return hw->deep_sleep(hw->context,slots[i].raw,high);
    }
    return RISC_DEEP_SLEEP_INVALID;
}
static int32_t light_sleep_for(void *c,uint64_t token,bool high,uint32_t duration,risc_light_sleep_result_v1 *out) {
    (void)c;
    if (!started || !token || !out || out->struct_size<sizeof(*out) || !duration || duration>RISC_TIMED_SLEEP_MAX_MS) return RISC_LIGHT_SLEEP_INVALID;
    if (hw->struct_size<GARDEN_GPIO_LIGHT_SLEEP_FOR_V1_SIZE || !hw->light_sleep_for) return RISC_LIGHT_SLEEP_UNSUPPORTED;
    for(size_t i=0;i<48;i++)if(slots[i].token==token) {
        if (!(slots[i].flags&RISC_GPIO_INPUT) || (slots[i].flags&RISC_GPIO_OUTPUT)) return RISC_LIGHT_SLEEP_INVALID;
        return hw->light_sleep_for(hw->context,slots[i].raw,high,duration,out);
    }
    return RISC_LIGHT_SLEEP_INVALID;
}
static int32_t deep_sleep_for(void *c,uint64_t token,bool high,uint32_t duration) {
    (void)c;
    if(!started || !token || !duration || duration>RISC_TIMED_SLEEP_MAX_MS)return RISC_DEEP_SLEEP_INVALID;
    if(hw->struct_size<GARDEN_GPIO_DEEP_SLEEP_FOR_V1_SIZE || !hw->deep_sleep_for)return RISC_DEEP_SLEEP_UNSUPPORTED;
    for(size_t i=0;i<48;i++)if(slots[i].token==token) {
        if(!(slots[i].flags&RISC_GPIO_INPUT) || (slots[i].flags&RISC_GPIO_OUTPUT))return RISC_DEEP_SLEEP_INVALID;
        return hw->deep_sleep_for(hw->context,slots[i].raw,high,duration);
    }
    return RISC_DEEP_SLEEP_INVALID;
}
static int32_t wake_source(void *c,uint64_t token,bool high,uint32_t modes){
    (void)c;if(!started || !token || modes&~3u)return RISC_LIGHT_SLEEP_INVALID;
    if(hw->struct_size<GARDEN_GPIO_WAKE_SOURCE_V1_SIZE || !hw->wake_source)return RISC_LIGHT_SLEEP_UNSUPPORTED;
    for(size_t i=0;i<48;i++)if(slots[i].token==token){
        if(!(slots[i].flags&RISC_GPIO_INPUT) || (slots[i].flags&RISC_GPIO_OUTPUT))return RISC_LIGHT_SLEEP_INVALID;
        return hw->wake_source(hw->context,slots[i].raw,high,modes);
    }return RISC_LIGHT_SLEEP_INVALID;
}
static int32_t light_sleep_set(void *c,uint64_t token,bool high,uint32_t ms,risc_light_sleep_result_v1 *out){
    (void)c;if(!started || !token || !out || out->struct_size<sizeof(*out) || ms>RISC_TIMED_SLEEP_MAX_MS)return RISC_LIGHT_SLEEP_INVALID;
    if(hw->struct_size<GARDEN_GPIO_LIGHT_SLEEP_SET_V1_SIZE || !hw->light_sleep_set)return RISC_LIGHT_SLEEP_UNSUPPORTED;
    for(size_t i=0;i<48;i++)if(slots[i].token==token){
        if(!(slots[i].flags&RISC_GPIO_INPUT) || (slots[i].flags&RISC_GPIO_OUTPUT))return RISC_LIGHT_SLEEP_INVALID;
        return hw->light_sleep_set(hw->context,slots[i].raw,high,ms,out);
    }return RISC_LIGHT_SLEEP_INVALID;
}
static int32_t deep_sleep_set(void *c,uint64_t token,bool high,uint32_t ms){
    (void)c;if(!started || !token || ms>RISC_TIMED_SLEEP_MAX_MS)return RISC_DEEP_SLEEP_INVALID;
    if(hw->struct_size<GARDEN_GPIO_DEEP_SLEEP_SET_V1_SIZE || !hw->deep_sleep_set)return RISC_DEEP_SLEEP_UNSUPPORTED;
    for(size_t i=0;i<48;i++)if(slots[i].token==token){
        if(!(slots[i].flags&RISC_GPIO_INPUT) || (slots[i].flags&RISC_GPIO_OUTPUT))return RISC_DEEP_SLEEP_INVALID;
        return hw->deep_sleep_set(hw->context,slots[i].raw,high,ms);
    }return RISC_DEEP_SLEEP_INVALID;
}
static bool quiesce(void) {
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token)
            return false;
    started = false;
    hw = NULL;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started)
        return false;
    const tw_hw_gpio_controller_v1 *config =
        tw_config(d, n, "espressif,esp32s3-gpio", "controller.gpio", sizeof(*config));
    if (!config || config->unit || config->features)
        return false;
    hw = tw_dep(d, n, "platform.gpio", offsetof(garden_gpio_v1,light_sleep));
    if (!hw || !hw->claim || !hw->write || !hw->read || !hw->release)
        return false;
    started = true;
    return true;
}
static const risc_gpio_bank_api_v1 api = {1,         sizeof(api), NULL,       claim_pin,
                                          write_pin, read_pin,    release_pin, light_sleep, deep_sleep, light_sleep_for, deep_sleep_for, wake_source, light_sleep_set, deep_sleep_set};
TW_DRIVER("twatch-gpio", "gpio.bank", 1, api)
