"""
Configuration Module - Cấu hình tĩnh cho hệ thống RS-485
"""

# ============================================================================
# RS-485 / SERIAL SETTINGS
# ============================================================================
DEFAULT_COM_PORT = "COM11"
DEFAULT_BAUDRATE = 9600
DEFAULT_PARITY = "E"  # Even, Odd, None
DEFAULT_STOPBITS = 1
DEFAULT_DATABITS = 8
DEFAULT_TIMEOUT = 1.0

AVAILABLE_PORTS = ["COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM14"]
AVAILABLE_BAUDRATES = [9600, 19200, 38400, 57600, 115200]
AVAILABLE_PARITY = ["N", "E", "O"]  # None, Even, Odd
AVAILABLE_STOPBITS = [1, 2]

# ============================================================================
# DEVICE CONFIGURATION
# ============================================================================
DEVICE_SENSOR = {
    "name": "SHT20 Temperature Sensor",
    "slave_id": 1,
    "protocol": "Modbus RTU",
    "function_code": 0x04,  # Read Input Registers
    "start_register": 0x0001,
    "count": 2,  # 2 registers (Temp, Humi)
}

DEVICE_DRIVE = {
    "name": "EZi-STEP Stepper Driver",
    "slave_id": 2,
    "protocol": "Modbus RTU",
    "function_code": 0x03,  # Read Holding Registers
    "status_register": 0x1010,
    "position_register": 0x1000,
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_FILE = "logs/slave_monitor.log"
LOG_MAX_LINES = 200
LOG_FORMAT = "[%(asctime)s.%(msecs)03d] %(levelname)s %(component)s %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# ============================================================================
# UI CONFIGURATION
# ============================================================================
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 900
REFRESH_INTERVAL_MS = 500
LOG_REFRESH_MS = 200