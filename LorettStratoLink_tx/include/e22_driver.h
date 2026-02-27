#ifndef E22_DRIVER_H
#define E22_DRIVER_H

#include "stm32f4xx_hal.h"
#include <stdbool.h>

/*
 * Driver for Ebyte E22-xxxT33S LoRa modules.
 *
 * Provides:
 *   - Configuration via register write (M0=1, M1=1 mode)
 *   - Transparent data transmission (M0=0, M1=0 mode)
 *   - AUX pin polling for busy/ready state
 */

typedef struct {
    UART_HandleTypeDef *huart;
    GPIO_TypeDef *aux_port;     uint16_t aux_pin;
    GPIO_TypeDef *m0_port;      uint16_t m0_pin;
    GPIO_TypeDef *m1_port;      uint16_t m1_pin;
} E22_Handle;

typedef struct {
    uint8_t addh;
    uint8_t addl;
    uint8_t net_id;
    uint8_t uart_baud;      /* E22_BAUD_xxx */
    uint8_t uart_parity;    /* E22_PARITY_xxx */
    uint8_t air_rate;       /* E22_AIRRATE_xxx */
    uint8_t sub_packet;     /* E22_SUBPKT_xxx */
    uint8_t rssi_noise;     /* E22_RSSI_NOISE_xxx */
    uint8_t tx_power;       /* E22_TXPWR_xxx */
    uint8_t channel;
    uint8_t rssi_byte;      /* E22_RSSI_BYTE_xxx */
    uint8_t tx_method;      /* E22_TX_TRANSPARENT / fixed */
    uint8_t wor_cycle;      /* E22_WOR_xxx */
    uint16_t crypt_key;
} E22_Config;

/* Wait for AUX pin HIGH (module ready), with timeout.
 * Returns true if ready, false on timeout. */
bool e22_wait_aux(const E22_Handle *h, uint32_t timeout_ms);

/* Enter configuration mode (M0=1, M1=1) */
void e22_mode_config(const E22_Handle *h);

/* Enter transparent transmission mode (M0=0, M1=0) */
void e22_mode_transparent(const E22_Handle *h);

/* Write configuration registers to the module.
 * Must be in config mode first. */
bool e22_write_config(const E22_Handle *h, const E22_Config *cfg);

/* Read current configuration from the module.
 * Must be in config mode first. */
bool e22_read_config(const E22_Handle *h, E22_Config *cfg);

/* Fill an E22_Config with sensible defaults for the transmitter. */
void e22_default_tx_config(E22_Config *cfg);

/* Fill an E22_Config with sensible defaults for the receiver
 * (RSSI byte enabled). */
void e22_default_rx_config(E22_Config *cfg);

/* Send data in transparent mode.
 * Waits for AUX ready before and after transmission. */
bool e22_transmit(const E22_Handle *h, const uint8_t *data, uint16_t len,
                  uint32_t timeout_ms);

#endif /* E22_DRIVER_H */
