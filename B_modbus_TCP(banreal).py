import sys, time, socket, threading, json
from collections import deque

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QHBoxLayout,
    QLineEdit, QMessageBox, QGroupBox, QGridLayout, QFrame,
    QScrollArea, QPlainTextEdit
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont

from pyModbusTCP.client import ModbusClient

# =========================================
# CẤU HÌNH
# =========================================

A_HOST = "192.168.0.121"
A_MODBUS_PORT = 502

SERVER_PORT = 5002
BUFFER_SIZE = 4096

# MAP HOLDING REGISTER TRÊN A
A_HR_TARGET_ADDR = 0
A_HR_MODE_ADDR = 8
A_HR_CMD_ADDR = 10
A_HR_CMD_REG_COUNT = 6

AUTO_STATE_MAP = {
    0: "Idle",
    1: "Waiting count",
    2: "Motor running",
    3: "Waiting reset",
    4: "Alarm",
    5: "Timeout motor",
    6: "Disabled",
    7: "Waiting target",
    8: "Manual",
}


# =========================================
# SIGNAL EMITTER
# =========================================

class SignalEmitter(QObject):
    log_signal = pyqtSignal(str)
    status_update = pyqtSignal(dict)
    connection_signal = pyqtSignal(str, str)
    forward_signal = pyqtSignal(str)


# =========================================
# LAYER B – SCADA SUPERVISOR
# =========================================

