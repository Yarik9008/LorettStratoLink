#ifndef SD_FATFS_H
#define SD_FATFS_H

#include "stm32f4xx_hal.h"
#include <stdbool.h>
#include <stdint.h>

/*
 * SD card access via SDIO + FatFs wrapper.
 *
 * Provides:
 *   - SD card initialisation (HAL_SD + FatFs mount)
 *   - JPEG file enumeration on root directory
 *   - File read into RAM buffer
 */

/* Initialise SDIO peripheral and mount FAT32 volume.
 * Returns true on success. */
bool sd_init(void);

/* Rewind enumeration to the first JPEG file on the card. */
void sd_rewind(void);

/* Open the next *.JPG file on the card.
 * On success: stores filename (8.3) into name_out (at least 13 chars),
 *             stores file size into *size_out, returns true.
 * On end-of-list: returns false. */
bool sd_next_jpeg(char *name_out, uint32_t *size_out);

/* Read the entire currently-enumerated file into buf.
 * buf must be at least *size_out bytes.
 * Returns number of bytes actually read, or 0 on error. */
uint32_t sd_read_file(const char *name, uint8_t *buf, uint32_t max_len);

/* Get the HAL SD handle (for MSP callbacks). */
SD_HandleTypeDef *sd_get_handle(void);

#endif /* SD_FATFS_H */
