# ============================================================================
# FILE: slave/config.py
# ============================================================================
"""
Cấu hình hệ thống Slave Server
"""

# Modbus TCP Server
BIND_IP = "0.0.0.0"
PORT = 5020
UNIT_ID = 1
UPDATE_INTERVAL_MS = 500

# Serial Configuration
BAUDRATE = 9600
SERIAL_TIMEOUT = 1.0
SLAVE_ID_DRIVER = 2
SLAVE_ID_SHT20 = 1

# Register Map
REG_RUN = 0x0000                    # Coil: RUN motor
REG_RESET = 0x0001                 # Coil: RESET fault
REG_SETPOINT_SPEED = 0x0100        # HR: Setpoint speed (pps)
REG_MODE = 0x0102                  # HR: Mode
REG_TARGET_POSITION = 0x0104       # HR: Target position (32-bit)
REG_POSITION_FEEDBACK = 0x1000     # IR: Current position (32-bit)
REG_SPEED_FEEDBACK = 0x1002        # IR: Speed feedback (16-bit)
REG_TEMP_SENSOR = 0x1004           # IR: Temperature from SHT20 (*10)
REG_HUMI_SENSOR = 0x1005           # IR: Humidity from SHT20 (*10)
REG_DRIVE_STATUS = 0x1010          # IR: Drive status word
DI_READY = 0x0000                  # DI: Ready bit
DI_FAULT = 0x0001                  # DI: Fault bit