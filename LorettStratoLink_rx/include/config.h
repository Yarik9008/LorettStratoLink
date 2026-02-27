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

/* USART2 — PC output (USB-UART bridge) */
#define PC_UART                 USART2
#define PC_UART_IRQn            USART2_IRQn
#define PC_UART_TX_PIN          GPIO_PIN_2
#define PC_UART_RX_PIN          GPIO_PIN_3
#define PC_UART_PORT            GPIOA
#define PC_UART_AF              GPIO_AF7_USART2
#define PC_UART_BAUD            115200

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

/* ── Protocol constants ───────────────────────────────────────── */

#define FEC_PKT_SIZE            256
#define FEC_SYNC_BYTE           0x55
#define FEC_TYPE_BYTE           0x68

/* RSSI byte appended by E22 when RSSI_BYTE_ON (1 extra byte) */
#define E22_RSSI_BYTE_ENABLED   1

/* Ring buffer for E22 UART RX */
#define RX_RING_SIZE            1024

/* TELEM packet constants (must match Python ground station) */
#define TELEM_SYNC              0xA55A
#define TELEM_PROTO_VER         0x01
#define TELEM_TYPE_ID           0x30
#define TELEM_PKT_SIZE          10

/* ── E22 register definitions (same as TX) ────────────────────── */

#define E22_CMD_WRITE           0xC0
#define E22_CMD_READ            0xC1
#define E22_REG_ADDH            0x00

#define E22_BAUD_9600           (0x03 << 5)
#define E22_PARITY_8N1          (0x00 << 3)
#define E22_AIRRATE_9K6         0x04
#define E22_SUBPKT_240          (0x00 << 6)
#define E22_RSSI_NOISE_OFF      (0x00 << 5)
#define E22_TXPWR_33DBM         0x00
#define E22_RSSI_BYTE_OFF       (0x00 << 7)
#define E22_RSSI_BYTE_ON        (0x01 << 7)
#define E22_TX_TRANSPARENT      (0x00 << 6)
#define E22_WOR_2000MS          0x03

#define E22_DEFAULT_CHANNEL     0x17
#define E22_DEFAULT_AIRRATE     E22_AIRRATE_9K6

#endif /* CONFIG_H */
