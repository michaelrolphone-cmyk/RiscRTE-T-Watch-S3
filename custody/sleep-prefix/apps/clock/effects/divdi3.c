/* App-local PIC 64-bit division/remainder for integer animation curves.
 * Avoid non-PIC Xtensa libgcc assembly in a dynamically loaded shared ELF.
 * Fixed64 iterations, complete bit domain, no signed-overflow operations. */
#include <stdint.h>
static uint64_t divide_bits(uint64_t n,uint64_t d,uint64_t *remainder) {
    uint64_t q=0,r=0;
    if(d)for(unsigned bit=64;bit;bit--) {
        uint64_t carry=r>>63;
        r=(r<<1)|((n>>(bit-1))&1u);
        if(carry||r>=d){r-=d;q|=(uint64_t)1<<(bit-1);}
    }
    if(remainder)*remainder=r;
    return q;
}
uint64_t __udivdi3(uint64_t n,uint64_t d){return divide_bits(n,d,0);}
uint64_t __umoddi3(uint64_t n,uint64_t d){uint64_t r;divide_bits(n,d,&r);return r;}
int64_t __divdi3(int64_t numerator,int64_t denominator) {
    uint64_t n=(uint64_t)numerator,d=(uint64_t)denominator;
    if(numerator<0)n=0u-n;
    if(denominator<0)d=0u-d;
    uint64_t q=divide_bits(n,d,0);
    if((numerator<0)!=(denominator<0))q=0u-q;
    return (int64_t)q;
}
int64_t __moddi3(int64_t numerator,int64_t denominator) {
    uint64_t n=(uint64_t)numerator,d=(uint64_t)denominator,r;
    if(numerator<0)n=0u-n;
    if(denominator<0)d=0u-d;
    divide_bits(n,d,&r);
    if(numerator<0)r=0u-r;
    return (int64_t)r;
}
