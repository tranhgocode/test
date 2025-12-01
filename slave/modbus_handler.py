"""
Modbus Handler - Xử lý RS-485 Modbus RTU với CRC + serial management
"""
import time
import serial
from datetime import datetime
from .logger_handler import logger

class CRC16:
    """Tính toán CRC16 theo chuẩn Modbus"""
    @staticmethod
    def calculate(data: bytes) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF
    
    @staticmethod
    def append(data: bytes) -> bytes:
        """Thêm CRC vào cuối frame"""
        crc = CRC16.calculate(data)
        return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    
    @staticmethod
    def verify(frame: bytes) -> bool:
        """Kiểm tra CRC của frame"""
        if len(frame) < 3:
            return False
        data = frame[:-2]
        crc_rx = (frame[-1] << 8) | frame[-2]
        crc_calc = CRC16.calculate(data)
        return crc_rx == crc_calc

class ModbusFrame:
    """Builder cho Modbus frames"""
    
    @staticmethod
    def build_fc03(slave_id: int, start_reg: int, count: int) -> bytes:
        """FC03: Read Holding Registers"""
        data = bytes([
            slave_id,
            0x03,
            (start_reg >> 8) & 0xFF,
            start_reg & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF
        ])
        return CRC16.append(data)
    
    @staticmethod
    def build_fc04(slave_id: int, start_reg: int, count: int) -> bytes:
        """FC04: Read Input Registers"""
        data = bytes([
            slave_id,
            0x04,
            (start_reg >> 8) & 0xFF,
            start_reg & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF
        ])
        return CRC16.append(data)
    
    @staticmethod
    def build_fc06(slave_id: int, reg_addr: int, reg_val: int) -> bytes:
        """FC06: Write Single Register"""
        data = bytes([
            slave_id,
            0x06,
            (reg_addr >> 8) & 0xFF,
            reg_addr & 0xFF,
            (reg_val >> 8) & 0xFF,
            reg_val & 0xFF
        ])
        return CRC16.append(data)

class RS485Manager:
    """Quản lý kết nối RS-485/Serial"""
    
    def __init__(self, port: str, baudrate: int, parity: str = "E", 
                 stopbits: int = 1, databits: int = 8, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.databits = databits
        self.timeout = timeout
        self.ser = None
        self.is_open = False
        
        # Statistics
        self.tx_count = 0
        self.rx_count = 0
        self.timeout_count = 0
        self.crc_error_count = 0
        self.last_tx_frame = b""
        self.last_rx_frame = b""
        self.last_error = ""
        self.last_success_time = None
    
    def open(self) -> bool:
        """Mở cổng serial"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.databits,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            time.sleep(0.1)
            self.is_open = True
            logger.info(
                f"Opened {self.port} {self.baudrate} {self.databits}{self.parity}{self.stopbits}",
                "RS485"
            )
            return True
        except Exception as e:
            self.is_open = False
            self.last_error = str(e)
            logger.error(f"Failed to open {self.port}: {e}", "RS485")
            return False
    
    def close(self):
        """Đóng cổng serial"""
        if self.ser:
            self.ser.close()
            self.is_open = False
            logger.info(f"Closed {self.port}", "RS485")
    
    def transact(self, frame: bytes, timeout_override: float = None) -> bytes:
        """
        Gửi frame và nhận response
        
        Args:
            frame: Modbus frame (với CRC)
            timeout_override: Override timeout nếu cần
        
        Returns:
            Response bytes hoặc rỗng nếu error
        """
        if not self.is_open or not self.ser:
            self.last_error = "Port not open"
            logger.error("Port not open", "RS485")
            return b""
        
        try:
            # Gửi
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.01)
            
            self.ser.write(frame)
            self.ser.flush()
            time.sleep(0.05)  # Inter-frame delay
            
            self.last_tx_frame = frame
            self.tx_count += 1
            logger.debug(f"TX: {frame.hex().upper()}", "RS485")
            
            # Nhận
            timeout = timeout_override if timeout_override else self.timeout
            response = b""
            start = time.time()
            
            while time.time() - start < timeout:
                chunk = self.ser.read(256)
                if chunk:
                    response += chunk
                    time.sleep(0.02)  # Đợi data tiếp theo
                else:
                    if response:
                        break
                    time.sleep(0.01)
            
            self.last_rx_frame = response
            
            if not response:
                self.timeout_count += 1
                self.last_error = "Timeout"
                logger.warning(f"Timeout waiting for response", "RS485")
                return b""
            
            # Kiểm tra CRC
            if not CRC16.verify(response):
                self.crc_error_count += 1
                self.last_error = "CRC Error"
                logger.warning(
                    f"CRC Error - RX: {response.hex().upper()}",
                    "RS485"
                )
                return b""
            
            self.rx_count += 1
            self.last_success_time = datetime.now()
            self.last_error = ""
            logger.debug(f"RX: {response.hex().upper()}", "RS485")
            
            return response
        
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Transaction error: {e}", "RS485")
            return b""
    
    def ping(self, slave_id: int) -> bool:
        """Ping một slave qua FC03 (đọc 1 register)"""
        frame = ModbusFrame.build_fc03(slave_id, 0x0000, 1)
        response = self.transact(frame)
        return len(response) > 0 and response[0] == slave_id
    
    def get_stats(self):
        """Trả về thống kê"""
        return {
            "tx_count": self.tx_count,
            "rx_count": self.rx_count,
            "timeout_count": self.timeout_count,
            "crc_error_count": self.crc_error_count,
            "last_tx": self.last_tx_frame.hex().upper() if self.last_tx_frame else "---",
            "last_rx": self.last_rx_frame.hex().upper() if self.last_rx_frame else "---",
            "last_error": self.last_error,
            "last_success": self.last_success_time.strftime("%H:%M:%S") if self.last_success_time else "Never"
        }

class DataParser:
    """Parse Modbus responses thành dữ liệu hữu ích"""
    
    @staticmethod
    def parse_fc03_fc04(response: bytes) -> dict:
        """Parse FC03/FC04 response"""
        if len(response) < 5:
            return {"error": "Response too short"}
        
        slave_id = response[0]
        func_code = response[1]
        byte_count = response[2]
        
        if len(response) < 3 + byte_count + 2:
            return {"error": "Incomplete data"}
        
        registers = []
        for i in range(byte_count // 2):
            hi = response[3 + i*2]
            lo = response[3 + i*2 + 1]
            registers.append((hi << 8) | lo)
        
        return {
            "slave_id": slave_id,
            "func_code": func_code,
            "registers": registers,
            "byte_count": byte_count
        }
    
    @staticmethod
    def parse_sht20_response(response: bytes) -> dict:
        """Parse SHT20 sensor response (2 registers)"""
        parsed = DataParser.parse_fc03_fc04(response)
        if "error" in parsed:
            return parsed
        
        if len(parsed.get("registers", [])) >= 2:
            temp_raw = parsed["registers"][0]
            humi_raw = parsed["registers"][1]
            return {
                "temperature_c": temp_raw / 10.0,
                "humidity_percent": humi_raw / 10.0,
                "raw_temp": temp_raw,
                "raw_humi": humi_raw
            }
        
        return {"error": "Insufficient registers"}
    


    