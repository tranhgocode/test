# ============================================================================
# FILE: slave/modbus_memory.py
# ============================================================================
"""
Modbus Memory Manager
"""
import threading

class ModbusMemory:
    """Quản lý vùng nhớ Modbus."""
    
    def __init__(self):
        self.coils = [False] * 256
        self.discrete_inputs = [False] * 256
        self.holding_registers = [0] * 512
        self.input_registers = [0] * 512
        self.lock = threading.RLock()
    
    def read_coil(self, addr: int) -> bool:
        with self.lock:
            return self.coils[addr] if addr < len(self.coils) else False
    
    def write_coil(self, addr: int, value: bool):
        with self.lock:
            if addr < len(self.coils):
                self.coils[addr] = value
    
    def read_discrete_input(self, addr: int) -> bool:
        with self.lock:
            return self.discrete_inputs[addr] if addr < len(self.discrete_inputs) else False
    
    def write_discrete_input(self, addr: int, value: bool):
        with self.lock:
            if addr < len(self.discrete_inputs):
                self.discrete_inputs[addr] = value
    
    def read_holding_register(self, addr: int) -> int:
        with self.lock:
            return self.holding_registers[addr] if addr < len(self.holding_registers) else 0
    
    def write_holding_register(self, addr: int, value: int):
        with self.lock:
            if addr < len(self.holding_registers):
                self.holding_registers[addr] = value & 0xFFFF
    
    def read_input_register(self, addr: int) -> int:
        with self.lock:
            return self.input_registers[addr] if addr < len(self.input_registers) else 0
    
    def write_input_register(self, addr: int, value: int):
        with self.lock:
            if addr < len(self.input_registers):
                self.input_registers[addr] = value & 0xFFFF
    
    def read_holding_registers(self, start: int, count: int) -> list:
        with self.lock:
            return [self.holding_registers[start + i] if start + i < len(self.holding_registers) else 0 
                    for i in range(count)]
    
    def write_holding_registers(self, start: int, values: list):
        with self.lock:
            for i, val in enumerate(values):
                if start + i < len(self.holding_registers):
                    self.holding_registers[start + i] = val & 0xFFFF
    
    def read_input_registers(self, start: int, count: int) -> list:
        with self.lock:
            return [self.input_registers[start + i] if start + i < len(self.input_registers) else 0 
                    for i in range(count)]
    
    def write_input_registers(self, start: int, values: list):
        with self.lock:
            for i, val in enumerate(values):
                if start + i < len(self.input_registers):
                    self.input_registers[start + i] = val & 0xFFFF
