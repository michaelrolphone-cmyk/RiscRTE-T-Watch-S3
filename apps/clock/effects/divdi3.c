/* App-local PIC signed division for the copied integer animation curves.
 * Avoid pulling non-PIC Xtensa libgcc assembly into a loadable shared ELF.
 * Fixed 64 iterations; truncates toward zero. The animation's divisors are
 * positive constants; handle the complete bit domain without signed overflow. */
#include <stdint.h>
int64_t __divdi3(int64_t numerator,int64_t denominator) {
    if (!denominator) return 0;
    uint64_t n=(uint64_t)numerator,d=(uint64_t)denominator;
    const int negative=(numerator<0)!=(denominator<0);
    if(numerator<0)n=0u-n;
    if(denominator<0)d=0u-d;
    uint64_t q=0,r=0;
    for(unsigned bit=64;bit;bit--) {
        uint64_t carry=r>>63;
        r=(r<<1)|((n>>(bit-1))&1u);
        if(carry || r>=d){r-=d;q|=(uint64_t)1<<(bit-1);}
    }
    if(negative)q=0u-q;
    return (int64_t)q;
}
