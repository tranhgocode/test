"""
Device Manager - Quản lý Sensor và Drive devices
"""
from datetime import datetime
from .modbus_handler import RS485Manager, ModbusFrame, DataParser
from .logger_handler import logger
from .config import DEVICE_SENSOR, DEVICE_DRIVE

class ModbusDevice:
    """Base class cho Modbus devices"""
    
    def __init__(self, name: str, slave_id: int, rs485_manager: RS485Manager):
        self.name = name
        self.slave_id = slave_id
        self.rs485 = rs485_manager
        
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
        success = self.rs485.ping(self.slave_id)
        
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
    
    def __init__(self, rs485_manager: RS485Manager):
        super().__init__(
            DEVICE_SENSOR["name"],
            DEVICE_SENSOR["slave_id"],
            rs485_manager
        )
    
    def read(self) -> bool:
        """Đọc Temp + Humi từ SHT20"""
        frame = ModbusFrame.build_fc04(
            self.slave_id,
            DEVICE_SENSOR["start_register"],
            DEVICE_SENSOR["count"]
        )
        
        response = self.rs485.transact(frame)
        
        if not response:
            self.timeout_count += 1
            self.last_error = self.rs485.last_error or "No response"
            self.is_connected = False
            logger.warning(f"{self.name} read timeout", "SENSOR")
            return False
        
        # Parse response
        parsed = DataParser.parse_sht20_response(response)
        
        if "error" in parsed:
            self.last_error = parsed["error"]
            if "CRC" in self.rs485.last_error:
                self.crc_error_count += 1
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
    
    def __init__(self, rs485_manager: RS485Manager):
        super().__init__(
            DEVICE_DRIVE["name"],
            DEVICE_DRIVE["slave_id"],
            rs485_manager
        )
    
    def read_status(self) -> bool:
        """Đọc status từ driver"""
        frame = ModbusFrame.build_fc03(
            self.slave_id,
            DEVICE_DRIVE["status_register"],
            1
        )
        
        response = self.rs485.transact(frame)
        
        if not response:
            self.timeout_count += 1
            self.last_error = self.rs485.last_error or "No response"
            self.is_connected = False
            logger.warning(f"{self.name} status read timeout", "DRIVE")
            return False
        
        # Parse response
        parsed = DataParser.parse_fc03_fc04(response)
        
        if "error" in parsed:
            self.last_error = parsed["error"]
            if "CRC" in self.rs485.last_error:
                self.crc_error_count += 1
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
        frame = ModbusFrame.build_fc03(
            self.slave_id,
            DEVICE_DRIVE["position_register"],
            2  # 32-bit position
        )
        
        response = self.rs485.transact(frame)
        
        if not response:
            self.last_error = self.rs485.last_error or "No response"
            logger.warning(f"{self.name} position read timeout", "DRIVE")
            return False
        
        parsed = DataParser.parse_fc03_fc04(response)
        
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
        frame = ModbusFrame.build_fc06(self.slave_id, 0x0000, 1)
        response = self.rs485.transact(frame)
        success = len(response) > 0
        
        if success:
            logger.info(f"{self.name} Step ON", "DRIVE")
        else:
            logger.warning(f"{self.name} Step ON failed", "DRIVE")
        
        return success
    
    def step_off(self) -> bool:
        """Tắt motor"""
        frame = ModbusFrame.build_fc06(self.slave_id, 0x0000, 0)
        response = self.rs485.transact(frame)
        success = len(response) > 0
        
        if success:
            logger.info(f"{self.name} Step OFF", "DRIVE")
        else:
            logger.warning(f"{self.name} Step OFF failed", "DRIVE")
        
        return success

class DeviceManager:
    """Quản lý tất cả devices"""
    
    def __init__(self, rs485_manager: RS485Manager):
        self.rs485 = rs485_manager
        self.sensor = SensorDevice(rs485_manager)
        self.drive = DriveDevice(rs485_manager)
    
    def get_all_status(self) -> dict:
        """Lấy status tất cả devices"""
        return {
            "rs485": self.rs485.get_stats(),
            "sensor": self.sensor.get_status(),
            "drive": self.drive.get_status()
        }