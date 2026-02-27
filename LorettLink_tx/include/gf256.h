#ifndef GF256_H
#define GF256_H

#include <stdint.h>

/*
 * GF(2^8) arithmetic with primitive polynomial
 * p(x) = x^8 + x^4 + x^3 + x^2 + 1  (0x11D)
 *
 * Compatible with Python reedsolo library defaults:
 *   prim=0x11d, generator=2, c_exp=8
 */

#define GF_PRIM_POLY  0x11D

void     gf256_init(void);
uint8_t  gf256_mul(uint8_t a, uint8_t b);
uint8_t  gf256_div(uint8_t a, uint8_t b);
uint8_t  gf256_pow(uint8_t base, int exp);
uint8_t  gf256_exp(int i);

#endif /* GF256_H */
