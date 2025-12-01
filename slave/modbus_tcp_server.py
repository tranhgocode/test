"""
Modbus TCP Server - PLC Slave giả lập (chạy trên PC 2)
Nhận request từ Master qua TCP/IP, trả lời dữ liệu từ devices
"""
import socket
import threading
import time
from datetime import datetime
from .logger_handler import logger
from .modbus_handler import CRC16, ModbusFrame, DataParser

class ModbusTCPServer:
    """Modbus TCP Server (Slave)"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 502):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.server_thread = None
        
        # Device data storage
        self.input_registers = {}      # FC04: Read Input Registers
        self.holding_registers = {}    # FC03/FC06: Read/Write Holding Registers
        
        # Statistics
        self.request_count = 0
        self.response_count = 0
        self.error_count = 0
        self.last_client = ""
        self.last_request_time = None
    
    def initialize_registers(self):
        """Khởi tạo các registers với giá trị mặc định"""
        # ===== Input Registers (Slave ID 1 - SHT20 Sensor) =====
        self.input_registers[1] = {
            0x0001: 250,   # Temp: 25.0°C
            0x0002: 600,   # Humidity: 60.0%
        }
        
        # ===== Input Registers (Slave ID 2 - Drive Status) =====
        self.input_registers[2] = {
            0x1000: 0x0000,  # Position High
            0x1001: 0x0000,  # Position Low
            0x1010: 0x0000,  # Status word
        }
        
        # ===== Holding Registers (Slave ID 2 - Drive Control) =====
        self.holding_registers[2] = {
            0x0000: 0x0000,  # Step enable
            0x0001: 0x0000,  # Alarm reset
            0x0002: 0x0000,  # Stop
            0x0010: 0x0000,  # Target position (High)
            0x0011: 0x0000,  # Target position (Low)
            0x0012: 0x0000,  # Speed (High)
            0x0013: 0x0000,  # Speed (Low)
            0x0020: 0x0000,  # Incremental (High)
            0x0021: 0x0000,  # Incremental (Low)
            0x0022: 0x0000,  # Incremental speed (High)
            0x0023: 0x0000,  # Incremental speed (Low)
            0x0030: 0x0000,  # JOG speed (High)
            0x0031: 0x0000,  # JOG speed (Low)
            0x0032: 0x0000,  # JOG direction
        }
        
        logger.info("Registers initialized", "MODBUS_SERVER")
    
    def start(self) -> bool:
        """Khởi động Modbus TCP Server"""
        try:
            self.initialize_registers()
            
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            self.server_thread = threading.Thread(target=self._accept_connections, daemon=True)
            self.server_thread.start()
            
            logger.info(f"Modbus TCP Server started on {self.host}:{self.port}", "MODBUS_SERVER")
            return True
        except Exception as e:
            logger.error(f"Failed to start server: {e}", "MODBUS_SERVER")
            return False
    
    def stop(self):
        """Dừng Modbus TCP Server"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        logger.info("Modbus TCP Server stopped", "MODBUS_SERVER")
    
    def _accept_connections(self):
        """Accept client connections"""
        while self.running:
            try:
                client_socket, client_addr = self.server_socket.accept()
                self.last_client = f"{client_addr[0]}:{client_addr[1]}"
                logger.info(f"Client connected: {self.last_client}", "MODBUS_SERVER")
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_addr),
                    daemon=True
                )
                client_thread.start()
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}", "MODBUS_SERVER")
    
    def _handle_client(self, client_socket: socket.socket, client_addr: tuple):
        """Handle single client connection"""
        try:
            client_socket.settimeout(5.0)
            
            while self.running:
                try:
                    # Receive request
                    request = client_socket.recv(1024)
                    
                    if not request:
                        break
                    
                    self.request_count += 1
                    self.last_request_time = datetime.now()
                    
                    logger.debug(f"Request from {client_addr[0]}: {request.hex().upper()}", "MODBUS_SERVER")
                    
                    # Parse and handle request
                    response = self._process_request(request)
                    
                    if response:
                        client_socket.send(response)
                        self.response_count += 1
                        logger.debug(f"Response: {response.hex().upper()}", "MODBUS_SERVER")
                    else:
                        self.error_count += 1
                
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Handle client error: {e}", "MODBUS_SERVER")
                    break
        
        except Exception as e:
            logger.error(f"Client handler error: {e}", "MODBUS_SERVER")
        finally:
            try:
                client_socket.close()
            except:
                pass
            logger.info(f"Client disconnected: {client_addr[0]}", "MODBUS_SERVER")
    
    def _process_request(self, request: bytes) -> bytes:
        """Process Modbus TCP request and return response"""
        try:
            # Parse MBAP header (7 bytes)
            if len(request) < 8:
                return b""
            
            tid = (request[0] << 8) | request[1]      # Transaction ID
            pid = (request[2] << 8) | request[3]      # Protocol ID (should be 0)
            length = (request[4] << 8) | request[5]   # Length
            unit_id = request[6]                        # Unit ID (Slave ID)
            func_code = request[7]                      # Function Code
            
            if pid != 0:  # Protocol ID must be 0 for Modbus
                return b""
            
            # Extract PDU (without MBAP header)
            pdu = request[7:]
            
            # Route to appropriate handler
            if func_code == 0x03:  # Read Holding Registers
                response_pdu = self._handle_fc03(unit_id, pdu)
            elif func_code == 0x04:  # Read Input Registers
                response_pdu = self._handle_fc04(unit_id, pdu)
            elif func_code == 0x06:  # Write Single Register
                response_pdu = self._handle_fc06(unit_id, pdu)
            elif func_code == 0x10:  # Write Multiple Registers
                response_pdu = self._handle_fc16(unit_id, pdu)
            else:
                # Unsupported function code
                response_pdu = bytes([func_code + 0x80, 0x01])  # Exception
            
            # Build MBAP header for response
            response = bytes([
                (tid >> 8) & 0xFF, tid & 0xFF,        # Transaction ID
                0x00, 0x00,                            # Protocol ID
                (len(response_pdu) + 1) >> 8, (len(response_pdu) + 1) & 0xFF,  # Length
                unit_id                                # Unit ID
            ])
            
            return response + response_pdu
        
        except Exception as e:
            logger.error(f"Process request error: {e}", "MODBUS_SERVER")
            return b""
    
    def _handle_fc03(self, unit_id: int, pdu: bytes) -> bytes:
        """FC03: Read Holding Registers"""
        try:
            if len(pdu) < 5:
                return bytes([0x03 + 0x80, 0x03])  # Exception: Illegal data value
            
            func_code = pdu[0]
            start_addr = (pdu[1] << 8) | pdu[2]
            count = (pdu[3] << 8) | pdu[4]
            
            if count < 1 or count > 125:
                return bytes([func_code + 0x80, 0x03])
            
            # Get registers
            registers = []
            for i in range(count):
                addr = start_addr + i
                if unit_id in self.holding_registers and addr in self.holding_registers[unit_id]:
                    registers.append(self.holding_registers[unit_id][addr])
                else:
                    registers.append(0)
            
            # Build response
            byte_count = len(registers) * 2
            response = bytearray([func_code, byte_count])
            
            for reg in registers:
                response.append((reg >> 8) & 0xFF)
                response.append(reg & 0xFF)
            
            logger.info(f"FC03: Slave {unit_id}, Addr 0x{start_addr:04X}, Count {count}", "MODBUS_SERVER")
            return bytes(response)
        
        except Exception as e:
            logger.error(f"FC03 error: {e}", "MODBUS_SERVER")
            return bytes([0x03 + 0x80, 0x03])
    
    def _handle_fc04(self, unit_id: int, pdu: bytes) -> bytes:
        """FC04: Read Input Registers"""
        try:
            if len(pdu) < 5:
                return bytes([0x04 + 0x80, 0x03])
            
            func_code = pdu[0]
            start_addr = (pdu[1] << 8) | pdu[2]
            count = (pdu[3] << 8) | pdu[4]
            
            if count < 1 or count > 125:
                return bytes([func_code + 0x80, 0x03])
            
            # Get registers
            registers = []
            for i in range(count):
                addr = start_addr + i
                if unit_id in self.input_registers and addr in self.input_registers[unit_id]:
                    registers.append(self.input_registers[unit_id][addr])
                else:
                    registers.append(0)
            
            # Build response
            byte_count = len(registers) * 2
            response = bytearray([func_code, byte_count])
            
            for reg in registers:
                response.append((reg >> 8) & 0xFF)
                response.append(reg & 0xFF)
            
            logger.info(f"FC04: Slave {unit_id}, Addr 0x{start_addr:04X}, Count {count}", "MODBUS_SERVER")
            return bytes(response)
        
        except Exception as e:
            logger.error(f"FC04 error: {e}", "MODBUS_SERVER")
            return bytes([0x04 + 0x80, 0x03])
    
    def _handle_fc06(self, unit_id: int, pdu: bytes) -> bytes:
        """FC06: Write Single Register"""
        try:
            if len(pdu) < 5:
                return bytes([0x06 + 0x80, 0x03])
            
            func_code = pdu[0]
            reg_addr = (pdu[1] << 8) | pdu[2]
            reg_val = (pdu[3] << 8) | pdu[4]
            
            # Store value
            if unit_id not in self.holding_registers:
                self.holding_registers[unit_id] = {}
            
            self.holding_registers[unit_id][reg_addr] = reg_val
            
            logger.info(f"FC06: Slave {unit_id}, Addr 0x{reg_addr:04X}, Value 0x{reg_val:04X}", "MODBUS_SERVER")
            
            # Echo back request as response
            return pdu
        
        except Exception as e:
            logger.error(f"FC06 error: {e}", "MODBUS_SERVER")
            return bytes([0x06 + 0x80, 0x03])
    
    def _handle_fc16(self, unit_id: int, pdu: bytes) -> bytes:
        """FC16 (0x10): Write Multiple Registers"""
        try:
            if len(pdu) < 7:
                return bytes([0x10 + 0x80, 0x03])
            
            func_code = pdu[0]
            start_addr = (pdu[1] << 8) | pdu[2]
            count = (pdu[3] << 8) | pdu[4]
            byte_count = pdu[5]
            
            if byte_count != count * 2:
                return bytes([func_code + 0x80, 0x03])
            
            # Parse registers from request
            if len(pdu) < 6 + byte_count:
                return bytes([func_code + 0x80, 0x03])
            
            if unit_id not in self.holding_registers:
                self.holding_registers[unit_id] = {}
            
            for i in range(count):
                addr = start_addr + i
                val = (pdu[6 + i*2] << 8) | pdu[6 + i*2 + 1]
                self.holding_registers[unit_id][addr] = val
            
            logger.info(f"FC16: Slave {unit_id}, Addr 0x{start_addr:04X}, Count {count}", "MODBUS_SERVER")
            
            # Build response
            response = bytearray([func_code, (start_addr >> 8) & 0xFF, start_addr & 0xFF,
                                 (count >> 8) & 0xFF, count & 0xFF])
            return bytes(response)
        
        except Exception as e:
            logger.error(f"FC16 error: {e}", "MODBUS_SERVER")
            return bytes([0x10 + 0x80, 0x03])
    
    def update_input_register(self, unit_id: int, addr: int, value: int):
        """Update input register value (for sensor/drive data)"""
        if unit_id not in self.input_registers:
            self.input_registers[unit_id] = {}
        self.input_registers[unit_id][addr] = value
    
    def get_stats(self) -> dict:
        """Get server statistics"""
        return {
            "running": self.running,
            "request_count": self.request_count,
            "response_count": self.response_count,
            "error_count": self.error_count,
            "last_client": self.last_client,
            "last_request": self.last_request_time.strftime("%H:%M:%S") if self.last_request_time else "Never"
        }