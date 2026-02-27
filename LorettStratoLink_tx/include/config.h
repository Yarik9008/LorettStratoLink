#ifndef CONFIG_H
#define CONFIG_H

#include "stm32f4xx_hal.h"

/* ── Pin assignments ─────────────────────────────────────────── */

/* USART1 — E22 radio module */
#define E22_UART                USART1
#define E22_UART_IRQn           USART1_IRQn
#define E22_UART_TX_PIN         GPIO_PIN_9
#define E22_UART_RX_PIN         GPIO_PIN_10
#define E22_UART_PORT           GPIOA
#define E22_UART_AF             GPIO_AF7_USART1
#define E22_UART_BAUD           9600

/* USART2 — debug log output */
#define DBG_UART                USART2
#define DBG_UART_IRQn           USART2_IRQn
#define DBG_UART_TX_PIN         GPIO_PIN_2
#define DBG_UART_RX_PIN         GPIO_PIN_3
#define DBG_UART_PORT           GPIOA
#define DBG_UART_AF             GPIO_AF7_USART2
#define DBG_UART_BAUD           115200

/* E22 control lines */
#define E22_AUX_PIN             GPIO_PIN_0
#define E22_AUX_PORT            GPIOB
#define E22_M0_PIN              GPIO_PIN_1
#define E22_M0_PORT             GPIOB
#define E22_M1_PIN              GPIO_PIN_2
#define E22_M1_PORT             GPIOB

/* Status LED */
#define LED_PIN                 GPIO_PIN_5
#define LED_PORT                GPIOA

/* SDIO (directly used by HAL, pins listed for reference):
 *   PC8  = D0,  PC9  = D1,  PC10 = D2,  PC11 = D3
 *   PC12 = CK,  PD2  = CMD                           */

/* ── Protocol constants (must match Python ground station) ──── */

#define PKT_SIZE                256
#define BLOCK_PAYLOAD           200
#define HEADER_SIZE             20
#define CRC_SIZE                4
#define RESERVED_SIZE           (PKT_SIZE - HEADER_SIZE - BLOCK_PAYLOAD - CRC_SIZE)
#define RS_MAX                  255

#define SYNC_BYTE               0x55
#define TYPE_FEC                0x68

#define FTYPE_RAW               0x00
#define FTYPE_JPEG              0x01
#define FTYPE_WEBP              0x02

/* ── Transmission parameters ─────────────────────────────────── */

#define DEFAULT_CALLSIGN        "LORETT"
#define DEFAULT_FEC_RATIO_NUM   25      /* 25 / 100 = 0.25 */
#define DEFAULT_FEC_RATIO_DEN   100
#define INTER_PACKET_DELAY_MS   50
#define FILE_BUF_MAX            65536   /* max JPEG file size in RAM */
#define MAX_PARITY_PER_GROUP    128
#define WINDOW_SIZE             64

/* ── E22 register map ─────────────────────────────────────────── */

#define E22_CMD_WRITE           0xC0
#define E22_CMD_READ            0xC1
#define E22_REG_ADDH            0x00
#define E22_REG_ADDL            0x01
#define E22_REG_NETID           0x02
#define E22_REG_REG0            0x03
#define E22_REG_REG1            0x04
#define E22_REG_CH              0x05
#define E22_REG_REG3            0x06
#define E22_REG_CRYPT_H         0x07
#define E22_REG_CRYPT_L         0x08

/* REG0 bit fields */
#define E22_BAUD_9600           (0x03 << 5)
#define E22_BAUD_115200         (0x07 << 5)
#define E22_PARITY_8N1          (0x00 << 3)
#define E22_AIRRATE_2K4         0x02
#define E22_AIRRATE_4K8         0x03
#define E22_AIRRATE_9K6         0x04
#define E22_AIRRATE_19K2        0x05
#define E22_AIRRATE_62K5        0x07

/* REG1 bit fields */
#define E22_SUBPKT_240          (0x00 << 6)
#define E22_RSSI_NOISE_OFF      (0x00 << 5)
#define E22_TXPWR_33DBM         0x00
#define E22_TXPWR_30DBM         0x01
#define E22_TXPWR_27DBM         0x02

/* REG3 bit fields */
#define E22_RSSI_BYTE_OFF       (0x00 << 7)
#define E22_RSSI_BYTE_ON        (0x01 << 7)
#define E22_TX_TRANSPARENT      (0x00 << 6)
#define E22_WOR_2000MS          0x03

/* Default radio config */
#define E22_DEFAULT_CHANNEL     0x17    /* channel 23 — adjust per band plan */
#define E22_DEFAULT_AIRRATE     E22_AIRRATE_9K6

#endif /* CONFIG_H */
