import sys
import time
import struct
import threading
import serial

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QGridLayout, QTextEdit, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

from pyModbusTCP.server import ModbusServer

# ==========================
# CẤU HÌNH HỆ THỐNG
# ==========================
MODBUS_TCP_PORT = 502

SERIAL_TIMEOUT = 1.0
READ_INTERVAL_MS = 300

SLAVE_ID_DRIVER = 2
SLAVE_ID_SHT20 = 1
SLAVE_ID_COUNTER = 3

# Tham số auto chạy motor khi counter DONE
AUTO_MOVE_PULSES = 5000
AUTO_MOVE_SPEED = 8000

# MAP HOLDING REGISTER
HR_TARGET_ADDR = 0        # B/C ghi target counter (A → Arduino)
HR_MODE_ADDR = 8          # 0=AUTO, 1=MANUAL
HR_CMD_ADDR = 10          # packet lệnh MANUAL từ B/C
HR_CMD_REG_COUNT = 6      # CMD, POS_HI, POS_LO, SPEED, SOURCE, PRIORITY


# ==========================
# MODBUS RTU HELPER
# ==========================
def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def verify_crc(resp: bytes) -> bool:
    if len(resp) < 5:
        return False
    data = resp[:-2]
    recv_crc = resp[-2] | (resp[-1] << 8)
    calc_crc = crc16_modbus(data)
    return recv_crc == calc_crc


