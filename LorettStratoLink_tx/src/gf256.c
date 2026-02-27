#include "gf256.h"

static uint8_t exp_table[512];
static uint8_t log_table[256];

void gf256_init(void)
{
    int x = 1;
    for (int i = 0; i < 255; i++) {
        exp_table[i] = (uint8_t)x;
        log_table[x] = (uint8_t)i;
        x <<= 1;
        if (x & 0x100)
            x ^= GF_PRIM_POLY;
    }
    for (int i = 255; i < 512; i++)
        exp_table[i] = exp_table[i - 255];
    log_table[0] = 0;
}

uint8_t gf256_exp(int i)
{
    return exp_table[((i % 255) + 255) % 255];
}

uint8_t gf256_mul(uint8_t a, uint8_t b)
{
    if (a == 0 || b == 0) return 0;
    return exp_table[log_table[a] + log_table[b]];
}

uint8_t gf256_div(uint8_t a, uint8_t b)
{
    if (a == 0) return 0;
    /* b == 0 is division by zero — caller's responsibility */
    return exp_table[(log_table[a] - log_table[b] + 255) % 255];
}

uint8_t gf256_pow(uint8_t base, int exp)
{
    if (base == 0) return 0;
    return exp_table[(log_table[base] * exp) % 255];
}
