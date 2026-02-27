#ifndef E22_DRIVER_H
#define E22_DRIVER_H

#include "stm32f4xx_hal.h"
#include <stdbool.h>

typedef struct {
    UART_HandleTypeDef *huart;
    GPIO_TypeDef *aux_port;     uint16_t aux_pin;
    GPIO_TypeDef *m0_port;      uint16_t m0_pin;
    GPIO_TypeDef *m1_port;      uint16_t m1_pin;
} E22_Handle;

typedef struct {
    uint8_t addh, addl, net_id;
    uint8_t uart_baud, uart_parity, air_rate;
    uint8_t sub_packet, rssi_noise, tx_power;
    uint8_t channel;
    uint8_t rssi_byte, tx_method, wor_cycle;
    uint16_t crypt_key;
} E22_Config;

bool e22_wait_aux(const E22_Handle *h, uint32_t timeout_ms);
void e22_mode_config(const E22_Handle *h);
void e22_mode_transparent(const E22_Handle *h);
bool e22_write_config(const E22_Handle *h, const E22_Config *cfg);
bool e22_read_config(const E22_Handle *h, E22_Config *cfg);
void e22_default_rx_config(E22_Config *cfg);

#endif /* E22_DRIVER_H */
