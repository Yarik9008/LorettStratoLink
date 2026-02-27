#include "stm32f4xx_hal.h"

void NMI_Handler(void)              { while (1); }
void HardFault_Handler(void)        { while (1); }
void MemManage_Handler(void)        { while (1); }
void BusFault_Handler(void)         { while (1); }
void UsageFault_Handler(void)       { while (1); }
void SVC_Handler(void)              {}
void DebugMon_Handler(void)         {}
void PendSV_Handler(void)           {}

void SysTick_Handler(void)
{
    HAL_IncTick();
}

/* UART1 interrupt — handled in main via extern declaration */
extern UART_HandleTypeDef huart_e22;

void USART1_IRQHandler(void)
{
    HAL_UART_IRQHandler(&huart_e22);
}
