#include "ble_epd_client.h"
#include "config.h"
#include <WiFi.h>
#include <time.h>

BleEpdClient::BleEpdClient() {}

BleEpdClient& BleEpdClient::getInstance() {
    static BleEpdClient instance;
    return instance;
}

void BleEpdClient::begin() {
    NimBLEDevice::init("ESP32-EPD-Gateway");
    NimBLEDevice::setPower(ESP_PWR_LVL_P9); // 最大发射功率
    NimBLEDevice::setMTU(247);
    pBLEScan = NimBLEDevice::getScan();
    pBLEScan->setAdvertisedDeviceCallbacks(new AdvertisedDeviceCallbacks(this));
    pBLEScan->setActiveScan(true);
    pBLEScan->setInterval(100);
    pBLEScan->setWindow(99);
}

void BleEpdClient::AdvertisedDeviceCallbacks::onResult(NimBLEAdvertisedDevice* advertisedDevice) {
    String addr = advertisedDevice->getAddress().toString().c_str();
    String name = advertisedDevice->getName().c_str();
    int rssi = advertisedDevice->getRSSI();

    bool isEpd = false;
    if (advertisedDevice->haveServiceUUID() && 
        advertisedDevice->isAdvertisingService(NimBLEUUID(EPD_SERVICE_UUID))) {
        isEpd = true;
    } else if (name.indexOf("EPD") >= 0 || name.indexOf("epd") >= 0 || name.startsWith("NRF_EPD_")) {
        isEpd = true;
    }

    // 查重并更新
    bool found = false;
    for (auto& dev : parent->scanResults) {
        if (dev.address.equalsIgnoreCase(addr)) {
            dev.rssi = rssi;
            if (name.length() > 0) dev.name = name;
            if (isEpd) dev.isEpd = true;
            found = true;
            break;
        }
    }
    if (!found) {
        parent->scanResults.push_back({name.length() > 0 ? name : "未知设备", addr, rssi, isEpd});
    }
}

void BleEpdClient::startScan(uint32_t durationSec, std::function<void()> onComplete) {
    if (scanning) return;
    scanResults.clear();
    scanning = true;
    scanCompleteCallback = onComplete;

    pBLEScan->start(durationSec, false);
    scanning = false;
    if (scanCompleteCallback) {
        scanCompleteCallback();
    }
}

bool BleEpdClient::isScanning() {
    return scanning;
}

std::vector<DiscoveredDevice> BleEpdClient::getScanResults() {
    return scanResults;
}

static bool connectDevice(NimBLEClient* pClient, const String& macAddress) {
    pClient->setConnectTimeout(8);

    NimBLEScan* pScan = NimBLEDevice::getScan();
    pScan->setActiveScan(true);

    for (int attempt = 1; attempt <= 3; attempt++) {
        Serial.printf("[BLE] 扫描探路 (第 %d/3 次，3 秒)... 目标 MAC: %s\n", attempt, macAddress.c_str());
        NimBLEScanResults results = pScan->start(3, false);

        NimBLEAdvertisedDevice* targetDev = nullptr;
        for (int i = 0; i < results.getCount(); i++) {
            NimBLEAdvertisedDevice dev = results.getDevice(i);
            if (strcasecmp(dev.getAddress().toString().c_str(), macAddress.c_str()) == 0) {
                targetDev = results.getDevice(dev.getAddress());
                break;
            }
        }

        if (targetDev != nullptr) {
            int rssi = targetDev->getRSSI();
            Serial.printf("[BLE] 命中目标墨水屏! RSSI: %d dBm%s，停止扫描并建立连接...\n", 
                          rssi, rssi < -88 ? " (信号偏弱)" : " (信号良好)");
            pScan->stop();
            delay(100);

            bool ok = pClient->connect(targetDev);
            pScan->clearResults();
            if (ok) {
                Serial.println("[BLE] 蓝牙链路建立成功！");
                return true;
            }
            Serial.printf("[BLE] 连接未完成 (错误码: %d)，重试...\n", pClient->getLastError());
            delay(500);
        } else {
            pScan->clearResults();
            if (attempt < 3) delay(400);
        }
    }

    // 2. 备选方案: 直接按地址类型发起连接
    uint8_t primaryType = BLE_ADDR_PUBLIC;
    if (macAddress.length() >= 2) {
        uint8_t firstByte = strtoul(macAddress.substring(0, 2).c_str(), nullptr, 16);
        if ((firstByte & 0xC0) == 0xC0) {
            primaryType = BLE_ADDR_RANDOM;
        }
    }

    NimBLEAddress addr1(macAddress.c_str(), primaryType);
    Serial.printf("[BLE] 尝试直接连接 (地址类型: %s): %s\n", primaryType == BLE_ADDR_RANDOM ? "RANDOM" : "PUBLIC", macAddress.c_str());
    if (pClient->connect(addr1)) {
        return true;
    }

    uint8_t fallbackType = (primaryType == BLE_ADDR_RANDOM) ? BLE_ADDR_PUBLIC : BLE_ADDR_RANDOM;
    NimBLEAddress addr2(macAddress.c_str(), fallbackType);
    Serial.printf("[BLE] 尝试备选类型 (%s): %s\n", fallbackType == BLE_ADDR_RANDOM ? "RANDOM" : "PUBLIC", macAddress.c_str());
    return pClient->connect(addr2);
}