def build_fc03(slave_id: int, start_reg: int, count: int) -> bytes:
    data = bytes([
        slave_id, 0x03,
        (start_reg >> 8) & 0xFF, start_reg & 0xFF,
        (count >> 8) & 0xFF, count & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_fc04(slave_id: int, start_reg: int, count: int) -> bytes:
    data = bytes([
        slave_id, 0x04,
        (start_reg >> 8) & 0xFF, start_reg & 0xFF,
        (count >> 8) & 0xFF, count & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_fc06(slave_id: int, reg_addr: int, reg_val: int) -> bytes:
    data = bytes([
        slave_id, 0x06,
        (reg_addr >> 8) & 0xFF, reg_addr & 0xFF,
        (reg_val >> 8) & 0xFF, reg_val & 0xFF
    ])
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_fc16(slave_id: int, start_reg: int, registers: list) -> bytes:
    reg_count = len(registers)
    byte_count = reg_count * 2
    data = bytearray([
        slave_id, 0x10,
        (start_reg >> 8) & 0xFF, start_reg & 0xFF,
        (reg_count >> 8) & 0xFF, reg_count & 0xFF,
        byte_count
    ])
    for reg in registers:
        data.append((reg >> 8) & 0xFF)
        data.append(reg & 0xFF)
    crc = crc16_modbus(bytes(data))
    return bytes(data) + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def pack_u32(val: int) -> list:
    return [(val >> 16) & 0xFFFF, val & 0xFFFF]


def pack_s32(val: int) -> list:
    if val < 0:
        val = (1 << 32) + val
    return [(val >> 16) & 0xFFFF, val & 0xFFFF]


def unpack_s32_from_bytes(b: bytes, offset: int) -> int:
    val = (b[offset] << 24) | (b[offset+1] << 16) | (b[offset+2] << 8) | b[offset+3]
    if val & 0x80000000:
        val = val - (1 << 32)
    return val


# ==========================
# SIGNAL EMITTER (thread → UI)
# ==========================
class SignalEmitter(QObject):
    log_signal = pyqtSignal(str)
    tcp_status_signal = pyqtSignal(str)


# ==========================
# MAIN GUI – PLC HMI
# ==========================
class LayerA_PLC(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LAYER A - FIELD CONTROLLER (PLC MODE)")
        self.setGeometry(50, 50, 900, 700)

        # Serial / Modbus RTU
        self.ser = None
        self.ser_lock = threading.Lock()

        # Driver state
        self.current_position = 0
        self.current_speed = 0
        self.driver_alarm = False
        self.driver_inpos = False
        self.driver_running = False

        # SHT20
        self.temperature = 0.0
        self.humidity = 0.0
        self.sht20_ok = False

        # Counter Arduino
        self.counter_value = 0
        self.counter_target = 0
        self.counter_done = False

        # AUTO logic
        self.auto_enabled = True
        self.motor_state = "Idle"
        self.last_motor_cmd_time = time.time()

        # Target nhận từ Modbus TCP HR0
        self.last_tcp_target = 0

        # Modbus TCP server
        self.modbus_server = None
        self.running = True

        # Signals
        self.signals = SignalEmitter()
        self.signals.log_signal.connect(self.append_log)
        self.signals.tcp_status_signal.connect(self.update_tcp_status)

        self._build_ui()
        self._start_modbus_tcp_server()

        # Timers
        self.timer_read = QTimer()
        self.timer_read.timeout.connect(self.read_all_devices)
        self.timer_read.start(READ_INTERVAL_MS)

        self.timer_auto = QTimer()
        self.timer_auto.timeout.connect(self.auto_cycle)
        self.timer_auto.start(200)

    # --------------------------
    # UI LAYOUT
    # --------------------------
    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # ===== STATUS BAR =====
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Box)
        status_frame.setLineWidth(2)
        status_frame.setStyleSheet("border: 2px solid #d0d0d0; background: #f5f5f5;")
        s_layout = QVBoxLayout()

        self.lbl_main_status = QLabel("PLC AUTO MODE (AUTO/MANUAL từ Layer B)")
        self.lbl_main_status.setAlignment(Qt.AlignCenter)
        self.lbl_main_status.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-size: 18pt;
            font-weight: bold;
            padding: 16px;
            border-radius: 6px;
        """)
        s_layout.addWidget(self.lbl_main_status)

        self.lbl_sub_status = QLabel(
            "Layer A acts as PLC: AUTO cycle theo counter hoặc MANUAL nhận lệnh từ B/C.\n"
            f"Target count từ Layer B via Modbus TCP HR{HR_TARGET_ADDR}."
        )
        self.lbl_sub_status.setAlignment(Qt.AlignCenter)
        self.lbl_sub_status.setStyleSheet("color:#555555; font-size:10pt; padding:4px;")
        s_layout.addWidget(self.lbl_sub_status)

        status_frame.setLayout(s_layout)
        layout.addWidget(status_frame)

        # ===== CONNECTION STATUS =====
        conn_group = QGroupBox("CONNECTION STATUS")
        conn_group.setStyleSheet("""
            QGroupBox {
                font-weight:bold;
                font-size:11pt;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                margin-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
        """)
        conn_layout = QGridLayout()

        conn_layout.addWidget(QLabel("RS485 Interface:"), 0, 0)
        self.lbl_serial_status = QLabel("Disconnected")
        self.lbl_serial_status.setStyleSheet("font-weight:bold; font-size:11pt; color:#777777;")
        conn_layout.addWidget(self.lbl_serial_status, 0, 1)

        row_serial = QHBoxLayout()
        self.combo_port = QComboBox()
        self.combo_port.addItems(["COM11", "COM3", "COM4", "COM5", "COM6", "COM7"])
        row_serial.addWidget(QLabel("Port:"))
        row_serial.addWidget(self.combo_port)

        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.combo_baud.setCurrentText("9600")
        row_serial.addWidget(QLabel("Baud:"))
        row_serial.addWidget(self.combo_baud)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setStyleSheet("""
            background:#e0e0e0;
            color:#333333;
            font-weight:bold;
            padding:4px 10px;
            border:1px solid #c0c0c0;
            border-radius:3px;
        """)
        self.btn_connect.clicked.connect(self.connect_serial)
        row_serial.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setStyleSheet("""
            background:#f0f0f0;
            color:#555555;
            padding:4px 10px;
            border:1px solid #cccccc;
            border-radius:3px;
        """)
        self.btn_disconnect.clicked.connect(self.disconnect_serial)
        self.btn_disconnect.setEnabled(False)
        row_serial.addWidget(self.btn_disconnect)

        conn_layout.addLayout(row_serial, 1, 0, 1, 2)

        conn_layout.addWidget(QLabel("Modbus TCP Server:"), 2, 0)
        self.lbl_tcp_status = QLabel("Starting...")
        self.lbl_tcp_status.setStyleSheet("font-weight:bold; font-size:11pt; color:#999999;")
        conn_layout.addWidget(self.lbl_tcp_status, 2, 1)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # ===== MONITORING =====
        mon_group = QGroupBox("DEVICE & PROCESS MONITORING")
        mon_group.setStyleSheet("""
            QGroupBox {
                font-weight:bold;
                font-size:11pt;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                margin-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
        """)
        mon_layout = QGridLayout()

        self.lbl_temp = QLabel("--.- °C")
        self.lbl_temp.setAlignment(Qt.AlignCenter)
        self.lbl_temp.setStyleSheet("""
            background:#ffffff;
            color:#333333;
            font-size:16pt;
            padding:10px;
            border-radius:6px;
            border:1px solid #cccccc;
        """)
        mon_layout.addWidget(self.lbl_temp, 0, 0)

        self.lbl_humi = QLabel("--.- %")
        self.lbl_humi.setAlignment(Qt.AlignCenter)
        self.lbl_humi.setStyleSheet("""
            background:#ffffff;
            color:#333333;
            font-size:16pt;
            padding:10px;
            border-radius:6px;
            border:1px solid #cccccc;
        """)
        mon_layout.addWidget(self.lbl_humi, 0, 1)

        self.lbl_sht_status = QLabel("SHT20: OFFLINE")
        self.lbl_sht_status.setStyleSheet("font-weight:bold; color:#c0392b;")
        mon_layout.addWidget(self.lbl_sht_status, 1, 0, 1, 2)

        self.lbl_pos = QLabel("Position: 0 pulse")
        self.lbl_pos.setStyleSheet("font-size:12pt; font-weight:bold;")
        mon_layout.addWidget(self.lbl_pos, 2, 0, 1, 2)

        self.lbl_drv_alarm = QLabel("Alarm: NO")
        self.lbl_drv_alarm.setStyleSheet("color:#27ae60; font-weight:bold;")
        mon_layout.addWidget(self.lbl_drv_alarm, 3, 0)

        self.lbl_drv_inpos = QLabel("InPos: NO")
        self.lbl_drv_inpos.setStyleSheet("color:#f39c12; font-weight:bold;")
        mon_layout.addWidget(self.lbl_drv_inpos, 3, 1)

        self.lbl_drv_run = QLabel("Running: NO")
        self.lbl_drv_run.setStyleSheet("color:#95a5a6; font-weight:bold;")
        mon_layout.addWidget(self.lbl_drv_run, 4, 0)

        self.lbl_counter = QLabel("Counter: 0 / 0")
        self.lbl_counter.setStyleSheet("font-size:12pt; font-weight:bold;")
        mon_layout.addWidget(self.lbl_counter, 5, 0, 1, 2)

        self.lbl_counter_done = QLabel("Counter DONE: NO")
        self.lbl_counter_done.setStyleSheet("color:#95a5a6; font-weight:bold;")
        mon_layout.addWidget(self.lbl_counter_done, 6, 0, 1, 2)

        self.lbl_auto_state = QLabel("AUTO STATE: Idle")
        self.lbl_auto_state.setStyleSheet("font-size:12pt; font-weight:bold; color:#2c3e50;")
        mon_layout.addWidget(self.lbl_auto_state, 7, 0, 1, 2)

        self.lbl_mode_info = QLabel("MODE: AUTO")
        self.lbl_mode_info.setStyleSheet("font-size:11pt; font-weight:bold; color:#27ae60;")
        mon_layout.addWidget(self.lbl_mode_info, 8, 0, 1, 2)

        self.lbl_tcp_target = QLabel("TCP Target: 0")
        self.lbl_tcp_target.setStyleSheet("font-size:11pt; font-weight:bold; color:#555555;")
        mon_layout.addWidget(self.lbl_tcp_target, 9, 0, 1, 2)

        mon_group.setLayout(mon_layout)
        layout.addWidget(mon_group)

        # ===== LOG =====
        log_group = QGroupBox("SYSTEM LOG")
        log_group.setStyleSheet("""
            QGroupBox {
                font-weight:bold;
                font-size:11pt;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                margin-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
        """)
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("""
            background:#f5f5f5;
            color:#333333;
            font-family:'Consolas';
            font-size:9pt;
            border-radius:4px;
            border:1px solid #d0d0d0;
        """)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        self.setLayout(layout)
        self.log("Layer A (PLC mode) initialized.")
        self.log("AUTO cycle enabled.")
        self.log(f"Listening for TARGET from B via Modbus TCP HR{HR_TARGET_ADDR}.")
        self.log(f"MODE control via HR{HR_MODE_ADDR} (0=AUTO, 1=MANUAL).")

    # --------------------------
    # SERIAL / RTU
    # --------------------------
    def connect_serial(self):
        if self.ser and self.ser.is_open:
            self.log("Already connected.")
            return

        port = self.combo_port.currentText()
        baud = int(self.combo_baud.currentText())
        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=SERIAL_TIMEOUT)
            time.sleep(0.1)
            self.lbl_serial_status.setText("Connected")
            self.lbl_serial_status.setStyleSheet("font-weight:bold; font-size:11pt; color:#27ae60;")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.log(f"RS485 connected on {port} @ {baud}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot connect:\n{e}")
            self.log(f"RS485 error: {e}")

    def disconnect_serial(self):
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
        self.lbl_serial_status.setText("Disconnected")
        self.lbl_serial_status.setStyleSheet("font-weight:bold; font-size:11pt; color:#777777;")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.log("RS485 disconnected")

    def send_frame(self, frame: bytes) -> bytes:
        if not self.ser or not self.ser.is_open:
            return b""
        with self.ser_lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write(frame)
                self.ser.flush()
                time.sleep(0.02)

                resp = b""
                start = time.time()
                while time.time() - start < SERIAL_TIMEOUT:
                    chunk = self.ser.read(256)
                    if chunk:
                        resp += chunk
                        time.sleep(0.03)
                    else:
                        if resp:
                            break
                        time.sleep(0.01)
                return resp
            except Exception as e:
                self.log(f"Serial error: {e}")
                return b""

    # --------------------------
    # READ DEVICES
    # --------------------------
    def read_all_devices(self):
        # Đọc vị trí hiện tại
        frame = build_fc03(SLAVE_ID_DRIVER, 0x1000, 2)
        resp = self.send_frame(frame)
        if len(resp) >= 9 and resp[1] == 0x03 and verify_crc(resp):
            try:
                self.current_position = unpack_s32_from_bytes(resp, 3)
            except:
                pass

        time.sleep(0.01)

        # Đọc status driver
        frame = build_fc03(SLAVE_ID_DRIVER, 0x1010, 1)
        resp = self.send_frame(frame)
        if len(resp) >= 7 and resp[1] == 0x03 and verify_crc(resp):
            sw = (resp[3] << 8) | resp[4]
            self.driver_alarm = bool((sw >> 8) & 0x01)
            self.driver_inpos = bool((sw >> 4) & 0x01)
            self.driver_running = bool((sw >> 2) & 0x01)

        time.sleep(0.01)

        # Đọc SHT20
        frame = build_fc04(SLAVE_ID_SHT20, 0x0001, 2)
        resp = self.send_frame(frame)
        if len(resp) >= 9 and resp[1] == 0x04 and verify_crc(resp):
            try:
                self.temperature = ((resp[3] << 8) | resp[4]) / 10.0
                self.humidity = ((resp[5] << 8) | resp[6]) / 10.0
                self.sht20_ok = True
            except:
                self.sht20_ok = False
        else:
            self.sht20_ok = False

        time.sleep(0.01)

        # Đọc Counter Arduino
        frame = build_fc03(SLAVE_ID_COUNTER, 0x0000, 4)
        resp = self.send_frame(frame)
        if len(resp) >= 13 and resp[1] == 0x03 and verify_crc(resp):
            hr0 = (resp[3] << 8) | resp[4]
            hr1 = (resp[5] << 8) | resp[6]
            hr2 = (resp[7] << 8) | resp[8]
            self.counter_value = hr0
            self.counter_target = hr1
            self.counter_done = bool(hr2 & 0x0001)

        self.update_ui()
        self.update_input_registers()

    # --------------------------
    # CHECK TARGET FROM TCP
    # --------------------------
    def check_target_from_tcp(self):
        if not self.modbus_server:
            return

        try:
            hr = self.modbus_server.data_bank.get_holding_registers(HR_TARGET_ADDR, 1)
            if not hr or len(hr) < 1:
                return

            target = hr[0]

            # Thay đổi target → gửi xuống Arduino
            if target != self.last_tcp_target:
                self.last_tcp_target = target
                self.log(f"TARGET HR{HR_TARGET_ADDR} = {target} → gửi xuống Arduino")

                frame = build_fc06(SLAVE_ID_COUNTER, 0x0001, target)
                resp = self.send_frame(frame)

                if resp and len(resp) >= 8:
                    self.log(f"Arduino nhận target = {target}")
                else:
                    self.log("Arduino không confirm target")

                self.counter_target = target

        except Exception as e:
            self.log(f"Error reading HR{HR_TARGET_ADDR}: {e}")

    # --------------------------
    # PROCESS MANUAL COMMAND (ĐÃ SỬA)
    # --------------------------
    def process_manual_command(self):
        if not self.modbus_server:
            return

        try:
            regs = self.modbus_server.data_bank.get_holding_registers(
                HR_CMD_ADDR, HR_CMD_REG_COUNT
            )
            if not regs or len(regs) < HR_CMD_REG_COUNT:
                return

            cmd, pos_hi, pos_lo, speed, source_code, priority = regs

            if cmd == 0:
                return

            pos_val = ((pos_hi & 0xFFFF) << 16) | (pos_lo & 0xFFFF)
            if pos_val & 0x80000000:
                pos_val -= (1 << 32)

            src_text = "B" if source_code == 2 else ("C" if source_code == 3 else "Unknown")

            self.log(
                f"MANUAL CMD={cmd} from {src_text} "
                f"prio={priority}, pos={pos_val}, speed={speed}"
            )

            # Chuẩn hóa speed
            if speed < 0:
                speed = 0
            if speed > 0xFFFFFFFF:
                speed = 0xFFFFFFFF

            frame = b""

            # STEP ON
            if cmd == 1:
                frame = build_fc06(SLAVE_ID_DRIVER, 0x0000, 1)

            # STEP OFF
            elif cmd == 2:
                frame = build_fc06(SLAVE_ID_DRIVER, 0x0000, 0)

            # MOVE ABS (giữ nguyên địa chỉ bạn đang dùng)
            elif cmd == 3:
                frame = build_fc16(
                    SLAVE_ID_DRIVER,
                    0x20,
                    pack_s32(pos_val) + pack_u32(speed)
                )

            # JOG CW (MOVE VELOCITY CW)
            elif cmd == 5:
                speed_regs = pack_u32(speed)
                frame = build_fc16(
                    SLAVE_ID_DRIVER,
                    0x0030,
                    speed_regs + [0, 1]   # [speed_hi, speed_lo, 0, dir=1(CW)]
                )

            # JOG CCW (MOVE VELOCITY CCW)
            elif cmd == 6:
                speed_regs = pack_u32(speed)
                frame = build_fc16(
                    SLAVE_ID_DRIVER,
                    0x0030,
                    speed_regs + [0, 0]   # dir=0(CCW)
                )

            # STOP
            elif cmd == 7:
                frame = build_fc06(SLAVE_ID_DRIVER, 0x0002, 1)

            # RESET ALARM
            elif cmd == 8:
                frame = build_fc06(SLAVE_ID_DRIVER, 0x0001, 1)

            # EMERGENCY STOP (cũng dùng STOP register)
            elif cmd == 9:
                frame = build_fc06(SLAVE_ID_DRIVER, 0x0002, 1)

            # Gửi nếu có lệnh
            if frame:
                self.send_frame(frame)

            # Clear CMD
            self.modbus_server.data_bank.set_holding_registers(HR_CMD_ADDR, [0])

        except Exception as e:
            self.log(f"Error in process_manual_command: {e}")

    # --------------------------
    # AUTO CYCLE
    # --------------------------
        # --------------------------
    # AUTO CYCLE (FIXED – lặp nhiều chu kỳ)
    # --------------------------
    def auto_cycle(self):
        # Cập nhật target từ Layer B/C xuống Arduino
        self.check_target_from_tcp()

        # Đọc MODE từ HR_MODE_ADDR (0=AUTO, 1=MANUAL)
        mode = 0
        if self.modbus_server:
            try:
                m = self.modbus_server.data_bank.get_holding_registers(HR_MODE_ADDR, 1)
                if m and len(m) >= 1:
                    mode = m[0]
                    if not hasattr(self, "_last_mode_logged"):
                        self._last_mode_logged = -1
                    if mode != self._last_mode_logged:
                        self.log(f"MODE from HR{HR_MODE_ADDR} = {mode}")
                        self._last_mode_logged = mode
            except Exception as e:
                self.log(f"Error reading HR_MODE: {e}")
                mode = 0

        # ---------- MANUAL MODE ----------
        if mode == 1:
            self.motor_state = "Manual"
            self.process_manual_command()
            self.update_ui()
            self.update_input_registers()
            return

        # ---------- AUTO MODE ----------
        if not self.auto_enabled:
            self.motor_state = "Disabled"
            self.update_ui()
            self.update_input_registers()
            return

        if self.driver_alarm:
            if self.motor_state != "Alarm":
                self.log("AUTO stopped: driver alarm.")
            self.motor_state = "Alarm"
            self.update_ui()
            self.update_input_registers()
            return

        if self.counter_target <= 0:
            # Chưa được set target từ Layer B/C
            self.motor_state = "Waiting target"
            self.update_ui()
            self.update_input_registers()
            return

        # ==================================================
        # 1. Nếu COUNTER DONE và motor KHÔNG ở trạng thái chạy
        #    → phát lệnh chạy motor (bắt đầu 1 chu kỳ mới)
        # ==================================================
        if self.counter_done and self.motor_state not in ("Motor running", "Alarm"):
            frame = build_fc16(
                SLAVE_ID_DRIVER,
                0x20,
                pack_s32(AUTO_MOVE_PULSES) + pack_u32(AUTO_MOVE_SPEED)
            )
            self.send_frame(frame)
            self.current_speed = AUTO_MOVE_SPEED
            self.motor_state = "Motor running"
            self.last_motor_cmd_time = time.time()
            self.log(
                f"AUTO: count reached target "
                f"({self.counter_value}/{self.counter_target}), "
                f"run motor +{AUTO_MOVE_PULSES} pulses."
            )
            # Sau khi phát lệnh chạy thì chờ InPos ở vòng kế tiếp
            self.update_ui()
            self.update_input_registers()
            return

        # ==================================================
        # 2. Motor đang chạy → chờ INPOS hoặc TIMEOUT
        # ==================================================
        if self.motor_state == "Motor running":
            if self.driver_inpos:
                # Motor đã in position → gửi lệnh reset counter (HR3 = 1)
                frame = build_fc06(SLAVE_ID_COUNTER, 0x0003, 1)
                self.send_frame(frame)
                self.motor_state = "Waiting reset"
                self.last_motor_cmd_time = time.time()
                self.log("AUTO: motor in-position, reset counter (HR3=1).")
            elif time.time() - self.last_motor_cmd_time > 10:
                # Quá 10 giây chưa InPos → lỗi timeout
                self.motor_state = "Timeout motor"
                self.log("AUTO: timeout waiting for motor InPos.")
            self.update_ui()
            self.update_input_registers()
            return

        # ==================================================
        # 3. Đang chờ Arduino RESET counter sau khi nhận HR3=1
        #    Khi thấy counter_value = 0 và DONE đã clear → quay lại Idle
        # ==================================================
        if self.motor_state == "Waiting reset":
            if self.counter_value == 0 and not self.counter_done:
                self.motor_state = "Idle"
                self.log("AUTO: new cycle started (counter reset).")
            self.update_ui()
            self.update_input_registers()
            return

        # ==================================================
        # 4. Các trạng thái còn lại trong AUTO (Idle / Waiting count / Timeout...)
        #    → chỉ đơn giản là đang CHỜ COUNTER ĐẠT TARGET
        # ==================================================
        if self.motor_state not in (
            "Idle",
            "Waiting count",
            "Waiting target",
            "Timeout motor",
        ):
            # Nếu đang ở trạng thái lạ mà vẫn AUTO → đưa về Waiting count
            self.motor_state = "Waiting count"
        elif not self.counter_done:
            # Đang đếm nhưng chưa DONE
            self.motor_state = "Waiting count"

        self.update_ui()
        self.update_input_registers()


    # --------------------------
    # UPDATE UI
    # --------------------------
    def update_ui(self):
        self.lbl_temp.setText(f"{self.temperature:.1f} °C")
        self.lbl_humi.setText(f"{self.humidity:.1f} %")

        if self.sht20_ok:
            self.lbl_sht_status.setText("SHT20: ONLINE")
            self.lbl_sht_status.setStyleSheet("font-weight:bold; color:#27ae60;")
        else:
            self.lbl_sht_status.setText("SHT20: OFFLINE")
            self.lbl_sht_status.setStyleSheet("font-weight:bold; color:#c0392b;")

        self.lbl_pos.setText(f"Position: {self.current_position:,} pulse")

        if self.driver_alarm:
            self.lbl_drv_alarm.setText("Alarm: YES")
            self.lbl_drv_alarm.setStyleSheet("color:#c0392b; font-weight:bold;")
        else:
            self.lbl_drv_alarm.setText("Alarm: NO")
            self.lbl_drv_alarm.setStyleSheet("color:#27ae60; font-weight:bold;")

        if self.driver_inpos:
            self.lbl_drv_inpos.setText("InPos: YES")
            self.lbl_drv_inpos.setStyleSheet("color:#27ae60; font-weight:bold;")
        else:
            self.lbl_drv_inpos.setText("InPos: NO")
            self.lbl_drv_inpos.setStyleSheet("color:#f39c12; font-weight:bold;")

        if self.driver_running:
            self.lbl_drv_run.setText("Running: YES")
            self.lbl_drv_run.setStyleSheet("color:#3498db; font-weight:bold;")
        else:
            self.lbl_drv_run.setText("Running: NO")
            self.lbl_drv_run.setStyleSheet("color:#95a5a6; font-weight:bold;")

        self.lbl_counter.setText(f"Counter: {self.counter_value} / {self.counter_target}")
        if self.counter_done:
            self.lbl_counter_done.setText("Counter DONE: YES")
            self.lbl_counter_done.setStyleSheet("color:#27ae60; font-weight:bold;")
        else:
            self.lbl_counter_done.setText("Counter DONE: NO")
            self.lbl_counter_done.setStyleSheet("color:#95a5a6; font-weight:bold;")

        self.lbl_auto_state.setText(f"AUTO STATE: {self.motor_state}")
        self.lbl_tcp_target.setText(f"TCP Target: {self.last_tcp_target}")

        mode = 0
        if self.modbus_server:
            try:
                m = self.modbus_server.data_bank.get_holding_registers(HR_MODE_ADDR, 1)
                if m and len(m) >= 1:
                    mode = m[0]
            except:
                pass

        if mode == 1:
            self.lbl_mode_info.setText("MODE: MANUAL")
            self.lbl_mode_info.setStyleSheet("font-size:11pt; font-weight:bold; color:#e67e22;")
        else:
            self.lbl_mode_info.setText("MODE: AUTO")
            self.lbl_mode_info.setStyleSheet("font-size:11pt; font-weight:bold; color:#27ae60;")

    # --------------------------
    # UPDATE INPUT REGISTERS
    # --------------------------
    def update_input_registers(self):
        if not self.modbus_server:
            return

        try:
            pos = self.current_position
            if pos < 0:
                pos_val = (1 << 32) + pos
            else:
                pos_val = pos
            pos_hi = (pos_val >> 16) & 0xFFFF
            pos_lo = pos_val & 0xFFFF

            speed = max(0, min(int(self.current_speed), 0xFFFF))
            temp = max(-32768, min(int(self.temperature * 10), 32767)) & 0xFFFF
            humi = max(0, min(int(self.humidity * 10), 0xFFFF))

            status_word = 0
            if self.driver_alarm:
                status_word |= 1 << 0
            if self.driver_inpos:
                status_word |= 1 << 1
            if self.driver_running:
                status_word |= 1 << 2

            state_map = {
                "Idle": 0,
                "Waiting count": 1,
                "Motor running": 2,
                "Waiting reset": 3,
                "Alarm": 4,
                "Timeout motor": 5,
                "Disabled": 6,
                "Waiting target": 7,
                "Manual": 8,
            }
            auto_code = state_map.get(self.motor_state, 0)

            mode_val = 0
            try:
                m = self.modbus_server.data_bank.get_holding_registers(HR_MODE_ADDR, 1)
                if m and len(m) >= 1:
                    mode_val = m[0]
            except:
                pass

            regs = [
                pos_hi,
                pos_lo,
                speed,
                temp,
                humi,
                status_word,
                self.counter_value,
                self.counter_target,
                auto_code,
                mode_val,
            ]
            self.modbus_server.data_bank.set_input_registers(0, regs)
        except Exception as e:
            self.log(f"Error updating input regs: {e}")

    # --------------------------
    # START MODBUS TCP SERVER
    # --------------------------
    def _start_modbus_tcp_server(self):
        def server_thread():
            try:
                self.modbus_server = ModbusServer(
                    host="0.0.0.0",
                    port=MODBUS_TCP_PORT,
                    no_block=True
                )
                self.modbus_server.start()

                # Init Input Registers & Holding Registers
                self.modbus_server.data_bank.set_input_registers(0, [0] * 32)

                hr_init = [0] * 100
                hr_init[HR_TARGET_ADDR] = 0
                hr_init[HR_MODE_ADDR] = 0
                hr_init[HR_CMD_ADDR] = 0
                self.modbus_server.data_bank.set_holding_registers(0, hr_init)

                self.signals.tcp_status_signal.emit(f"Listening on {MODBUS_TCP_PORT}")
                self.signals.log_signal.emit(f"Modbus TCP Server started on port {MODBUS_TCP_PORT}")

                while self.running:
                    time.sleep(0.5)
            except Exception as e:
                self.signals.log_signal.emit(f"Modbus server error: {e}")
                self.signals.tcp_status_signal.emit("Modbus server error")

        threading.Thread(target=server_thread, daemon=True).start()

    # --------------------------
    # HELPERS
    # --------------------------
    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")

    def append_log(self, msg: str):
        self.log(msg)

    def update_tcp_status(self, text: str):
        self.lbl_tcp_status.setText(text)
        if "Listening" in text or "listening" in text:
            self.lbl_tcp_status.setStyleSheet("font-weight:bold; font-size:11pt; color:#27ae60;")
        elif "error" in text.lower():
            self.lbl_tcp_status.setStyleSheet("font-weight:bold; font-size:11pt; color:#c0392b;")
        else:
            self.lbl_tcp_status.setStyleSheet("font-weight:bold; font-size:11pt; color:#e67e22;")

    def closeEvent(self, event):
        self.running = False
        self.timer_read.stop()
        self.timer_auto.stop()

        if self.ser:
            try:
                self.ser.close()
            except:
                pass

        if self.modbus_server:
            try:
                self.modbus_server.stop()
            except:
                pass

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = LayerA_PLC()
    gui.show()
    sys.exit(app.exec())
