/*
 * Minimal newlib syscall stubs for bare-metal STM32.
 * Required by snprintf / printf from <stdio.h>.
 */

#include <sys/stat.h>
#include <errno.h>
#include <stdint.h>

extern uint32_t _end;      /* provided by linker script */
static uint8_t *heap_ptr = (uint8_t *)&_end;

void *_sbrk(int incr)
{
    uint8_t *prev = heap_ptr;
    heap_ptr += incr;
    return prev;
}

int _close(int fd)   { (void)fd; return -1; }
int _fstat(int fd, struct stat *st) { (void)fd; st->st_mode = S_IFCHR; return 0; }
int _isatty(int fd)  { (void)fd; return 1; }
int _lseek(int fd, int ptr, int dir) { (void)fd; (void)ptr; (void)dir; return 0; }
int _read(int fd, char *buf, int len) { (void)fd; (void)buf; (void)len; return 0; }
int _write(int fd, char *buf, int len) { (void)fd; (void)buf; return len; }
void _exit(int status) { (void)status; while(1); }
int _kill(int pid, int sig) { (void)pid; (void)sig; errno = EINVAL; return -1; }
int _getpid(void) { return 1; }
