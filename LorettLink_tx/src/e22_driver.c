#include "e22_driver.h"
#include "config.h"
#include <string.h>

/* ── Helpers ──────────────────────────────────────────────────── */

bool e22_wait_aux(const E22_Handle *h, uint32_t timeout_ms)
{
    uint32_t start = HAL_GetTick();
    while (HAL_GPIO_ReadPin(h->aux_port, h->aux_pin) == GPIO_PIN_RESET) {
        if ((HAL_GetTick() - start) > timeout_ms)
            return false;
    }
    return true;
}

void e22_mode_config(const E22_Handle *h)
{
    HAL_GPIO_WritePin(h->m0_port, h->m0_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(h->m1_port, h->m1_pin, GPIO_PIN_SET);
    HAL_Delay(50);
    e22_wait_aux(h, 500);
}

void e22_mode_transparent(const E22_Handle *h)
{
    HAL_GPIO_WritePin(h->m0_port, h->m0_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(h->m1_port, h->m1_pin, GPIO_PIN_RESET);
    HAL_Delay(50);
    e22_wait_aux(h, 500);
}

/* ── Configuration ────────────────────────────────────────────── */

bool e22_write_config(const E22_Handle *h, const E22_Config *cfg)
{
    uint8_t cmd[12];
    cmd[0] = E22_CMD_WRITE;
    cmd[1] = E22_REG_ADDH;
    cmd[2] = 9;                     /* length: 9 registers */
    cmd[3] = cfg->addh;
    cmd[4] = cfg->addl;
    cmd[5] = cfg->net_id;
    cmd[6] = cfg->uart_baud | cfg->uart_parity | cfg->air_rate;
    cmd[7] = cfg->sub_packet | cfg->rssi_noise | cfg->tx_power;
    cmd[8] = cfg->channel;
    cmd[9] = cfg->rssi_byte | cfg->tx_method | cfg->wor_cycle;
    cmd[10] = (uint8_t)(cfg->crypt_key >> 8);
    cmd[11] = (uint8_t)(cfg->crypt_key);

    if (HAL_UART_Transmit(h->huart, cmd, 12, 200) != HAL_OK)
        return false;

    /* Wait for module to respond */
    uint8_t resp[12];
    HAL_StatusTypeDef rc = HAL_UART_Receive(h->huart, resp, 12, 500);
    if (rc != HAL_OK)
        return false;

    return (resp[0] == 0xC1);
}

bool e22_read_config(const E22_Handle *h, E22_Config *cfg)
{
    uint8_t cmd[3] = { E22_CMD_READ, E22_REG_ADDH, 9 };

    if (HAL_UART_Transmit(h->huart, cmd, 3, 200) != HAL_OK)
        return false;

    uint8_t resp[12];
    if (HAL_UART_Receive(h->huart, resp, 12, 500) != HAL_OK)
        return false;

    if (resp[0] != 0xC1 || resp[2] != 9)
        return false;

    cfg->addh       = resp[3];
    cfg->addl       = resp[4];
    cfg->net_id     = resp[5];
    cfg->uart_baud  = resp[6] & 0xE0;
    cfg->uart_parity= resp[6] & 0x18;
    cfg->air_rate   = resp[6] & 0x07;
    cfg->sub_packet = resp[7] & 0xC0;
    cfg->rssi_noise = resp[7] & 0x20;
    cfg->tx_power   = resp[7] & 0x03;
    cfg->channel    = resp[8];
    cfg->rssi_byte  = resp[9] & 0x80;
    cfg->tx_method  = resp[9] & 0x40;
    cfg->wor_cycle  = resp[9] & 0x07;
    cfg->crypt_key  = ((uint16_t)resp[10] << 8) | resp[11];
    return true;
}

/* ── Defaults ─────────────────────────────────────────────────── */

void e22_default_tx_config(E22_Config *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    cfg->addh       = 0x00;
    cfg->addl       = 0x00;
    cfg->net_id     = 0x00;
    cfg->uart_baud  = E22_BAUD_9600;
    cfg->uart_parity= E22_PARITY_8N1;
    cfg->air_rate   = E22_DEFAULT_AIRRATE;
    cfg->sub_packet = E22_SUBPKT_240;
    cfg->rssi_noise = E22_RSSI_NOISE_OFF;
    cfg->tx_power   = E22_TXPWR_33DBM;
    cfg->channel    = E22_DEFAULT_CHANNEL;
    cfg->rssi_byte  = E22_RSSI_BYTE_OFF;
    cfg->tx_method  = E22_TX_TRANSPARENT;
    cfg->wor_cycle  = E22_WOR_2000MS;
    cfg->crypt_key  = 0x0000;
}

void e22_default_rx_config(E22_Config *cfg)
{
    e22_default_tx_config(cfg);
    cfg->rssi_byte  = E22_RSSI_BYTE_ON;
}

/* ── Transmit ─────────────────────────────────────────────────── */

bool e22_transmit(const E22_Handle *h, const uint8_t *data, uint16_t len,
                  uint32_t timeout_ms)
{
    if (!e22_wait_aux(h, timeout_ms))
        return false;

    if (HAL_UART_Transmit(h->huart, (uint8_t *)data, len, timeout_ms) != HAL_OK)
        return false;

    return e22_wait_aux(h, timeout_ms);
}
