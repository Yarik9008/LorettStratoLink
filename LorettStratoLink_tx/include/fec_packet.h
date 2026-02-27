#ifndef FEC_PACKET_H
#define FEC_PACKET_H

#include <stdint.h>

/*
 * FEC packet builder — 256-byte packets compatible with Python ground station.
 *
 * Packet layout (big-endian where multi-byte):
 *   [0]       sync        0x55
 *   [1]       type        0x68
 *   [2..5]    callsign    base-40, big-endian
 *   [6]       image_id
 *   [7..8]    block_id    big-endian
 *   [9..10]   k_data      big-endian
 *   [11..12]  n_total     big-endian
 *   [13..16]  file_size   big-endian
 *   [17]      file_type
 *   [18]      m_per_group
 *   [19]      num_groups
 *   [20..219] payload     200 bytes
 *   [220..223] crc32      CRC-32 of bytes [1..219]
 *   [224..255] reserved   32 zero bytes
 */

typedef struct {
    uint32_t callsign_enc;
    uint8_t  image_id;
    uint16_t block_id;
    uint16_t k_data;
    uint16_t n_total;
    uint32_t file_size;
    uint8_t  file_type;
    uint8_t  m_per_group;
    uint8_t  num_groups;
    const uint8_t *payload;   /* points to 200 bytes (or fewer, zero-padded) */
} FecPacketInfo;

/* Base-40 callsign encode / decode */
uint32_t callsign_encode(const char *call);
void     callsign_decode(uint32_t val, char *out6);

/* Detect JPEG / WebP by magic bytes */
uint8_t  detect_file_type(const uint8_t *data, uint32_t len);

/* Build a 256-byte FEC packet into buf[256]. */
void fec_build_packet(const FecPacketInfo *info, uint8_t *buf);

/* Software CRC-32 compatible with Python zlib.crc32 */
void     crc32_init_table(void);
uint32_t crc32_calc(const uint8_t *data, uint32_t len);

/* CRC-16 CCITT (used for TELEM packets) */
uint16_t crc16_ccitt(const uint8_t *data, uint16_t len);

/* Compute RS group parameters from K data blocks and FEC ratio.
 * Returns g_size (data blocks per RS group), m_g (parity per group),
 * and num_groups via pointers. */
void fec_group_params(int k, int fec_ratio_num, int fec_ratio_den,
                      int *g_size, int *m_g, int *num_groups);

#endif /* FEC_PACKET_H */
