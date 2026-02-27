#include "stm32f4xx_hal.h"
#include "config.h"
#include "e22_driver.h"
#include "telem.h"
#include <string.h>
#include <stdio.h>

/* ═══════════════════════════════════════════════════════════════
 *  Peripheral handles (huart_e22 is extern'd in stm32f4xx_it.c)
 * ═══════════════════════════════════════════════════════════════ */

UART_HandleTypeDef huart_e22;
static UART_HandleTypeDef huart_pc;
static E22_Handle         e22;

/* ═══════════════════════════════════════════════════════════════
 *  Ring buffer for interrupt-driven E22 UART RX
 * ═══════════════════════════════════════════════════════════════ */

static volatile uint8_t  rx_ring[RX_RING_SIZE];
static volatile uint16_t rx_head;
static volatile uint16_t rx_tail;
static uint8_t           rx_byte;   /* single-byte IT receive target */

static uint16_t ring_count(void)
{
    return (uint16_t)((rx_head - rx_tail) & (RX_RING_SIZE - 1));
}

static uint8_t ring_pop(void)
{
    uint8_t b = rx_ring[rx_tail];
    rx_tail = (rx_tail + 1) & (RX_RING_SIZE - 1);
    return b;
}

static void ring_read(uint8_t *dst, uint16_t n)
{
    for (uint16_t i = 0; i < n; i++)
        dst[i] = ring_pop();
}

static uint8_t ring_peek(uint16_t offset)
{
    return rx_ring[(rx_tail + offset) & (RX_RING_SIZE - 1)];
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        rx_ring[rx_head] = rx_byte;
        rx_head = (rx_head + 1) & (RX_RING_SIZE - 1);
        HAL_UART_Receive_IT(&huart_e22, &rx_byte, 1);
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  Debug printf via PC UART
 * ═══════════════════════════════════════════════════════════════ */

static char dbg_line[128];
#define DBG(fmt, ...) do {                                         \
    int _n = snprintf(dbg_line, sizeof(dbg_line), fmt, ##__VA_ARGS__); \
    HAL_UART_Transmit(&huart_pc, (uint8_t*)dbg_line,               \
                      (uint16_t)_n, 50);                           \
} while(0)

/* ═══════════════════════════════════════════════════════════════
 *  System clock: HSI 16 MHz → PLL → 180 MHz
 * ═══════════════════════════════════════════════════════════════ */

static void SystemClock_Config(void)
{
    RCC_OscInitTypeDef osc = {0};
    osc.OscillatorType  = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState        = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState    = RCC_PLL_ON;
    osc.PLL.PLLSource   = RCC_PLLSOURCE_HSI;
    osc.PLL.PLLM        = 16;
    osc.PLL.PLLN        = 360;
    osc.PLL.PLLP        = RCC_PLLP_DIV2;
    osc.PLL.PLLQ        = 8;
    HAL_RCC_OscConfig(&osc);

    HAL_PWREx_EnableOverDrive();

    RCC_ClkInitTypeDef clk = {0};
    clk.ClockType       = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                           RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource    = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider   = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider  = RCC_HCLK_DIV4;
    clk.APB2CLKDivider  = RCC_HCLK_DIV2;
    HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_5);
}

/* ═══════════════════════════════════════════════════════════════
 *  GPIO init
 * ═══════════════════════════════════════════════════════════════ */

static void GPIO_Init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    GPIO_InitTypeDef gi = {0};

    gi.Pin   = LED_PIN;
    gi.Mode  = GPIO_MODE_OUTPUT_PP;
    gi.Pull  = GPIO_NOPULL;
    gi.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(LED_PORT, &gi);

    gi.Pin  = E22_M0_PIN;
    HAL_GPIO_Init(E22_M0_PORT, &gi);
    gi.Pin  = E22_M1_PIN;
    HAL_GPIO_Init(E22_M1_PORT, &gi);
    HAL_GPIO_WritePin(E22_M0_PORT, E22_M0_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(E22_M1_PORT, E22_M1_PIN, GPIO_PIN_SET);

    gi.Pin  = E22_AUX_PIN;
    gi.Mode = GPIO_MODE_INPUT;
    gi.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(E22_AUX_PORT, &gi);
}

/* ═══════════════════════════════════════════════════════════════
 *  UART init
 * ═══════════════════════════════════════════════════════════════ */

