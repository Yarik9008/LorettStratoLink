#include "stm32f4xx_hal.h"
#include "config.h"
#include "gf256.h"
#include "rs_encode.h"
#include "fec_packet.h"
#include "e22_driver.h"
#include "sd_fatfs.h"
#include <string.h>
#include <stdio.h>

/* ═══════════════════════════════════════════════════════════════
 *  Peripheral handles
 * ═══════════════════════════════════════════════════════════════ */

static UART_HandleTypeDef huart_e22;
static UART_HandleTypeDef huart_dbg;
static E22_Handle         e22;

/* ═══════════════════════════════════════════════════════════════
 *  Buffers
 * ═══════════════════════════════════════════════════════════════ */

static uint8_t  file_buf[FILE_BUF_MAX];
static uint8_t  parity_buf[MAX_PARITY_PER_GROUP][BLOCK_PAYLOAD];
static uint8_t  pkt_buf[PKT_SIZE];
static uint8_t  rs_gen[MAX_PARITY_PER_GROUP + 1];

/* debug printf via UART2 */
static char dbg_line[128];
#define DBG(fmt, ...) do {                                         \
    int _n = snprintf(dbg_line, sizeof(dbg_line), fmt, ##__VA_ARGS__); \
    HAL_UART_Transmit(&huart_dbg, (uint8_t*)dbg_line,              \
                      (uint16_t)_n, 50);                           \
} while(0)

/* ═══════════════════════════════════════════════════════════════
 *  System clock: HSI 16 MHz → PLL → 180 MHz SYSCLK
 * ═══════════════════════════════════════════════════════════════ */

static void SystemClock_Config(void)
{
    RCC_OscInitTypeDef osc = {0};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState       = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState   = RCC_PLL_ON;
    osc.PLL.PLLSource  = RCC_PLLSOURCE_HSI;
    osc.PLL.PLLM       = 16;
    osc.PLL.PLLN       = 360;
    osc.PLL.PLLP       = RCC_PLLP_DIV2;    /* 180 MHz */
    osc.PLL.PLLQ       = 8;                /* 45 MHz for SDIO */
    HAL_RCC_OscConfig(&osc);

    HAL_PWREx_EnableOverDrive();

    RCC_ClkInitTypeDef clk = {0};
    clk.ClockType      = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                          RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource   = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider  = RCC_SYSCLK_DIV1;      /* 180 MHz */
    clk.APB1CLKDivider = RCC_HCLK_DIV4;         /* 45  MHz */
    clk.APB2CLKDivider = RCC_HCLK_DIV2;         /* 90  MHz */
    HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_5);
}

/* ═══════════════════════════════════════════════════════════════
 *  GPIO init (LED, E22 control lines)
 * ═══════════════════════════════════════════════════════════════ */

static void GPIO_Init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    GPIO_InitTypeDef gi = {0};

    /* LED */
    gi.Pin   = LED_PIN;
    gi.Mode  = GPIO_MODE_OUTPUT_PP;
    gi.Pull  = GPIO_NOPULL;
    gi.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(LED_PORT, &gi);

    /* E22 M0, M1 — outputs, default HIGH (config mode at boot) */
    gi.Pin  = E22_M0_PIN;
    HAL_GPIO_Init(E22_M0_PORT, &gi);
    gi.Pin  = E22_M1_PIN;
    HAL_GPIO_Init(E22_M1_PORT, &gi);
    HAL_GPIO_WritePin(E22_M0_PORT, E22_M0_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(E22_M1_PORT, E22_M1_PIN, GPIO_PIN_SET);

    /* E22 AUX — input */
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
    /* E22 UART */
    huart_e22.Instance          = E22_UART;
    huart_e22.Init.BaudRate     = E22_UART_BAUD;
    huart_e22.Init.WordLength   = UART_WORDLENGTH_8B;
    huart_e22.Init.StopBits     = UART_STOPBITS_1;
    huart_e22.Init.Parity       = UART_PARITY_NONE;
    huart_e22.Init.Mode         = UART_MODE_TX_RX;
    huart_e22.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart_e22.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart_e22);

    /* Debug UART */
    huart_dbg.Instance          = DBG_UART;
    huart_dbg.Init.BaudRate     = DBG_UART_BAUD;
    huart_dbg.Init.WordLength   = UART_WORDLENGTH_8B;
    huart_dbg.Init.StopBits     = UART_STOPBITS_1;
    huart_dbg.Init.Parity       = UART_PARITY_NONE;
    huart_dbg.Init.Mode         = UART_MODE_TX_RX;
    huart_dbg.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart_dbg.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart_dbg);
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
    e22_default_tx_config(&cfg);
    if (!e22_write_config(&e22, &cfg)) {
        DBG("[E22] config write FAILED\r\n");
        return false;
    }
    DBG("[E22] configured: ch=%u air=%u pwr=%u\r\n",
        cfg.channel, cfg.air_rate, cfg.tx_power);

    e22_mode_transparent(&e22);
    return true;
}

/* ═══════════════════════════════════════════════════════════════
 *  FEC encoding & transmission of one file
 * ═══════════════════════════════════════════════════════════════ */

static uint8_t image_id_counter = 0;

