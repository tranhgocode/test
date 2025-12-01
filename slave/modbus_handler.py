"""
Modbus Handler - Sử dụng pymodbus cho RS-485 Serial RTU + Modbus TCP
"""
import time
from datetime import datetime
from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException
from .logger_handler import logger


class ModbusClientManager:
    """Base class quản lý Modbus Client với pymodbus"""
    
    def __init__(self):
        self.client = None
        self.is_open = False
        
        # Statistics
        self.tx_count = 0
        self.rx_count = 0
        self.timeout_count = 0
        self.error_count = 0
        self.last_tx_frame = ""
        self.last_rx_frame = ""
        self.last_error = ""
        self.last_success_time = None
    
    def open(self) -> bool:
        """Mở kết nối - override trong subclass"""
        raise NotImplementedError
    
    def close(self):
        """Đóng kết nối"""
        if self.client:
            self.client.close()
            self.is_open = False
    
    def _log_transaction(self, request_type: str, success: bool):
        """Log transaction details"""
        self.tx_count += 1
        if success:
            self.rx_count += 1
            self.last_success_time = datetime.now()
            self.last_error = ""
        else:
            self.timeout_count += 1
    
    def read_holding_registers(self, slave_id: int, address: int, count: int) -> dict:
        """FC03: Read Holding Registers"""
        if not self.is_open or not self.client:
            self.last_error = "Not connected"
            return {"error": self.last_error}
        
        try:
            self.last_tx_frame = f"FC03 Slave={slave_id} Addr=0x{address:04X} Count={count}"
            
            result = self.client.read_holding_registers(
                address=address,
                count=count,
                slave=slave_id
            )
            
            if result.isError():
                self.timeout_count += 1
                self.last_error = f"Modbus Error: {result}"
                self.last_rx_frame = "ERROR"
                logger.warning(f"FC03 failed: {self.last_error}", "MODBUS")
                return {"error": self.last_error}
            
            self._log_transaction("FC03", True)
            registers = result.registers
            self.last_rx_frame = f"FC03 OK: {len(registers)} regs"
            
            logger.debug(f"FC03: Slave {slave_id}, {len(registers)} registers read", "MODBUS")
            
            return {
                "registers": registers,
                "count": len(registers)
            }
            
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            self.last_rx_frame = "EXCEPTION"
            logger.error(f"FC03 exception: {e}", "MODBUS")
            return {"error": str(e)}
    
    def read_input_registers(self, slave_id: int, address: int, count: int) -> dict:
        """FC04: Read Input Registers"""
        if not self.is_open or not self.client:
            self.last_error = "Not connected"
            return {"error": self.last_error}
        
        try:
            self.last_tx_frame = f"FC04 Slave={slave_id} Addr=0x{address:04X} Count={count}"
            
            result = self.client.read_input_registers(
                address=address,
                count=count,
                slave=slave_id
            )
            
            if result.isError():
                self.timeout_count += 1
                self.last_error = f"Modbus Error: {result}"
                self.last_rx_frame = "ERROR"
                logger.warning(f"FC04 failed: {self.last_error}", "MODBUS")
                return {"error": self.last_error}
            
            self._log_transaction("FC04", True)
            registers = result.registers
            self.last_rx_frame = f"FC04 OK: {len(registers)} regs"
            
            logger.debug(f"FC04: Slave {slave_id}, {len(registers)} registers read", "MODBUS")
            
            return {
                "registers": registers,
                "count": len(registers)
            }
            
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            self.last_rx_frame = "EXCEPTION"
            logger.error(f"FC04 exception: {e}", "MODBUS")
            return {"error": str(e)}
    
    def write_register(self, slave_id: int, address: int, value: int) -> bool:
        """FC06: Write Single Register"""
        if not self.is_open or not self.client:
            self.last_error = "Not connected"
            return False
        
        try:
            self.last_tx_frame = f"FC06 Slave={slave_id} Addr=0x{address:04X} Val=0x{value:04X}"
            
            result = self.client.write_register(
                address=address,
                value=value,
                slave=slave_id
            )
            
            if result.isError():
                self.timeout_count += 1
                self.last_error = f"Modbus Error: {result}"
                self.last_rx_frame = "ERROR"
                logger.warning(f"FC06 failed: {self.last_error}", "MODBUS")
                return False
            
            self._log_transaction("FC06", True)
            self.last_rx_frame = f"FC06 OK"
            
            logger.debug(f"FC06: Slave {slave_id}, wrote 0x{value:04X} to 0x{address:04X}", "MODBUS")
            return True
            
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            self.last_rx_frame = "EXCEPTION"
            logger.error(f"FC06 exception: {e}", "MODBUS")
            return False
    
    def write_registers(self, slave_id: int, address: int, values: list) -> bool:
        """FC16: Write Multiple Registers"""
        if not self.is_open or not self.client:
            self.last_error = "Not connected"
            return False
        
        try:
            self.last_tx_frame = f"FC16 Slave={slave_id} Addr=0x{address:04X} Count={len(values)}"
            
            result = self.client.write_registers(
                address=address,
                values=values,
                slave=slave_id
            )
            
            if result.isError():
                self.timeout_count += 1
                self.last_error = f"Modbus Error: {result}"
                self.last_rx_frame = "ERROR"
                logger.warning(f"FC16 failed: {self.last_error}", "MODBUS")
                return False
            
            self._log_transaction("FC16", True)
            self.last_rx_frame = f"FC16 OK: {len(values)} regs"
            
            logger.debug(f"FC16: Slave {slave_id}, wrote {len(values)} registers", "MODBUS")
            return True
            
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            self.last_rx_frame = "EXCEPTION"
            logger.error(f"FC16 exception: {e}", "MODBUS")
            return False
    
    def ping(self, slave_id: int) -> bool:
        """Ping một slave bằng cách đọc 1 register"""
        result = self.read_holding_registers(slave_id, 0x0000, 1)
        return "error" not in result
    
    def get_stats(self) -> dict:
        """Trả về thống kê"""
        return {
            "tx_count": self.tx_count,
            "rx_count": self.rx_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "last_tx": self.last_tx_frame or "---",
            "last_rx": self.last_rx_frame or "---",
            "last_error": self.last_error,
            "last_success": self.last_success_time.strftime("%H:%M:%S") if self.last_success_time else "Never"
        }


