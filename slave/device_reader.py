# ============================================================================
# FILE: slave/device_reader.py
# ============================================================================
"""
Device Reader - Đọc dữ liệu từ thiết bị thực
"""
from .config import (
    SLAVE_ID_DRIVER, SLAVE_ID_SHT20,
    REG_POSITION_FEEDBACK, REG_TEMP_SENSOR, REG_HUMI_SENSOR, REG_DRIVE_STATUS,
    DI_READY, DI_FAULT
)
from .utils import build_fc03, build_fc04

class DeviceReader:
    """Đọc dữ liệu từ thiết bị thực qua serial."""
    
    def __init__(self, memory, serial_worker, signals):
        self.memory = memory
        self.serial_worker = serial_worker
        self.signals = signals
    
    def read_sht20(self) -> dict:
        """Đọc SHT20 (Temp + Humi)."""
        frame = build_fc04(SLAVE_ID_SHT20, 0x0001, 0x0002)
        resp = self.serial_worker.send_frame(frame)
        
        result = {"success": False, "temp": 0, "humi": 0}
        
        if len(resp) >= 9 and resp[1] == 0x04:
            try:
                temp_raw = (resp[3] << 8) | resp[4]
                humi_raw = (resp[5] << 8) | resp[6]
                
                result["success"] = True
                result["temp"] = temp_raw
                result["humi"] = humi_raw
                
                self.memory.write_input_register(REG_TEMP_SENSOR, temp_raw)
                self.memory.write_input_register(REG_HUMI_SENSOR, humi_raw)
                
                self.signals.event_logged.emit(f"✓ SHT20: Temp={temp_raw/10:.1f}°C Humi={humi_raw/10:.1f}%")
            except Exception as e:
                self.signals.event_logged.emit(f"✗ SHT20 error: {e}")
        else:
            self.signals.event_logged.emit("✗ SHT20 NO RESPONSE")
        
        return result
    
    def read_drive_position(self) -> dict:
        """Đọc vị trí động cơ."""
        frame = build_fc03(SLAVE_ID_DRIVER, 0x1000, 2)
        resp = self.serial_worker.send_frame(frame)
        
        result = {"success": False, "position": 0}
        
        if len(resp) >= 9 and resp[1] == 0x03:
            try:
                pos_hi = (resp[3] << 8) | resp[4]
                pos_lo = (resp[5] << 8) | resp[6]
                position = (pos_hi << 16) | pos_lo
                
                if position & 0x80000000:
                    position = position - (1 << 32)
                
                result["success"] = True
                result["position"] = position
                
                self.memory.write_input_register(REG_POSITION_FEEDBACK, pos_hi)
                self.memory.write_input_register(REG_POSITION_FEEDBACK + 1, pos_lo)
                
                self.signals.event_logged.emit(f"✓ Drive Position: {position} pulse")
            except Exception as e:
                self.signals.event_logged.emit(f"✗ Drive position error: {e}")
        else:
            self.signals.event_logged.emit("✗ Drive NO RESPONSE")
        
        return result
    
    def read_drive_status(self) -> dict:
        """Đọc trạng thái động cơ."""
        frame = build_fc03(SLAVE_ID_DRIVER, 0x1010, 1)
        resp = self.serial_worker.send_frame(frame)
        
        result = {"success": False, "status": 0}
        
        if len(resp) >= 7 and resp[1] == 0x03:
            try:
                status_word = (resp[3] << 8) | resp[4]
                result["success"] = True
                result["status"] = status_word
                
                self.memory.write_input_register(REG_DRIVE_STATUS, status_word)
                
                alarm = (status_word >> 8) & 0xFF
                inpos = (status_word >> 4) & 0x0F
                running = (status_word >> 2) & 0x03
                
                status_str = f"Alarm={'YES' if alarm else 'NO'} InPos={'YES' if inpos else 'NO'} Run={'YES' if running else 'NO'}"
                self.signals.event_logged.emit(f"✓ Drive Status: {status_str}")
                
                self.memory.write_discrete_input(DI_FAULT, bool(alarm))
                self.memory.write_discrete_input(DI_READY, not bool(alarm))
            except Exception as e:
                self.signals.event_logged.emit(f"✗ Drive status error: {e}")
        else:
            self.signals.event_logged.emit("✗ Drive status NO RESPONSE")
        
        return result