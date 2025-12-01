"""
Device Manager - Quản lý Sensor và Drive devices với pymodbus
"""
from datetime import datetime
from .modbus_handler import RS485Manager, ModbusTCPManager, DataParser
from .logger_handler import logger
from .config import DEVICE_SENSOR, DEVICE_DRIVE


class ModbusDevice:
    """Base class cho Modbus devices"""
    
    def __init__(self, name: str, slave_id: int, manager):
        self.name = name
        self.slave_id = slave_id
        self.manager = manager
        
        # Status tracking
        self.is_connected = False
        self.last_read_time = None
        self.ok_count = 0
        self.timeout_count = 0
        self.error_count = 0
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
            "error_count": self.error_count,
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
        result = self.manager.read_input_registers(
            self.slave_id,
            DEVICE_SENSOR["start_register"],
            DEVICE_SENSOR["count"]
        )
        
        if "error" in result:
            self.timeout_count += 1
            self.last_error = result["error"]
            self.is_connected = False
            logger.warning(f"{self.name} read failed: {self.last_error}", "SENSOR")
            return False
        
        # Parse response
        parsed = DataParser.parse_sht20_response(result["registers"])
        
        if "error" in parsed:
            self.error_count += 1
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
        result = self.manager.read_holding_registers(
            self.slave_id,
            DEVICE_DRIVE["status_register"],
            1
        )
        
        if "error" in result:
            self.timeout_count += 1
            self.last_error = result["error"]
            self.is_connected = False
            logger.warning(f"{self.name} status read failed", "DRIVE")
            return False
        
        # Decode status word
        if len(result.get("registers", [])) > 0:
            status_word = result["registers"][0]
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
        result = self.manager.read_holding_registers(
            self.slave_id,
            DEVICE_DRIVE["position_register"],
            2
        )
        
        if "error" in result:
            self.last_error = result["error"]
            logger.warning(f"{self.name} position read failed", "DRIVE")
            return False
        
        if len(result.get("registers", [])) < 2:
            self.last_error = "Insufficient registers"
            logger.warning(f"{self.name} position parse error", "DRIVE")
            return False
        
        # Combine 2 registers into 32-bit signed
        pos = DataParser.parse_position_registers(result["registers"])
        
        self.last_data["position"] = f"{pos:,} pulse"
        logger.debug(f"Position: {pos} pulse", "DRIVE")
        return True
    
    def step_on(self) -> bool:
        """Bật motor"""
        success = self.manager.write_register(self.slave_id, 0x0000, 1)
        
        if success:
            logger.info(f"{self.name} Step ON", "DRIVE")
        else:
            logger.warning(f"{self.name} Step ON failed", "DRIVE")
        
        return success
    
    def step_off(self) -> bool:
        """Tắt motor"""
        success = self.manager.write_register(self.slave_id, 0x0000, 0)
        
        if success:
            logger.info(f"{self.name} Step OFF", "DRIVE")
        else:
            logger.warning(f"{self.name} Step OFF failed", "DRIVE")
        
        return success
    
    def reset_alarm(self) -> bool:
        """Reset alarm"""
        success = self.manager.write_register(self.slave_id, 0x0001, 1)
        
        if success:
            logger.info(f"{self.name} Reset Alarm", "DRIVE")
        else:
            logger.warning(f"{self.name} Reset Alarm failed", "DRIVE")
        
        return success
    
    def move_stop(self) -> bool:
        """Dừng chuyển động"""
        success = self.manager.write_register(self.slave_id, 0x0002, 1)
        
        if success:
            logger.info(f"{self.name} Stop", "DRIVE")
        else:
            logger.warning(f"{self.name} Stop failed", "DRIVE")
        
        return success
    
    def jog_cw(self, speed_pps: int) -> bool:
        """JOG chiều CW"""
        try:
            speed_regs = DataParser.pack_u32_to_regs(speed_pps)
            registers = speed_regs + [0, 1]  # direction=1 (CW)
            
            success = self.manager.write_registers(self.slave_id, 0x30, registers)
            
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
            speed_regs = DataParser.pack_u32_to_regs(speed_pps)
            registers = speed_regs + [0, 0]  # direction=0 (CCW)
            
            success = self.manager.write_registers(self.slave_id, 0x30, registers)
            
            if success:
                logger.info(f"{self.name} JOG CCW @ {speed_pps} pps", "DRIVE")
            else:
                logger.warning(f"{self.name} JOG CCW failed", "DRIVE")
            
            return success
        except Exception as e:
            logger.error(f"JOG CCW error: {e}", "DRIVE")
            return False
    
    def move_absolute(self, position: int, speed_pps: int) -> bool:
        """Move đến vị trí tuyệt đối"""
        try:
            pos_regs = DataParser.pack_s32_to_regs(position)
            speed_regs = DataParser.pack_u32_to_regs(speed_pps)
            registers = pos_regs + speed_regs
            
            success = self.manager.write_registers(self.slave_id, 0x10, registers)
            
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
            pos_regs = DataParser.pack_s32_to_regs(offset)
            speed_regs = DataParser.pack_u32_to_regs(speed_pps)
            registers = pos_regs + speed_regs
            
            success = self.manager.write_registers(self.slave_id, 0x20, registers)
            
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
