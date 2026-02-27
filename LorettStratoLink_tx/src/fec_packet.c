#include "fec_packet.h"
#include "config.h"
#include <string.h>

/* ── CRC-32 (zlib-compatible) ─────────────────────────────────── */

static uint32_t crc32_table[256];

void crc32_init_table(void)
{
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int j = 0; j < 8; j++)
            c = (c & 1) ? ((c >> 1) ^ 0xEDB88320U) : (c >> 1);
        crc32_table[i] = c;
    }
}

uint32_t crc32_calc(const uint8_t *data, uint32_t len)
{
    uint32_t crc = 0xFFFFFFFFU;
    for (uint32_t i = 0; i < len; i++)
        crc = (crc >> 8) ^ crc32_table[(crc ^ data[i]) & 0xFF];
    return crc ^ 0xFFFFFFFFU;
}

/* ── CRC-16 CCITT ─────────────────────────────────────────────── */

uint16_t crc16_ccitt(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) : (crc << 1);
    }
    return crc & 0xFFFF;
}

/* ── Base-40 callsign ─────────────────────────────────────────── */

static const char BASE40[] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_. ";

static int b40_index(char ch)
{
    for (int i = 0; i < 40; i++)
        if (BASE40[i] == ch) return i;
    return 0;
}

static char to_upper(char c)
{
    return (c >= 'a' && c <= 'z') ? (char)(c - 32) : c;
}

uint32_t callsign_encode(const char *call)
{
    char buf[7];
    int i;
    for (i = 0; i < 6 && call[i]; i++)
        buf[i] = to_upper(call[i]);
    for (; i < 6; i++)
        buf[i] = ' ';
    buf[6] = '\0';

    uint32_t v = 0;
    for (i = 0; i < 6; i++)
        v = v * 40 + (uint32_t)b40_index(buf[i]);
    return v;
}

void callsign_decode(uint32_t val, char *out6)
{
    for (int i = 5; i >= 0; i--) {
        out6[i] = BASE40[val % 40];
        val /= 40;
    }
    out6[6] = '\0';
}

/* ── File type detection ──────────────────────────────────────── */

uint8_t detect_file_type(const uint8_t *data, uint32_t len)
{
    if (len >= 2 && data[0] == 0xFF && data[1] == 0xD8)
        return FTYPE_JPEG;
    if (len >= 12 && data[0] == 'R' && data[1] == 'I' &&
        data[2] == 'F' && data[3] == 'F' &&
        data[8] == 'W' && data[9] == 'E' &&
        data[10] == 'B' && data[11] == 'P')
        return FTYPE_WEBP;
    return FTYPE_RAW;
}

/* ── RS group parameters (mirrors Python _rs_group_params) ───── */

void fec_group_params(int k, int fec_ratio_num, int fec_ratio_den,
                      int *g_size, int *m_g, int *num_groups)
{
    int m_desired = (k * fec_ratio_num + fec_ratio_den - 1) / fec_ratio_den;
    if (m_desired < 1) m_desired = 1;

    if (k + m_desired <= RS_MAX) {
        *g_size   = k;
        *m_g      = m_desired;
        *num_groups = 1;
        return;
    }

    int mg = (fec_ratio_num * RS_MAX + (fec_ratio_num + fec_ratio_den) / 2)
             / (fec_ratio_num + fec_ratio_den);
    if (mg < 1)   mg = 1;
    if (mg > 127) mg = 127;

    int gs = RS_MAX - mg;
    int ng = (k + gs - 1) / gs;

    *g_size    = gs;
    *m_g       = mg;
    *num_groups = ng;
}

/* ── Packet builder ───────────────────────────────────────────── */

static void put_be16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v >> 8);
    p[1] = (uint8_t)(v);
}

static void put_be32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)(v);
}

void fec_build_packet(const FecPacketInfo *info, uint8_t *buf)
{
    memset(buf, 0, PKT_SIZE);

    buf[0] = SYNC_BYTE;
    buf[1] = TYPE_FEC;
    put_be32(&buf[2],  info->callsign_enc);
    buf[6] = info->image_id;
    put_be16(&buf[7],  info->block_id);
    put_be16(&buf[9],  info->k_data);
    put_be16(&buf[11], info->n_total);
    put_be32(&buf[13], info->file_size);
    buf[17] = info->file_type;
    buf[18] = info->m_per_group;
    buf[19] = info->num_groups;

    if (info->payload)
        memcpy(&buf[HEADER_SIZE], info->payload, BLOCK_PAYLOAD);

    uint32_t crc = crc32_calc(&buf[1], HEADER_SIZE + BLOCK_PAYLOAD - 1);
    put_be32(&buf[HEADER_SIZE + BLOCK_PAYLOAD], crc);
}
