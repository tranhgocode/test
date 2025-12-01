"""
Device Manager - Quản lý Sensor và Drive devices với đầy đủ điều khiển
"""
from datetime import datetime
from .modbus_handler import (
    RS485Manager, ModbusFrame, ModbusTCPManager, ModbusTCPFrame, DataParser
)
from .logger_handler import logger
from .config import DEVICE_SENSOR, DEVICE_DRIVE, CONNECTION_MODE

class ModbusDevice:
    """Base class cho Modbus devices"""
    
    def __init__(self, name: str, slave_id: int, manager):
        self.name = name
        self.slave_id = slave_id
        self.manager = manager
        self.is_tcp = isinstance(manager, ModbusTCPManager)
        
        # Status tracking
        self.is_connected = False
        self.last_read_time = None
        self.ok_count = 0
        self.timeout_count = 0
        self.crc_error_count = 0
        self.last_error = ""
        self.last_data = {}
    
    def ping(self) -> bool:
        """Ping device"""
        logger.info(f"Pinging {self.name} (slave {self.slave_id})", "DEVICE")
        success = self.manager.ping(self.slave_id)
        
        if success:
            self.is_connected = True
            self.ok_count += 1
            self.last_error = ""
            logger.info(f"{self.name} OK", "DEVICE")
        else:
            self.is_connected = False
            self.timeout_count += 1
            self.last_error = "Ping timeout"
            logger.warning(f"{self.name} Ping failed", "DEVICE")
        
        return success
    
    def get_status(self) -> dict:
        """Trả về status của device"""
        return {
            "name": self.name,
            "slave_id": self.slave_id,
            "connected": self.is_connected,
            "ok_count": self.ok_count,
            "timeout_count": self.timeout_count,
            "crc_error_count": self.crc_error_count,
            "last_error": self.last_error,
            "last_read": self.last_read_time.strftime("%H:%M:%S") if self.last_read_time else "Never",
            "data": self.last_data
        }

class SensorDevice(ModbusDevice):
    """SHT20 Temperature & Humidity Sensor"""
    
    def __init__(self, manager):
        super().__init__(
            DEVICE_SENSOR["name"],
            DEVICE_SENSOR["slave_id"],
            manager
        )
    
    def read(self) -> bool:
        """Đọc Temp + Humi từ SHT20"""
        if self.is_tcp:
            frame = ModbusTCPFrame.build_fc04(
                self.slave_id,
                DEVICE_SENSOR["start_register"],
                DEVICE_SENSOR["count"]
            )
        else:
            frame = ModbusFrame.build_fc04(
                self.slave_id,
                DEVICE_SENSOR["start_register"],
                DEVICE_SENSOR["count"]
            )
        
        response = self.manager.transact(frame)
        
        if not response:
            self.timeout_count += 1
            self.last_error = self.manager.last_error or "No response"
            self.is_connected = False
            logger.warning(f"{self.name} read timeout", "SENSOR")
            return False
        
        # Parse response
        parsed = DataParser.parse_sht20_response(response, self.is_tcp)
        
        if "error" in parsed:
            self.last_error = parsed["error"]
            logger.warning(f"{self.name} parse error: {parsed['error']}", "SENSOR")
            return False
        
        # Success
        self.last_data = {
            "temperature": f"{parsed['temperature_c']:.1f} °C",
            "humidity": f"{parsed['humidity_percent']:.1f} %",
            "raw": parsed
        }
        self.is_connected = True
        self.ok_count += 1
        self.last_read_time = datetime.now()
        self.last_error = ""
        
        logger.info(
            f"Temp: {parsed['temperature_c']:.1f}°C, Humi: {parsed['humidity_percent']:.1f}%",
            "SENSOR"
        )
        return True

