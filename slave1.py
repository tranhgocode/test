"""
================================================================================
                    SENSOR DASHBOARD - MÁY CHỦ GIÁM SÁT
================================================================================

Chương trình này chia làm 3 chức năng chính:

📌 1. SHT20 SENSOR (Cảm biến nhiệt độ và độ ẩm)
   - Đọc dữ liệu nhiệt độ và độ ẩm từ cảm biến SHT20 qua Modbus RTU
   - Hiển thị thời gian thực trên giao diện GUI
   - Tự động đọc liên tục theo chu kỳ

📌 2. DRIVE CONTROL (Điều khiển động cơ bước EZi-STEP)
   - Điều khiển động cơ bước: bật/tắt, reset alarm
   - Các chế độ di chuyển: JOG, Velocity, Absolute, Incremental
   - Đọc vị trí hiện tại và trạng thái động cơ
   - Tự động giám sát trạng thái driver

📌 3. GUI (Giao diện người dùng)
   - Hiển thị và điều khiển toàn bộ hệ thống
   - Kết nối cổng COM serial
   - Hiển thị thông tin TX/RX để debug
   - Quản lý các timer cho tự động đọc dữ liệu

================================================================================
"""

import sys, time, struct
import serial
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QHBoxLayout,
    QLineEdit, QMessageBox, QComboBox, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal

# ============================================================================
# CẤU HÌNH HỆ THỐNG
# ============================================================================
# CONFIGURE HERE
COM_PORT = "COM11"
BAUDRATE = 9600
SLAVE_ID = 2
SLAVE_ID_SHT20 = 1
SERIAL_TIMEOUT = 1.0
READ_INTERVAL_MS = 500
#

# ============================================================================
# PHẦN 1: UTILITY FUNCTIONS (HÀM TIỆN ÍCH)
# ============================================================================
# Các hàm hỗ trợ tính toán CRC, đóng gói/giải mã dữ liệu Modbus

def crc16_modbus(data: bytes) -> int:
    """
    [UTILITY] Tính toán Modbus CRC16 cho dữ liệu gói tin thô.
    
    Hàm này tính checksum CRC16 theo chuẩn Modbus RTU để đảm bảo
    tính toàn vẹn dữ liệu khi truyền qua serial.
    
    Args:
        data: Mảng byte cần tính CRC
    
    Returns:
        Giá trị CRC16 dạng số nguyên 16-bit
    """
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF

# ============================================================================
# PHẦN 2: SHT20 SENSOR FUNCTIONS (HÀM CẢMBIẾN SHT20)
# ============================================================================
# Các hàm liên quan đến việc giao tiếp với cảm biến nhiệt độ/độ ẩm SHT20

