# 墨水屏数据中继服务端 (EPD Server)

本项目为 ESP32 墨水屏网关的局域网中继服务端。负责管理电子相册（3 卡槽轮播）、即时便签插播（支持手机快捷指令/HTTP 推送）、24 小时分时段自定义排程调度，并将内容渲染转换为墨水屏专用的点阵二进制流（`screen.bin`）。

---

## 快速部署指南 (局域网其他机器)

服务端采用原生 Python 编写，极简轻量，无任何重型数据库或外部复杂依赖。

### 1. 环境准备
- **操作系统**: Linux / macOS / Windows
- **Python 版本**: Python 3.10 或更高版本
- **中文字体支持**（确保便签与时钟汉字正常渲染）:
  - **Debian / Ubuntu / Armbian**:
    ```bash
    sudo apt update && sudo apt install -y fonts-wqy-zenhei
    ```
  - **CentOS / RHEL**:
    ```bash
    sudo yum install -y wqy-zenhei-fonts
    ```
  - **免 root / 免包管理器方案**:
    直接将任意中文字体（如 `.ttc` 或 `.ttf`）复制到 `server/fonts/font.ttc` 即可自动识别使用。

---

### 2. 一键启动 (推荐)

进入 `server` 目录后运行：
```bash
./start.sh
```
`start.sh` 会自动创建隔离虚拟环境 `venv`、安装 Python 依赖库并启动服务，默认监听 `0.0.0.0:8000`。

---

### 3. 手动启动

若习惯手动管理 Python 环境：
```bash
cd server

# 1. 创建虚拟环境 (可选但推荐)
python3 -m venv venv
source venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行服务
python main.py
# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000
```

启动成功后，浏览器打开局域网地址：`http://<服务器IP>:8000` 即可进入 Web 管理面板。

---

### 4. 后台常驻运行 (Linux 机器)

#### 方案 A：nohup 简易后台
```bash
nohup ./start.sh > server.log 2>&1 &
```

#### 方案 B：systemd 开机自启服务 (推荐生产使用)
在 `/etc/systemd/system/epd-server.service` 创建服务配置：
```ini
[Unit]
Description=EPD Relay Server
After=network.target

[Service]
Type=simple
User=eastwoodnet
WorkingDirectory=/path/to/esp32-gateway/server
ExecStart=/path/to/esp32-gateway/server/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
启用并启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now epd-server
```

---

## ESP32 网关联动配置

服务端部署完毕后，记下该机器在局域网中的 IP 地址（例如 `192.168.1.100`）：
1. 连接 ESP32 管理后台（浏览器访问 `http://192.168.1.118` 或 `http://epd-gateway.local`）。
2. 在 **参数设置** 中，将 **HTTP 轮询图片地址** 修改为：
   ```
   http://192.168.1.100:8000/screen.bin
   ```
3. 在服务端的 Web 管理面板（`http://192.168.1.100:8000`）底部「系统设置」中，将 **ESP32 网关地址** 配置为网关实际 IP（例如 `http://192.168.1.118`），以便每次推送便签时服务端能立即主动触发网关同步，实现秒级上屏。

---

## 常用 API 接口

| 接口路径 | 请求方式 | 功能描述 |
|---|---|---|
| `/screen.bin` | GET | 网关拉取墨水屏点阵核心入口 (支持 ETag 304 缓存) |
| `/api/push` | POST / GET | 外部推送便签插播 (支持 iPhone 快捷指令或脚本) |
| `/api/memo/clear` | POST | 提前清除当前便签，恢复正常时段排程 |
| `/api/memo/status`| GET | 获取当前便签插播状态与剩余时长 |
| `/api/album/slot/{id}` | POST | 上传并替换卡槽照片 (id: 1 ~ 3) |
| `/api/schedule` | POST / GET | 24小时自由时段排程规则读写 |
| `/api/trigger` | POST | 手动命令网关立即唤醒拉取并刷新屏幕 |

### iPhone 快捷指令 / 手机推送示例
向墨水屏推送一条临时备忘（GET 方式极简调用）：
```
http://192.168.1.100:8000/api/push?title=会议提醒&text=下午三点代码评审会议&duration_min=60&sender=手机推送
```
或通过 POST JSON 发送：
```bash
curl -X POST http://192.168.1.100:8000/api/push \
  -H "Content-Type: application/json" \
  -d '{
    "title": "☕ 咖啡时间",
    "text": "休息一下喝杯咖啡吧！",
    "duration_min": 30,
    "sender": "快捷指令"
  }'
```