class DriveDevice(ModbusDevice):
    """EZi-STEP Stepper Driver"""
    
    def __init__(self, manager):
        super().__init__(
            DEVICE_DRIVE["name"],
            DEVICE_DRIVE["slave_id"],
            manager
        )
    
    def read_status(self) -> bool:
        """Đọc status từ driver"""
        if self.is_tcp:
            frame = ModbusTCPFrame.build_fc03(
                self.slave_id,
                DEVICE_DRIVE["status_register"],
                1
            )
        else:
            frame = ModbusFrame.build_fc03(
                self.slave_id,
                DEVICE_DRIVE["status_register"],
                1
            )
        
        response = self.manager.transact(frame)
        
        if not response:
            self.timeout_count += 1
            self.last_error = self.manager.last_error or "No response"
            self.is_connected = False
            logger.warning(f"{self.name} status read timeout", "DRIVE")
            return False
        
        # Parse response
        parsed = DataParser.parse_fc03_fc04(response, self.is_tcp)
        
        if "error" in parsed:
            self.last_error = parsed["error"]
            logger.warning(f"{self.name} parse error: {parsed['error']}", "DRIVE")
            return False
        
        # Decode status word
        if len(parsed.get("registers", [])) > 0:
            status_word = parsed["registers"][0]
            alarm = bool(status_word & 0x8000)
            inpos = bool(status_word & 0x0010)
            running = bool(status_word & 0x0004)
            
            self.last_data = {
                "status_word": f"0x{status_word:04X}",
                "alarm": "YES" if alarm else "NO",
                "in_position": "YES" if inpos else "NO",
                "running": "YES" if running else "NO"
            }
            self.is_connected = True
            self.ok_count += 1
            self.last_read_time = datetime.now()
            self.last_error = ""
            
            logger.info(
                f"Status: Alarm={alarm}, InPos={inpos}, Running={running}",
                "DRIVE"
            )
            return True
        
        return False
    
    def read_position(self) -> bool:
        """Đọc vị trí hiện tại"""
        if self.is_tcp:
            frame = ModbusTCPFrame.build_fc03(
                self.slave_id,
                DEVICE_DRIVE["position_register"],
                2
            )
        else:
            frame = ModbusFrame.build_fc03(
                self.slave_id,
                DEVICE_DRIVE["position_register"],
                2
            )
        
        response = self.manager.transact(frame)
        
        if not response:
            self.last_error = self.manager.last_error or "No response"
            logger.warning(f"{self.name} position read timeout", "DRIVE")
            return False
        
        parsed = DataParser.parse_fc03_fc04(response, self.is_tcp)
        
        if "error" in parsed or len(parsed.get("registers", [])) < 2:
            self.last_error = parsed.get("error", "Invalid response")
            logger.warning(f"{self.name} position parse error", "DRIVE")
            return False
        
        # Combine 2 registers into 32-bit signed
        hi = parsed["registers"][0]
        lo = parsed["registers"][1]
        pos = (hi << 16) | lo
        
        # Convert to signed
        if pos & 0x80000000:
            pos = pos - (1 << 32)
        
        self.last_data["position"] = f"{pos:,} pulse"
        logger.debug(f"Position: {pos} pulse", "DRIVE")
        return True
    
    def step_on(self) -> bool:
        """Bật motor"""
        if self.is_tcp:
            frame = ModbusTCPFrame.build_fc06(self.slave_id, 0x0000, 1)
        else:
            frame = ModbusFrame.build_fc06(self.slave_id, 0x0000, 1)
        
        response = self.manager.transact(frame)
        success = len(response) > 0
        
        if success:
            logger.info(f"{self.name} Step ON", "DRIVE")
        else:
            logger.warning(f"{self.name} Step ON failed", "DRIVE")
        
        return success
    
    def step_off(self) -> bool:
        """Tắt motor"""
        if self.is_tcp:
            frame = ModbusTCPFrame.build_fc06(self.slave_id, 0x0000, 0)
        else:
            frame = ModbusFrame.build_fc06(self.slave_id, 0x0000, 0)
        
        response = self.manager.transact(frame)
        success = len(response) > 0
        
        if success:
            logger.info(f"{self.name} Step OFF", "DRIVE")
        else:
            logger.warning(f"{self.name} Step OFF failed", "DRIVE")
        
        return success
    
    def reset_alarm(self) -> bool:
        """Reset alarm"""
        if self.is_tcp:
            frame = ModbusTCPFrame.build_fc06(self.slave_id, 0x0001, 1)
        else:
            frame = ModbusFrame.build_fc06(self.slave_id, 0x0001, 1)
        
        response = self.manager.transact(frame)
        success = len(response) > 0
        
        if success:
            logger.info(f"{self.name} Reset Alarm", "DRIVE")
        else:
            logger.warning(f"{self.name} Reset Alarm failed", "DRIVE")
        
        return success
    
    def move_stop(self) -> bool:
        """Dừng chuyển động"""
        if self.is_tcp:
            frame = ModbusTCPFrame.build_fc06(self.slave_id, 0x0002, 1)
        else:
            frame = ModbusFrame.build_fc06(self.slave_id, 0x0002, 1)
        
        response = self.manager.transact(frame)
        success = len(response) > 0
        
        if success:
            logger.info(f"{self.name} Stop", "DRIVE")
        else:
            logger.warning(f"{self.name} Stop failed", "DRIVE")
        
        return success
    
    def pack_u32_to_regs(self, val: int) -> list:
        """Pack 32-bit unsigned thành 2 registers"""
        hi = (val >> 16) & 0xFFFF
        lo = val & 0xFFFF
        return [hi, lo]
    
    def pack_s32_to_regs(self, val: int) -> list:
        """Pack 32-bit signed thành 2 registers"""
        if val < 0:
            val = (1 << 32) + val
        hi = (val >> 16) & 0xFFFF
        lo = val & 0xFFFF
        return [hi, lo]
    
    def jog_cw(self, speed_pps: int) -> bool:
        """JOG chiều CW"""
        try:
            speed_regs = self.pack_u32_to_regs(speed_pps)
            registers = speed_regs + [0, 1]  # direction=1 (CW)
            
            if self.is_tcp:
                frame = ModbusTCPFrame.build_fc16(self.slave_id, 0x30, registers)
            else:
                frame = ModbusFrame.build_fc16(self.slave_id, 0x30, registers)
            
            response = self.manager.transact(frame)
            success = len(response) > 0
            
            if success:
                logger.info(f"{self.name} JOG CW @ {speed_pps} pps", "DRIVE")
            else:
                logger.warning(f"{self.name} JOG CW failed", "DRIVE")
            
            return success
        except Exception as e:
            logger.error(f"JOG CW error: {e}", "DRIVE")
            return False
    
    def jog_ccw(self, speed_pps: int) -> bool:
        """JOG chiều CCW"""
        try:
            speed_regs = self.pack_u32_to_regs(speed_pps)
            registers = speed_regs + [0, 0]  # direction=0 (CCW)
            
            if self.is_tcp:
                frame = ModbusTCPFrame.build_fc16(self.slave_id, 0x30, registers)
            else:
                frame = ModbusFrame.build_fc16(self.slave_id, 0x30, registers)
            
            response = self.manager.transact(frame)
            success = len(response) > 0
            
            if success:
                logger.info(f"{self.name} JOG CCW @ {speed_pps} pps", "DRIVE")
            else:
                logger.warning(f"{self.name} JOG CCW failed", "DRIVE")
            
            return success
        except Exception as e:
            logger.error(f"JOG CCW error: {e}", "DRIVE")
            return False
    
    def move_velocity(self, speed_pps: int, direction: int) -> bool:
        """Move ở chế độ velocity"""
        try:
            speed_regs = self.pack_u32_to_regs(speed_pps)
            registers = speed_regs + [0, direction & 0xFF]
            
            if self.is_tcp:
                frame = ModbusTCPFrame.build_fc16(self.slave_id, 0x30, registers)
            else:
                frame = ModbusFrame.build_fc16(self.slave_id, 0x30, registers)
            
            response = self.manager.transact(frame)
            success = len(response) > 0
            
            if success:
                logger.info(f"{self.name} Move Velocity: {speed_pps} pps, Dir: {direction}", "DRIVE")
            else:
                logger.warning(f"{self.name} Move Velocity failed", "DRIVE")
            
            return success
        except Exception as e:
            logger.error(f"Move Velocity error: {e}", "DRIVE")
            return False
    
    def move_absolute(self, position: int, speed_pps: int) -> bool:
        """Move đến vị trí tuyệt đối"""
        try:
            pos_regs = self.pack_s32_to_regs(position)
            speed_regs = self.pack_u32_to_regs(speed_pps)
            registers = pos_regs + speed_regs
            
            if self.is_tcp:
                frame = ModbusTCPFrame.build_fc16(self.slave_id, 0x10, registers)
            else:
                frame = ModbusFrame.build_fc16(self.slave_id, 0x10, registers)
            
            response = self.manager.transact(frame)
            success = len(response) > 0
            
            if success:
                logger.info(f"{self.name} Move Absolute: pos={position}, speed={speed_pps} pps", "DRIVE")
            else:
                logger.warning(f"{self.name} Move Absolute failed", "DRIVE")
            
            return success
        except Exception as e:
            logger.error(f"Move Absolute error: {e}", "DRIVE")
            return False
    
    def move_incremental(self, offset: int, speed_pps: int) -> bool:
        """Move tương đối (incremental)"""
        try:
            pos_regs = self.pack_s32_to_regs(offset)
            speed_regs = self.pack_u32_to_regs(speed_pps)
            registers = pos_regs + speed_regs
            
            if self.is_tcp:
                frame = ModbusTCPFrame.build_fc16(self.slave_id, 0x20, registers)
            else:
                frame = ModbusFrame.build_fc16(self.slave_id, 0x20, registers)
            
            response = self.manager.transact(frame)
            success = len(response) > 0
            
            if success:
                logger.info(f"{self.name} Move Incremental: offset={offset}, speed={speed_pps} pps", "DRIVE")
            else:
                logger.warning(f"{self.name} Move Incremental failed", "DRIVE")
            
            return success
        except Exception as e:
            logger.error(f"Move Incremental error: {e}", "DRIVE")
            return False

class DeviceManager:
    """Quản lý tất cả devices"""
    
    def __init__(self, manager):
        self.manager = manager
        self.sensor = SensorDevice(manager)
        self.drive = DriveDevice(manager)
    
    def get_all_status(self) -> dict:
        """Lấy status tất cả devices"""
        return {
            "modbus": self.manager.get_stats(),
            "sensor": self.sensor.get_status(),
            "drive": self.drive.get_status()
        }