"""
Main GUI - PyQt5 Modbus RTU Monitor Interface
Usage: python -m slave.main_gui
"""
import sys
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox, QGroupBox, QTextEdit,
    QTabWidget, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor

from .config import *
from .modbus_handler import RS485Manager
from .device_manager import DeviceManager
from .logger_handler import logger

class SignalEmitter(QObject):
    """Helper class để emit signals từ threads"""
    update_signal = pyqtSignal()

class SlaveMonitorGUI(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔧 RS-485 Modbus RTU Monitor")
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Initialize components
        self.rs485 = None
        self.device_manager = None
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
        
        # Tab 1: RS-485 Settings
        tabs.addTab(self.create_rs485_tab(), "🔌 RS-485 Settings")
        
        # Tab 2: Sensor Device
        tabs.addTab(self.create_sensor_tab(), "🌡 Sensor (SHT20)")
        
        # Tab 3: Drive Device
        tabs.addTab(self.create_drive_tab(), "⚙ Drive (EZi-STEP)")
        
        # Tab 4: Event Log
        tabs.addTab(self.create_log_tab(), "📋 Event Log")
        
        main_layout.addWidget(tabs)
        
        central.setLayout(main_layout)
        self.setCentralWidget(central)
    
    def create_rs485_tab(self):
        """RS-485 / COM Settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Group: Port Configuration
        grp_config = QGroupBox("Port Configuration")
        grp_layout = QVBoxLayout()
        
        # Row: COM Port
        row = QHBoxLayout()
        row.addWidget(QLabel("COM Port:"))
        self.combo_port = QComboBox()
        self.combo_port.addItems(AVAILABLE_PORTS)
        self.combo_port.setCurrentText(DEFAULT_COM_PORT)
        row.addWidget(self.combo_port)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Row: Baudrate
        row = QHBoxLayout()
        row.addWidget(QLabel("Baudrate:"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems([str(b) for b in AVAILABLE_BAUDRATES])
        self.combo_baud.setCurrentText(str(DEFAULT_BAUDRATE))
        row.addWidget(self.combo_baud)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Row: Parity, Stopbits, Databits, Timeout
        row = QHBoxLayout()
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
        
        row.addWidget(QLabel("Databits:"))
        self.spin_databits = QSpinBox()
        self.spin_databits.setValue(DEFAULT_DATABITS)
        self.spin_databits.setRange(5, 8)
        row.addWidget(self.spin_databits)
        
        row.addWidget(QLabel("Timeout (s):"))
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setValue(int(DEFAULT_TIMEOUT))
        self.spin_timeout.setRange(1, 10)
        row.addWidget(self.spin_timeout)
        row.addStretch()
        grp_layout.addLayout(row)
        
        grp_config.setLayout(grp_layout)
        layout.addWidget(grp_config)
        
        # Group: Actions
        grp_actions = QGroupBox("Connection")
        grp_layout = QVBoxLayout()
        
        row = QHBoxLayout()
        self.btn_open = QPushButton("🔓 Open Port")
        self.btn_open.setStyleSheet("background-color: #90EE90; font-weight: bold; padding: 8px;")
        self.btn_open.clicked.connect(self.on_open_port)
        row.addWidget(self.btn_open)
        
        self.btn_close = QPushButton("🔒 Close Port")
        self.btn_close.setStyleSheet("background-color: #FFB6C1; font-weight: bold; padding: 8px;")
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.on_close_port)
        row.addWidget(self.btn_close)
        
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Status
        self.lbl_port_status = QLabel("Status: CLOSED")
        self.lbl_port_status.setStyleSheet("background-color: #ffffcc; padding: 8px; font-size: 11pt; font-weight: bold;")
        grp_layout.addWidget(self.lbl_port_status)
        
        grp_actions.setLayout(grp_layout)
        layout.addWidget(grp_actions)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_sensor_tab(self):
        """Sensor device tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        grp = QGroupBox(f"📊 {DEVICE_SENSOR['name']}")
        grp_layout = QVBoxLayout()
        
        # Info row
        row = QHBoxLayout()
        row.addWidget(QLabel(f"Slave ID: {DEVICE_SENSOR['slave_id']}"))
        row.addWidget(QLabel(f"Protocol: {DEVICE_SENSOR['protocol']}"))
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Status
        self.lbl_sensor_connected = QLabel("Status: ❌ Disconnected")
        self.lbl_sensor_connected.setStyleSheet("font-size: 11pt; font-weight: bold; color: red;")
        grp_layout.addWidget(self.lbl_sensor_connected)
        
        # Last response
        self.lbl_sensor_last_read = QLabel("Last Read: Never")
        self.lbl_sensor_last_read.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_sensor_last_read)
        
        # Data
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
        self.lbl_sensor_counters = QLabel("OK: 0 | Timeout: 0 | CRC Error: 0")
        self.lbl_sensor_counters.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_sensor_counters)
        
        # Buttons
        row = QHBoxLayout()
        btn_ping = QPushButton("📡 Ping")
        btn_ping.clicked.connect(lambda: self.device_manager and self.device_manager.sensor.ping())
        row.addWidget(btn_ping)
        
        btn_read = QPushButton("📖 Read Once")
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
        
        # Info row
        row = QHBoxLayout()
        row.addWidget(QLabel(f"Slave ID: {DEVICE_DRIVE['slave_id']}"))
        row.addWidget(QLabel(f"Protocol: {DEVICE_DRIVE['protocol']}"))
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Status
        self.lbl_drive_connected = QLabel("Status: ❌ Disconnected")
        self.lbl_drive_connected.setStyleSheet("font-size: 11pt; font-weight: bold; color: red;")
        grp_layout.addWidget(self.lbl_drive_connected)
        
        # Last response
        self.lbl_drive_last_read = QLabel("Last Read: Never")
        self.lbl_drive_last_read.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_drive_last_read)
        
        # Data
        row = QHBoxLayout()
        self.lbl_drive_status = QLabel("Status: ---")
        self.lbl_drive_status.setStyleSheet("font-size: 11pt; font-weight: bold;")
        row.addWidget(self.lbl_drive_status)
        
        self.lbl_drive_position = QLabel("Position: ---")
        self.lbl_drive_position.setStyleSheet("font-size: 11pt; font-weight: bold;")
        row.addWidget(self.lbl_drive_position)
        row.addStretch()
        grp_layout.addLayout(row)
        
        # Counters
        self.lbl_drive_counters = QLabel("OK: 0 | Timeout: 0 | CRC Error: 0")
        self.lbl_drive_counters.setStyleSheet("font-size: 10pt;")
        grp_layout.addWidget(self.lbl_drive_counters)
        
        # Buttons
        row = QHBoxLayout()
        btn_ping = QPushButton("📡 Ping")
        btn_ping.clicked.connect(lambda: self.device_manager and self.device_manager.drive.ping())
        row.addWidget(btn_ping)
        
        btn_status = QPushButton("📖 Read Status")
        btn_status.clicked.connect(lambda: self.device_manager and self.device_manager.drive.read_status())
        row.addWidget(btn_status)
        
        btn_pos = QPushButton("📍 Read Position")
        btn_pos.clicked.connect(lambda: self.device_manager and self.device_manager.drive.read_position())
        row.addWidget(btn_pos)
        
        btn_on = QPushButton("✓ Step ON")
        btn_on.setStyleSheet("background-color: #90EE90;")
        btn_on.clicked.connect(lambda: self.device_manager and self.device_manager.drive.step_on())
        row.addWidget(btn_on)
        
        btn_off = QPushButton("✗ Step OFF")
        btn_off.setStyleSheet("background-color: #FFB6C1;")
        btn_off.clicked.connect(lambda: self.device_manager and self.device_manager.drive.step_off())
        row.addWidget(btn_off)
        row.addStretch()
        grp_layout.addLayout(row)
        
        grp.setLayout(grp_layout)
        layout.addWidget(grp)
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_log_tab(self):
        """Event log tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Buttons
        row = QHBoxLayout()
        btn_clear = QPushButton("🗑 Clear Log")
        btn_clear.clicked.connect(self.on_clear_log)
        row.addWidget(btn_clear)
        
        btn_export = QPushButton("💾 Export CSV")
        btn_export.clicked.connect(self.on_export_log)
        row.addWidget(btn_export)
        row.addStretch()
        layout.addLayout(row)
        
        # Log text
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier New", 9))
        self.log_text.setStyleSheet("background-color: #f5f5f5;")
        layout.addWidget(self.log_text)
        
        widget.setLayout(layout)
        return widget
    
    def on_open_port(self):
        """Open RS-485 port"""
        if self.rs485 is not None:
            QMessageBox.warning(self, "Error", "Port already open")
            return
        
        port = self.combo_port.currentText()
        baudrate = int(self.combo_baud.currentText())
        parity = self.combo_parity.currentText()
        stopbits = int(self.combo_stopbits.currentText())
        databits = self.spin_databits.value()
        timeout = self.spin_timeout.value()
        
        self.rs485 = RS485Manager(
            port=port,
            baudrate=baudrate,
            parity=parity,
            stopbits=stopbits,
            databits=databits,
            timeout=float(timeout)
        )
        
        if self.rs485.open():
            self.device_manager = DeviceManager(self.rs485)
            self.lbl_port_status.setText(f"✅ Status: OPEN ({port})")
            self.lbl_port_status.setStyleSheet("background-color: #90EE90; padding: 8px; font-size: 11pt; font-weight: bold;")
            self.btn_open.setEnabled(False)
            self.btn_close.setEnabled(True)
            logger.info(f"Opened {port} {baudrate} {databits}{parity}{stopbits}", "UI")
        else:
            self.lbl_port_status.setText("❌ Status: FAILED TO OPEN")
            self.lbl_port_status.setStyleSheet("background-color: #FFB6C1; padding: 8px; font-size: 11pt; font-weight: bold;")
            self.rs485 = None
            self.device_manager = None
    
    def on_close_port(self):
        """Close RS-485 port"""
        if self.rs485:
            self.rs485.close()
            self.rs485 = None
            self.device_manager = None
            self.lbl_port_status.setText("❌ Status: CLOSED")
            self.lbl_port_status.setStyleSheet("background-color: #ffffcc; padding: 8px; font-size: 11pt; font-weight: bold;")
            self.btn_open.setEnabled(True)
            self.btn_close.setEnabled(False)
            logger.info("Port closed", "UI")
    
    def refresh_ui(self):
        """Update UI every REFRESH_INTERVAL_MS"""
        if not self.device_manager:
            return
        
        status = self.device_manager.get_all_status()
        
        # Update Sensor
        sensor_st = status["sensor"]
        self.lbl_sensor_connected.setText(
            f"Status: {'✅ Connected' if sensor_st['connected'] else '❌ Disconnected'}"
        )
        self.lbl_sensor_connected.setStyleSheet(
            f"font-size: 11pt; font-weight: bold; color: {'green' if sensor_st['connected'] else 'red'};"
        )
        
        self.lbl_sensor_last_read.setText(f"Last Read: {sensor_st['last_read']}")
        
        if "temperature" in sensor_st["data"]:
            self.lbl_sensor_temp.setText(f"Temp: {sensor_st['data']['temperature']}")
            self.lbl_sensor_humi.setText(f"Humi: {sensor_st['data']['humidity']}")
        
        self.lbl_sensor_counters.setText(
            f"OK: {sensor_st['ok_count']} | Timeout: {sensor_st['timeout_count']} | CRC Error: {sensor_st['crc_error_count']}"
        )
        
        # Update Drive
        drive_st = status["drive"]
        self.lbl_drive_connected.setText(
            f"Status: {'✅ Connected' if drive_st['connected'] else '❌ Disconnected'}"
        )
        self.lbl_drive_connected.setStyleSheet(
            f"font-size: 11pt; font-weight: bold; color: {'green' if drive_st['connected'] else 'red'};"
        )
        
        self.lbl_drive_last_read.setText(f"Last Read: {drive_st['last_read']}")
        
        status_txt = " | ".join([f"{k}: {v}" for k, v in drive_st["data"].items() if k != "position"])
        self.lbl_drive_status.setText(f"Status: {status_txt}" if status_txt else "Status: ---")
        
        if "position" in drive_st["data"]:
            self.lbl_drive_position.setText(f"Position: {drive_st['data']['position']}")
        
        self.lbl_drive_counters.setText(
            f"OK: {drive_st['ok_count']} | Timeout: {drive_st['timeout_count']} | CRC Error: {drive_st['crc_error_count']}"
        )
        
        # Update log
        log_entries = logger.get_buffer()
        self.log_text.setPlainText("\n".join(log_entries[-50:]))  # Last 50 lines
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def on_clear_log(self):
        """Clear log buffer"""
        logger.clear_buffer()
        self.log_text.clear()
        logger.info("Log cleared", "UI")
    
    def on_export_log(self):
        """Export log to CSV"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/slave_log_{timestamp}.csv"
        logger.export_csv(filename)
        QMessageBox.information(self, "Success", f"Logs exported to {filename}")
    
    def closeEvent(self, event):
        """Cleanup before exit"""
        if self.rs485:
            self.rs485.close()
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