# ESP32 墨水屏无线中继网关与管理系统

本项目是一套基于 **ESP32-S3 (LilyGO T-Display-S3)** 与 **nRF52811 电子价签 (EPD-nRF5 固件)** 的智能墨水屏物联网中继与展示系统。配合局域网轻量 Python 服务端，实现相册轮播、分时段展示与手机即时便签秒级插播。

---

## 架构组成

```
┌─────────────────────────┐          HTTP/WiFi          ┌───────────────────────────┐
│     EPD 中继服务端      │ ───────────────────────────> │      ESP32 智能网关       │
│  (Python / FastAPI)     │ <─────────────────────────── │  (LilyGO T-Display-S3)   │
│  - 3卡槽相册轮播        │    主动触发 /api/trigger      │  - LCD 彩色仪表盘         │
│  - 24h 自定义时段排程   │                              │  - 自动 Wi-Fi / AP 配网  │
│  - 手机便签/快捷指令插播│                              │  - ETag 304 智能差量缓存  │
└─────────────────────────┘                              └─────────────┬─────────────┘
                                                                       │ BLE 5.0 (240B)
                                                                       │ 自动版本适配
                                                                       ▼
                                                         ┌───────────────────────────┐
                                                         │   盒马 4.2" 三色墨水屏   │
                                                         │   (SSD1619 / nRF52811)    │
                                                         └───────────────────────────┘
```

---

## 目录结构

- `src/` & `include/`: ESP32 网关固件源代码 (PlatformIO 工程)
  - `ble_epd_client.cpp`: 墨水屏 BLE 驱动引擎（内置自动固件版本判定、传统/新版双协议自适应、全自动分包重传）
  - `http_puller.cpp`: 墨水屏点阵数据拉取与 ETag 缓存管理器
  - `web_portal.cpp`: ESP32 本地 Web 管理控制台与配网页面
  - `display_ui.cpp`: LilyGO 板载 LCD 状态仪表盘
- `server/`: 局域网 Python 中继服务端
  - `main.py`: FastAPI 服务端入口与 API 路由
  - `src/`: 调度、便签、相册、字体渲染与点阵转换模块
  - `static/` & `templates/`: Web 管理端界面
  - `start.sh`: 一键启动脚本
  - `README.md`: 服务端详细局域网部署与接口文档

---

## 快速上手

### 1. 网关固件编译与烧录 (PlatformIO)
```bash
# 编译并烧录固件至 ESP32
pio run --target upload

# 查看串口监控
pio device monitor -b 115200
```

### 2. 服务端启动 (局域网机器)
```bash
cd server
./start.sh
```
浏览器打开 `http://<服务器IP>:8000` 即可配置排程、上传相册或推送备忘。
详细说明请参阅 [server/README.md](file:///home/eastwoodnet/worktemp/esp32-gateway/server/README.md)。