static void transmit_file(const uint8_t *data, uint32_t file_size)
{
    uint8_t ftype = detect_file_type(data, file_size);
    int k = (int)((file_size + BLOCK_PAYLOAD - 1) / BLOCK_PAYLOAD);
    if (k < 1) k = 1;

    int gs, mg, ng;
    fec_group_params(k, DEFAULT_FEC_RATIO_NUM, DEFAULT_FEC_RATIO_DEN,
                     &gs, &mg, &ng);
    int n = k + ng * mg;

    uint32_t cs_enc = callsign_encode(DEFAULT_CALLSIGN);
    uint8_t  iid    = image_id_counter++;

    DBG("[TX] file %u bytes, K=%d N=%d mg=%d ng=%d\r\n",
        (unsigned)file_size, k, n, mg, ng);

    /* ── Transmit K data blocks ──────────────────────────────── */
    for (int i = 0; i < k; i++) {
        const uint8_t *payload = data + (uint32_t)i * BLOCK_PAYLOAD;
        uint8_t block[BLOCK_PAYLOAD];
        uint32_t off = (uint32_t)i * BLOCK_PAYLOAD;
        uint32_t avail = (off + BLOCK_PAYLOAD <= file_size)
                         ? BLOCK_PAYLOAD : (file_size - off);
        memcpy(block, payload, avail);
        if (avail < BLOCK_PAYLOAD)
            memset(block + avail, 0, BLOCK_PAYLOAD - avail);

        FecPacketInfo pi = {
            .callsign_enc = cs_enc,
            .image_id     = iid,
            .block_id     = (uint16_t)i,
            .k_data       = (uint16_t)k,
            .n_total      = (uint16_t)n,
            .file_size    = file_size,
            .file_type    = ftype,
            .m_per_group  = (uint8_t)mg,
            .num_groups   = (uint8_t)ng,
            .payload      = block,
        };
        fec_build_packet(&pi, pkt_buf);
        e22_transmit(&e22, pkt_buf, PKT_SIZE, 2000);

        HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
        HAL_Delay(INTER_PACKET_DELAY_MS);
    }

    /* ── Compute and transmit parity blocks per RS group ─────── */
    rs_generator_poly(mg, rs_gen);

    for (int g = 0; g < ng; g++) {
        /* count data blocks belonging to this group */
        int gk = 0;
        for (int i = g; i < k; i += ng) gk++;
        int pad_count = gs - gk;

        memset(parity_buf, 0, (size_t)mg * BLOCK_PAYLOAD);

        /* RS encode column by column */
        uint8_t col_msg[RS_MAX];
        uint8_t col_par[MAX_PARITY_PER_GROUP];

        for (int col = 0; col < BLOCK_PAYLOAD; col++) {
            int pos = 0;
            for (int i = g; i < k; i += ng) {
                uint32_t off = (uint32_t)i * BLOCK_PAYLOAD + (uint32_t)col;
                col_msg[pos++] = (off < file_size) ? data[off] : 0;
            }
            for (int p = 0; p < pad_count; p++)
                col_msg[pos++] = 0;

            rs_encode_msg(col_msg, gs, mg, rs_gen, col_par);

            for (int p = 0; p < mg; p++)
                parity_buf[p][col] = col_par[p];
        }

        /* transmit parity blocks for this group */
        int parity_base = k + g * mg;
        for (int p = 0; p < mg; p++) {
            FecPacketInfo pi = {
                .callsign_enc = cs_enc,
                .image_id     = iid,
                .block_id     = (uint16_t)(parity_base + p),
                .k_data       = (uint16_t)k,
                .n_total      = (uint16_t)n,
                .file_size    = file_size,
                .file_type    = ftype,
                .m_per_group  = (uint8_t)mg,
                .num_groups   = (uint8_t)ng,
                .payload      = parity_buf[p],
            };
            fec_build_packet(&pi, pkt_buf);
            e22_transmit(&e22, pkt_buf, PKT_SIZE, 2000);

            HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
            HAL_Delay(INTER_PACKET_DELAY_MS);
        }
    }

    DBG("[TX] file done, %d packets sent\r\n", n);
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

    gf256_init();
    crc32_init_table();

    DBG("\r\n=== LORett StratoLink TX ===\r\n");

    /* ── SD card ──────────────────────────────────────────────── */
    if (!sd_init()) {
        DBG("[SD] init FAILED\r\n");
        while (1) {
            HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
            HAL_Delay(200);
        }
    }
    DBG("[SD] mounted OK\r\n");

    /* ── Radio module ─────────────────────────────────────────── */
    if (!Radio_Init()) {
        DBG("[E22] init FAILED — continuing without radio\r\n");
    }

    /* ── Main loop: enumerate JPEG files and transmit ─────────── */
    while (1) {
        sd_rewind();

        char     fname[13];
        uint32_t fsize;
        int      file_count = 0;

        while (sd_next_jpeg(fname, &fsize)) {
            DBG("[FILE] %s  %lu bytes\r\n", fname, (unsigned long)fsize);

            if (fsize > FILE_BUF_MAX) {
                DBG("[FILE] too large, skipping\r\n");
                continue;
            }

            uint32_t rd = sd_read_file(fname, file_buf, FILE_BUF_MAX);
            if (rd == 0) {
                DBG("[FILE] read error\r\n");
                continue;
            }

            transmit_file(file_buf, rd);
            file_count++;

            HAL_Delay(1000);
        }

        if (file_count == 0)
            DBG("[FILE] no JPEG files found\r\n");

        DBG("[TX] cycle complete, %d files\r\n", file_count);

        /* Pause before repeating the cycle */
        HAL_Delay(5000);
    }
}