def build_read_sht20(slave_id: int) -> bytes:
    """
    [SHT20] Tạo gói tin Modbus FC04 để đọc dữ liệu từ cảm biến SHT20.
    
    Hàm này xây dựng frame Modbus Function Code 04 (Read Input Registers)
    để yêu cầu SHT20 trả về giá trị nhiệt độ và độ ẩm.
    
    Args:
        slave_id: ID của slave SHT20 trên bus Modbus
    
    Returns:
        Gói tin Modbus hoàn chỉnh kèm CRC
    """
    func = 0x04
    reg = 0x0001
    count = 0x0002
    data = bytes([
        slave_id, func,
        (reg >> 8) & 0xFF, reg & 0xFF,
        (count >> 8) & 0xFF, count & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

# ============================================================================
# PHẦN 3: DRIVE CONTROL FUNCTIONS (HÀM ĐIỀU KHIỂN DRIVER)
# ============================================================================
# Các hàm xây dựng gói tin Modbus để điều khiển động cơ bước EZi-STEP

# Build Modbus FC03 Read Holding Registers
def build_fc03(slave_id: int, start_reg: int, count: int) -> bytes:
    """
    [DRIVE] Tạo gói tin Modbus FC03 để đọc thanh ghi từ driver EZi-STEP.
    
    Function Code 03 dùng để đọc các thanh ghi holding (vị trí, trạng thái, v.v.)
    từ driver động cơ bước.
    
    Args:
        slave_id: ID của slave driver trên bus Modbus
        start_reg: Địa chỉ thanh ghi bắt đầu đọc
        count: Số lượng thanh ghi cần đọc
    
    Returns:
        Gói tin Modbus FC03 hoàn chỉnh kèm CRC
    """
    data = bytes([
        slave_id,
        0x03,
        (start_reg >> 8) & 0xFF,
        start_reg & 0xFF,
        (count >> 8) & 0xFF,
        count & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

def build_fc06(slave_id: int, reg_addr: int, reg_val: int) -> bytes:
    """
    [DRIVE] Tạo gói tin Modbus FC06 để ghi một thanh ghi trên driver.
    
    Function Code 06 dùng để ghi giá trị vào một thanh ghi đơn lẻ
    (ví dụ: bật/tắt motor, reset alarm).
    
    Args:
        slave_id: ID của slave driver
        reg_addr: Địa chỉ thanh ghi cần ghi
        reg_val: Giá trị 16-bit cần ghi vào thanh ghi
    
    Returns:
        Gói tin Modbus FC06 hoàn chỉnh kèm CRC
    """
    data = bytes([
        slave_id,
        0x06,
        (reg_addr >> 8) & 0xFF,
        reg_addr & 0xFF,
        (reg_val >> 8) & 0xFF,
        reg_val & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

def build_fc16(slave_id: int, start_reg: int, registers: list) -> bytes:
    """
    [DRIVE] Tạo gói tin Modbus FC16 để ghi nhiều thanh ghi cùng lúc.
    
    Function Code 16 (Write Multiple Registers) dùng để ghi nhiều giá trị
    liên tiếp (ví dụ: vị trí + tốc độ cho lệnh di chuyển).
    
    Args:
        slave_id: ID của slave driver
        start_reg: Địa chỉ thanh ghi bắt đầu ghi
        registers: Danh sách các giá trị 16-bit cần ghi
    
    Returns:
        Gói tin Modbus FC16 hoàn chỉnh kèm CRC
    """
    reg_count = len(registers)
    byte_count = reg_count * 2
    
    data = bytearray([
        slave_id,
        0x10,
        (start_reg >> 8) & 0xFF,
        start_reg & 0xFF,
        (reg_count >> 8) & 0xFF,
        reg_count & 0xFF,
        byte_count
    ])
    
    for reg in registers:
        data.append((reg >> 8) & 0xFF)
        data.append(reg & 0xFF)
    
    crc = crc16_modbus(bytes(data))
    return bytes(data) + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

# ============================================================================
# PHẦN 4: DATA PACKING/UNPACKING UTILITIES
# ============================================================================
# Các hàm chuyển đổi dữ liệu 32-bit sang/từ định dạng thanh ghi Modbus 16-bit

def pack_u32_to_regs(val: int) -> list:
    """
    [UTILITY] Chia giá trị 32-bit không dấu thành hai thanh ghi Modbus 16-bit.
    
    Dùng cho các giá trị dương như tốc độ (pps).
    
    Args:
        val: Giá trị 32-bit không dấu
    
    Returns:
        Danh sách [thanh ghi cao, thanh ghi thấp]
    """
    hi = (val >> 16) & 0xFFFF
    lo = val & 0xFFFF
    return [hi, lo]

def pack_s32_to_regs(val: int) -> list:
    """[UTILITY] Split signed 32-bit value into two registers preserving sign."""
    if val < 0:
        val = (1 << 32) + val
    hi = (val >> 16) & 0xFFFF
    lo = val & 0xFFFF
    return [hi, lo]

def unpack_s32_from_bytes(b: bytes, offset: int) -> int:
    """[UTILITY] Unpack signed 32-bit integer from Modbus payload (Big Endian)."""
    val = (b[offset] << 24) | (b[offset+1] << 16) | (b[offset+2] << 8) | b[offset+3]
    # Convert to signed
    if val & 0x80000000:
        val = val - (1 << 32)
    return val

class SerialWorker(QThread):
    """[UTILITY] Background thread managing raw serial IO for both Driver and SHT20."""
    response_received = pyqtSignal(bytes, str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, port, baudrate, timeout):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.running = False
        
    def run(self):
        try:
            self.ser = serial.Serial(
                self.port, 
                self.baudrate, 
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            time.sleep(0.1)
            self.running = True
        except Exception as e:
            self.error_occurred.emit(f"Cannot open {self.port}: {e}")
    
    def send_frame(self, frame: bytes) -> bytes:
        if not self.ser or not self.running:
            self.error_occurred.emit("Serial port not open")
            return b""
        
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.01)
            
            self.ser.write(frame)
            self.ser.flush()
            time.sleep(0.2)  # Tăng delay để đợi ESP32 xử lý
            
            resp = b""
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                chunk = self.ser.read(256)
                if chunk:
                    resp += chunk
                    # Nếu đã có dữ liệu, đợi thêm một chút để nhận hết
                    time.sleep(0.05)
                else:
                    if resp:  # Đã có data rồi thì thoát
                        break
                    time.sleep(0.01)
            
            self.response_received.emit(resp, frame.hex().upper())
            return resp
            
        except Exception as e:
            self.error_occurred.emit(f"Serial error: {e}")
            return b""
    
    def close(self):
        self.running = False
        if self.ser:
            self.ser.close()

class DriverGUI(QWidget):
    """[GUI] Main window orchestrating Driver controls, status views, and SHT20 widgets."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MÁY CHỦ GIÁM SÁT")
        self.setGeometry(200, 200, 850, 800)
        
        self.worker = None
        self.read_count = 0
        self.error_count = 0
        
        layout = QVBoxLayout()
        
        # Status
        self.status = QLabel("Status: Initializing...")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("background-color: #ffffcc; padding: 8px; font-size: 11pt; font-weight: bold;")
        layout.addWidget(self.status)
        
        # Port selection
        row_port = QHBoxLayout()
        row_port.addWidget(QLabel("COM Port:"))
        self.combo_port = QComboBox()
        self.combo_port.addItems(["COM11", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8"])
        row_port.addWidget(self.combo_port)
        btn_reconnect = QPushButton("Reconnect")
        btn_reconnect.clicked.connect(self.reconnect_serial)
        row_port.addWidget(btn_reconnect)
        row_port.addStretch()
        layout.addLayout(row_port)

        # EZi-STEP Status Display
        group_status = QGroupBox("📊 EZi-STEP Status Monitor")
        group_status.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        status_layout = QVBoxLayout()
        
        row_pos = QHBoxLayout()
        self.lbl_position = QLabel("Position: --- pulse")
        self.lbl_position.setStyleSheet("font-size: 14pt; font-weight: bold; color: blue;")
        row_pos.addWidget(self.lbl_position)
        btn_read_pos = QPushButton("Read Position")
        btn_read_pos.clicked.connect(self.read_position)
        row_pos.addWidget(btn_read_pos)
        status_layout.addLayout(row_pos)
        
        row_sts = QHBoxLayout()
        self.lbl_alarm = QLabel("Alarm: ---")
        self.lbl_alarm.setStyleSheet("font-size: 12pt;")
        row_sts.addWidget(self.lbl_alarm)
        
        self.lbl_inpos = QLabel("InPosition: ---")
        self.lbl_inpos.setStyleSheet("font-size: 12pt;")
        row_sts.addWidget(self.lbl_inpos)
        
        self.lbl_running = QLabel("Running: ---")
        self.lbl_running.setStyleSheet("font-size: 12pt;")
        row_sts.addWidget(self.lbl_running)
        
        btn_read_status = QPushButton("Read Status")
        btn_read_status.clicked.connect(self.read_status)
        row_sts.addWidget(btn_read_status)
        status_layout.addLayout(row_sts)
        
        # Auto-read controls
        row_auto = QHBoxLayout()
        btn_auto_start = QPushButton("▶ Start Auto-Read")
        btn_auto_start.setStyleSheet("background-color: #90EE90;")
        btn_auto_start.clicked.connect(self.start_auto_read)
        row_auto.addWidget(btn_auto_start)
        
        btn_auto_stop = QPushButton("⏸ Stop Auto-Read")
        btn_auto_stop.setStyleSheet("background-color: #FFB6C1;")
        btn_auto_stop.clicked.connect(self.stop_auto_read)
        row_auto.addWidget(btn_auto_stop)
        row_auto.addStretch()
        status_layout.addLayout(row_auto)
        
        group_status.setLayout(status_layout)
        layout.addWidget(group_status)

        # Driver Control
        group_control = QGroupBox("🎮 Driver Control")
        group_control.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        control_layout = QVBoxLayout()
        
        # Buttons driver row1
        row = QHBoxLayout()
        btn_reset = QPushButton("⚠ RESET ALARM")
        btn_reset.setStyleSheet("background-color: #FFA500; font-weight: bold;")
        btn_reset.clicked.connect(self.reset_alarm)
        row.addWidget(btn_reset)

        btn_enable = QPushButton("✓ STEP ON")
        btn_enable.setStyleSheet("background-color: #90EE90; font-weight: bold;")
        btn_enable.clicked.connect(self.step_on)
        row.addWidget(btn_enable)

        btn_disable = QPushButton("✗ STEP OFF")
        btn_disable.setStyleSheet("background-color: #FFB6C1; font-weight: bold;")
        btn_disable.clicked.connect(self.step_off)
        row.addWidget(btn_disable)

        control_layout.addLayout(row)

        # Buttons row2
        row2 = QHBoxLayout()
        btn_jog_ccw = QPushButton("◀ JOG CCW")
        btn_jog_ccw.setStyleSheet("background-color: #87CEEB; font-weight: bold;")
        btn_jog_ccw.clicked.connect(self.jog_ccw)
        row2.addWidget(btn_jog_ccw)

        btn_jog_cw = QPushButton("JOG CW ▶")
        btn_jog_cw.setStyleSheet("background-color: #87CEEB; font-weight: bold;")
        btn_jog_cw.clicked.connect(self.jog_cw)
        row2.addWidget(btn_jog_cw)

        btn_stop = QPushButton("■ STOP")
        btn_stop.setStyleSheet("background-color: #FF6B6B; font-weight: bold;")
        btn_stop.clicked.connect(self.move_stop)
        row2.addWidget(btn_stop)

        control_layout.addLayout(row2)

        # Speed row
        row_speed = QHBoxLayout()
        row_speed.addWidget(QLabel("Speed (pps):"))
        self.le_speed = QLineEdit("15000")
        self.le_speed.setFixedWidth(100)
        row_speed.addWidget(self.le_speed)
        row_speed.addWidget(QLabel("Direction:"))
        self.le_dir = QLineEdit("1")
        self.le_dir.setFixedWidth(50)
        row_speed.addWidget(self.le_dir)
        btn_move_vel = QPushButton("Move Velocity")
        btn_move_vel.clicked.connect(self.move_velocity)
        row_speed.addWidget(btn_move_vel)
        row_speed.addStretch()
        control_layout.addLayout(row_speed)

        # Move rows
        row_move = QHBoxLayout()
        row_move.addWidget(QLabel("Position:"))
        self.le_abspos = QLineEdit("10000")
        self.le_abspos.setFixedWidth(100)
        row_move.addWidget(self.le_abspos)
        row_move.addWidget(QLabel("Speed (pps):"))
        self.le_runpps = QLineEdit("10000")
        self.le_runpps.setFixedWidth(100)
        row_move.addWidget(self.le_runpps)
        btn_abs = QPushButton("Move Absolute")
        btn_abs.clicked.connect(self.move_abs)
        row_move.addWidget(btn_abs)
        btn_inc = QPushButton("Move Incremental")
        btn_inc.clicked.connect(self.move_inc)
        row_move.addWidget(btn_inc)
        control_layout.addLayout(row_move)
        
        group_control.setLayout(control_layout)
        layout.addWidget(group_control)

        # ===== SHT20 Sensor =====
        group_sht = QGroupBox("🌡 SHT20 Temperature & Humidity Sensor")
        group_sht.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        sht_layout = QVBoxLayout()

        row_sht = QHBoxLayout()
        self.lbl_temp = QLabel("Temp: --- °C")
        self.lbl_temp.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FF4500;")
        row_sht.addWidget(self.lbl_temp)
        
        self.lbl_humi = QLabel("Humi: --- %")
        self.lbl_humi.setStyleSheet("font-size: 14pt; font-weight: bold; color: #1E90FF;")
        row_sht.addWidget(self.lbl_humi)

        btn_sht_start = QPushButton("▶ Start")
        btn_sht_start.setStyleSheet("background-color: #90EE90;")
        btn_sht_start.clicked.connect(self.start_sht)
        row_sht.addWidget(btn_sht_start)

        btn_sht_stop = QPushButton("⏸ Stop")
        btn_sht_stop.setStyleSheet("background-color: #FFB6C1;")
        btn_sht_stop.clicked.connect(self.stop_sht)
        row_sht.addWidget(btn_sht_stop)

        sht_layout.addLayout(row_sht)
        
        # Read count
        self.lbl_read_count = QLabel("Reads: 0 | Errors: 0")
        self.lbl_read_count.setStyleSheet("font-size: 10pt;")
        sht_layout.addWidget(self.lbl_read_count)
        
        group_sht.setLayout(sht_layout)
        layout.addWidget(group_sht)

        # TX/RX display
        group_comm = QGroupBox("📡 Last Communication")
        group_comm.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        comm_layout = QVBoxLayout()
        
        self.resp_label = QLabel("TX/RX: Waiting...")
        self.resp_label.setWordWrap(True)
        self.resp_label.setStyleSheet("background-color: #f0f0f0; padding: 8px; font-family: 'Courier New', monospace; font-size: 9pt;")
        comm_layout.addWidget(self.resp_label)
        
        group_comm.setLayout(comm_layout)
        layout.addWidget(group_comm)

        # Timers
        self.timer_sht20 = QTimer()
        self.timer_sht20.timeout.connect(self.read_sht20)
        
        self.timer_auto_read = QTimer()
        self.timer_auto_read.timeout.connect(self.auto_read_status)

        self.setLayout(layout)
        self.init_serial()

    def init_serial(self):
        """[GUI] Initialize or reinitialize the shared SerialWorker instance."""
        if self.worker:
            self.worker.close()
            self.worker.wait()
        
        self.worker = SerialWorker(COM_PORT, BAUDRATE, SERIAL_TIMEOUT)
        self.worker.response_received.connect(self.on_response)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()
        time.sleep(0.2)
        self.status.setText("✓ Status: Ready")
        self.status.setStyleSheet("background-color: #90EE90; padding: 8px; font-size: 11pt; font-weight: bold;")

    def reconnect_serial(self):
        """[GUI] Handle reconnect button press and update COM port selection."""
        global COM_PORT
        port = self.combo_port.currentText()
        COM_PORT = port
        self.init_serial()
        self.status.setText(f"✓ Status: Reconnected to {port}")

    def on_response(self, resp, tx_hex):
        """[GUI] Display latest TX/RX frames for troubleshooting."""
        rx_hex = resp.hex().upper() if resp else '(timeout)'
        self.resp_label.setText(f"TX: {tx_hex}\nRX: {rx_hex}")

    def on_error(self, error_msg):
        """[GUI] Surface serial errors to the user via status banner."""
        self.status.setText(f"✗ Error: {error_msg}")
        self.status.setStyleSheet("background-color: #FFB6C1; padding: 8px; font-size: 11pt; font-weight: bold;")

    def send_and_read(self, frame: bytes):
        """[UTILITY] Dispatch frame through SerialWorker and return raw bytes."""
        if self.worker:
            return self.worker.send_frame(frame)
        return b""

    # ===== Read Functions =====
    def read_position(self):
        """[DRIVE] Đọc vị trí hiện tại từ driver."""
        frame = build_fc03(SLAVE_ID, 0x1000, 2)  # Reg 0x1000, 2 registers (32-bit)
        resp = self.send_and_read(frame)
        
        if len(resp) >= 9 and resp[1] == 0x03:
            try:
                position = unpack_s32_from_bytes(resp, 3)
                self.lbl_position.setText(f"Position: {position:,} pulse")
                self.lbl_position.setStyleSheet("font-size: 14pt; font-weight: bold; color: green;")
            except Exception as e:
                self.lbl_position.setText(f"Position: ERROR ({e})")
                self.lbl_position.setStyleSheet("font-size: 14pt; font-weight: bold; color: red;")
        else:
            self.lbl_position.setText("Position: NO RESPONSE")
            self.lbl_position.setStyleSheet("font-size: 14pt; font-weight: bold; color: red;")

    def read_status(self):
        """[DRIVE] Đọc trạng thái EZi-STEP và cập nhật nhãn cảnh báo."""
        frame = build_fc03(SLAVE_ID, 0x1010, 1)  # Reg 0x1010, 1 register
        resp = self.send_and_read(frame)
        
        if len(resp) >= 7 and resp[1] == 0x03:
            try:
                status_word = (resp[3] << 8) | resp[4]
                alarm = (status_word >> 8) & 0xFF
                inpos = (status_word >> 4) & 0x0F
                running = (status_word >> 2) & 0x03
                
                self.lbl_alarm.setText(f"Alarm: {'YES' if alarm else 'NO'}")
                self.lbl_alarm.setStyleSheet(
                    f"font-size: 12pt; font-weight: bold; color: {'red' if alarm else 'green'};"
                )
                
                self.lbl_inpos.setText(f"InPosition: {'YES' if inpos else 'NO'}")
                self.lbl_inpos.setStyleSheet(
                    f"font-size: 12pt; font-weight: bold; color: {'green' if inpos else 'orange'};"
                )
                
                self.lbl_running.setText(f"Running: {'YES' if running else 'NO'}")
                self.lbl_running.setStyleSheet(
                    f"font-size: 12pt; font-weight: bold; color: {'blue' if running else 'gray'};"
                )
            except Exception as e:
                self.lbl_alarm.setText(f"Alarm: ERROR")
                self.lbl_inpos.setText(f"InPosition: ERROR")
                self.lbl_running.setText(f"Running: ERROR")
        else:
            self.lbl_alarm.setText("Alarm: NO DATA")
            self.lbl_inpos.setText("InPosition: NO DATA")
            self.lbl_running.setText("Running: NO DATA")

    def start_auto_read(self):
        """[DRIVE] Kích hoạt timer đọc vị trí/trạng thái định kỳ."""
        self.timer_auto_read.start(READ_INTERVAL_MS)
        self.status.setText("⟳ Auto-reading EZi-STEP status...")
        self.status.setStyleSheet("background-color: #87CEEB; padding: 8px; font-size: 11pt; font-weight: bold;")

    def stop_auto_read(self):
        """[DRIVE] Ngắt auto-read để người dùng điều khiển thủ công."""
        self.timer_auto_read.stop()
        self.status.setText("✓ Stopped auto-reading")
        self.status.setStyleSheet("background-color: #90EE90; padding: 8px; font-size: 11pt; font-weight: bold;")

    def auto_read_status(self):
        """[DRIVE] Vòng đọc kép vị trí + trạng thái gọi bởi timer."""
        self.read_position()
        time.sleep(0.1)
        self.read_status()

    # ===== Driver Commands =====
    def step_on(self):
        """[DRIVE] Bật nguồn step để driver sẵn sàng nhận lệnh."""
        frame = build_fc06(SLAVE_ID, 0x0000, 1)
        self.send_and_read(frame)
        self.status.setText("✓ Step Motor ON")

    def step_off(self):
        """[DRIVE] Tắt nguồn step nhằm hạ driver về trạng thái an toàn."""
        frame = build_fc06(SLAVE_ID, 0x0000, 0)
        self.send_and_read(frame)
        self.status.setText("✓ Step Motor OFF")

    def reset_alarm(self):
        """[DRIVE] Reset cờ alarm để xóa lỗi máy."""
        frame = build_fc06(SLAVE_ID, 0x0001, 1)
        self.send_and_read(frame)
        self.status.setText("✓ Alarm Reset")

    def move_stop(self):
        """[DRIVE] Gửi lệnh dừng chuyển động khẩn cấp."""
        frame = build_fc06(SLAVE_ID, 0x0002, 1)
        self.send_and_read(frame)
        self.status.setText("✓ Motor Stopped")

    def jog_cw(self):
        """[DRIVE] JOG theo chiều thuận với tốc độ đặt trong ô Speed."""
        try:
            pps = int(self.le_speed.text())
            dir_val = int(self.le_dir.text()) & 0xFF
            speed_regs = pack_u32_to_regs(pps)
            frame = build_fc16(SLAVE_ID, 0x30, speed_regs + [0, dir_val])
            self.send_and_read(frame)
            self.status.setText(f"✓ JOG CW @ {pps} pps")
        except ValueError:
            self.status.setText("✗ Error: Invalid speed/direction value")

    def jog_ccw(self):
        """[DRIVE] JOG theo chiều nghịch dựa trên cùng tốc độ cấu hình."""
        try:
            pps = int(self.le_speed.text())
            dir_val = 0 if int(self.le_dir.text()) == 1 else 1
            speed_regs = pack_u32_to_regs(pps)
            frame = build_fc16(SLAVE_ID, 0x30, speed_regs + [0, dir_val])
            self.send_and_read(frame)
            self.status.setText(f"✓ JOG CCW @ {pps} pps")
        except ValueError:
            self.status.setText("✗ Error: Invalid speed/direction value")

    def move_velocity(self):
        """[DRIVE] Chạy motor ở chế độ vận tốc hở, không xét vị trí."""
        try:
            pps = int(self.le_speed.text())
            direction = int(self.le_dir.text()) & 0xFF
            speed_regs = pack_u32_to_regs(pps)
            frame = build_fc16(SLAVE_ID, 0x30, speed_regs + [0, direction])
            self.send_and_read(frame)
            self.status.setText(f"✓ Move Velocity: {pps} pps, Dir: {direction}")
        except ValueError:
            self.status.setText("✗ Error: Invalid speed/direction value")

    def move_abs(self):
        """[DRIVE] Di chuyển tới vị trí tuyệt đối với tốc độ mong muốn."""
        try:
            pos = int(self.le_abspos.text())
            pps = int(self.le_runpps.text())
            frame = build_fc16(SLAVE_ID, 0x10,
                pack_s32_to_regs(pos) + pack_u32_to_regs(pps))
            self.send_and_read(frame)
            self.status.setText(f"✓ Move Absolute: pos={pos}, speed={pps} pps")
        except ValueError:
            self.status.setText("✗ Error: Invalid position/speed value")

    def move_inc(self):
        """[DRIVE] Di chuyển tương đối (incremental) dựa trên giá trị nhập."""
        try:
            pos = int(self.le_abspos.text())
            pps = int(self.le_runpps.text())
            frame = build_fc16(SLAVE_ID, 0x20,
                pack_s32_to_regs(pos) + pack_u32_to_regs(pps))
            self.send_and_read(frame)
            self.status.setText(f"✓ Move Incremental: pos={pos}, speed={pps} pps")
        except ValueError:
            self.status.setText("✗ Error: Invalid position/speed value")

    # ===== SHT20 =====
    def start_sht(self):
        """[SHT20] Bắt đầu vòng đọc cảm biến với timer riêng."""
        self.timer_sht20.start(READ_INTERVAL_MS)
        self.status.setText("⟳ Reading SHT20...")
        self.read_count = 0
        self.error_count = 0

    def stop_sht(self):
        """[SHT20] Ngừng truy vấn SHT20 để giải phóng bus."""
        self.timer_sht20.stop()
        self.status.setText("✓ Stopped reading SHT20")

    def read_sht20(self):
        """[SHT20] Gửi FC04 và cập nhật nhãn nhiệt độ/độ ẩm."""
        frame = build_read_sht20(SLAVE_ID_SHT20)
        resp = self.send_and_read(frame)
        
        if len(resp) >= 9 and resp[1] == 0x04:
            try:
                temp = (resp[3] << 8) | resp[4]
                humi = (resp[5] << 8) | resp[6]
                self.lbl_temp.setText(f"Temp: {temp/10:.1f} °C")
                self.lbl_humi.setText(f"Humi: {humi/10:.1f} %")
                self.read_count += 1
            except Exception as e:
                self.error_count += 1
                self.lbl_temp.setText("Temp: ERR")
                self.lbl_humi.setText("Humi: ERR")
        else:
            self.error_count += 1
            self.lbl_temp.setText("Temp: NO DATA")
            self.lbl_humi.setText("Humi: NO DATA")
        
        self.lbl_read_count.setText(f"Reads: {self.read_count} | Errors: {self.error_count}")

    def closeEvent(self, event):
        """[GUI] Đảm bảo thread serial đóng trước khi thoát ứng dụng."""
        if self.worker:
            self.worker.close()
            self.worker.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = DriverGUI()
    gui.show()
    sys.exit(app.exec())
