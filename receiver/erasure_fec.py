"""Erasure-FEC передача файлов — кодирование Reed-Solomon по GF(2^8).

Файл разбивается на K блоков данных; кодер RS строит M блоков чётности по группам
(лимит GF(2^8) — 255 символов). Блоки данных распределены по группам (интерливинг).
Потеря до M_per_group блоков в группе восстанавливается декодером.

Формат пакета: 256 байт (sync 0x55, type 0x68, callsign, image_id, block_id,
k_data, n_total, file_size, file_type, m_per_group, num_groups, payload 200 Б, crc32, reserved).
"""

import struct
import zlib
import math
from dataclasses import dataclass
from typing import Optional

from reedsolo import RSCodec, ReedSolomonError

PKT_SIZE = 256
BLOCK_PAYLOAD = 200
HEADER_SIZE = 20
CRC_SIZE = 4
RESERVED_SIZE = PKT_SIZE - HEADER_SIZE - BLOCK_PAYLOAD - CRC_SIZE  # 32
RS_MAX = 255  # GF(2^8) max codeword

SYNC_BYTE = 0x55
TYPE_FEC = 0x68

FTYPE_RAW = 0x00
FTYPE_JPEG = 0x01
FTYPE_WEBP = 0x02

_BASE40 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_. "


def encode_callsign(call: str) -> int:
    call = call.upper().ljust(6)[:6]
    v = 0
    for ch in call:
        v = v * 40 + max(_BASE40.find(ch), 0)
    return v & 0xFFFFFFFF


def decode_callsign(val: int) -> str:
    chars = []
    for _ in range(6):
        chars.append(_BASE40[val % 40])
        val //= 40
    return "".join(reversed(chars)).strip()


def detect_file_type(data: bytes) -> int:
    if data[:2] == b"\xff\xd8":
        return FTYPE_JPEG
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return FTYPE_WEBP
    return FTYPE_RAW


def _rs_group_params(k: int, fec_ratio: float) -> tuple[int, int, int]:
    """Compute (g_size, m_g, num_groups) that fit GF(2^8).

    Returns the data blocks per group, parity per group, and group count.
    """
    m_desired = max(1, math.ceil(k * fec_ratio))

    if k + m_desired <= RS_MAX:
        return k, m_desired, 1

    m_g = max(1, min(round(fec_ratio * RS_MAX / (1 + fec_ratio)), 127))
    g_size = RS_MAX - m_g
    num_groups = math.ceil(k / g_size)
    return g_size, m_g, num_groups


# ═══════════════════════════════════════════════════════════════
#  FEC Packet
# ═══════════════════════════════════════════════════════════════

@dataclass
class FECPacket:
    callsign: str = ""
    image_id: int = 0
    block_id: int = 0
    k_data: int = 0
    n_total: int = 0
    file_size: int = 0
    file_type: int = 0
    m_per_group: int = 0
    num_groups: int = 1
    payload: bytes = b""

    @property
    def is_parity(self) -> bool:
        return self.block_id >= self.k_data

    # Header: >BB I B HHH I BBB  (sync, type, cs, iid, bid, k, n, fsz, ft, mg, ng)
    _HDR = ">BBIBHHHIBBB"

    def to_bytes(self) -> bytes:
        cs = encode_callsign(self.callsign)
        pl = (self.payload + b"\x00" * BLOCK_PAYLOAD)[:BLOCK_PAYLOAD]
        hdr = struct.pack(
            self._HDR,
            SYNC_BYTE, TYPE_FEC, cs,
            self.image_id & 0xFF,
            self.block_id & 0xFFFF,
            self.k_data & 0xFFFF,
            self.n_total & 0xFFFF,
            self.file_size & 0xFFFFFFFF,
            self.file_type & 0xFF,
            self.m_per_group & 0xFF,
            self.num_groups & 0xFF,
        )
        body = hdr[1:] + pl  # skip sync for CRC scope
        crc = zlib.crc32(body) & 0xFFFFFFFF
        pad = b"\x00" * RESERVED_SIZE
        return hdr + pl + struct.pack(">I", crc) + pad

    @classmethod
    def from_bytes(cls, raw: bytes) -> Optional["FECPacket"]:
        if len(raw) < PKT_SIZE or raw[0] != SYNC_BYTE or raw[1] != TYPE_FEC:
            return None
        body = raw[1 : HEADER_SIZE + BLOCK_PAYLOAD]
        expected = struct.unpack_from(">I", raw, HEADER_SIZE + BLOCK_PAYLOAD)[0]
        if (zlib.crc32(body) & 0xFFFFFFFF) != expected:
            return None
        vals = struct.unpack_from(cls._HDR, raw)
        (_, _, cs, iid, bid, k, n, fsz, ft, mg, ng) = vals
        pl = raw[HEADER_SIZE : HEADER_SIZE + BLOCK_PAYLOAD]
        return cls(
            callsign=decode_callsign(cs),
            image_id=iid, block_id=bid, k_data=k, n_total=n,
            file_size=fsz, file_type=ft,
            m_per_group=mg, num_groups=ng,
            payload=bytes(pl),
        )


