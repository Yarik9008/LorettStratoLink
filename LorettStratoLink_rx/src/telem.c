#include "telem.h"
#include "config.h"

static uint16_t crc16_ccitt(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) : (crc << 1);
    }
    return crc & 0xFFFF;
}

int telem_build(uint8_t *buf, int16_t rssi, int8_t snr, uint8_t tx_power)
{
    buf[0] = (uint8_t)(TELEM_SYNC & 0xFF);          /* 0x5A */
    buf[1] = (uint8_t)((TELEM_SYNC >> 8) & 0xFF);   /* 0xA5 */
    buf[2] = TELEM_PROTO_VER;
    buf[3] = TELEM_TYPE_ID;
    buf[4] = (uint8_t)(rssi & 0xFF);
    buf[5] = (uint8_t)((rssi >> 8) & 0xFF);
    buf[6] = (uint8_t)snr;
    buf[7] = tx_power;

    uint16_t crc = crc16_ccitt(&buf[2], 6);
    buf[8] = (uint8_t)(crc & 0xFF);
    buf[9] = (uint8_t)((crc >> 8) & 0xFF);

    return TELEM_PKT_SIZE;
}
