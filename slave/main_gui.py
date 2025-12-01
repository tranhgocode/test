"""
Main GUI - PyQt5 Modbus RTU/TCP Monitor Interface
Usage: python -m slave.main_gui
"""
import sys
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox, QGroupBox, QTextEdit,
    QTabWidget, QFrame, QMessageBox, QLineEdit, QDoubleSpinBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor

from .config import *
from .modbus_handler import RS485Manager, ModbusTCPManager, ModbusFrame, ModbusTCPFrame
from .device_manager import DeviceManager
from .logger_handler import logger
from .modbus_tcp_server import ModbusTCPServer

class SignalEmitter(QObject):
    """Helper class để emit signals từ threads"""
    update_signal = pyqtSignal()

class EventLogWindow(QMainWindow):
    """Floating Event Log window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📋 Event Log Monitor")
        self.setGeometry(800, 100, 600, 600)
        
        central = QWidget()
        layout = QVBoxLayout()
        
        # Buttons
        row = QHBoxLayout()
        btn_clear = QPushButton("🗑 Clear")
        btn_clear.clicked.connect(self.on_clear)
        row.addWidget(btn_clear)
        
        btn_export = QPushButton("💾 Export CSV")
        btn_export.clicked.connect(self.on_export)
        row.addWidget(btn_export)
        
        btn_auto_scroll = QPushButton("⬇ Auto Scroll")
        btn_auto_scroll.setCheckable(True)
        btn_auto_scroll.setChecked(True)
        self.auto_scroll = btn_auto_scroll
        row.addWidget(btn_auto_scroll)
        row.addStretch()
        layout.addLayout(row)
        
        # Log text
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier New", 8))
        self.log_text.setStyleSheet("background-color: #f5f5f5; color: #333;")
        layout.addWidget(self.log_text)
        
        central.setLayout(layout)
        self.setCentralWidget(central)
    
    def update_log(self, log_entries):
        """Update log display"""
        self.log_text.setPlainText("\n".join(log_entries[-100:]))  # Last 100 lines
        if self.auto_scroll.isChecked():
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def on_clear(self):
        """Clear log"""
        logger.clear_buffer()
        self.log_text.clear()
        logger.info("Log cleared", "UI")
    
    def on_export(self):
        """Export log to CSV"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/slave_log_{timestamp}.csv"
        logger.export_csv(filename)
        QMessageBox.information(self, "Success", f"Logs exported to:\n{filename}")

