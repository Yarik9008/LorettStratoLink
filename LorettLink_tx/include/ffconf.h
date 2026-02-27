/*
 * FatFs R0.12c configuration — read-only, FAT32, minimal footprint.
 * Must match framework-stm32cubef4 FatFs revision 68300.
 */

#define _FFCONF 68300   /* Must match ff.h _FATFS value */

/* ── Function configuration ───────────────────────────────────── */
#define _FS_READONLY    1       /* Read-only: no write functions */
#define _FS_MINIMIZE    0       /* 0 = all read features enabled */
#define _USE_STRFUNC    0
#define _USE_FIND       1       /* f_findfirst / f_findnext */
#define _USE_MKFS       0
#define _USE_FASTSEEK   0
#define _USE_EXPAND     0
#define _USE_CHMOD      0
#define _USE_LABEL      0
#define _USE_FORWARD    0

/* ── Locale and namespace ─────────────────────────────────────── */
#define _CODE_PAGE      1       /* 1 = ASCII only (no extended chars, saves flash) */
#define _USE_LFN        0       /* 0 = 8.3 names only (saves RAM) */
#define _MAX_LFN        255
#define _LFN_UNICODE    0
#define _STRF_ENCODE    0
#define _FS_RPATH       0

/* ── Drive / volume ───────────────────────────────────────────── */
#define _VOLUMES        1
#define _STR_VOLUME_ID  0
#define _MULTI_PARTITION 0
#define _MIN_SS         512
#define _MAX_SS         512
#define _USE_TRIM       0
#define _FS_NOFSINFO    0

/* ── System ───────────────────────────────────────────────────── */
#define _FS_TINY        1       /* Tiny config — less RAM */
#define _FS_EXFAT       0
#define _FS_NORTC       1       /* No RTC */
#define _NORTC_MON      1
#define _NORTC_MDAY     1
#define _NORTC_YEAR     2026
#define _FS_LOCK        0
#define _FS_REENTRANT   0
