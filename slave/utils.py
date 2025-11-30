# ============================================================================
# FILE: slave/utils.py
# ============================================================================
"""
Utility functions for Modbus RTU
"""

def crc16_modbus(data: bytes) -> int:
    """Tính toán Modbus CRC16."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_fc03(slave_id: int, start_reg: int, count: int) -> bytes:
    """Xây dựng gói tin Modbus FC03 (Read Holding Registers)."""
    data = bytes([
        slave_id,
        0x03,
        (start_reg >> 8) & 0xFF,
        start_reg & 0xFF,
        (count >> 8) & 0xFF,
        count & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_fc04(slave_id: int, start_reg: int, count: int) -> bytes:
    """Xây dựng gói tin Modbus FC04 (Read Input Registers)."""
    data = bytes([
        slave_id,
        0x04,
        (start_reg >> 8) & 0xFF,
        start_reg & 0xFF,
        (count >> 8) & 0xFF,
        count & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def unpack_s32_from_bytes(b: bytes, offset: int) -> int:
    """Unpack signed 32-bit từ Modbus payload."""
    val = (b[offset] << 24) | (b[offset+1] << 16) | (b[offset+2] << 8) | b[offset+3]
    if val & 0x80000000:
        val = val - (1 << 32)
    return val


def pack_u32_to_regs(val: int) -> list:
    """Chia giá trị 32-bit thành 2 register 16-bit."""
    hi = (val >> 16) & 0xFFFF
    lo = val & 0xFFFF
    return [hi, lo]