# ═══════════════════════════════════════════════════════════════
#  Encoder
# ═══════════════════════════════════════════════════════════════

class ErasureEncoder:
    def __init__(self, callsign: str = "LORETT", image_id: int = 0,
                 fec_ratio: float = 0.25):
        self.callsign = callsign
        self.image_id = image_id & 0xFF
        self.fec_ratio = max(0.01, min(fec_ratio, 2.0))

    def encode_file(self, path: str) -> list[FECPacket]:
        with open(path, "rb") as f:
            return self.encode_bytes(f.read())

    def encode_bytes(self, data: bytes) -> list[FECPacket]:
        file_size = len(data)
        ftype = detect_file_type(data)
        k = max(1, math.ceil(file_size / BLOCK_PAYLOAD))

        g_size, m_g, num_groups = _rs_group_params(k, self.fec_ratio)
        m_total = num_groups * m_g
        n = k + m_total

        padded = data + b"\x00" * (k * BLOCK_PAYLOAD - file_size)
        # data_matrix[i] = list of BLOCK_PAYLOAD byte values for block i
        data_matrix = [
            list(padded[i * BLOCK_PAYLOAD : (i + 1) * BLOCK_PAYLOAD])
            for i in range(k)
        ]

        # Parity computation — per RS-group, interleaved assignment
        # Block i belongs to group (i % num_groups)
        parity_matrix: list[list[int]] = []  # flat list of parity rows
        for g in range(num_groups):
            group_indices = [i for i in range(k) if i % num_groups == g]
            gk = len(group_indices)
            pad_count = g_size - gk  # zero-padding rows to fill RS block

            rs = RSCodec(m_g)
            group_parity = [[0] * BLOCK_PAYLOAD for _ in range(m_g)]

            for col in range(BLOCK_PAYLOAD):
                col_syms = bytes(data_matrix[idx][col] for idx in group_indices)
                col_syms += b"\x00" * pad_count  # pad to g_size
                encoded = rs.encode(col_syms)
                par = encoded[g_size:]  # last m_g bytes
                for p in range(m_g):
                    group_parity[p][col] = par[p]

            parity_matrix.extend(group_parity)

        # Assemble packets
        common = dict(callsign=self.callsign, image_id=self.image_id,
                      k_data=k, n_total=n, file_size=file_size, file_type=ftype,
                      m_per_group=m_g, num_groups=num_groups)

        packets: list[FECPacket] = []
        for i in range(k):
            packets.append(FECPacket(
                block_id=i,
                payload=bytes(data_matrix[i]),
                **common,
            ))
        for p_idx, prow in enumerate(parity_matrix):
            packets.append(FECPacket(
                block_id=k + p_idx,
                payload=bytes(prow),
                **common,
            ))
        return packets


# ═══════════════════════════════════════════════════════════════
#  Decoder
# ═══════════════════════════════════════════════════════════════

