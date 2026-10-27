# EPD-ESP32gateway - E-Paper Wireless Gateway & Relay System

简体中文 | [English](./README_EN.md)

A smart, low-power E-Paper display IoT system powered by an **ESP32 intelligent gateway** and **nRF52811 Electronic Shelf Labels (running EPD-nRF5 firmware)**. Features 3-slot photo album rotation, customizable 24-hour time-slot scheduling, and instant desktop push memos via iPhone Shortcuts and Webhooks.

> **Notice**: This repository includes the full open-source relay server code (Python / FastAPI) and precompiled firmware binaries for the **LilyGO T-Display-S3** board. Future releases will port the gateway to more affordable, standard ESP32 / ESP32-C3 minimal hardware.

---

## Key Features

- **📸 Digital Photo Album**: Supports 3 independent photo slots with configurable rotation intervals (10–1440 min). Built-in Floyd-Steinberg and Atkinson dithering algorithms tailored for 3-color (Black/White/Red) displays.
- **📅 Online Schedule & Calendar Dashboard (iCal / Webcal)**: Subscribe to Apple Calendar, Google Calendar, or Feishu/Lark ICS feeds to visualize today's agenda and timeline on a 400×300 BWR display.
- **⛅ Live Weather & Multi-Day Forecast**: Integrated keyless `wttr.in` weather service displaying current temperature, weather conditions, humidity, wind, and forecast.
- **⏰ 24-Hour Time-Slot Scheduling**: Define custom display rules throughout the day (e.g., Calendar/Clock in the morning, Task/Memo during work hours, Photo Album in the evening, Sleep/DND at night). Seamlessly handles cross-midnight time spans.
- **🚀 Instant Push Memo (Priority Override)**: Send instant notifications to your e-paper display via iPhone Shortcuts or HTTP POST/GET requests. Supports custom display durations (e.g., 30 minutes), automatically reverting to scheduled tasks upon expiration.
- **⚡ Dual-Protocol BLE 5.0 Auto-Adaptation**: Automatically inspects firmware version characteristics to support both legacy ESL firmware (v1.5–v1.9 nibble packet flags, e.g., Hema/Hanshow 0x18) and modern v1.10+ RLE compression flags, eliminating screen snow/static corruption caused by unwritten black RAM.
- **🔋 ETag 304 Smart Caching & Zero-Comm DND**: HTTP 304 diff detection skips redundant BLE transmissions when content is unchanged. Night DND retains screen image with zero radio activity to maximize battery life.
- **📊 Onboard LCD Status Dashboard**: The gateway's 1.9" color LCD displays real-time local IP, Wi-Fi RSSI, BLE connection status, data transfer progress, and countdown to the next pull.

---

## Screen Rendering Preview

| ⛅ Weather Dashboard (wttr.in) | 📅 Today's Agenda (iCal / Webcal) |
| :---: | :---: |
| ![Weather Screen Preview](./docs/images/preview_weather.png) | ![Calendar Screen Preview](./docs/images/preview_calendar.png) |
| *Live weather conditions, humidity, wind, and 3-day forecast* | *Timeline schedule, ongoing event indicator, and event list* |

---

## System Architecture

```
┌─────────────────────────────────┐
│     iPhone / PC / Webhook       │
│  (Shortcuts / REST / Browser)   │
└────────────────┬────────────────┘
                 │ HTTP API
                 ▼
┌─────────────────────────────────┐          HTTP/WiFi          ┌─────────────────────────────────┐
│        EPD Relay Server         │ ───────────────────────────> │          ESP32 Gateway          │
│       (Python / FastAPI)        │ <─────────────────────────── │      (LilyGO T-Display-S3)      │
│  - 3-slot album & scheduler     │    Trigger /api/trigger     │  - Onboard Color LCD Dashboard  │
│  - Typography & 3-color render  │                              │  - Web Portal & AP Config       │
│  - Memo priority lifecycle      │                              │  - ETag 304 smart diff cache    │
└─────────────────────────────────┘                              └───────────────┬─────────────────┘
                                                                                 │ BLE 5.0 (240B Chunk)
                                                                                 │ Protocol Auto-Adapt
                                                                                 ▼
                                                                   ┌───────────────────────────────┐
                                                                   │     4.2" BWR ESL Display      │
                                                                   │     (SSD1619 / nRF52811)      │
                                                                   └───────────────────────────────┘
```

---

## Repository Structure

```
├── firmware/                       # ESP32 Gateway Precompiled Binaries
│   ├── lilygo_t_display_s3_full_0x0.bin  # Complete merged binary (One-click flash at 0x0)
│   ├── bootloader.bin              # ESP32-S3 secondary bootloader (0x0)
│   ├── partitions.bin              # Partition table (0x8000)
│   ├── firmware.bin                # Gateway application binary (0x10000)
│   └── README.md                   # Flashing instructions
│
├── server/                         # EPD Relay Server Source (Lightweight Python)
│   ├── main.py                     # FastAPI entry point & REST endpoints
│   ├── requirements.txt            # Python dependencies
│   ├── start.sh                    # Automated startup script (Linux/macOS)
│   ├── README.md                   # Server deployment and API documentation
│   ├── src/                        # Scheduling, album, memo, and dot-matrix conversion
│   ├── static/                     # Web assets, dithering logic, and style
│   ├── templates/                  # Web dashboard HTML template
│   ├── data/                       # Local configuration & persistence
│   └── fonts/                      # Font directory
│
├── README.md                       # Main documentation (Chinese)
└── README_EN.md                    # Main documentation (English)
```

