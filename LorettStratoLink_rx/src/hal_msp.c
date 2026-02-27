#include "stm32f4xx_hal.h"
#include "config.h"

void HAL_MspInit(void)
{
    __HAL_RCC_SYSCFG_CLK_ENABLE();
    __HAL_RCC_PWR_CLK_ENABLE();
}

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

        HAL_NVIC_SetPriority(E22_UART_IRQn, 1, 0);
        HAL_NVIC_EnableIRQ(E22_UART_IRQn);
    }
    else if (huart->Instance == USART2) {
        __HAL_RCC_USART2_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();
        gi.Pin       = PC_UART_TX_PIN | PC_UART_RX_PIN;
        gi.Mode      = GPIO_MODE_AF_PP;
        gi.Pull      = GPIO_PULLUP;
        gi.Speed     = GPIO_SPEED_FREQ_HIGH;
        gi.Alternate = PC_UART_AF;
        HAL_GPIO_Init(PC_UART_PORT, &gi);
    }
}

void HAL_UART_MspDeInit(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        __HAL_RCC_USART1_CLK_DISABLE();
        HAL_GPIO_DeInit(E22_UART_PORT, E22_UART_TX_PIN | E22_UART_RX_PIN);
        HAL_NVIC_DisableIRQ(E22_UART_IRQn);
    }
    else if (huart->Instance == USART2) {
        __HAL_RCC_USART2_CLK_DISABLE();
        HAL_GPIO_DeInit(PC_UART_PORT, PC_UART_TX_PIN | PC_UART_RX_PIN);
    }
}
