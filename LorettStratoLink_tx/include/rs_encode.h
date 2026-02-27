#ifndef RS_ENCODE_H
#define RS_ENCODE_H

#include <stdint.h>

/*
 * Reed-Solomon systematic encoder over GF(2^8).
 *
 * Produces parity symbols identical to Python reedsolo.RSCodec(nsym)
 * with default parameters (fcr=0, generator=2, prim=0x11d).
 *
 * gf256_init() must be called before any RS function.
 */

/* Build generator polynomial of degree nsym.
 * gen[] must hold at least (nsym + 1) bytes.
 * Coefficients stored highest-degree first: gen[0] = 1 (leading). */
void rs_generator_poly(int nsym, uint8_t *gen);

/* Compute nsym parity bytes for message msg[0..msg_len-1].
 * gen[] must be pre-built with rs_generator_poly(nsym, gen).
 * parity[] must hold at least nsym bytes. */
void rs_encode_msg(const uint8_t *msg, int msg_len,
                   int nsym, const uint8_t *gen,
                   uint8_t *parity);

#endif /* RS_ENCODE_H */
