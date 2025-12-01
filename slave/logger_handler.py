"""
Logger Handler - Hệ thống logging tập trung với thread-safe queue
"""
import logging
import os
from datetime import datetime
from collections import deque
from threading import Lock

class ComponentFormatter(logging.Formatter):
    """Custom formatter hỗ trợ 'component' field"""
    def format(self, record):
        if not hasattr(record, 'component'):
            record.component = "SYSTEM"
        return super().format(record)

class LogBuffer:
    """Thread-safe buffer lưu giữ log entries"""
    def __init__(self, max_lines=200):
        self.max_lines = max_lines
        self.buffer = deque(maxlen=max_lines)
        self.lock = Lock()
    
    def add(self, message: str):
        with self.lock:
            self.buffer.append(message)
    
    def get_all(self):
        with self.lock:
            return list(self.buffer)
    
    def clear(self):
        with self.lock:
            self.buffer.clear()
    
    def export_csv(self, filename: str):
        """Export log entries to CSV format"""
        with self.lock:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("Timestamp,Level,Component,Message\n")
                for entry in self.buffer:
                    f.write(entry + "\n")

class SlaveLogger:
    """Logger singleton cho toàn hệ thống"""
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.log_buffer = LogBuffer(max_lines=200)
        self.logger = logging.getLogger("SlaveMonitor")
        self.logger.setLevel(logging.DEBUG)
        
        # Tạo thư mục logs nếu chưa tồn tại
        os.makedirs("logs", exist_ok=True)
        
        # Handler: File
        fh = logging.FileHandler("logs/slave_monitor.log", encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        
        # Handler: Custom buffer cho UI
        class BufferHandler(logging.Handler):
            def __init__(self, buffer):
                super().__init__()
                self.buffer = buffer
            
            def emit(self, record):
                msg = self.format(record)
                self.buffer.add(msg)
        
        bh = BufferHandler(self.log_buffer)
        bh.setLevel(logging.DEBUG)
        
        # Formatter
        fmt = ComponentFormatter(
            "[%(asctime)s.%(msecs)03d] %(levelname)-5s [%(component)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        
        fh.setFormatter(fmt)
        bh.setFormatter(fmt)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(bh)
    
    def info(self, msg: str, component: str = "SYSTEM"):
        extra = {"component": component}
        self.logger.info(msg, extra=extra)
    
    def warning(self, msg: str, component: str = "SYSTEM"):
        extra = {"component": component}
        self.logger.warning(msg, extra=extra)
    
    def error(self, msg: str, component: str = "SYSTEM"):
        extra = {"component": component}
        self.logger.error(msg, extra=extra)
    
    def debug(self, msg: str, component: str = "SYSTEM"):
        extra = {"component": component}
        self.logger.debug(msg, extra=extra)
    
    def get_buffer(self):
        """Lấy tất cả log entries"""
        return self.log_buffer.get_all()
    
    def clear_buffer(self):
        """Xóa log buffer"""
        self.log_buffer.clear()
    
    def export_csv(self, filename: str):
        """Export logs to CSV"""
        self.log_buffer.export_csv(filename)
        self.info(f"Logs exported to {filename}", "LOGGER")

# Singleton instance
logger = SlaveLogger()