bool BleEpdClient::clearScreen(const String& macAddress) {
    if (macAddress.length() == 0) return false;

    Serial.printf("[BLE] 正在连接清屏设备: %s\n", macAddress.c_str());
    NimBLEClient* pClient = NimBLEDevice::createClient();
    if (pClient == nullptr) return false;
    pClient->setConnectTimeout(8);
    if (!connectDevice(pClient, macAddress)) {
        Serial.println("[BLE] 连接失败");
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    NimBLERemoteService* pSvc = pClient->getService(NimBLEUUID(EPD_SERVICE_UUID));
    if (!pSvc) {
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    NimBLERemoteCharacteristic* pChar = pSvc->getCharacteristic(NimBLEUUID(EPD_CHAR_DATA_UUID));
    if (!pChar) {
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    uint8_t initCmd[1] = { EPD_CMD_INIT };
    if (!pChar->writeValue(initCmd, 1, true) || !pClient->isConnected()) {
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    delay(100);

    uint8_t clearCmd[1] = { EPD_CMD_CLEAR };
    if (!pChar->writeValue(clearCmd, 1, true)) {
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    delay(200);

    pClient->disconnect();
    NimBLEDevice::deleteClient(pClient);
    Serial.println("[BLE] 清屏指令已发送");
    return true;
}

// 辅助函数: 发送单个通道数据
static bool sendChannel(NimBLERemoteCharacteristic* pChar, 
                        const uint8_t* channelData, size_t channelLen, 
                        bool isRedChannel, size_t chunkSize, 
                        uint8_t fwVersion,
                        int startPct, int endPct,
                        std::function<void(int, const String&)> progressCb) {
    size_t totalChunks = (channelLen + chunkSize - 1) / chunkSize;
    uint8_t packet[256];

    for (size_t i = 0; i < totalChunks; i++) {
        size_t offset = i * chunkSize;
        size_t currentChunkSize = ((offset + chunkSize) > channelLen) ? (channelLen - offset) : chunkSize;

        uint8_t flags;
        if (fwVersion >= 0x1A) {
            // 新版固件 (v1.10+ / 0x1A及以上，EPD_service.c 采用位域解析):
            //   bit 0: 0=黑白通道, 1=红色通道
            //   bit 1: 1=首包 (begin, 复位驱动写入指针), 0=后续包
            //   bit 2: 0=原始未压缩点阵, 1=RLE 压缩数据
            flags = (isRedChannel ? 0x01 : 0x00) | ((i == 0) ? 0x02 : 0x00);
        } else {
            // 传统协议 (v1.5 - v1.9，如盒马/汉朔 4.2 寸固件 0x18，SSD16xx/UC81xx 采用高低半字节解析):
            //   高 4 位 (MSB): 0x00=首包 (begin), 0xF0=后续包 (cont)
            //   低 4 位 (LSB): 0x0F=黑白通道 (RAM1), 0x00=红色通道 (RAM2)
            if (!isRedChannel) {
                flags = (i == 0) ? 0x0F : 0xFF;
            } else {
                flags = (i == 0) ? 0x00 : 0xF0;
            }
        }

        packet[0] = EPD_CMD_WRITE_IMAGE;
        packet[1] = flags;
        memcpy(&packet[2], &channelData[offset], currentChunkSize);

        bool ok = pChar->writeValue(packet, currentChunkSize + 2, true);
        if (!ok) {
            delay(50);
            ok = pChar->writeValue(packet, currentChunkSize + 2, true);
        }

        if (!ok) {
            Serial.printf("[BLE] 写入分包 %d (%s) 失败\n", i, isRedChannel ? "Red" : "BW");
            return false;
        }

        delay(8); // 注入传输延时节奏，防止连续大吞吐压垮从机缓冲区

        if (progressCb && (i % 6 == 0 || i == totalChunks - 1)) {
            int pct = startPct + (int)(((float)(i + 1) / totalChunks) * (endPct - startPct));
            progressCb(pct, String("推送") + (isRedChannel ? "红色通道: " : "黑白通道: ") + String(i + 1) + "/" + String(totalChunks));
        }
    }
    return true;
}

bool BleEpdClient::pushImage(const String& macAddress, const uint8_t* data, size_t length,
                            std::function<void(int percent, const String& status)> progressCb,
                            uint8_t colors) {
    if (macAddress.length() == 0 || data == nullptr || length == 0 || (colors >= 3 && length % 2 != 0)) {
        if (progressCb) progressCb(0, "参数错误或图像数据长度无效");
        return false;
    }

    if (progressCb) progressCb(5, "正在连接墨水屏...");
    Serial.printf("[BLE] 连接墨水屏: %s\n", macAddress.c_str());

    NimBLEClient* pClient = NimBLEDevice::createClient();
    if (pClient == nullptr) {
        if (progressCb) progressCb(0, "无法创建蓝牙客户端");
        return false;
    }
    pClient->setConnectTimeout(10);

    if (!connectDevice(pClient, macAddress)) {
        Serial.println("[BLE] 连接超时/失败");
        if (progressCb) progressCb(0, "蓝牙连接失败");
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    // 自动协商 MTU
    delay(100);
    uint16_t mtu = pClient->getMTU();
    Serial.printf("[BLE] 协商 MTU 大小: %d\n", mtu);

    NimBLERemoteService* pSvc = pClient->getService(NimBLEUUID(EPD_SERVICE_UUID));
    if (!pSvc) {
        Serial.println("[BLE] 未找到 EPD 服务");
        if (progressCb) progressCb(0, "未找到墨水屏服务");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    NimBLERemoteCharacteristic* pChar = pSvc->getCharacteristic(NimBLEUUID(EPD_CHAR_DATA_UUID));
    if (!pChar) {
        Serial.println("[BLE] 未找到数据特征");
        if (progressCb) progressCb(0, "未找到数据特征");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    // 1. 发送初始化命令 (EPD_CMD_INIT)
    if (progressCb) progressCb(10, "初始化墨水屏驱动...");
    uint8_t initCmd[1] = { EPD_CMD_INIT };
    if (!pChar->writeValue(initCmd, 1, true) || !pClient->isConnected()) {
        if (progressCb) progressCb(0, "墨水屏初始化失败");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    delay(200);

    // 自动检测固件版本以适配协议标志
    uint8_t fwVersion = 0x18; // 默认采用兼容度最高的标准固件 (0x18)
    NimBLERemoteCharacteristic* pVerChar = pSvc->getCharacteristic(NimBLEUUID(EPD_CHAR_VER_UUID));
    if (pVerChar && pVerChar->canRead()) {
        std::string verVal = pVerChar->readValue();
        if (verVal.length() > 0) {
            fwVersion = (uint8_t)verVal[0];
        }
    }
    Serial.printf("[BLE] 墨水屏固件版本: 0x%02X (%s)\n",
                  fwVersion, fwVersion >= 0x1A ? "新版协议 V1.10+ RLE" : "兼容协议 V1.5-V1.9");

    // 2. 分包发送图像数据
    if (mtu <= 5) {
        if (progressCb) progressCb(0, "蓝牙 MTU 过小");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    size_t chunkSize = mtu - 5;
    if (chunkSize > 240) chunkSize = 240;

    // 双通道 (黑白 + 红色) 判定：
    // 优先使用调用方提供的屏幕颜色数，避免纯靠数据长度猜测出错：
    bool isDualChannel = (colors != 0) ? (colors >= 3) : (length >= 20000 && length % 2 == 0);
    size_t channelLen = isDualChannel ? (length / 2) : length;

    Serial.printf("[BLE] 开始推送点阵: %s, 单通道大小: %d 字节, 分包大小: %d 字节\n",
                  isDualChannel ? "三色 (黑白+红)" : "单色 (黑白)", channelLen, chunkSize);

    // 发送黑白通道
    if (!sendChannel(pChar, data, channelLen, false, chunkSize, fwVersion, 15, isDualChannel ? 55 : 90, progressCb)) {
        if (progressCb) progressCb(0, "黑白通道写入失败");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    // 发送红色通道 (如果有)
    if (isDualChannel) {
        delay(100);
        const uint8_t* redData = &data[channelLen];
        if (!sendChannel(pChar, redData, channelLen, true, chunkSize, fwVersion, 55, 90, progressCb)) {
            if (progressCb) progressCb(0, "红色通道写入失败");
            pClient->disconnect();
            NimBLEDevice::deleteClient(pClient);
            return false;
        }
    }

    // 3. 发送刷新命令 (EPD_CMD_REFRESH)
    if (progressCb) progressCb(95, "触发屏幕刷新...");
    Serial.println("[BLE] 发送刷新指令 (0x05)");
    uint8_t refreshCmd[1] = { EPD_CMD_REFRESH };
    if (!pChar->writeValue(refreshCmd, 1, true)) {
        if (progressCb) progressCb(0, "屏幕刷新指令发送失败");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    delay(300);

    // 4. 断开连接并释放资源
    pClient->disconnect();
    NimBLEDevice::deleteClient(pClient);

    if (progressCb) progressCb(100, "同步并刷新完成！");
    Serial.println("[BLE] 图像推送完成");
    return true;
}

bool BleEpdClient::setCalendarMode(const String& macAddress, uint32_t timestamp, int8_t timezone,
                                   std::function<void(int percent, const String& status)> progressCb) {
    return setDisplayModeAndTime(macAddress, timestamp, timezone, 1, progressCb);
}

bool BleEpdClient::setClockMode(const String& macAddress, uint32_t timestamp, int8_t timezone,
                                std::function<void(int percent, const String& status)> progressCb) {
    return setDisplayModeAndTime(macAddress, timestamp, timezone, 2, progressCb);
}

bool BleEpdClient::setDisplayModeAndTime(const String& macAddress, uint32_t timestamp, int8_t timezone, uint8_t mode,
                                         std::function<void(int percent, const String& status)> progressCb) {
    if (macAddress.length() == 0) return false;

    // 1. 时间校验与主动 NTP 校准 (防止未校准时间导致墨水屏显示 1970 年)
    if (timestamp < 1700000000) {
        time_t now = time(nullptr);
        if (now < 1700000000 && WiFi.status() == WL_CONNECTED) {
            if (progressCb) progressCb(5, "正在校准网络时间...");
            Serial.println("[NTP] 当前本地时间未同步，正在主动校准网络时间...");
            configTime(8 * 3600, 0, "ntp.aliyun.com", "pool.ntp.org", "time.nist.gov");
            unsigned long t0 = millis();
            while (millis() - t0 < 3000) {
                delay(200);
                now = time(nullptr);
                if (now > 1700000000) break;
            }
        }
        if (now > 1700000000) {
            timestamp = (uint32_t)now;
            Serial.printf("[NTP] 时间校准成功，当前时间戳: %u\n", timestamp);
        } else {
            // 兜底时间 2026-10-04 12:00:00 UTC (1791115200)
            timestamp = 1791115200;
            Serial.printf("[NTP] 无法获取网络时间，使用当前安全预设时间戳: %u\n", timestamp);
        }
    }

    if (progressCb) progressCb(10, "正在连接墨水屏...");
    Serial.printf("[BLE] 设置墨水屏模式: %s, 时间戳: %u, 时区: %d\n", mode == 1 ? "日历模式" : "时钟模式", timestamp, timezone);
    NimBLEClient* pClient = NimBLEDevice::createClient();
    if (pClient == nullptr) return false;
    pClient->setConnectTimeout(8);
    if (!connectDevice(pClient, macAddress)) {
        Serial.println("[BLE] 连接失败");
        if (progressCb) progressCb(0, "蓝牙连接失败");
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    NimBLERemoteService* pSvc = pClient->getService(NimBLEUUID(EPD_SERVICE_UUID));
    if (!pSvc) {
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    NimBLERemoteCharacteristic* pChar = pSvc->getCharacteristic(NimBLEUUID(EPD_CHAR_DATA_UUID));
    if (!pChar) {
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }

    // 2. 关键修复 1: 发送初始化命令 (EPD_CMD_INIT)
    // 墨水屏在更新完图片(MODE_PICTURE)后，硬件引脚和驱动均处于深度休眠中。
    // 切换至日历前必须先发送 0x01，唤醒驱动并重新装载引脚配置！
    if (progressCb) progressCb(25, "唤醒并初始化墨水屏驱动...");
    Serial.println("[BLE] 发送驱动初始化指令 (EPD_CMD_INIT: 0x01)...");
    uint8_t initCmd[1] = { EPD_CMD_INIT };
    if (!pChar->writeValue(initCmd, 1, true) || !pClient->isConnected()) {
        if (progressCb) progressCb(0, "墨水屏初始化失败");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    delay(200);

    // 3. 发送时间同步与模式切换命令 (EPD_CMD_SET_TIME: 0x20)
    if (progressCb) progressCb(40, "下发日历模式指令与时间戳...");
    uint8_t packet[7];
    packet[0] = EPD_CMD_SET_TIME; // 0x20
    packet[1] = (timestamp >> 24) & 0xFF;
    packet[2] = (timestamp >> 16) & 0xFF;
    packet[3] = (timestamp >> 8) & 0xFF;
    packet[4] = timestamp & 0xFF;
    packet[5] = timezone; // 8
    packet[6] = mode;     // 1: CALENDAR, 2: CLOCK

    if (!pChar->writeValue(packet, 7, true)) {
        if (progressCb) progressCb(0, "模式与时间指令发送失败");
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
        return false;
    }
    Serial.println("[BLE] 日历/时钟模式指令已发送，墨水屏开始进入后台图形渲染与屏幕刷新");

    // 4. 关键修复 2: 保持蓝牙连接，等待墨水屏执行 DrawGUI 渲染与物理全刷完成 (约18秒)
    // 严禁在 200ms 后立即调用 disconnect！
    // 墨水屏固件在收到 0x20 后，后台 DrawGUI 绘图和物理波形全刷整整需要 15~17 秒 (三色屏更久)。
    // 如果 ESP32 过早断开，墨水屏底层中断会执行 on_disconnect()，
    // 强行将 SPI 引脚 Uninit 并关断电源，导致驱动死锁引发看门狗 WDT 复位，
    // 看门狗复位后墨水屏将以 timestamp=0 (1970年) 重新初始化！
    Serial.println("[BLE] 正在保持蓝牙连接，等待墨水屏完成全屏物理刷新 (安全等待18秒)...");
    for (int i = 0; i < 18; i++) {
        delay(1000);
        if (!pClient->isConnected()) {
            if (progressCb) progressCb(0, "刷新期间蓝牙连接断开");
            NimBLEDevice::deleteClient(pClient);
            return false;
        }
        int pct = 45 + (int)((i + 1) * 3.0f);
        if (progressCb && (i % 3 == 0 || i == 17)) {
            progressCb(pct, String("墨水屏全刷中: ") + String(i + 1) + "/18s");
        }
    }

    // 5. 墨水屏全刷完成且进入安全休眠后，安全断开蓝牙
    pClient->disconnect();
    NimBLEDevice::deleteClient(pClient);
    if (progressCb) progressCb(100, "模式切换与全屏刷新完成！");
    Serial.println("[BLE] 模式切换与全刷已圆满完成");
    return true;
}

bool BleEpdClient::sendTestPattern(const String& macAddress, uint16_t width, uint16_t height, uint8_t colors,
                                   std::function<void(int percent, const String& status)> progressCb) {
    if (width == 0 || height == 0) {
        width = 400; height = 300;
    }
    size_t bytesPerRow = (width + 7) / 8;
    size_t channelSize = bytesPerRow * height;
    bool isDual = (colors >= 3);
    size_t totalSize = isDual ? (channelSize * 2) : channelSize;

    uint8_t* buf = (uint8_t*)malloc(totalSize);
    if (!buf) {
        if (progressCb) progressCb(0, "内存不足，无法生成测试图案");
        return false;
    }

    uint8_t* bw = buf;
    uint8_t* red = isDual ? (buf + channelSize) : nullptr;

    memset(bw, 0xFF, channelSize);
    if (isDual && red) memset(red, 0xFF, channelSize);

    // 绘制外边框与网格
    for (int y = 0; y < height; y++) {
        for (int xByte = 0; xByte < bytesPerRow; xByte++) {
            int idx = y * bytesPerRow + xByte;
            // 上下外边框
            if (y < 4 || y >= height - 4) {
                bw[idx] = 0x00;
            }
            // 左右外边框
            if (xByte == 0) bw[idx] &= 0x0F;
            if (xByte == bytesPerRow - 1) bw[idx] &= 0xF0;

            // 网格横线
            if (y % 25 == 0 && (!isDual || y < height / 2)) {
                bw[idx] = 0x55;
            }
        }
    }

    // 若三色屏幕，绘制红色高亮横幅
    if (isDual && red) {
        int rStartY = height * 3 / 5;
        int rEndY = height * 9 / 10;
        int rStartXByte = bytesPerRow / 10;
        int rEndXByte = bytesPerRow * 9 / 10;
        for (int y = rStartY; y < rEndY; y++) {
            for (int xByte = rStartXByte; xByte < rEndXByte; xByte++) {
                int idx = y * bytesPerRow + xByte;
                red[idx] = 0x00; // 红色显色
            }
        }
    }

    bool res = pushImage(macAddress, buf, totalSize, progressCb, colors);
    free(buf);
    return res;
}
