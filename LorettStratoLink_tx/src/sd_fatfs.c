#include "sd_fatfs.h"
#include "config.h"
#include "ff.h"
#include <string.h>

/* ── HAL SD handle ────────────────────────────────────────────── */

static SD_HandleTypeDef hsd;
static FATFS            fatfs;
static DIR              dir;
static uint8_t          dir_open;

SD_HandleTypeDef *sd_get_handle(void) { return &hsd; }

/* ═══════════════════════════════════════════════════════════════
 *  FatFs R0.12c disk I/O layer (diskio.c replacement)
 * ═══════════════════════════════════════════════════════════════ */

#include "diskio.h"

DSTATUS disk_initialize(BYTE pdrv)
{
    (void)pdrv;
    return 0;
}

DSTATUS disk_status(BYTE pdrv)
{
    (void)pdrv;
    return 0;
}

DRESULT disk_read(BYTE pdrv, BYTE *buff, DWORD sector, UINT count)
{
    (void)pdrv;
    if (HAL_SD_ReadBlocks(&hsd, buff, (uint32_t)sector, count, 5000) != HAL_OK)
        return RES_ERROR;
    while (HAL_SD_GetCardState(&hsd) != HAL_SD_CARD_TRANSFER)
        ;
    return RES_OK;
}

DRESULT disk_write(BYTE pdrv, const BYTE *buff, DWORD sector, UINT count)
{
    (void)pdrv; (void)buff; (void)sector; (void)count;
    return RES_WRPRT;
}

DRESULT disk_ioctl(BYTE pdrv, BYTE cmd, void *buff)
{
    (void)pdrv;
    switch (cmd) {
    case CTRL_SYNC:
        return RES_OK;
    case GET_SECTOR_COUNT: {
        HAL_SD_CardInfoTypeDef ci;
        HAL_SD_GetCardInfo(&hsd, &ci);
        *(DWORD *)buff = ci.LogBlockNbr;
        return RES_OK;
    }
    case GET_SECTOR_SIZE:
        *(WORD *)buff = 512;
        return RES_OK;
    case GET_BLOCK_SIZE: {
        HAL_SD_CardInfoTypeDef ci;
        HAL_SD_GetCardInfo(&hsd, &ci);
        *(DWORD *)buff = ci.LogBlockSize / 512;
        return RES_OK;
    }
    default:
        return RES_PARERR;
    }
}

DWORD get_fattime(void)
{
    /* Fixed timestamp: 2026-01-01 00:00:00 */
    return ((DWORD)(2026 - 1980) << 25)
         | ((DWORD)1  << 21)
         | ((DWORD)1  << 16)
         | ((DWORD)0  << 11)
         | ((DWORD)0  << 5)
         | ((DWORD)0  << 0);
}

/* ═══════════════════════════════════════════════════════════════
 *  Public API
 * ═══════════════════════════════════════════════════════════════ */

bool sd_init(void)
{
    hsd.Instance                 = SDIO;
    hsd.Init.ClockEdge           = SDIO_CLOCK_EDGE_RISING;
    hsd.Init.ClockBypass         = SDIO_CLOCK_BYPASS_DISABLE;
    hsd.Init.ClockPowerSave      = SDIO_CLOCK_POWER_SAVE_DISABLE;
    hsd.Init.BusWide             = SDIO_BUS_WIDE_1B;
    hsd.Init.HardwareFlowControl = SDIO_HARDWARE_FLOW_CONTROL_DISABLE;
    hsd.Init.ClockDiv            = 4;

    if (HAL_SD_Init(&hsd) != HAL_OK)
        return false;

    if (HAL_SD_ConfigWideBusOperation(&hsd, SDIO_BUS_WIDE_4B) != HAL_OK) {
        /* fall back to 1-bit — not fatal */
    }

    FRESULT fr = f_mount(&fatfs, "", 1);
    if (fr != FR_OK)
        return false;

    return true;
}

void sd_rewind(void)
{
    if (dir_open) {
        f_closedir(&dir);
        dir_open = 0;
    }
}

static int is_jpeg_name(const char *fn)
{
    size_t len = strlen(fn);
    if (len < 5) return 0;
    const char *ext = fn + len - 4;
    if (ext[0] != '.') return 0;
    char e1 = ext[1] | 0x20, e2 = ext[2] | 0x20, e3 = ext[3] | 0x20;
    return (e1 == 'j' && e2 == 'p' && e3 == 'g');
}

bool sd_next_jpeg(char *name_out, uint32_t *size_out)
{
    FILINFO fno;
    FRESULT fr;

    if (!dir_open) {
        fr = f_opendir(&dir, "/");
        if (fr != FR_OK) return false;
        dir_open = 1;
    }

    while ((fr = f_readdir(&dir, &fno)) == FR_OK && fno.fname[0] != '\0') {
        if (fno.fattrib & AM_DIR)
            continue;
        if (!is_jpeg_name(fno.fname))
            continue;
        strncpy(name_out, fno.fname, 13);
        name_out[12] = '\0';
        *size_out = (uint32_t)fno.fsize;
        return true;
    }

    f_closedir(&dir);
    dir_open = 0;
    return false;
}

uint32_t sd_read_file(const char *name, uint8_t *buf, uint32_t max_len)
{
    FIL fil;
    if (f_open(&fil, name, FA_READ) != FR_OK)
        return 0;

    UINT br = 0;
    f_read(&fil, buf, max_len, &br);
    f_close(&fil);
    return (uint32_t)br;
}
