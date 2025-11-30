# ============================================================================
# FILE: slave/serial_worker.py
# ============================================================================
"""
Serial Communication Worker Thread
"""
import time
import serial
from PyQt5.QtCore import QThread, pyqtSignal

class SerialWorker(QThread):
    """Thread quản lý serial communication."""
    response_received = pyqtSignal(bytes, str)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    def __init__(self, port: str, baudrate: int, timeout: float):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.running = False
    
    def run(self):
        """Khởi tạo serial port."""
        try:
            self.ser = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            time.sleep(0.2)
            self.running = True
            self.status_changed.emit(f"✓ Connected to {self.port}")
        except Exception as e:
            self.error_occurred.emit(f"Cannot open {self.port}: {e}")
            self.status_changed.emit(f"✗ Failed: {self.port}")
    
    def send_frame(self, frame: bytes) -> bytes:
        """Gửi frame và nhận response."""
        if not self.ser or not self.running:
            self.error_occurred.emit("Serial port not open")
            return b""
        
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.01)
            
            self.ser.write(frame)
            self.ser.flush()
            time.sleep(0.15)
            
            resp = b""
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                chunk = self.ser.read(256)
                if chunk:
                    resp += chunk
                    time.sleep(0.05)
                else:
                    if resp:
                        break
                    time.sleep(0.01)
            
            self.response_received.emit(resp, frame.hex().upper())
            return resp
            
        except Exception as e:
            self.error_occurred.emit(f"Serial error: {e}")
            return b""
    
    def close(self):
        """Đóng serial port."""
        self.running = False
        if self.ser:
            self.ser.close()