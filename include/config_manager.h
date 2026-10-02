#pragma once

#include <Arduino.h>
#include <Preferences.h>

struct AppConfig {
    String wifi_ssid;
    String wifi_pass;
    String ble_mac;
    String ble_name;
    String server_url;
    String auth_token;
    String token_header;
    uint32_t refresh_interval; // 分钟
    bool enable_deep_sleep;    // 是否开启深度睡眠
    String last_etag;          // 缓存校验 ETag
    String last_sync_time;     // 上次同步时间
    String last_sync_status;   // 上次同步状态说明
    String screen_model;       // 屏幕型号预设 (如 4.2_bwr, 2.9_bwr 等)
    uint16_t screen_width;     // 像素宽度
    uint16_t screen_height;    // 像素高度
    uint8_t screen_colors;     // 2=黑白, 3=三色(黑白红)
    String mdns_host;          // mDNS 主机名 (如 epd-gateway)
};

class ConfigManager {
public:
    static ConfigManager& getInstance();

    bool begin();
    bool load();
    bool save();
    void resetToDefaults();

    AppConfig config;

private:
    ConfigManager();
    Preferences prefs;
    const char* PREF_NAMESPACE = "epd_gw";
};
