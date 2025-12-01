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
