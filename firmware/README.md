# EPD-ESP32gateway Precompiled Firmware / 预编译固件说明

本目录提供已编译完成的 ESP32 墨水屏网关固件二进制文件，适用于 **LilyGO T-Display-S3** 开发板。

---

## 固件文件清单

| 文件名 | 烧录起始地址 (Offset) | 说明 |
|---|---|---|
| **`lilygo_t_display_s3_full_0x0.bin`** | **`0x0`** | **完整合并固件（推荐，单文件一键烧录）** |
| `bootloader.bin` | `0x0` | ESP32-S3 二级引导程序 |
| `partitions.bin` | `0x8000` | 分区表文件 (16MB Flash 配置) |
| `firmware.bin` | `0x10000` | 网关主应用程序固件 |

---

## 烧录方法

### 方法一：使用 esptool 命令行烧录（推荐）

确保电脑已安装 Python 及 `esptool`：
```bash
pip install esptool
```

将 LilyGO T-Display-S3 插入电脑 USB 口，确认串口号（Linux/macOS 通常为 `/dev/ttyACM0` 或 `/dev/ttyUSB0`，Windows 为 `COMx`）：

#### 1. 单文件快速烧录（推荐）：
```bash
esptool --chip esp32s3 write-flash 0x0 lilygo_t_display_s3_full_0x0.bin
```

#### 2. 分段文件烧录：
```bash
esptool --chip esp32s3 write-flash \
  0x0 bootloader.bin \
  0x8000 partitions.bin \
  0x10000 firmware.bin
```

---

### 方法二：使用图形化 / Web 烧录工具

1. 浏览器打开 [ESP Web Tool](https://esp.huhn.me/) 或 [ESPHome Web Flasher](https://web.esphome.io/)。
2. 连接开发板串口。
3. 选择 `lilygo_t_display_s3_full_0x0.bin`，地址填写 `0x0`，点击 Program 烧录。

---

## 首次配网与使用

1. 烧录完成后，开发板屏幕亮起并显示状态仪表盘。
2. 若尚未配置 Wi-Fi，板载屏幕将提示进入 **AP 配网模式**：
   - **热点名称 (SSID)**: `EPD-Gateway-XXXX`
   - **初始密码**: `12345678`
   - **配网管理 IP**: `http://192.168.4.1`
3. 连接热点后在浏览器打开配网页面，填入家庭/办公室 Wi-Fi 及密码，设备将自动重启并连入局域网。
4. 随后即可在同局域网浏览器中访问 `http://epd-gateway.local` 或屏幕上显示的局域网 IP 进行墨水屏绑定与测试。
