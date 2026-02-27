"""Транспорт LorettLink — разбор потока на FEC-пакеты (256 Б) и TELEM (10 Б, sync 0xA55A)."""

import struct
from dataclasses import dataclass

from erasure_fec import FECPacket, PKT_SIZE, SYNC_BYTE as FEC_SYNC, TYPE_FEC

# ═══════════════════════════════════════════════════════════════
#  TELEM (sync 0xA55A)
# ═══════════════════════════════════════════════════════════════

TELEM_SYNC = 0xA55A
TELEM_SYNC_BYTES = struct.pack("<H", TELEM_SYNC)
TELEM_TYPE = 0x30
TELEM_LEN = 10
PROTO_VER = 0x01


def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


@dataclass
class TelemInfo:
    rssi: int = 0
    snr: int = 0
    tx_power: int = 0


def build_telem(rssi: int, snr: int, tx_power: int) -> bytes:
    body = struct.pack("<BBhbB", PROTO_VER, TELEM_TYPE, rssi, snr, tx_power)
    crc = crc16_ccitt(body)
    return struct.pack("<H", TELEM_SYNC) + body + struct.pack("<H", crc)


# ═══════════════════════════════════════════════════════════════
#  Stream parser (FEC + TELEM)
# ═══════════════════════════════════════════════════════════════

class StreamParser:
    def __init__(self):
        self._buf = bytearray()

    def reset(self):
        self._buf.clear()

    def feed(self, data: bytes) -> list:
        self._buf.extend(data)
        results: list = []

        while len(self._buf) >= 2:
            fec_idx = self._buf.find(bytes([FEC_SYNC]))
            telem_idx = self._buf.find(TELEM_SYNC_BYTES)

            candidates = []
            if fec_idx >= 0:
                candidates.append(fec_idx)
            if telem_idx >= 0:
                candidates.append(telem_idx)
            if not candidates:
                self._buf.clear()
                break

            first = min(candidates)
            if first > 0:
                self._buf = self._buf[first:]
                continue

            if self._buf[0] == FEC_SYNC and self._buf[1] == TYPE_FEC:
                if len(self._buf) < PKT_SIZE:
                    break
                raw = bytes(self._buf[:PKT_SIZE])
                pkt = FECPacket.from_bytes(raw)
                if pkt is not None:
                    results.append(pkt)
                    self._buf = self._buf[PKT_SIZE:]
                else:
                    self._buf = self._buf[1:]
                continue

            # TELEM packet: 0x5A 0xA5
            if len(self._buf) >= 2 and self._buf[0:2] == TELEM_SYNC_BYTES:
                if len(self._buf) < TELEM_LEN:
                    break
                raw = bytes(self._buf[:TELEM_LEN])
                body = raw[2:-2]
                expected = struct.unpack_from("<H", raw, TELEM_LEN - 2)[0]
                if crc16_ccitt(body) == expected:
                    _, _, _, rssi, snr, txp, _ = struct.unpack("<HBBhbBH", raw)
                    results.append(TelemInfo(rssi, snr, txp))
                    self._buf = self._buf[TELEM_LEN:]
                else:
                    self._buf = self._buf[2:]
                continue

            self._buf = self._buf[1:]

        if len(self._buf) > 0x10000:
            self._buf = self._buf[-4096:]
        return results
