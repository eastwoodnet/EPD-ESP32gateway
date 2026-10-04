#pragma once

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <vector>
#include <functional>

struct DiscoveredDevice {
    String name;
    String address;
    int rssi;
    bool isEpd;
};

class BleEpdClient {
public:
    static BleEpdClient& getInstance();

    void begin();
    
    // BLE 扫描周边墨水屏
    void startScan(uint32_t durationSec = 5, std::function<void()> onComplete = nullptr);
    bool isScanning();
    std::vector<DiscoveredDevice> getScanResults();

    // 图像与控制传输 (自动支持单色或三色数据)
    bool pushImage(const String& macAddress, const uint8_t* data, size_t length, 
                   std::function<void(int percent, const String& status)> progressCb = nullptr);
    bool clearScreen(const String& macAddress);
    
    // 切换墨水屏显示模式并同步时间 (1=日历模式, 2=时钟模式)
    bool setCalendarMode(const String& macAddress, uint32_t timestamp = 0, int8_t timezone = 8,
                         std::function<void(int percent, const String& status)> progressCb = nullptr);
    bool setClockMode(const String& macAddress, uint32_t timestamp = 0, int8_t timezone = 8,
                      std::function<void(int percent, const String& status)> progressCb = nullptr);
    bool setDisplayModeAndTime(const String& macAddress, uint32_t timestamp, int8_t timezone, uint8_t mode,
                               std::function<void(int percent, const String& status)> progressCb = nullptr);

    // 发送墨水屏内置测试图案 (按配置的尺寸与颜色自适应生成)
    bool sendTestPattern(const String& macAddress, uint16_t width = 400, uint16_t height = 300, uint8_t colors = 3,
                         std::function<void(int percent, const String& status)> progressCb = nullptr);

private:
    BleEpdClient();
    NimBLEScan* pBLEScan = nullptr;
    std::vector<DiscoveredDevice> scanResults;
    bool scanning = false;
    std::function<void()> scanCompleteCallback = nullptr;

    class AdvertisedDeviceCallbacks : public NimBLEAdvertisedDeviceCallbacks {
    public:
        AdvertisedDeviceCallbacks(BleEpdClient* parent) : parent(parent) {}
        void onResult(NimBLEAdvertisedDevice* advertisedDevice) override;
    private:
        BleEpdClient* parent;
    };

    friend class AdvertisedDeviceCallbacks;
};
