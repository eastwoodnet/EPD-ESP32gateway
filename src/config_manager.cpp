#include "config_manager.h"
#include "config.h"

ConfigManager::ConfigManager() {}

ConfigManager& ConfigManager::getInstance() {
    static ConfigManager instance;
    return instance;
}

bool ConfigManager::begin() {
    return load();
}

bool ConfigManager::load() {
    if (!prefs.begin(PREF_NAMESPACE, false)) {
        Serial.println("[Config] 无法初始化 NVS Preferences");
        resetToDefaults();
        return false;
    }

    config.wifi_ssid = prefs.getString("ssid", "");
    config.wifi_pass = prefs.getString("pass", "");
    config.ble_mac = prefs.getString("ble_mac", "");
    config.ble_name = prefs.getString("ble_name", "");
    config.server_url = prefs.getString("srv_url", "http://192.168.1.100:8000/screen.bin");
    config.auth_token = prefs.getString("token", "");
    config.token_header = prefs.getString("t_hdr", "Authorization");
    config.refresh_interval = prefs.getUInt("interval", DEFAULT_REFRESH_MINUTES);
    config.enable_deep_sleep = prefs.getBool("sleep", false);
    config.last_etag = prefs.getString("etag", "");
    config.last_sync_time = prefs.getString("last_sync", "从未同步");
    config.last_sync_status = prefs.getString("last_stat", "等待首次同步");
    config.screen_model = prefs.getString("sc_model", "4.2_bwr");
    config.screen_width = prefs.getUShort("sc_w", 400);
    config.screen_height = prefs.getUShort("sc_h", 300);
    config.screen_colors = prefs.getUChar("sc_c", 3);
    config.mdns_host = prefs.getString("mdns", "epd-gateway");

    prefs.end();
    Serial.println("[Config] 配置加载成功:");
    Serial.printf("  SSID: %s\n", config.wifi_ssid.c_str());
    Serial.printf("  BLE MAC: %s\n", config.ble_mac.c_str());
    Serial.printf("  Server: %s\n", config.server_url.c_str());
    Serial.printf("  Screen: %s (%dx%d, %d色)\n", config.screen_model.c_str(), config.screen_width, config.screen_height, config.screen_colors);
    Serial.printf("  Interval: %d min\n", config.refresh_interval);
    return true;
}

bool ConfigManager::save() {
    if (!prefs.begin(PREF_NAMESPACE, false)) {
        Serial.println("[Config] 写入 NVS 失败");
        return false;
    }

    prefs.putString("ssid", config.wifi_ssid);
    prefs.putString("pass", config.wifi_pass);
    prefs.putString("ble_mac", config.ble_mac);
    prefs.putString("ble_name", config.ble_name);
    prefs.putString("srv_url", config.server_url);
    prefs.putString("token", config.auth_token);
    prefs.putString("t_hdr", config.token_header);
    prefs.putUInt("interval", config.refresh_interval);
    prefs.putBool("sleep", config.enable_deep_sleep);
    prefs.putString("etag", config.last_etag);
    prefs.putString("last_sync", config.last_sync_time);
    prefs.putString("last_stat", config.last_sync_status);
    prefs.putString("sc_model", config.screen_model);
    prefs.putUShort("sc_w", config.screen_width);
    prefs.putUShort("sc_h", config.screen_height);
    prefs.putUChar("sc_c", config.screen_colors);
    prefs.putString("mdns", config.mdns_host);

    prefs.end();
    Serial.println("[Config] 配置已保存到 NVS");
    return true;
}

void ConfigManager::resetToDefaults() {
    config.wifi_ssid = "";
    config.wifi_pass = "";
    config.ble_mac = "";
    config.ble_name = "";
    config.server_url = "http://192.168.1.100:8000/screen.bin";
    config.auth_token = "";
    config.token_header = "Authorization";
    config.refresh_interval = DEFAULT_REFRESH_MINUTES;
    config.enable_deep_sleep = false;
    config.last_etag = "";
    config.last_sync_time = "从未同步";
    config.last_sync_status = "等待首次同步";
    config.screen_model = "4.2_bwr";
    config.screen_width = 400;
    config.screen_height = 300;
    config.screen_colors = 3;
    config.mdns_host = "epd-gateway";

    if (prefs.begin(PREF_NAMESPACE, false)) {
        prefs.clear();
        prefs.end();
    }
}