class LayerB_SCADASupervisor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LAYER B - SCADA SUPERVISOR (Priority 2)")
        self.setGeometry(100, 100, 1200, 800)

        # ===== STATE =====
        self.current_position = 0
        self.current_speed = 0
        self.temperature = 0.0
        self.humidity = 0.0
        self.driver_alarm = False
        self.driver_inpos = False
        self.driver_running = False

        self.counter_value = 0
        self.counter_target = 0
        self.auto_state_code = 0
        self.sht20_enabled = True
        self.current_mode = 0

        # NEW: STEP & JOG STATE từ Layer A (IR10, IR11)
        self.step_enabled = False    # IR10: 0/1
        self.jog_state = 0           # IR11: 0=OFF, 1=CW, 2=CCW

        # network / modbus
        self.modbus_client_a = None
        self.modbus_connected = False
        self.modbus_lock = threading.Lock()

        # TCP server cho Layer C
        self.server_socket = None
        self.client_c = None
        self.running = True

        # statistics
        self.commands_forwarded = 0
        self.commands_from_c = 0
        self.status_updates = 0
        self.start_time = time.time()
        self.command_history = deque(maxlen=10)

        # signals
        self.signals = SignalEmitter()
        self.signals.log_signal.connect(self.append_log)
        self.signals.status_update.connect(self.update_displays)
        self.signals.connection_signal.connect(self.update_connection_status)
        self.signals.forward_signal.connect(self.show_forward_animation)

        # UI
        self._build_ui()

        # Modbus client tới Layer A
        self._init_modbus_to_a()

        # Server JSON cho Layer C
        self._start_server_for_c()

        # Thread poll A
        self._start_modbus_poll_thread()

        # Stats update timer
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_statistics)
        self.stats_timer.start(1000)

    # =========================================================
    #   UI
    # =========================================================
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # 1. MAIN STATUS BAR
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setFrameShape(QFrame.Box)
        self.status_bar_frame.setLineWidth(2)
        self.status_bar_frame.setStyleSheet("border: 2px solid #d0d0d0;")
        status_bar_layout = QVBoxLayout()

        self.lbl_main_status = QLabel("SCADA SUPERVISOR - MONITOR & CONTROL")
        self.lbl_main_status.setAlignment(Qt.AlignCenter)
        self.lbl_main_status.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            padding: 20px;
            font-size: 18pt;
            font-weight: bold;
            border-radius: 10px;
        """)
        status_bar_layout.addWidget(self.lbl_main_status)

        self.status_bar_frame.setLayout(status_bar_layout)
        layout.addWidget(self.status_bar_frame)

        # 2. NETWORK TOPOLOGY
        topology_group = QGroupBox("NETWORK TOPOLOGY & STATUS")
        topology_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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
        topology_layout = QVBoxLayout()

        conn_frame = QFrame()
        conn_frame.setFrameShape(QFrame.StyledPanel)
        conn_frame.setStyleSheet("background: #f5f5f5; border-radius: 5px;")
        conn_layout = QGridLayout()

        conn_layout.addWidget(QLabel("Connection to Layer A (Modbus TCP):"), 0, 0)
        self.lbl_conn_a = QLabel("Connecting...")
        self.lbl_conn_a.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e67e22;")
        conn_layout.addWidget(self.lbl_conn_a, 0, 1)

        self.lbl_a_detail = QLabel(f"Target: {A_HOST}:{A_MODBUS_PORT} (Modbus TCP)")
        self.lbl_a_detail.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        conn_layout.addWidget(self.lbl_a_detail, 0, 2)

        conn_frame.setLayout(conn_layout)
        topology_layout.addWidget(conn_frame)

        topology_group.setLayout(topology_layout)
        layout.addWidget(topology_group)

        # 3. SYSTEM HEALTH
        health_group = QGroupBox("SYSTEM HEALTH & STATISTICS")
        health_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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
        health_layout = QGridLayout()

        health_layout.addWidget(QLabel("Uptime:"), 0, 0)
        self.lbl_uptime = QLabel("00:00:00")
        self.lbl_uptime.setStyleSheet("font-weight: bold; font-size: 11pt; color: #27ae60;")
        health_layout.addWidget(self.lbl_uptime, 0, 1)

        health_layout.addWidget(QLabel("Commands forwarded to A:"), 1, 0)
        self.lbl_cmd_forwarded = QLabel("0")
        self.lbl_cmd_forwarded.setStyleSheet("font-weight: bold; font-size: 11pt; color: #9b59b6;")
        health_layout.addWidget(self.lbl_cmd_forwarded, 1, 1)

        health_layout.addWidget(QLabel("Status updates from A:"), 1, 2)
        self.lbl_status_updates = QLabel("0")
        self.lbl_status_updates.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e67e22;")
        health_layout.addWidget(self.lbl_status_updates, 1, 3)

        health_group.setLayout(health_layout)
        layout.addWidget(health_group)

        # 4. PROCESS STATE
        process_group = QGroupBox("PROCESS / COUNTER STATE (FROM LAYER A)")
        process_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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
        process_layout = QGridLayout()

        self.lbl_counter = QLabel("Counter: -- / --")
        self.lbl_counter.setStyleSheet("font-size: 13pt; font-weight: bold; color: #2c3e50;")
        process_layout.addWidget(self.lbl_counter, 0, 0, 1, 2)

        self.lbl_counter_done = QLabel("DONE: --")
        self.lbl_counter_done.setStyleSheet("font-size: 11pt; font-weight: bold; color: #95a5a6;")
        process_layout.addWidget(self.lbl_counter_done, 1, 0)

        self.lbl_auto_state = QLabel("AUTO STATE: Unknown")
        self.lbl_auto_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #2c3e50;")
        process_layout.addWidget(self.lbl_auto_state, 1, 1)

        process_group.setLayout(process_layout)
        layout.addWidget(process_group)

        # 5. MODE CONTROL
        mode_group = QGroupBox("MODE CONTROL (Layer A AUTO / MANUAL)")
        mode_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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
        mode_layout = QHBoxLayout()

        self.lbl_mode_status = QLabel("Mode: AUTO")
        self.lbl_mode_status.setStyleSheet("font-weight: bold; font-size: 11pt; color: #27ae60;")
        mode_layout.addWidget(self.lbl_mode_status)

        self.btn_mode_auto = QPushButton("A → AUTO")
        self.btn_mode_auto.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 6px;
            border: 1px solid #c0c0c0;
            border-radius: 4px;
        """)
        self.btn_mode_auto.clicked.connect(lambda: self.set_mode(0))
        mode_layout.addWidget(self.btn_mode_auto)

        self.btn_mode_manual = QPushButton("A → MANUAL")
        self.btn_mode_manual.setStyleSheet("""
            background: #f0f0f0;
            color: #333333;
            font-weight: bold;
            padding: 6px;
            border: 1px solid #c0c0c0;
            border-radius: 4px;
        """)
        self.btn_mode_manual.clicked.connect(lambda: self.set_mode(1))
        mode_layout.addWidget(self.btn_mode_manual)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # 6. REAL-TIME DATA FROM A
        data_group = QGroupBox("REAL-TIME DEVICE DATA FROM LAYER A")
        data_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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
        data_layout = QVBoxLayout()

        sensor_frame = QFrame()
        sensor_frame.setFrameShape(QFrame.StyledPanel)
        sensor_frame.setStyleSheet("background: #f5f5f5; border-radius: 5px;")
        sensor_layout = QHBoxLayout()

        self.lbl_temp = QLabel("--°C")
        self.lbl_temp.setAlignment(Qt.AlignCenter)
        self.lbl_temp.setStyleSheet("""
            background: #ffffff;
            color: #333333;
            font-size: 16pt;
            font-weight: bold;
            padding: 12px;
            border-radius: 8px;
            min-width: 140px;
            border: 1px solid #cccccc;
        """)
        sensor_layout.addWidget(self.lbl_temp)

        self.lbl_humi = QLabel("--%")
        self.lbl_humi.setAlignment(Qt.AlignCenter)
        self.lbl_humi.setStyleSheet("""
            background: #ffffff;
            color: #333333;
            font-size: 16pt;
            font-weight: bold;
            padding: 12px;
            border-radius: 8px;
            min-width: 140px;
            border: 1px solid #cccccc;
        """)
        sensor_layout.addWidget(self.lbl_humi)

        sensor_frame.setLayout(sensor_layout)
        data_layout.addWidget(sensor_frame)

        driver_frame = QFrame()
        driver_frame.setFrameShape(QFrame.StyledPanel)
        driver_frame.setStyleSheet("background: #f5f5f5; border-radius: 5px; padding: 8px;")
        driver_layout = QGridLayout()

        self.lbl_position = QLabel("Position: -- pulse")
        self.lbl_position.setStyleSheet("font-size: 13pt; font-weight: bold; color: #2c3e50;")
        driver_layout.addWidget(self.lbl_position, 0, 0)

        self.lbl_speed = QLabel("Speed: -- pps")
        self.lbl_speed.setStyleSheet("font-size: 13pt; font-weight: bold; color: #2c3e50;")
        driver_layout.addWidget(self.lbl_speed, 0, 1)

        self.lbl_alarm = QLabel("Alarm: --")
        self.lbl_alarm.setStyleSheet("font-size: 11pt; font-weight: bold;")
        driver_layout.addWidget(self.lbl_alarm, 1, 0)

        self.lbl_inpos = QLabel("InPos: --")
        self.lbl_inpos.setStyleSheet("font-size: 11pt; font-weight: bold;")
        driver_layout.addWidget(self.lbl_inpos, 1, 1)

        self.lbl_running = QLabel("Running: --")
        self.lbl_running.setStyleSheet("font-size: 11pt; font-weight: bold;")
        driver_layout.addWidget(self.lbl_running, 1, 2)

        # NEW: STEP STATE
        self.lbl_step_state = QLabel("STEP: --")
        self.lbl_step_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #95a5a6;")
        driver_layout.addWidget(self.lbl_step_state, 2, 0)

        # NEW: JOG STATE
        self.lbl_jog_state = QLabel("JOG: --")
        self.lbl_jog_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #95a5a6;")
        driver_layout.addWidget(self.lbl_jog_state, 2, 1)

        driver_frame.setLayout(driver_layout)
        data_layout.addWidget(driver_frame)

        data_group.setLayout(data_layout)
        layout.addWidget(data_group)
        
        toggle_frame = QFrame()
        toggle_frame.setFrameShape(QFrame.StyledPanel)
        toggle_layout = QHBoxLayout()


        self.btn_toggle_sht20 = QPushButton("SHT20: ON")
        self.btn_toggle_sht20.setStyleSheet("""
        background: #27ae60;
        color: white;
        font-weight: bold;
        padding: 6px;
        border-radius: 4px;
        """)
        self.btn_toggle_sht20.clicked.connect(self.toggle_sht20)


        toggle_layout.addWidget(self.btn_toggle_sht20)
        toggle_frame.setLayout(toggle_layout)
        layout.addWidget(toggle_frame)

        # 7. SET TARGET COUNT
        target_group = QGroupBox("SET TARGET COUNT (B → A → Arduino Counter)")
        target_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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
        target_layout = QGridLayout()

        target_layout.addWidget(QLabel("Target count:"), 0, 0)
        self.le_target_count = QLineEdit("20")
        self.le_target_count.setStyleSheet("padding: 6px; font-size: 10pt;")
        target_layout.addWidget(self.le_target_count, 0, 1)

        self.btn_set_target = QPushButton("SEND TARGET → A")
        self.btn_set_target.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border: 1px solid #c0c0c0;
            border-radius: 4px;
        """)
        self.btn_set_target.clicked.connect(self.set_counter_target)
        target_layout.addWidget(self.btn_set_target, 0, 2)

        self.lbl_target_info = QLabel("Current target from A: --")
        self.lbl_target_info.setStyleSheet("color: #2c3e50; font-size: 10pt;")
        target_layout.addWidget(self.lbl_target_info, 1, 0, 1, 3)

        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        
        # 8. MANUAL OVERRIDE CONTROL
        control_group = QGroupBox("LAYER B MANUAL OVERRIDE (via Modbus → Layer A)")
        control_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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
        control_layout = QVBoxLayout()

        info_label = QLabel("Các lệnh này chỉ hoạt động khi Layer A đang ở MANUAL (HR8=1).")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("""
            background: #f5f5f5;
            color: #555555;
            padding: 8px;
            border-radius: 5px;
            font-weight: bold;
        """)
        control_layout.addWidget(info_label)

        pos_frame = QFrame()
        pos_frame.setFrameShape(QFrame.StyledPanel)
        pos_layout = QGridLayout()

        pos_layout.addWidget(QLabel("Position:"), 0, 0)
        self.le_pos = QLineEdit("20000")
        self.le_pos.setStyleSheet("padding: 5px; font-size: 10pt;")
        pos_layout.addWidget(self.le_pos, 0, 1)

        pos_layout.addWidget(QLabel("Speed:"), 0, 2)
        self.le_speed = QLineEdit("8000")
        self.le_speed.setStyleSheet("padding: 5px; font-size: 10pt;")
        pos_layout.addWidget(self.le_speed, 0, 3)

        self.btn_override = QPushButton("OVERRIDE MOVE ABS")
        self.btn_override.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 10px;
            font-size: 11pt;
            border-radius: 5px;
            border: 1px solid #c0c0c0;
        """)
        self.btn_override.clicked.connect(self.override_motor)
        pos_layout.addWidget(self.btn_override, 1, 0, 1, 4)

        pos_frame.setLayout(pos_layout)
        control_layout.addWidget(pos_frame)

        jog_frame = QFrame()
        jog_frame.setFrameShape(QFrame.StyledPanel)
        jog_layout = QHBoxLayout()

        jog_layout.addWidget(QLabel("JOG Speed:"))
        self.le_jog_speed = QLineEdit("12000")
        self.le_jog_speed.setStyleSheet("padding: 5px; font-size: 10pt;")
        jog_layout.addWidget(self.le_jog_speed)

        self.btn_jog_ccw = QPushButton("JOG CCW")
        self.btn_jog_ccw.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border: 1px solid #c0c0c0;
            border-radius: 4px;
        """)
        self.btn_jog_ccw.clicked.connect(lambda: self.jog_move(-1))
        jog_layout.addWidget(self.btn_jog_ccw)

        self.btn_jog_cw = QPushButton("JOG CW")
        self.btn_jog_cw.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border: 1px solid #c0c0c0;
            border-radius: 4px;
        """)
        self.btn_jog_cw.clicked.connect(lambda: self.jog_move(1))
        jog_layout.addWidget(self.btn_jog_cw)

        jog_frame.setLayout(jog_layout)
        control_layout.addWidget(jog_frame)

        step_frame = QFrame()
        step_frame.setFrameShape(QFrame.StyledPanel)
        step_layout = QHBoxLayout()

        self.btn_step_on = QPushButton("STEP ON")
        self.btn_step_on.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #c0c0c0;
        """)
        self.btn_step_on.clicked.connect(self.step_on)
        step_layout.addWidget(self.btn_step_on)

        self.btn_step_off = QPushButton("STEP OFF")
        self.btn_step_off.setStyleSheet("""
            background: #f0f0f0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #c0c0c0;
        """)
        self.btn_step_off.clicked.connect(self.step_off)
        step_layout.addWidget(self.btn_step_off)

        self.btn_reset_alarm = QPushButton("RESET ALARM")
        self.btn_reset_alarm.setStyleSheet("""
            background: #f0f0f0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #c0c0c0;
        """)
        self.btn_reset_alarm.clicked.connect(self.reset_alarm)
        step_layout.addWidget(self.btn_reset_alarm)

        step_frame.setLayout(step_layout)
        control_layout.addWidget(step_frame)

        btn_frame = QFrame()
        btn_frame.setFrameShape(QFrame.StyledPanel)
        btn_layout = QHBoxLayout()

        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #c0c0c0;
        """)
        self.btn_stop.clicked.connect(self.stop_motor)
        btn_layout.addWidget(self.btn_stop)

        self.btn_release = QPushButton("RELEASE CONTROL → LOCAL")
        self.btn_release.setStyleSheet("""
            background: #e0e0e0;
            color: #333333;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #c0c0c0;
        """)
        self.btn_release.clicked.connect(self.release_control)
        btn_layout.addWidget(self.btn_release)

        self.btn_emergency = QPushButton("EMERGENCY")
        self.btn_emergency.setStyleSheet("""
            background: #d9534f;
            color: white;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #c9302c;
        """)
        self.btn_emergency.clicked.connect(self.emergency_stop)
        btn_layout.addWidget(self.btn_emergency)

        btn_frame.setLayout(btn_layout)
        control_layout.addWidget(btn_frame)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # 9. LOG
        log_group = QGroupBox("System Log")
        log_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
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

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(160)
        self.log_text.setStyleSheet("""
            background: #f5f5f5;
            color: #333333;
            font-family: 'Courier New';
            font-size: 9pt;
            border-radius: 5px;
            border: 1px solid #d0d0d0;
        """)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        self.log("Layer B SCADA Supervisor initialized")
        self.log(f"Will use Modbus TCP to Layer A at {A_HOST}:{A_MODBUS_PORT}")
        self.log(f"Target written to HR{A_HR_TARGET_ADDR} (must match A)")
        self.log(f"MODE written to HR{A_HR_MODE_ADDR} (0=AUTO, 1=MANUAL)")
        self.log(f"Listening for Layer C on port {SERVER_PORT}")

    # =========================================================
    #   MODBUS TCP TO LAYER A
    # =========================================================
    def _init_modbus_to_a(self):
        try:
            self.modbus_client_a = ModbusClient(
                host=A_HOST,
                port=A_MODBUS_PORT,
                auto_open=True,
                auto_close=False,
                timeout=3.0
            )
            self.log("Modbus client to Layer A initialized")
        except Exception as e:
            self.log(f"Error init Modbus client: {e}")

    def _start_modbus_poll_thread(self):
        def loop():
            while self.running:
                self.poll_a_status_from_a()
                time.sleep(0.5)
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    @staticmethod
    def _regs_to_s32(hi, lo):
        val = ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)
        if val & 0x80000000:
            val = val - (1 << 32)
        return val

    @staticmethod
    def _s32_to_regs(val):
        if val < 0:
            val = (1 << 32) + val
        hi = (val >> 16) & 0xFFFF
        lo = val & 0xFFFF
        return hi, lo

    def poll_a_status_from_a(self):
        """Đọc Input Registers 0..11 từ Layer A (mở rộng thêm STEP/JOG)."""
        if not self.modbus_client_a:
            return
        try:
            with self.modbus_lock:
                regs = self.modbus_client_a.read_input_registers(0, 12)

            if regs is None:
                if self.modbus_connected:
                    self.modbus_connected = False
                    self.signals.connection_signal.emit("a", "Disconnected")
                return

            if not self.modbus_connected:
                self.modbus_connected = True
                self.signals.connection_signal.emit("a", "Connected")
                self.signals.log_signal.emit("Connected to Layer A (Modbus TCP)")

            if len(regs) < 12:
                return

            pos_hi, pos_lo, speed, temp10, humi10, status_word, \
                cnt_val, cnt_target, auto_code, mode_val, \
                step_state, jog_state = regs

            self.current_position = self._regs_to_s32(pos_hi, pos_lo)
            self.current_speed = speed
            if self.sht20_enabled:
                self.temperature = temp10 / 10.0
                self.humidity = humi10 / 10.0

            self.driver_alarm = bool(status_word & (1 << 0))
            self.driver_inpos = bool(status_word & (1 << 1))
            self.driver_running = bool(status_word & (1 << 2))

            self.counter_value = cnt_val
            self.counter_target = cnt_target
            self.auto_state_code = auto_code
            self.current_mode = mode_val

            self.step_enabled = bool(step_state)
            self.jog_state = jog_state

            self.status_updates += 1
            self.signals.status_update.emit({})

            if self.client_c:
                status = {
                    'type': 'status',
                    'timestamp': time.time(),
                    'data': {
                        'position': self.current_position,
                        'speed': self.current_speed,
                        'temperature': self.temperature,
                        'humidity': self.humidity,
                        'driver_alarm': self.driver_alarm,
                        'driver_inpos': self.driver_inpos,
                        'driver_running': self.driver_running,
                        'counter_value': self.counter_value,
                        'counter_target': self.counter_target,
                        'auto_state_code': self.auto_state_code,
                        'auto_state_text': AUTO_STATE_MAP.get(self.auto_state_code, "Unknown"),
                        'mode': self.current_mode,
                        'step_enabled': self.step_enabled,
                        'jog_state': self.jog_state,
                    }
                }
                self._send_to_c(status)

        except Exception as e:
            self.signals.log_signal.emit(f"Error polling A via Modbus: {e}")
            if self.modbus_connected:
                self.modbus_connected = False
                self.signals.connection_signal.emit("a", "Disconnected")

    # =========================================================
    #   GHI TARGET & LỆNH VÀO A
    # =========================================================
    def _write_target_to_a(self, target_val: int) -> bool:
        """Ghi target count vào HR A_HR_TARGET_ADDR trên Layer A."""
        if not self.modbus_client_a:
            self.log("Modbus client A not initialized")
            return False

        if target_val < 0 or target_val > 65535:
            self.log(f"Target {target_val} out of 16-bit range")
            return False

        try:
            with self.modbus_lock:
                if not self.modbus_client_a.is_open:
                    self.log(f"Modbus not open. Reconnecting to {A_HOST}:{A_MODBUS_PORT}...")
                    if not self.modbus_client_a.open():
                        self.log(f"Cannot open connection to {A_HOST}:{A_MODBUS_PORT}")
                        return False

                self.log(f"Writing TARGET={target_val} to HR{A_HR_TARGET_ADDR}...")
                ok = self.modbus_client_a.write_single_register(
                    A_HR_TARGET_ADDR, target_val
                )

            if not ok:
                error_msg = self.modbus_client_a.last_error_txt
                self.log(f"Write HR{A_HR_TARGET_ADDR} failed: {error_msg}")
                return False

            self.log(f"Target {target_val} → A HR{A_HR_TARGET_ADDR} SUCCESS")
            self.commands_forwarded += 1
            return True

        except Exception as e:
            self.log(f"Exception writing target to A: {e}")
            return False

    def _write_cmd_to_a(self, cmd, pos=None, speed=None,
                        origin_source="Layer_B", priority=None):
        """Ghi packet lệnh vào HR[A_HR_CMD_ADDR..] của A."""
        if not self.modbus_client_a:
            self.log("Modbus client A not initialized")
            return False

        if "Layer_C" in origin_source or "Machine_C" in origin_source:
            source_code = 3
            prio = priority if priority is not None else 3
        elif "Layer_B" in origin_source or "Machine_B" in origin_source:
            source_code = 2
            prio = priority if priority is not None else 2
        else:
            source_code = 2
            prio = priority if priority is not None else 2

        pos_hi = 0
        pos_lo = 0
        if pos is not None:
            pos_hi, pos_lo = self._s32_to_regs(pos)

        spd = speed if speed is not None else 0
        spd &= 0xFFFFFFFF

        regs = [0] * A_HR_CMD_REG_COUNT
        regs[0] = cmd
        regs[1] = pos_hi
        regs[2] = pos_lo
        regs[3] = spd & 0xFFFF
        regs[4] = source_code
        regs[5] = prio

        try:
            with self.modbus_lock:
                if not self.modbus_client_a.is_open:
                    self.log(f"Modbus not open. Reconnecting to {A_HOST}:{A_MODBUS_PORT}...")
                    if not self.modbus_client_a.open():
                        self.log(f"Cannot open connection to {A_HOST}:{A_MODBUS_PORT}")
                        return False

                self.log(f"Writing CMD packet to HR{A_HR_CMD_ADDR}: {regs}")
                ok = self.modbus_client_a.write_multiple_registers(A_HR_CMD_ADDR, regs)

            if ok:
                self.commands_forwarded += 1
                self.log(f"CMD={cmd} sent to A successfully")
                return True
            else:
                error_msg = self.modbus_client_a.last_error_txt
                self.log(f"Failed to write holding registers: {error_msg}")
                return False
        except Exception as e:
            self.log(f"Error writing cmd to A: {e}")
            return False

    # =========================================================
    #   SERVER JSON CHO LAYER C
    # =========================================================
    def _start_server_for_c(self):
        def server_thread():
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_socket.bind(("0.0.0.0", SERVER_PORT))
                self.server_socket.listen(1)

                self.signals.log_signal.emit(f"Server for Layer C started on port {SERVER_PORT}")

                while self.running:
                    try:
                        self.server_socket.settimeout(1.0)
                        client, addr = self.server_socket.accept()

                        if self.client_c:
                            try:
                                self.client_c.close()
                            except:
                                pass

                        self.client_c = client
                        self.signals.connection_signal.emit("c", "Connected")
                        self.signals.log_signal.emit(f"Layer C connected: {addr}")

                        threading.Thread(target=self._handle_c,
                                         args=(client,), daemon=True).start()
                    except socket.timeout:
                        continue
            except Exception as e:
                self.signals.log_signal.emit(f"Server for C error: {e}")

        threading.Thread(target=server_thread, daemon=True).start()

    def _handle_c(self, client):
        buffer = ""
        try:
            while self.running:
                data = client.recv(BUFFER_SIZE).decode('utf-8')
                if not data:
                    break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            command = json.loads(line)
                            self._handle_command_from_c(command)
                        except json.JSONDecodeError as e:
                            self.signals.log_signal.emit(f"JSON error from C: {e}")
        except Exception as e:
            self.signals.log_signal.emit(f"Error from C: {e}")
        finally:
            if client is self.client_c:
                self.client_c = None
            try:
                client.close()
            except:
                pass
            self.signals.connection_signal.emit("c", "Waiting for connection...")
            self.signals.log_signal.emit("Layer C disconnected")

    def _send_to_c(self, data):
        if not self.client_c:
            return
        try:
            message = json.dumps(data) + '\n'
            self.client_c.sendall(message.encode('utf-8'))
        except Exception as e:
            self.signals.log_signal.emit(f"Send to C error: {e}")
            self.client_c = None

    # =========================================================
    #   XỬ LÝ LỆNH TỪ LAYER C → A
    # =========================================================
    def _handle_command_from_c(self, command):
        cmd_type = command.get('type')
        source = command.get('source', 'Layer_C')

        if cmd_type == 'heartbeat':
            return

        self.commands_from_c += 1
        self.signals.forward_signal.emit(cmd_type)
        self.signals.log_signal.emit(f"Received from C: {cmd_type}")

        timestamp = time.strftime("%H:%M:%S")
        self.command_history.append(f"[{timestamp}] {source} → {cmd_type}")
        self.update_command_history()

        allowed = {'motor_control', 'jog_control', 'stop_motor',
                   'release_control', 'emergency_stop', 'set_target', 'set_mode'}
        if cmd_type not in allowed:
            self.signals.log_signal.emit(f"Rejected: unsupported command '{cmd_type}'")
            return

        self._execute_command(command, from_c=True)

    def _execute_command(self, command, from_c: bool):
        cmd_type = command.get('type')
        source = command.get('source', 'Layer_C' if from_c else 'Layer_B')
        priority = command.get('priority', 3 if from_c else 2)
        data = command.get('data', {})

        if cmd_type == 'heartbeat':
            return

        if cmd_type == 'set_target':
            target = int(data.get('target', 0))
            if self._write_target_to_a(target):
                self.log(f"SET TARGET {target} (from {source})")

        elif cmd_type == 'set_mode':
            mode = int(data.get('mode', 0))
            self.set_mode(mode)

        elif cmd_type == 'motor_control':
            step_cmd = data.get('step_command')
            alarm_reset = data.get('alarm_reset', False)

            if step_cmd == 'on':
                if self._write_cmd_to_a(1, origin_source=source, priority=priority):
                    self.log("STEP ON (via Modbus) from " + source)
            elif step_cmd == 'off':
                if self._write_cmd_to_a(2, origin_source=source, priority=priority):
                    self.log("STEP OFF (via Modbus) from " + source)
            elif alarm_reset:
                if self._write_cmd_to_a(8, origin_source=source, priority=priority):
                    self.log("RESET ALARM (via Modbus) from " + source)
            else:
                pos = int(data.get('position', self.current_position))
                speed = int(data.get('speed', self.current_speed if self.current_speed > 0 else 1000))
                if self._write_cmd_to_a(3, pos=pos, speed=speed,
                                        origin_source=source, priority=priority):
                    self.log(f"MOVE ABS (Modbus) from {source}: pos={pos:,} @ {speed:,}pps")

        elif cmd_type == 'jog_control':
            speed = int(data.get('speed', 0))
            direction = int(data.get('direction', 1))
            cmd = 5 if direction > 0 else 6
            if self._write_cmd_to_a(cmd, speed=speed, origin_source=source, priority=priority):
                dir_str = "CW" if direction > 0 else "CCW"
                self.log(f"JOG {dir_str} (Modbus) from {source}: {speed:,}pps")

        elif cmd_type == 'stop_motor':
            if self._write_cmd_to_a(7, origin_source=source, priority=priority):
                self.log(f"STOP (Modbus) from {source}")

        elif cmd_type == 'release_control':
            if self._write_cmd_to_a(7, origin_source="Local", priority=1):
                self.log("RELEASE CONTROL → Local (via Modbus)")

        elif cmd_type == 'emergency_stop':
            if self._write_cmd_to_a(9, origin_source=source, priority=priority):
                self.log(f"EMERGENCY STOP (Modbus) from {source}")

    # =========================================================
    #   UI UPDATES
    # =========================================================
    def update_connection_status(self, target, status):
        if target == "a":
            self.lbl_conn_a.setText(status)
            if "Connected" in status:
                color = "#27ae60"
            elif "Disconnected" in status:
                color = "#c0392b"
            else:
                color = "#e67e22"
            self.lbl_conn_a.setStyleSheet(f"font-weight: bold; font-size: 11pt; color: {color};")
        

    def update_displays(self, data):
        self.lbl_temp.setText(f"{self.temperature:.1f}°C")
        self.lbl_humi.setText(f"{self.humidity:.1f}%")

        self.lbl_position.setText(f"Position: {self.current_position:,} pulse")
        self.lbl_speed.setText(f"Speed: {self.current_speed:,} pps")

        if self.driver_alarm:
            self.lbl_alarm.setText("Alarm: YES")
            self.lbl_alarm.setStyleSheet("font-size: 11pt; font-weight: bold; color: #c0392b;")
        else:
            self.lbl_alarm.setText("Alarm: NO")
            self.lbl_alarm.setStyleSheet("font-size: 11pt; font-weight: bold; color: #27ae60;")

        if self.driver_inpos:
            self.lbl_inpos.setText("InPos: YES")
            self.lbl_inpos.setStyleSheet("font-size: 11pt; font-weight: bold; color: #27ae60;")
        else:
            self.lbl_inpos.setText("InPos: NO")
            self.lbl_inpos.setStyleSheet("font-size: 11pt; font-weight: bold; color: #f39c12;")

        if self.driver_running:
            self.lbl_running.setText("Running: YES")
            self.lbl_running.setStyleSheet("font-size: 11pt; font-weight: bold; color: #3498db;")
        else:
            self.lbl_running.setText("Running: NO")
            self.lbl_running.setStyleSheet("font-size: 11pt; font-weight: bold; color: #95a5a6;")

        # STEP STATE
        if self.step_enabled:
            self.lbl_step_state.setText("STEP: ON")
            self.lbl_step_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #27ae60;")
        else:
            self.lbl_step_state.setText("STEP: OFF")
            self.lbl_step_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #95a5a6;")

        # AUTO STATE
        self.lbl_counter.setText(f"Counter: {self.counter_value} / {self.counter_target}")
        auto_text = AUTO_STATE_MAP.get(self.auto_state_code, "Unknown")
        self.lbl_auto_state.setText(f"AUTO STATE: {auto_text}")

        # DONE LOGIC HIỂN THỊ
        done = False
        resetting = False

        if self.counter_target > 0 and self.counter_value >= self.counter_target:
            done = True
        if self.auto_state_code == 3:
            resetting = True
            done = True

        if resetting:
            self.lbl_counter_done.setText("DONE: YES (Resetting...)")
            self.lbl_counter_done.setStyleSheet("font-size: 11pt; font-weight: bold; color: #e67e22;")
        elif done:
            self.lbl_counter_done.setText("DONE: YES")
            self.lbl_counter_done.setStyleSheet("font-size: 11pt; font-weight: bold; color: #27ae60;")
        else:
            self.lbl_counter_done.setText("DONE: NO")
            self.lbl_counter_done.setStyleSheet("font-size: 11pt; font-weight: bold; color: #95a5a6;")

        # TARGET INFO
        if self.counter_target > 0:
            self.lbl_target_info.setText(f"Current target from A: {self.counter_target}")
        else:
            self.lbl_target_info.setText("Current target from A: --")

        # MODE
        if self.current_mode == 1:
            self.lbl_mode_status.setText("Mode: MANUAL")
            self.lbl_mode_status.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e67e22;")
        else:
            self.lbl_mode_status.setText("Mode: AUTO")
            self.lbl_mode_status.setStyleSheet("font-weight: bold; font-size: 11pt; color: #27ae60;")

        # JOG STATE
        if self.jog_state == 1:
            self.lbl_jog_state.setText("JOG: CW")
            self.lbl_jog_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #3498db;")
        elif self.jog_state == 2:
            self.lbl_jog_state.setText("JOG: CCW")
            self.lbl_jog_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #3498db;")
        else:
            self.lbl_jog_state.setText("JOG: OFF")
            self.lbl_jog_state.setStyleSheet("font-size: 11pt; font-weight: bold; color: #95a5a6;")

    def show_forward_animation(self, cmd_type):
        self.lbl_forward_status.setText(f"FORWARDING: {cmd_type}")
        self.lbl_forward_status.setStyleSheet("""
            background: #4a90e2;
            color: white;
            font-size: 12pt;
            font-weight: bold;
            padding: 12px;
            border-radius: 8px;
        """)
        QTimer.singleShot(1000, self.reset_forward_status)

    def reset_forward_status(self):
        self.lbl_forward_status.setText("Idle")
        self.lbl_forward_status.setStyleSheet("""
            background: #b0b0b0;
            color: white;
            font-size: 12pt;
            font-weight: bold;
            padding: 12px;
            border-radius: 8px;
        """)

    def update_command_history(self):
        self.history_text.clear()
        for line in list(self.command_history):
            self.history_text.appendPlainText(line)

    def update_statistics(self):
        uptime = int(time.time() - self.start_time)
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60
        self.lbl_uptime.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        
        self.lbl_cmd_forwarded.setText(str(self.commands_forwarded))
        self.lbl_status_updates.setText(str(self.status_updates))

    def toggle_sht20(self):
        self.sht20_enabled = not self.sht20_enabled

        if self.sht20_enabled:
            self.btn_toggle_sht20.setText("SHT20: ON")
            self.btn_toggle_sht20.setStyleSheet("""
                background: #27ae60;
                color: white;
                font-weight: bold;
                padding: 6px;
                border-radius: 4px;
            """)
            self.log("SHT20 sensor reading ENABLED")
        else:
            self.btn_toggle_sht20.setText("SHT20: OFF")
            self.btn_toggle_sht20.setStyleSheet("""
                background: #c0392b;
                color: white;
                font-weight: bold;
                padding: 6px;
                border-radius: 4px;
            """)
            self.log("SHT20 sensor reading DISABLED")


    # =========================================================
    #   SET MODE A: AUTO / MANUAL
    # =========================================================
    def set_mode(self, mode: int):
        """Ghi HR_MODE_ADDR trên A: 0=AUTO, 1=MANUAL"""
        if not self.modbus_client_a:
            QMessageBox.warning(self, "Error", "Modbus client to A not initialized")
            return

        if mode not in (0, 1):
            return

        try:
            with self.modbus_lock:
                if not self.modbus_client_a.is_open:
                    self.log(f"Modbus not open. Reconnecting to {A_HOST}:{A_MODBUS_PORT}...")
                    if not self.modbus_client_a.open():
                        self.log(f"Cannot connect to {A_HOST}:{A_MODBUS_PORT}")
                        QMessageBox.warning(self, "Error", "Cannot connect to Layer A")
                        return

                mode_text = "AUTO" if mode == 0 else "MANUAL"
                self.log(f"Writing MODE={mode} ({mode_text}) to HR{A_HR_MODE_ADDR}...")
                ok = self.modbus_client_a.write_single_register(A_HR_MODE_ADDR, mode)

            if ok:
                self.current_mode = mode
                if mode == 0:
                    self.lbl_mode_status.setText("Mode: AUTO")
                    self.lbl_mode_status.setStyleSheet("font-weight: bold; font-size: 11pt; color: #27ae60;")
                    self.log("Layer A MODE = AUTO (counter cycle)")
                else:
                    self.lbl_mode_status.setText("Mode: MANUAL")
                    self.lbl_mode_status.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e67e22;")
                    self.log("Layer A MODE = MANUAL (B/C control motor)")
            else:
                error_msg = self.modbus_client_a.last_error_txt
                self.log(f"Failed to write mode to A: {error_msg}")
                QMessageBox.warning(self, "Error", f"Failed to write mode: {error_msg}")

        except Exception as e:
            self.log(f"Exception writing mode to A: {e}")
            QMessageBox.warning(self, "Error", f"Exception: {e}")

    # =========================================================
    #   VALIDATE POS / SPEED
    # =========================================================
    def _validate_pos_speed(self, pos: int, speed: int) -> bool:
        if abs(pos) > 2_000_000_000:
            QMessageBox.warning(self, "Error", "Position too large!")
            return False
        if speed < 1 or speed > 200_000:
            QMessageBox.warning(self, "Error", "Speed out of range!")
            return False
        return True

    def _ensure_manual_mode(self) -> bool:
        """Chỉ cho phép UI B điều khiển motor khi A đang ở MANUAL."""
        if self.current_mode != 1:
            QMessageBox.warning(
                self, "Mode error",
                "Layer A đang ở AUTO.\nHãy chuyển sang MANUAL trước khi điều khiển từ B."
            )
            return False
        return True

    # =========================================================
    #   CONTROL COMMANDS TỪ UI B
    # =========================================================
    def set_counter_target(self):
        """Nút SET TARGET COUNT trên B → ghi HR0 của A."""
        try:
            target = int(self.le_target_count.text())
            if target <= 0 or target > 65535:
                QMessageBox.warning(self, "Error", "Target must be 1..65535")
                return
            if self._write_target_to_a(target):
                self.log(f"Target count set to {target} (Layer B → A HR{A_HR_TARGET_ADDR} → Arduino)")
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid target!")

    def override_motor(self):
        if not self._ensure_manual_mode():
            return
        try:
            pos = int(self.le_pos.text())
            speed = int(self.le_speed.text())

            if not self._validate_pos_speed(pos, speed):
                return

            command = {
                'type': 'motor_control',
                'priority': 2,
                'source': 'Layer_B',
                'timestamp': time.time(),
                'sync_mode': True,
                'data': {
                    'position': pos,
                    'speed': speed
                }
            }
            self._execute_command(command, from_c=False)
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid input!")

    def jog_move(self, direction):
        if not self._ensure_manual_mode():
            return
        try:
            speed = int(self.le_jog_speed.text())

            if not self._validate_pos_speed(0, speed):
                return

            command = {
                'type': 'jog_control',
                'priority': 2,
                'source': 'Layer_B',
                'timestamp': time.time(),
                'sync_mode': True,
                'data': {
                    'speed': speed,
                    'direction': direction
                }
            }
            self._execute_command(command, from_c=False)
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid speed!")

    def step_on(self):
        if not self._ensure_manual_mode():
            return
        command = {
            'type': 'motor_control',
            'priority': 2,
            'source': 'Layer_B',
            'timestamp': time.time(),
            'data': {
                'step_command': 'on'
            }
        }
        self._execute_command(command, from_c=False)

    def step_off(self):
        if not self._ensure_manual_mode():
            return
        command = {
            'type': 'motor_control',
            'priority': 2,
            'source': 'Layer_B',
            'timestamp': time.time(),
            'data': {
                'step_command': 'off'
            }
        }
        self._execute_command(command, from_c=False)

    def reset_alarm(self):
        if not self._ensure_manual_mode():
            return
        command = {
            'type': 'motor_control',
            'priority': 2,
            'source': 'Layer_B',
            'timestamp': time.time(),
            'data': {
                'alarm_reset': True
            }
        }
        self._execute_command(command, from_c=False)

    def stop_motor(self):
        if not self._ensure_manual_mode():
            return
        command = {
            'type': 'stop_motor',
            'priority': 2,
            'source': 'Layer_B',
            'timestamp': time.time()
        }
        self._execute_command(command, from_c=False)

    def release_control(self):
        if not self._ensure_manual_mode():
            return
        command = {
            'type': 'release_control',
            'priority': 2,
            'source': 'Layer_B',
            'timestamp': time.time()
        }
        self._execute_command(command, from_c=False)

    def emergency_stop(self):
        if not self._ensure_manual_mode():
            return
        reply = QMessageBox.question(
            self, 'Emergency Stop',
            'EMERGENCY STOP system?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            command = {
                'type': 'emergency_stop',
                'priority': 2,
                'source': 'Layer_B',
                'timestamp': time.time()
            }
            self._execute_command(command, from_c=False)

    # =========================================================
    #   HELPERS & CLOSE
    # =========================================================
    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        if self.log_text.document().blockCount() > 500:
            self.log_text.clear()
        self.log_text.appendPlainText(f"[{timestamp}] {message}")

    def append_log(self, message):
        self.log(message)

    def closeEvent(self, event):
        self.running = False
        self.stats_timer.stop()

        if self.modbus_client_a:
            try:
                self.modbus_client_a.close()
            except:
                pass

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        if self.client_c:
            try:
                self.client_c.close()
            except:
                pass

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = LayerB_SCADASupervisor()
    gui.show()
    sys.exit(app.exec())