class RS485Manager(ModbusClientManager):
    """Quản lý kết nối RS-485/Serial RTU với pymodbus"""
    
    def __init__(self, port: str, baudrate: int, parity: str = "N", 
                 stopbits: int = 1, databits: int = 8, timeout: float = 1.0):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.databits = databits
        self.timeout = timeout
    
    def open(self) -> bool:
        """Mở cổng serial"""
        try:
            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.databits,
                timeout=self.timeout
            )
            
            connected = self.client.connect()
            
            if connected:
                self.is_open = True
                logger.info(
                    f"Opened {self.port} {self.baudrate} {self.databits}{self.parity}{self.stopbits}",
                    "RS485"
                )
                return True
            else:
                self.is_open = False
                self.last_error = "Failed to connect"
                logger.error(f"Failed to open {self.port}", "RS485")
                return False
                
        except Exception as e:
            self.is_open = False
            self.last_error = str(e)
            logger.error(f"Failed to open {self.port}: {e}", "RS485")
            return False
    
    def close(self):
        """Đóng cổng serial"""
        super().close()
        if self.client:
            logger.info(f"Closed {self.port}", "RS485")


class ModbusTCPManager(ModbusClientManager):
    """Quản lý kết nối Modbus TCP/IP với pymodbus"""
    
    def __init__(self, host: str, port: int = 502, timeout: float = 2.0):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout
    
    def open(self) -> bool:
        """Kết nối TCP"""
        try:
            self.client = ModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=self.timeout
            )
            
            connected = self.client.connect()
            
            if connected:
                self.is_open = True
                logger.info(f"Connected to {self.host}:{self.port} (Modbus TCP)", "MODBUS_TCP")
                return True
            else:
                self.is_open = False
                self.last_error = "Failed to connect"
                logger.error(f"Failed to connect {self.host}:{self.port}", "MODBUS_TCP")
                return False
                
        except Exception as e:
            self.is_open = False
            self.last_error = str(e)
            logger.error(f"Failed to connect {self.host}:{self.port}: {e}", "MODBUS_TCP")
            return False
    
    def close(self):
        """Đóng TCP connection"""
        super().close()
        if self.client:
            logger.info(f"Closed connection to {self.host}:{self.port}", "MODBUS_TCP")


class DataParser:
    """Parse Modbus responses thành dữ liệu hữu ích"""
    
    @staticmethod
    def parse_sht20_response(registers: list) -> dict:
        """Parse SHT20 sensor response (2 registers)"""
        if len(registers) < 2:
            return {"error": "Insufficient registers"}
        
        temp_raw = registers[0]
        humi_raw = registers[1]
        
        # Convert to signed if needed
        if temp_raw & 0x8000:
            temp_raw = temp_raw - (1 << 16)
        if humi_raw & 0x8000:
            humi_raw = humi_raw - (1 << 16)
        
        return {
            "temperature_c": temp_raw / 10.0,
            "humidity_percent": humi_raw / 10.0,
            "raw_temp": temp_raw,
            "raw_humi": humi_raw
        }
    
    @staticmethod
    def parse_position_registers(registers: list) -> int:
        """Parse 2 registers thành 32-bit signed position"""
        if len(registers) < 2:
            return 0
        
        hi = registers[0]
        lo = registers[1]
        pos = (hi << 16) | lo
        
        # Convert to signed
        if pos & 0x80000000:
            pos = pos - (1 << 32)
        
        return pos
    
    @staticmethod
    def pack_s32_to_regs(val: int) -> list:
        """Pack 32-bit signed thành 2 registers"""
        if val < 0:
            val = (1 << 32) + val
        hi = (val >> 16) & 0xFFFF
        lo = val & 0xFFFF
        return [hi, lo]
    
    @staticmethod
    def pack_u32_to_regs(val: int) -> list:
        """Pack 32-bit unsigned thành 2 registers"""
        hi = (val >> 16) & 0xFFFF
        lo = val & 0xFFFF
        return [hi, lo]

