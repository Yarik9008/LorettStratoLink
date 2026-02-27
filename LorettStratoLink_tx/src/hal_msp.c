#include "stm32f4xx_hal.h"
#include "config.h"

/* ── Base MSP init (called by HAL_Init) ───────────────────────── */

void HAL_MspInit(void)
{
    __HAL_RCC_SYSCFG_CLK_ENABLE();
    __HAL_RCC_PWR_CLK_ENABLE();
}

/* ── UART MSP ─────────────────────────────────────────────────── */

void HAL_UART_MspInit(UART_HandleTypeDef *huart)
{
    GPIO_InitTypeDef gi = {0};

    if (huart->Instance == USART1) {
        __HAL_RCC_USART1_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();
        gi.Pin       = E22_UART_TX_PIN | E22_UART_RX_PIN;
        gi.Mode      = GPIO_MODE_AF_PP;
        gi.Pull      = GPIO_PULLUP;
        gi.Speed     = GPIO_SPEED_FREQ_HIGH;
        gi.Alternate = E22_UART_AF;
        HAL_GPIO_Init(E22_UART_PORT, &gi);
    }
    else if (huart->Instance == USART2) {
        __HAL_RCC_USART2_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();
        gi.Pin       = DBG_UART_TX_PIN | DBG_UART_RX_PIN;
        gi.Mode      = GPIO_MODE_AF_PP;
        gi.Pull      = GPIO_PULLUP;
        gi.Speed     = GPIO_SPEED_FREQ_HIGH;
        gi.Alternate = DBG_UART_AF;
        HAL_GPIO_Init(DBG_UART_PORT, &gi);
    }
}

void HAL_UART_MspDeInit(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        __HAL_RCC_USART1_CLK_DISABLE();
        HAL_GPIO_DeInit(E22_UART_PORT, E22_UART_TX_PIN | E22_UART_RX_PIN);
    }
    else if (huart->Instance == USART2) {
        __HAL_RCC_USART2_CLK_DISABLE();
        HAL_GPIO_DeInit(DBG_UART_PORT, DBG_UART_TX_PIN | DBG_UART_RX_PIN);
    }
}

/* ── SD / SDIO MSP ────────────────────────────────────────────── */

void HAL_SD_MspInit(SD_HandleTypeDef *hsd)
{
    (void)hsd;
    GPIO_InitTypeDef gi = {0};

    __HAL_RCC_SDIO_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();

    /* PC8..PC12 = D0..D3 + CK */
    gi.Pin       = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 |
                   GPIO_PIN_11 | GPIO_PIN_12;
    gi.Mode      = GPIO_MODE_AF_PP;
    gi.Pull      = GPIO_PULLUP;
    gi.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
    gi.Alternate = GPIO_AF12_SDIO;
    HAL_GPIO_Init(GPIOC, &gi);

    /* PD2 = CMD */
    gi.Pin       = GPIO_PIN_2;
    HAL_GPIO_Init(GPIOD, &gi);
}

void HAL_SD_MspDeInit(SD_HandleTypeDef *hsd)
{
    (void)hsd;
    __HAL_RCC_SDIO_CLK_DISABLE();
    HAL_GPIO_DeInit(GPIOC, GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 |
                           GPIO_PIN_11 | GPIO_PIN_12);
    HAL_GPIO_DeInit(GPIOD, GPIO_PIN_2);
}