---

## Quick Start

### Step 1: Flash the ESP32 Gateway Firmware

1. Connect your **LilyGO T-Display-S3** board to your computer via a USB Type-C cable.
2. Install `esptool`:
   ```bash
   pip install esptool
   ```
3. Flash the precompiled merged binary with one command:
   ```bash
   esptool --chip esp32s3 write-flash 0x0 firmware/lilygo_t_display_s3_full_0x0.bin
   ```
4. Once flashed, the onboard screen displays AP mode credentials (SSID: `EPD-Gateway-XXXX`, password: `12345678`). Connect to the hotspot and open `http://192.168.4.1` on your phone/browser to configure your local Wi-Fi. Refer to [firmware/README.md](./firmware/README.md) for details.

---

### Step 2: Deploy the Relay Server

The server can run on any LAN device (PC, Linux home server, NAS, Raspberry Pi). It is ultra-lightweight and uses **less than 50MB of RAM**.

#### 1. Prerequisites
- **Python**: Python 3.10 or higher.
- **Font Support** (ensures clean CJK / Chinese rendering):
  - **Debian / Ubuntu / Armbian**:
    ```bash
    sudo apt update && sudo apt install -y fonts-wqy-zenhei
    ```
  - **CentOS / RHEL**:
    ```bash
    sudo yum install -y wqy-zenhei-fonts
    ```
  - **No-Root / Windows / Manual**:
    Drop any `.ttc` or `.ttf` font file into `server/fonts/font.ttc`.

#### 2. Installation & Running

- **Method A: Automated One-Click Start (Linux / macOS)**
  ```bash
  cd server
  ./start.sh
  ```
  `start.sh` automatically checks/creates an isolated `venv`, installs required dependencies, and starts Uvicorn on `0.0.0.0:8000`.

- **Method B: Manual Cross-Platform Launch (Linux / macOS / Windows)**
  ```bash
  cd server

  # Create and activate virtual environment
  python3 -m venv venv
  source venv/bin/activate       # Windows PowerShell: .\venv\Scripts\Activate.ps1
                                 # Windows CMD: venv\Scripts\activate.bat

  # Install dependencies
  pip install -r requirements.txt

  # Start the server
  python main.py
  ```

- **Method C: Linux systemd Service (Background Autostart)**
  Create `/etc/systemd/system/epd-server.service`:
  ```ini
  [Unit]
  Description=EPD Relay Server
  After=network.target

  [Service]
  Type=simple
  User=YOUR_USERNAME
  WorkingDirectory=/path/to/esp32-gateway/server
  ExecStart=/path/to/esp32-gateway/server/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```
  Enable and start:
  ```bash
  sudo systemctl daemon-reload && sudo systemctl enable --now epd-server
  ```

Once started, open the web console in your browser: `http://<SERVER_IP>:8000`.

---

### Step 3: Link & Test

1. Open the ESP32 gateway portal (`http://<GATEWAY_IP>` or `http://epd-gateway.local`).
2. Under **Settings**, set the image pull URL to:
   ```
   http://<SERVER_IP>:8000/screen.bin
   ```
3. Under **Bluetooth E-Paper Management**, click **Scan**, select your ESL device (e.g. `NRF_EPD_XXXX`), and click **Bind**.
4. In the server dashboard (`http://<SERVER_IP>:8000`), enter the gateway address under **System Settings** (e.g., `http://192.168.1.118`).
5. Upload a photo to an album slot or push a memo—your e-paper will refresh immediately!

---

## Instant Push Example (iPhone Shortcuts)

Trigger an instant desk memo card via a simple HTTP GET request without opening any webpage:

```http
GET http://<SERVER_IP>:8000/api/push?title=Meeting+Reminder&text=Code+review+at+3:00+PM&duration_min=60&sender=Phone
```

**cURL Example**:
```bash
curl -X POST http://<SERVER_IP>:8000/api/push \
  -H "Content-Type: application/json" \
  -d '{
    "title": "☕ Coffee Break",
    "text": "Time to stretch and grab a cup of coffee!",
    "duration_min": 30,
    "sender": "Shortcuts"
  }'
```

---

## Roadmap

- [x] **LilyGO T-Display-S3**: Onboard color LCD dashboard with visual network/sync monitoring (precompiled firmware provided).
- [x] **Hema / Hanshow 4.2" BWR ESL**: Native support for SSD1619 controller and v1.8 legacy dot-matrix protocol.
- [ ] **Low-Cost Hardware Porting**: Porting gateway to screenless ESP32-WROOM-32 / ESP32-C3 boards ($2–$3 BOM cost) with dual-blink LED status indicators.
- [ ] **Multi-Screen Sizes**: Templates for 2.13", 2.9", and 7.5" ESL variants.
- [ ] **External Aggregation**: Plugins for Google Calendar, Todoist, and local weather forecasts.

---

## License

The server component is licensed under the [MIT License](./LICENSE). The precompiled firmware is provided free of charge for personal and hobbyist use.
