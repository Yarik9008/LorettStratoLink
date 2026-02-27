#ifndef TELEM_H
#define TELEM_H

#include <stdint.h>

/*
 * Build a 10-byte TELEM packet compatible with the Python StreamParser.
 *
 * Format (little-endian):
 *   [0..1]  sync       0xA55A (LE: 0x5A, 0xA5)
 *   [2]     version    0x01
 *   [3]     type       0x30
 *   [4..5]  rssi       int16_t LE
 *   [6]     snr        int8_t
 *   [7]     tx_power   uint8_t
 *   [8..9]  crc16      CRC-16 CCITT over bytes [2..7]
 */

/* Build TELEM packet into buf[10]. Returns 10 (packet length). */
int telem_build(uint8_t *buf, int16_t rssi, int8_t snr, uint8_t tx_power);

#endif /* TELEM_H */