class SlaveMonitorGUI(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔧 RS-485/Modbus Monitor & Control")
        self.setGeometry(50, 50, WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Initialize components
        self.modbus_manager = None
        self.device_manager = None
        self.log_window = None
        self.emitter = SignalEmitter()
        self.emitter.update_signal.connect(self.refresh_ui)
        
        # Setup UI
        self.init_ui()
        
        # Timers
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_ui)
        self.refresh_timer.start(REFRESH_INTERVAL_MS)
        
        logger.info("Application started", "UI")
    
    def init_ui(self):
        """Build UI"""
        central = QWidget()
        main_layout = QVBoxLayout()
        
        # Tab widget
        tabs = QTabWidget()
        
        # Tab 1: Connection Settings
        tabs.addTab(self.create_connection_tab(), "🔌 Connection Settings")
        
        # Tab 2: Sensor Device
        tabs.addTab(self.create_sensor_tab(), "🌡 Sensor (SHT20)")
        
        # Tab 3: Drive Device
        tabs.addTab(self.create_drive_tab(), "⚙ Drive (EZi-STEP)")
        
        main_layout.addWidget(tabs)
        
        central.setLayout(main_layout)
        self.setCentralWidget(central)
    
    def create_connection_tab(self):
        """Connection settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Group: Connection Mode
        grp_mode = QGroupBox("Connection Mode")
        grp_layout = QVBoxLayout()
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Serial RS-485", "Modbus TCP/IP"])
        self.combo_mode.setCurrentIndex(0 if CONNECTION_MODE == "SERIAL" else 1)
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        row.addWidget(self.combo_mode)
        row.addStretch()
        grp_layout.addLayout(row)
        
        grp_mode.setLayout(grp_layout)
        layout.addWidget(grp_mode)
        
        # Group: Serial Settings
        self.grp_serial = QGroupBox("Serial Configuration")
        grp_layout = QVBoxLayout()
        
        row = QHBoxLayout()
        row.addWidget(QLabel("COM Port:"))
        self.combo_port = QComboBox()
        self.combo_port.addItems(AVAILABLE_PORTS)
        self.combo_port.setCurrentText(DEFAULT_COM_PORT)
        row.addWidget(self.combo_port)
        row.addStretch()
        grp_layout.addLayout(row)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Baudrate:"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems([str(b) for b in AVAILABLE_BAUDRATES])
        self.combo_baud.setCurrentText(str(DEFAULT_BAUDRATE))
        row.addWidget(self.combo_baud)
        
        row.addWidget(QLabel("Parity:"))
        self.combo_parity = QComboBox()
        self.combo_parity.addItems(AVAILABLE_PARITY)
        self.combo_parity.setCurrentText(DEFAULT_PARITY)
        row.addWidget(self.combo_parity)
        
        row.addWidget(QLabel("Stopbits:"))
        self.combo_stopbits = QComboBox()
        self.combo_stopbits.addItems([str(s) for s in AVAILABLE_STOPBITS])
        self.combo_stopbits.setCurrentText(str(DEFAULT_STOPBITS))
        row.addWidget(self.combo_stopbits)
        row.addStretch()
        grp_layout.addLayout(row)
        
        self.grp_serial.setLayout(grp_layout)
        layout.addWidget(self.grp_serial)
        
        # Group: TCP Settings
        self.grp_tcp = QGroupBox("TCP/IP Configuration")
        grp_tcp_layout = QVBoxLayout()
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Host:"))
        self.le_host = QLineEdit(DEFAULT_TCP_HOST)
        row.addWidget(self.le_host)
        
        row.addWidget(QLabel("Port:"))
        self.spin_tcp_port = QSpinBox()
        self.spin_tcp_port.setValue(DEFAULT_TCP_PORT)
        self.spin_tcp_port.setRange(1, 65535)
        row.addWidget(self.spin_tcp_port)
        row.addStretch()
        grp_tcp_layout.addLayout(row)
        
        self.grp_tcp.setLayout(grp_tcp_layout)
        self.grp_tcp.setVisible(False)
        layout.addWidget(self.grp_tcp)
        
        # Group: Connection Actions
        grp_actions = QGroupBox("Connection Control")
        grp_layout = QVBoxLayout()
        
        row = QHBoxLayout()
        self.btn_open = QPushButton("🔓 Connect")
        self.btn_open.setStyleSheet("background-color: #90EE90; font-weight: bold; padding: 8px;")
        self.btn_open.clicked.connect(self.on_open_connection)
        row.addWidget(self.btn_open)
        
        self.btn_close = QPushButton("🔒 Disconnect")
        self.btn_close.setStyleSheet("background-color: #FFB6C1; font-weight: bold; padding: 8px;")
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.on_close_connection)
        row.addWidget(self.btn_close)
        
        btn_event_log = QPushButton("📋 Event Log Window")
        btn_event_log.setStyleSheet("background-color: #87CEEB; font-weight: bold; padding: 8px;")
        btn_event_log.clicked.connect(self.on_open_event_log)
        row.addWidget(btn_event_log)
        
        row.addStretch()
        grp_layout.addLayout(row)
        
        self.lbl_status = QLabel("Status: DISCONNECTED")
        self.lbl_status.setStyleSheet("background-color: #ffffcc; padding: 8px; font-size: 11pt; font-weight: bold;")
        grp_layout.addWidget(self.lbl_status)
        
        grp_actions.setLayout(grp_layout)
        layout.addWidget(grp_actions)
        
        # Group: Live TX/RX Display
        grp_txrx = QGroupBox("📡 Live Modbus Communication")
        grp_layout = QVBoxLayout()
        
        # Sensor TX/RX
        row = QHBoxLayout()
        row.addWidget(QLabel("🌡 Sensor TX:"))
        self.lbl_sensor_tx = QLabel("---")
        self.lbl_sensor_tx.setStyleSheet("background-color: #e8f5e9; font-family: Courier; font-size: 9pt;")
        row.addWidget(self.lbl_sensor_tx)
        grp_layout.addLayout(row)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("🌡 Sensor RX:"))
        self.lbl_sensor_rx = QLabel("---")
        self.lbl_sensor_rx.setStyleSheet("background-color: #c8e6c9; font-family: Courier; font-size: 9pt;")
        row.addWidget(self.lbl_sensor_rx)
        grp_layout.addLayout(row)
        
        # Drive TX/RX
        row = QHBoxLayout()
        row.addWidget(QLabel("⚙ Drive TX:"))
        self.lbl_drive_tx = QLabel("---")
        self.lbl_drive_tx.setStyleSheet("background-color: #fff3e0; font-family: Courier; font-size: 9pt;")
        row.addWidget(self.lbl_drive_tx)
        grp_layout.addLayout(row)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("⚙ Drive RX:"))
        self.lbl_drive_rx = QLabel("---")
        self.lbl_drive_rx.setStyleSheet("background-color: #ffe0b2; font-family: Courier; font-size: 9pt;")
        row.addWidget(self.lbl_drive_rx)
        grp_layout.addLayout(row)
        
        grp_txrx.setLayout(grp_layout)
        layout.addWidget(grp_txrx)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def on_mode_changed(self, index):
        """Toggle between Serial and TCP mode"""
        is_tcp = (index == 1)
        self.grp_serial.setVisible(not is_tcp)
        self.grp_tcp.setVisible(is_tcp)
    
    def create_sensor_tab(self):
        """Sensor device tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        grp = QGroupBox(f"📊 {DEVICE_SENSOR['name']}")
        grp_layout = QVBoxLayout()
        
        # Info
        row = QHBoxLayout()
        row.addWidget(QLabel(f"Slave ID: {DEVICE_SENSOR['slave_id']}"))
        row.addWidget(QLabel(f"Registers: 0x{DEVICE_SENSOR['start_register']:04X}"))
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Status
        self.lbl_sensor_status = QLabel("Status: ❌ Disconnected")
        self.lbl_sensor_status.setStyleSheet("font-size: 11pt; font-weight: bold; color: red;")
        grp_layout.addWidget(self.lbl_sensor_status)
        
        self.lbl_sensor_last = QLabel("Last Read: Never")
        self.lbl_sensor_last.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_sensor_last)
        
        # Data display
        row = QHBoxLayout()
        self.lbl_sensor_temp = QLabel("Temp: --- °C")
        self.lbl_sensor_temp.setStyleSheet("font-size: 13pt; font-weight: bold; color: #FF4500;")
        row.addWidget(self.lbl_sensor_temp)
        
        self.lbl_sensor_humi = QLabel("Humi: --- %")
        self.lbl_sensor_humi.setStyleSheet("font-size: 13pt; font-weight: bold; color: #1E90FF;")
        row.addWidget(self.lbl_sensor_humi)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Counters
        self.lbl_sensor_counters = QLabel("OK: 0 | Timeout: 0 | Error: 0")
        self.lbl_sensor_counters.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_sensor_counters)
        
        # Buttons
        row = QHBoxLayout()
        btn_ping = QPushButton("📡 Ping")
        btn_ping.clicked.connect(lambda: self.device_manager and self.device_manager.sensor.ping())
        row.addWidget(btn_ping)
        
        btn_read = QPushButton("📖 Read")
        btn_read.clicked.connect(lambda: self.device_manager and self.device_manager.sensor.read())
        row.addWidget(btn_read)
        row.addStretch()
        grp_layout.addLayout(row)
        
        grp.setLayout(grp_layout)
        layout.addWidget(grp)
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_drive_tab(self):
        """Drive device tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        grp = QGroupBox(f"🎮 {DEVICE_DRIVE['name']}")
        grp_layout = QVBoxLayout()
        
        # Info
        row = QHBoxLayout()
        row.addWidget(QLabel(f"Slave ID: {DEVICE_DRIVE['slave_id']}"))
        row.addWidget(QLabel(f"Status Reg: 0x{DEVICE_DRIVE['status_register']:04X}"))
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Status
        self.lbl_drive_status_text = QLabel("Status: ❌ Disconnected")
        self.lbl_drive_status_text.setStyleSheet("font-size: 11pt; font-weight: bold; color: red;")
        grp_layout.addWidget(self.lbl_drive_status_text)
        
        self.lbl_drive_last = QLabel("Last Read: Never")
        self.lbl_drive_last.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_drive_last)
        
        # Data
        row = QHBoxLayout()
        self.lbl_drive_info = QLabel("Status: --- | Position: ---")
        self.lbl_drive_info.setStyleSheet("font-size: 11pt; font-weight: bold;")
        row.addWidget(self.lbl_drive_info)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Counters
        self.lbl_drive_counters = QLabel("OK: 0 | Timeout: 0 | Error: 0")
        self.lbl_drive_counters.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_drive_counters)
        
        # Control buttons row 1
        row = QHBoxLayout()
        btn_ping = QPushButton("📡 Ping")
        btn_ping.clicked.connect(lambda: self.device_manager and self.device_manager.drive.ping())
        row.addWidget(btn_ping)
        
        btn_status = QPushButton("📖 Status")
        btn_status.clicked.connect(lambda: self.device_manager and self.device_manager.drive.read_status())
        row.addWidget(btn_status)
        
        btn_pos = QPushButton("📍 Position")
        btn_pos.clicked.connect(lambda: self.device_manager and self.device_manager.drive.read_position())
        row.addWidget(btn_pos)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Control buttons row 2 (ON/OFF/STOP)
        row = QHBoxLayout()
        btn_on = QPushButton("✓ Step ON")
        btn_on.setStyleSheet("background-color: #90EE90; font-weight: bold;")
        btn_on.clicked.connect(lambda: self.device_manager and self.device_manager.drive.step_on())
        row.addWidget(btn_on)
        
        btn_off = QPushButton("✗ Step OFF")
        btn_off.setStyleSheet("background-color: #FFB6C1; font-weight: bold;")
        btn_off.clicked.connect(lambda: self.device_manager and self.device_manager.drive.step_off())
        row.addWidget(btn_off)
        
        btn_stop = QPushButton("⏹ STOP")
        btn_stop.setStyleSheet("background-color: #FF6B6B; font-weight: bold;")
        btn_stop.clicked.connect(lambda: self.device_manager and self.device_manager.drive.move_stop())
        row.addWidget(btn_stop)
        
        btn_reset = QPushButton("⚠ Reset Alarm")
        btn_reset.setStyleSheet("background-color: #FFA500; font-weight: bold;")
        btn_reset.clicked.connect(lambda: self.device_manager and self.device_manager.drive.reset_alarm())
        row.addWidget(btn_reset)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # JOG controls
        row = QHBoxLayout()
        row.addWidget(QLabel("JOG Speed (pps):"))
        self.spin_jog_speed = QSpinBox()
        self.spin_jog_speed.setValue(10000)
        self.spin_jog_speed.setRange(100, 1000000)
        row.addWidget(self.spin_jog_speed)
        
        btn_jog_ccw = QPushButton("◀ JOG CCW")
        btn_jog_ccw.setStyleSheet("background-color: #87CEEB;")
        btn_jog_ccw.clicked.connect(lambda: self.device_manager and self.device_manager.drive.jog_ccw(self.spin_jog_speed.value()))
        row.addWidget(btn_jog_ccw)
        
        btn_jog_cw = QPushButton("JOG CW ▶")
        btn_jog_cw.setStyleSheet("background-color: #87CEEB;")
        btn_jog_cw.clicked.connect(lambda: self.device_manager and self.device_manager.drive.jog_cw(self.spin_jog_speed.value()))
        row.addWidget(btn_jog_cw)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Absolute move
        row = QHBoxLayout()
        row.addWidget(QLabel("Absolute Position:"))
        self.le_abs_pos = QLineEdit("0")
        self.le_abs_pos.setFixedWidth(100)
        row.addWidget(self.le_abs_pos)
        
        row.addWidget(QLabel("Speed (pps):"))
        self.spin_abs_speed = QSpinBox()
        self.spin_abs_speed.setValue(10000)
        self.spin_abs_speed.setRange(100, 1000000)
        row.addWidget(self.spin_abs_speed)
        
        btn_abs = QPushButton("Move Absolute")
        btn_abs.clicked.connect(self.on_move_absolute)
        row.addWidget(btn_abs)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Incremental move
        row = QHBoxLayout()
        row.addWidget(QLabel("Incremental Offset:"))
        self.le_inc_offset = QLineEdit("1000")
        self.le_inc_offset.setFixedWidth(100)
        row.addWidget(self.le_inc_offset)
        
        row.addWidget(QLabel("Speed (pps):"))
        self.spin_inc_speed = QSpinBox()
        self.spin_inc_speed.setValue(10000)
        self.spin_inc_speed.setRange(100, 1000000)
        row.addWidget(self.spin_inc_speed)
        
        btn_inc = QPushButton("Move Incremental")
        btn_inc.clicked.connect(self.on_move_incremental)
        row.addWidget(btn_inc)
        row.addStretch()
        grp_layout.addLayout(row)
        
        grp.setLayout(grp_layout)
        layout.addWidget(grp)
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def on_move_absolute(self):
        """Handle Move Absolute"""
        try:
            pos = int(self.le_abs_pos.text())
            speed = self.spin_abs_speed.value()
            if self.device_manager:
                self.device_manager.drive.move_absolute(pos, speed)
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid position value")
    
    def on_move_incremental(self):
        """Handle Move Incremental"""
        try:
            offset = int(self.le_inc_offset.text())
            speed = self.spin_inc_speed.value()
            if self.device_manager:
                self.device_manager.drive.move_incremental(offset, speed)
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid offset value")
    
    def on_open_event_log(self):
        """Open floating event log window"""
        if not self.log_window:
            self.log_window = EventLogWindow()
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()
    
    def on_open_connection(self):
        """Open connection"""
        if self.modbus_manager is not None:
            QMessageBox.warning(self, "Error", "Already connected")
            return
        
        mode_idx = self.combo_mode.currentIndex()
        is_tcp = (mode_idx == 1)
        
        try:
            if is_tcp:
                host = self.le_host.text()
                port = self.spin_tcp_port.value()
                self.modbus_manager = ModbusTCPManager(host, port, TCP_TIMEOUT)
                mode_str = f"TCP {host}:{port}"
            else:
                port = self.combo_port.currentText()
                baudrate = int(self.combo_baud.currentText())
                parity = self.combo_parity.currentText()
                stopbits = int(self.combo_stopbits.currentText())
                
                self.modbus_manager = RS485Manager(
                    port=port,
                    baudrate=baudrate,
                    parity=parity,
                    stopbits=stopbits,
                    timeout=DEFAULT_TIMEOUT
                )
                mode_str = f"{port} {baudrate} {parity}{stopbits}"
            
            if self.modbus_manager.open():
                self.device_manager = DeviceManager(self.modbus_manager)
                self.lbl_status.setText(f"✅ CONNECTED ({mode_str})")
                self.lbl_status.setStyleSheet("background-color: #90EE90; padding: 8px; font-size: 11pt; font-weight: bold;")
                self.btn_open.setEnabled(False)
                self.btn_close.setEnabled(True)
                logger.info(f"Connected: {mode_str}", "UI")
            else:
                self.lbl_status.setText("❌ CONNECTION FAILED")
                self.lbl_status.setStyleSheet("background-color: #FFB6C1; padding: 8px; font-size: 11pt; font-weight: bold;")
                self.modbus_manager = None
                self.device_manager = None
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.modbus_manager = None
            self.device_manager = None
    
    def on_close_connection(self):
        """Close connection"""
        if self.modbus_manager:
            self.modbus_manager.close()
            self.modbus_manager = None
            self.device_manager = None
            
            self.lbl_status.setText("❌ DISCONNECTED")
            self.lbl_status.setStyleSheet("background-color: #ffffcc; padding: 8px; font-size: 11pt; font-weight: bold;")
            self.btn_open.setEnabled(True)
            self.btn_close.setEnabled(False)
            logger.info("Disconnected", "UI")
    
    def refresh_ui(self):
        """Update UI periodically"""
        if not self.device_manager:
            return
        
        status = self.device_manager.get_all_status()
        
        # Update TX/RX display
        modbus_st = status["modbus"]
        self.lbl_sensor_tx.setText(modbus_st.get("last_tx", "---"))
        self.lbl_sensor_rx.setText(modbus_st.get("last_rx", "---"))
        
        # Update Sensor
        sensor_st = status["sensor"]
        self.lbl_sensor_status.setText(
            f"Status: {'✅ Connected' if sensor_st['connected'] else '❌ Disconnected'}"
        )
        self.lbl_sensor_status.setStyleSheet(
            f"font-size: 11pt; font-weight: bold; color: {'green' if sensor_st['connected'] else 'red'};"
        )
        
        self.lbl_sensor_last.setText(f"Last Read: {sensor_st['last_read']}")
        
        if "temperature" in sensor_st["data"]:
            self.lbl_sensor_temp.setText(f"Temp: {sensor_st['data']['temperature']}")
            self.lbl_sensor_humi.setText(f"Humi: {sensor_st['data']['humidity']}")
        
        self.lbl_sensor_counters.setText(
            f"OK: {sensor_st['ok_count']} | Timeout: {sensor_st['timeout_count']} | Error: {sensor_st['crc_error_count']}"
        )
        
        # Update Drive
        drive_st = status["drive"]
        self.lbl_drive_status_text.setText(
            f"Status: {'✅ Connected' if drive_st['connected'] else '❌ Disconnected'}"
        )
        self.lbl_drive_status_text.setStyleSheet(
            f"font-size: 11pt; font-weight: bold; color: {'green' if drive_st['connected'] else 'red'};"
        )
        
        self.lbl_drive_last.setText(f"Last Read: {drive_st['last_read']}")
        
        status_parts = [f"{k}: {v}" for k, v in drive_st["data"].items() if k not in ["position"]]
        status_txt = " | ".join(status_parts) if status_parts else "---"
        
        pos_txt = drive_st["data"].get("position", "---")
        self.lbl_drive_info.setText(f"Status: {status_txt} | Position: {pos_txt}")
        
        self.lbl_drive_counters.setText(
            f"OK: {drive_st['ok_count']} | Timeout: {drive_st['timeout_count']} | Error: {drive_st['crc_error_count']}"
        )
        
        # Update log window if open
        if self.log_window:
            log_entries = logger.get_buffer()
            self.log_window.update_log(log_entries)
    
    def closeEvent(self, event):
        """Cleanup before exit"""
        if self.modbus_manager:
            self.modbus_manager.close()
        if self.log_window:
            self.log_window.close()
        logger.info("Application closed", "UI")
        event.accept()

def main():
    """Application entry point"""
    app = QApplication(sys.argv)
    window = SlaveMonitorGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()