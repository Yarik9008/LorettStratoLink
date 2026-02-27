#include "rs_encode.h"
#include "gf256.h"
#include <string.h>

void rs_generator_poly(int nsym, uint8_t *gen)
{
    memset(gen, 0, (size_t)(nsym + 1));
    gen[0] = 1;

    for (int i = 0; i < nsym; i++) {
        uint8_t root = gf256_exp(i);        /* α^i, fcr=0 */
        gen[i + 1] = gf256_mul(gen[i], root);
        for (int j = i; j >= 1; j--)
            gen[j] = gen[j - 1] ^ gf256_mul(gen[j], root);
        gen[0] = gf256_mul(gen[0], root);
    }
}

void rs_encode_msg(const uint8_t *msg, int msg_len,
                   int nsym, const uint8_t *gen,
                   uint8_t *parity)
{
    memset(parity, 0, (size_t)nsym);

    for (int i = 0; i < msg_len; i++) {
        uint8_t feedback = msg[i] ^ parity[0];
        memmove(parity, parity + 1, (size_t)(nsym - 1));
        parity[nsym - 1] = 0;
        if (feedback != 0) {
            for (int j = 0; j < nsym; j++)
                parity[j] ^= gf256_mul(gen[j + 1], feedback);
        }
    }
}