static void UART_Init(void)
{
    huart_e22.Instance          = E22_UART;
    huart_e22.Init.BaudRate     = E22_UART_BAUD;
    huart_e22.Init.WordLength   = UART_WORDLENGTH_8B;
    huart_e22.Init.StopBits     = UART_STOPBITS_1;
    huart_e22.Init.Parity       = UART_PARITY_NONE;
    huart_e22.Init.Mode         = UART_MODE_TX_RX;
    huart_e22.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart_e22.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart_e22);

    huart_pc.Instance          = PC_UART;
    huart_pc.Init.BaudRate     = PC_UART_BAUD;
    huart_pc.Init.WordLength   = UART_WORDLENGTH_8B;
    huart_pc.Init.StopBits     = UART_STOPBITS_1;
    huart_pc.Init.Parity       = UART_PARITY_NONE;
    huart_pc.Init.Mode         = UART_MODE_TX_RX;
    huart_pc.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart_pc.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart_pc);
}

/* ═══════════════════════════════════════════════════════════════
 *  E22 radio configuration
 * ═══════════════════════════════════════════════════════════════ */

static bool Radio_Init(void)
{
    e22.huart    = &huart_e22;
    e22.aux_port = E22_AUX_PORT;
    e22.aux_pin  = E22_AUX_PIN;
    e22.m0_port  = E22_M0_PORT;
    e22.m0_pin   = E22_M0_PIN;
    e22.m1_port  = E22_M1_PORT;
    e22.m1_pin   = E22_M1_PIN;

    e22_mode_config(&e22);

    E22_Config cfg;
    e22_default_rx_config(&cfg);
    if (!e22_write_config(&e22, &cfg)) {
        DBG("[E22] config FAILED\r\n");
        return false;
    }
    DBG("[E22] RX configured: ch=%u air=%u rssi_byte=%s\r\n",
        cfg.channel, cfg.air_rate,
        (cfg.rssi_byte & 0x80) ? "ON" : "OFF");

    e22_mode_transparent(&e22);
    return true;
}

/* ═══════════════════════════════════════════════════════════════
 *  Packet processing
 * ═══════════════════════════════════════════════════════════════ */

/*
 * Expected data from E22 with RSSI byte enabled:
 *   [0..255]  FEC packet (256 bytes)
 *   [256]     RSSI byte (1 byte, unsigned, actual = value - 256 dBm)
 *
 * Total: 257 bytes per received RF frame.
 */
#define RX_FRAME_SIZE   (FEC_PKT_SIZE + E22_RSSI_BYTE_ENABLED)

static uint8_t  fec_buf[FEC_PKT_SIZE];
static uint8_t  telem_buf[TELEM_PKT_SIZE];
static uint32_t pkt_count;

static void process_packet(void)
{
    ring_read(fec_buf, FEC_PKT_SIZE);

    int16_t rssi_val = 0;
#if E22_RSSI_BYTE_ENABLED
    uint8_t rssi_raw = ring_pop();
    rssi_val = (int16_t)rssi_raw - 256;
#endif

    /* Forward FEC packet to PC */
    HAL_UART_Transmit(&huart_pc, fec_buf, FEC_PKT_SIZE, 500);

    /* Build and send TELEM packet with RSSI */
    telem_build(telem_buf, rssi_val, 0, 0);
    HAL_UART_Transmit(&huart_pc, telem_buf, TELEM_PKT_SIZE, 100);

    pkt_count++;
    HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
}

/* ═══════════════════════════════════════════════════════════════
 *  main()
 * ═══════════════════════════════════════════════════════════════ */

int main(void)
{
    HAL_Init();
    SystemClock_Config();
    GPIO_Init();
    UART_Init();

    DBG("\r\n=== LORett StratoLink RX ===\r\n");

    if (!Radio_Init()) {
        DBG("[E22] init FAILED — running as UART bridge only\r\n");
    }

    /* Start interrupt-driven reception from E22 */
    HAL_UART_Receive_IT(&huart_e22, &rx_byte, 1);

    DBG("[RX] listening...\r\n");

    while (1) {
        /* Scan ring buffer for FEC sync pattern */
        while (ring_count() >= RX_FRAME_SIZE) {
            /* Look for FEC sync byte 0x55 followed by type 0x68 */
            if (ring_peek(0) == FEC_SYNC_BYTE &&
                ring_peek(1) == FEC_TYPE_BYTE) {
                process_packet();
            } else {
                /* Discard one byte and re-scan */
                ring_pop();
            }
        }

        /* Periodic status LED heartbeat when idle */
        static uint32_t last_hb;
        if (HAL_GetTick() - last_hb > 2000) {
            last_hb = HAL_GetTick();
            HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
        }
    }
}
