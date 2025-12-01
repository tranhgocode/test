# Dự án Mô phỏng Mạng Truyền thông Công nghiệp - Python
## (Industrial Network Simulation - Python)

## Tổng quan Dự án

Dự án này mô phỏng một hệ thống mạng truyền thông công nghiệp với kiến trúc Master-Slave bằng Python:

- **Master (PC 1)**: Máy tính chủ điều khiển toàn bộ hệ thống, gửi lệnh và nhận dữ liệu
- **Slave/PLC (PC 2)**: Mô phỏng một bộ điều khiển có thể lập trình (PLC), thực thi lệnh từ Master
- **Thiết bị ngoại vi**: 
  - 1 cảm biến (Sensor): Đọc dữ liệu từ môi trường
  - 1 Drive điều khiển động cơ (Motor Drive): Điều khiển tốc độ/hướng quay động cơ

## Kiến trúc Hệ thống

```
┌──────────────┐ Gửi lệnh/Nhận dữ liệu ┌──────────────┐
│  PC 1        │ ◄────────────────────► │  PC 2        │
│  (Master)    │   Giao thức Modbus/   │  (PLC Slave) │
│              │   TCP hoặc Serial      │              │
└──────────────┘                        └──────────────┘
                                              │
                                    ┌─────────┴──────────┐
                                    │                    │
                              ┌─────────────┐    ┌──────────────┐
                              │   Sensor    │    │ Motor Drive  │
                              │ (Input I/O) │    │ (Output I/O) │
                              └─────────────┘    └──────────────┘
```

## Các thành phần chính

### 1. Master Application (PC 1)
- Ứng dụng giao diện người dùng để:
  - Gửi lệnh điều khiển đến PLC
  - Hiển thị trạng thái hệ thống real-time
  - Giám sát dữ liệu từ cảm biến
  - Kiểm soát tham số động cơ

### 2. PLC Emulator (PC 2)
- Mô phỏng hành vi của một PLC thực:
  - Nhận lệnh từ Master
  - Đọc dữ liệu từ cảm biến (mô phỏng hoặc thực)
  - Gửi tín hiệu điều khiển đến Motor Drive
  - Trả lời các truy vấn trạng thái

### 3. Thiết bị Ngoại vi
- **Cảm biến (Sensor)**: Cung cấp dữ liệu đầu vào (nhiệt độ, áp lực, vị trí, v.v.)
- **Motor Drive**: Nhận tín hiệu điều khiển và điều chỉnh hoạt động động cơ

## Giao thức Truyền thông

Dự án sử dụng các giao thức công nghiệp phổ biến:

- **Modbus RTU**: Truyền thông qua cáp Serial RS-485
- **Modbus TCP**: Truyền thông qua Ethernet (khuyến khích)
- **OPC UA**: Nếu cần hỗ trợ nâng cao

## Yêu cầu Hệ thống

### Phần mềm
- Python 3.8 trở lên
- pip (Python package manager)

### Thư viện Python cần thiết

```
pymodbus==3.1.0          # Giao thức Modbus
PyQt5==5.15.7            # Giao diện người dùng
pyserial==3.5            # Truyền thông Serial
numpy==1.24.0            # Xử lý dữ liệu số
requests==2.28.0         # HTTP requests (nếu cần)
```

## Hướng dẫn Cài đặt

### 1. Tạo Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 2. Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### 3. Cấu hình kết nối mạng
- Đảm bảo hai PC kết nối được với nhau qua Ethernet hoặc Serial
- Lưu ý địa chỉ IP hoặc cổng COM của từng PC

## Cấu trúc Thư mục Dự án

```
industrial-network-simulation/
├── master/
│   ├── src/
│   │   ├── main.py                 # Điểm khởi động Master
│   │   ├── master_controller.py    # Logic điều khiển chủ
│   │   ├── modbus_client.py        # Client Modbus
│   │   └── ui/
│   │       ├── __init__.py
│   │       └── main_window.py      # Giao diện PyQt5
│   └── config.py
├── plc_slave/
│   ├── src/
│   │   ├── main.py                 # Điểm khởi động PLC
│   │   ├── plc_emulator.py         # Mô phỏng PLC
│   │   ├── modbus_server.py        # Server Modbus
│   │   ├── sensor_interface.py     # Giao tiếp cảm biến
│   │   └── motor_controller.py     # Điều khiển động cơ
│   └── config.py
├── shared/
│   ├── __init__.py
│   ├── constants.py                # Hằng số chung
│   └── data_types.py               # Kiểu dữ liệu chung
├── requirements.txt
├── README.md
└── docs/
    └── protocol_specification.md   # Mô tả giao thức
```

## Quy tắc Lập trình Python

### Phong cách Code
- Tuân theo PEP 8 - Python Enhancement Proposal 8
- Sử dụng dòng lệnh tối đa 79 ký tự
- Cấu trúc rõ ràng với docstring cho các hàm
- Ưu tiên readability (khả năng đọc)

### Quy ước Đặt tên

**PascalCase** - Tên class và exception:
```python
class MasterController:
    pass

class SensorData:
    pass
```

**snake_case** - Tên biến, hàm, và phương thức:
```python
def read_sensor_value():
    pass

def send_command_to_plc():
    pass

motor_speed = 1500
```

**ALL_CAPS** - Hằng số:
```python
DEFAULT_TIMEOUT = 5.0
MAX_RETRY_COUNT = 3
MODBUS_TCP_PORT = 502
SENSOR_READ_INTERVAL = 1.0
```