class ErasureDecoder:
    def __init__(self):
        self.image_id: Optional[int] = None
        self.callsign: str = ""
        self.k_data: int = 0
        self.n_total: int = 0
        self.file_size: int = 0
        self.file_type: int = 0
        self.m_per_group: int = 0
        self.num_groups: int = 1
        self.blocks: dict[int, bytes] = {}
        self._decoded: Optional[bytes] = None

    def reset(self):
        self.image_id = None
        self.callsign = ""
        self.k_data = 0
        self.n_total = 0
        self.file_size = 0
        self.file_type = 0
        self.m_per_group = 0
        self.num_groups = 1
        self.blocks.clear()
        self._decoded = None

    def add_packet(self, pkt: FECPacket) -> bool:
        if self.image_id is not None and pkt.image_id != self.image_id:
            self.reset()
        if self.image_id is None:
            self.image_id = pkt.image_id
            self.callsign = pkt.callsign
            self.k_data = pkt.k_data
            self.n_total = pkt.n_total
            self.file_size = pkt.file_size
            self.file_type = pkt.file_type
            self.m_per_group = pkt.m_per_group
            self.num_groups = pkt.num_groups
        self.blocks[pkt.block_id] = (pkt.payload + b"\x00" * BLOCK_PAYLOAD)[:BLOCK_PAYLOAD]
        return True

    @property
    def received_count(self) -> int:
        return len(self.blocks)

    @property
    def can_decode(self) -> bool:
        return self.k_data > 0 and len(self.blocks) >= self.k_data

    @property
    def is_complete(self) -> bool:
        return self._decoded is not None

    @property
    def progress(self) -> float:
        if self.k_data == 0:
            return 0.0
        return min(len(self.blocks) / self.k_data, 1.0)

    def decode(self) -> Optional[bytes]:
        if not self.can_decode:
            return None

        k = self.k_data
        m_g = self.m_per_group
        ng = self.num_groups
        g_size = RS_MAX - m_g

        recovered = [[0] * BLOCK_PAYLOAD for _ in range(k)]

        try:
            for g in range(ng):
                group_data_ids = [i for i in range(k) if i % ng == g]
                gk = len(group_data_ids)
                pad_count = g_size - gk

                parity_start = k + g * m_g
                parity_ids = list(range(parity_start, parity_start + m_g))

                # Build erase_pos: positions 0..g_size-1 are data/padding,
                # positions g_size..g_size+m_g-1 are parity
                erase_pos = []
                for pos, did in enumerate(group_data_ids):
                    if did not in self.blocks:
                        erase_pos.append(pos)
                # Padding positions — they are known zero, NOT erasures
                for pos in range(m_g):
                    pid = parity_ids[pos]
                    if pid not in self.blocks:
                        erase_pos.append(g_size + pos)

                if len(erase_pos) > m_g:
                    return None

                rs = RSCodec(m_g)

                for col in range(BLOCK_PAYLOAD):
                    cw = bytearray(g_size + m_g)
                    for pos, did in enumerate(group_data_ids):
                        if did in self.blocks:
                            cw[pos] = self.blocks[did][col]
                    # padding positions stay zero (matching encoder)
                    for pos in range(m_g):
                        pid = parity_ids[pos]
                        if pid in self.blocks:
                            cw[g_size + pos] = self.blocks[pid][col]

                    msg, _, _ = rs.decode(cw, erase_pos=erase_pos)
                    for i, did in enumerate(group_data_ids):
                        recovered[did][col] = msg[i]

        except ReedSolomonError:
            return None

        flat = b"".join(bytes(row) for row in recovered)
        self._decoded = flat[: self.file_size]
        return self._decoded

    def assemble_partial(self) -> bytes:
        if self._decoded is not None:
            return self._decoded
        if self.k_data == 0:
            return b""
        parts = []
        for i in range(self.k_data):
            parts.append(self.blocks.get(i, b"\x00" * BLOCK_PAYLOAD))
        return b"".join(parts)[: self.file_size]