**Dấu gạch dưới (_)** - Thành viên private:
```python
class PLCEmulator:
    def __init__(self):
        self._internal_buffer = []
        self._connection_status = False
```

### Chất lượng Code
- Sử dụng tên biến và hàm rõ ràng mô tả chức năng
- Thêm docstring cho mỗi class và hàm
- Xử lý lỗi cho đầu vào người dùng và các lệnh gọi API/giao thức
- Validate dữ liệu nhận được từ các thiết bị ngoại vi
- Sử dụng type hints cho tính rõ ràng

### Ví dụ Code Structure

```python
"""
master_controller.py
Module điều khiển Master cho hệ thống truyền thông công nghiệp.
"""

from typing import Optional, Dict, Any
from shared.constants import DEFAULT_TIMEOUT, MAX_RETRY_COUNT


class MasterController:
    """
    Điều khiển Master - gửi lệnh đến PLC Slave.
    
    Attributes:
        host (str): Địa chỉ IP của PLC Slave
        port (int): Cổng kết nối
        timeout (float): Thời gian chờ timeout
    """
    
    def __init__(self, host: str, port: int, timeout: float = DEFAULT_TIMEOUT):
        """
        Khởi tạo MasterController.
        
        Args:
            host: Địa chỉ IP của PLC Slave
            port: Cổng kết nối
            timeout: Thời gian chờ timeout (giây)
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._retry_count = 0
    
    def send_command(self, command: Dict[str, Any]) -> bool:
        """
        Gửi lệnh đến PLC Slave.
        
        Args:
            command: Dictionary chứa lệnh
            
        Returns:
            bool: True nếu gửi thành công, False nếu lỗi
        """
        try:
            # Validate lệnh
            if not self._validate_command(command):
                return False
            
            # Gửi lệnh
            # Implementation ở đây
            return True
            
        except Exception as e:
            print(f"Lỗi khi gửi lệnh: {e}")
            return False
    
    def _validate_command(self, command: Dict[str, Any]) -> bool:
        """
        Xác thực tính hợp lệ của lệnh.
        
        Args:
            command: Lệnh cần xác thực
            
        Returns:
            bool: True nếu lệnh hợp lệ
        """
        required_keys = ['type', 'value']
        return all(key in command for key in required_keys)


def main():
    """Hàm chính của ứng dụng Master."""
    controller = MasterController('192.168.1.100', 502)
    # Khởi động ứng dụng
    pass


if __name__ == '__main__':
    main()
```

## Hướng dẫn Triển khai

### Bước 1: Chuẩn bị Môi trường
```bash
cd industrial-network-simulation
python -m venv venv
source venv/bin/activate  # hoặc venv\Scripts\activate trên Windows
pip install -r requirements.txt
```

### Bước 2: Cấu hình Thông số
Sửa file `config.py` trong cả master và plc_slave:
```python
# master/config.py
MASTER_HOST = '0.0.0.0'
MASTER_PORT = 5020
PLC_SLAVE_HOST = '192.168.1.100'  # IP của PC 2
PLC_SLAVE_PORT = 502

# plc_slave/config.py
PLC_HOST = '0.0.0.0'
PLC_PORT = 502
SENSOR_PORT = 'COM3'  # hoặc '/dev/ttyUSB0' trên Linux
MOTOR_CONTROL_PIN = 17  # GPIO pin nếu dùng Raspberry Pi
```

### Bước 3: Chạy ứng dụng

**Trên PC 2 (PLC Slave) - Chạy trước:**
```bash
cd plc_slave
python src/main.py
```

**Trên PC 1 (Master) - Chạy sau:**
```bash
cd master
python src/main.py
```

## Các Tính Năng Cần Triển khai

1. **Communication Layer**: Kết nối Master-Slave với pymodbus
2. **Sensor Interface**: Đọc dữ liệu từ cảm biến (Serial hoặc GPIO)
3. **Motor Control**: Gửi tín hiệu PWM đến drive động cơ
4. **Data Logging**: Ghi lại sự kiện và trạng thái hệ thống
5. **User Interface**: Giao diện PyQt5 để giám sát và điều khiển
6. **Error Handling**: Xử lý timeout, mất kết nối, dữ liệu không hợp lệ
7. **Threading**: Xử lý đa luồng để không làm treo UI

## Ví dụ Sử dụng Pymodbus

### Modbus Server (PLC Slave)
```python
from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataStore

# Tạo data store
store = ModbusSequentialDataStore()

# Khởi động server
StartTcpServer(address=("0.0.0.0", 502), datastore=store)
```

### Modbus Client (Master)
```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient('192.168.1.100', port=502)
client.connect()

# Đọc coil
result = client.read_coils(0, 1)

# Ghi register
client.write_register(0, 1500)
```

## Kiểm thử

- [ ] Kiểm thử kết nối Master-Slave
- [ ] Kiểm thử gửi/nhận lệnh
- [ ] Kiểm thử đọc dữ liệu cảm biến
- [ ] Kiểm thử điều khiển động cơ
- [ ] Kiểm thử xử lý lỗi (mất kết nối, timeout)
- [ ] Kiểm thử hiệu suất (độ trễ, throughput)

## Tài liệu Tham khảo

- [Pymodbus Documentation](https://pymodbus.readthedocs.io/)
- [PyQt5 Official Guide](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- [PEP 8 Style Guide](https://www.python.org/dev/peps/pep-0008/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
