#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <time.h>
#include <esp_wifi.h>
#include "config.h"
#include "config_manager.h"
#include "ble_epd_client.h"
#include "http_puller.h"
#include "web_portal.h"
#include "display_ui.h"

static bool isApMode = false;
static bool syncRequested = false;
static bool syncInProgress = false;
static unsigned long lastSyncMillis = 0;
static unsigned long lastUiUpdateMillis = 0;

#ifdef PIN_BUTTON_1
static unsigned long btn1PressTime = 0;
static bool btn1Pressed = false;
static bool btn1LongHandled = false;
#endif

// 前置声明
void startApMode();
bool startStaMode();
void performSync();
void handleSerialCommands();

int getRemainingSec() {
    AppConfig& cfg = ConfigManager::getInstance().config;
    if (cfg.refresh_interval == 0) return -1;
    unsigned long elapsedSec = (millis() - lastSyncMillis) / 1000;
    unsigned long totalSec = cfg.refresh_interval * 60;
    return (totalSec > elapsedSec) ? (int)(totalSec - elapsedSec) : 0;
}

void startApMode() {
    isApMode = true;
    WiFi.disconnect(true);
    WiFi.mode(WIFI_AP);

    String mac = WiFi.macAddress();
    mac.replace(":", "");
    String suffix = mac.substring(mac.length() > 4 ? mac.length() - 4 : 0);
    String apSsid = String(DEFAULT_AP_SSID_PREFIX) + suffix;

    WiFi.softAP(apSsid.c_str(), DEFAULT_AP_PASS);
    IPAddress apIp = WiFi.softAPIP();

    Serial.println("\n==========================================");
    Serial.printf("[WiFi] 启动 AP 配网热点: %s, 密码: %s\n", apSsid.c_str(), DEFAULT_AP_PASS);
    Serial.printf("[WiFi] Web 管理界面: http://%s\n", apIp.toString().c_str());
    Serial.println("==========================================\n");

    DisplayUI::getInstance().showApMode(apSsid, DEFAULT_AP_PASS, apIp.toString());
    WebPortal::getInstance().begin(true);
}

bool startStaMode() {
    AppConfig& cfg = ConfigManager::getInstance().config;
    if (cfg.wifi_ssid.length() == 0) {
        Serial.println("[WiFi] 未配置 WiFi SSID，转入 AP 模式");
        return false;
    }

    WiFi.disconnect(true);
    delay(100);
    WiFi.mode(WIFI_STA);

    const char* passPtr = (cfg.wifi_pass.length() > 0) ? cfg.wifi_pass.c_str() : nullptr;
    WiFi.begin(cfg.wifi_ssid.c_str(), passPtr);

    // 针对隐藏 SSID / 开放网络优化：启用全信道主动探测
    wifi_config_t conf;
    if (esp_wifi_get_config(WIFI_IF_STA, &conf) == ESP_OK) {
        conf.sta.scan_method = WIFI_ALL_CHANNEL_SCAN; // 全信道探测隐藏 SSID
        conf.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
        if (!passPtr || passPtr[0] == '\0') {
            conf.sta.threshold.authmode = WIFI_AUTH_OPEN;
        }
        esp_wifi_set_config(WIFI_IF_STA, &conf);
    }

    Serial.printf("[WiFi] 正在连接: %s (模式: %s) ...\n", 
                  cfg.wifi_ssid.c_str(), passPtr ? "加密网络" : "开放/无密码");
    DisplayUI::getInstance().showConnecting(cfg.wifi_ssid);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start < 15000)) {
        delay(200);

        #ifdef PIN_BUTTON_1
        if (digitalRead(PIN_BUTTON_1) == LOW) {
            Serial.println("[BTN1] 按键中断连接，进入 AP 模式");
            return false;
        }
        #endif
    }

    if (WiFi.status() == WL_CONNECTED) {
        isApMode = false;
        Serial.println("\n[WiFi] 连接成功！");
        Serial.printf("[WiFi] IP 地址: %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[WiFi] Web 界面: http://%s\n", WiFi.localIP().toString().c_str());

        // 启动局域网免记 IP 的 mDNS 服务 (http://epd-gateway.local)
        if (MDNS.begin(cfg.mdns_host.c_str())) {
            Serial.printf("[mDNS] 局域网免记 IP 域名已启动: http://%s.local\n", cfg.mdns_host.c_str());
            MDNS.addService("http", "tcp", 80);
        }

        // 启动 NTP 网络时间自动同步 (东八区北京时间)
        configTime(8 * 3600, 0, "ntp.aliyun.com", "pool.ntp.org", "time.nist.gov");

        String displayName = cfg.ble_name.length() > 0 ? cfg.ble_name : 
                            (cfg.ble_mac.length() > 0 ? cfg.ble_mac : "未绑定");
        DisplayUI::getInstance().showDashboard(WiFi.localIP().toString(), displayName, cfg.last_sync_status, getRemainingSec());

        WebPortal::getInstance().begin(false);
        return true;
    }

    Serial.println("[WiFi] 连接超时，转入 AP 模式");
    return false;
}

void performSync() {
    if (syncInProgress) return;
    syncInProgress = true;

    AppConfig& cfg = ConfigManager::getInstance().config;
    Serial.println("\n------------------------------------------");
    Serial.println("[Sync] 开始执行墨水屏同步任务...");

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[Sync] WiFi 未连接，跳过同步");
        cfg.last_sync_status = "WiFi未连接";
        ConfigManager::getInstance().save();
        syncInProgress = false;
        return;
    }

    if (cfg.server_url.length() == 0) {
        Serial.println("[Sync] 未配置 HTTP 图片服务器 URL");
        cfg.last_sync_status = "未配置图片URL";
        ConfigManager::getInstance().save();
        DisplayUI::getInstance().showToast("未配置图片URL!", 0xFD20);
        delay(1200);
        syncInProgress = false;
        return;
    }

    // 1. HTTP 拉取
    DisplayUI::getInstance().showProgress(10, "正在拉取 HTTP 图片数据...");
    HttpPullResponse resp = HttpPuller::fetchImage(cfg.server_url, cfg.auth_token, cfg.token_header, cfg.last_etag);

    if (resp.result == PULL_NOT_MODIFIED) {
        Serial.println("[Sync] 图像数据未改变 (304 Not Modified)");
        cfg.last_sync_status = "数据未改变 (304)";
        ConfigManager::getInstance().save();
        DisplayUI::getInstance().showProgress(100, "画面未变 (304 跳过)");
        delay(1000);
    } else if (resp.result == PULL_SUCCESS) {
        Serial.printf("[Sync] HTTP 下载成功，数据大小: %d 字节\n", resp.length);

        if (cfg.ble_mac.length() == 0) {
            Serial.println("[Sync] 未绑定墨水屏 BLE MAC 地址");
            cfg.last_sync_status = "未绑定墨水屏设备";
            ConfigManager::getInstance().save();
            DisplayUI::getInstance().showToast("未绑定墨水屏设备!", 0xF800);
            delay(1200);
        } else {
            DisplayUI::getInstance().showProgress(30, "已下载图片，连接墨水屏...");
            bool ok = BleEpdClient::getInstance().pushImage(cfg.ble_mac, resp.data, resp.length, [](int pct, const String& st) {
                DisplayUI::getInstance().showProgress(pct, st);
            }, cfg.screen_colors);

            if (ok) {
                Serial.println("[Sync] 墨水屏推送与刷新指令执行成功！");
                cfg.last_etag = resp.newEtag;
                cfg.last_sync_status = "同步成功";
                ConfigManager::getInstance().save();
                DisplayUI::getInstance().showProgress(100, "墨水屏刷新成功！");
                delay(1200);
            } else {
                Serial.println("[Sync] 墨水屏推送失败");
                cfg.last_sync_status = "蓝牙推送失败";
                ConfigManager::getInstance().save();
                DisplayUI::getInstance().showProgress(0, "蓝牙推送失败");
                delay(1200);
            }
        }
        HttpPuller::freeResponse(resp);
    } else {
        Serial.printf("[Sync] HTTP 拉取错误: %s\n", resp.errorMsg.c_str());
        cfg.last_sync_status = resp.errorMsg;
        ConfigManager::getInstance().save();
        DisplayUI::getInstance().showProgress(0, resp.errorMsg);
        HttpPuller::freeResponse(resp);
        delay(1500);
    }

    lastSyncMillis = millis();
    syncInProgress = false;
    Serial.println("[Sync] 同步任务结束");
    Serial.println("------------------------------------------\n");

    // 更新 Dashboard
    String displayName = cfg.ble_name.length() > 0 ? cfg.ble_name : 
                        (cfg.ble_mac.length() > 0 ? cfg.ble_mac : "未绑定");
    DisplayUI::getInstance().showDashboard(WiFi.localIP().toString(), displayName, cfg.last_sync_status, getRemainingSec());

    // 检查深度睡眠配置
    if (!isApMode && cfg.enable_deep_sleep && cfg.refresh_interval > 0) {
        Serial.printf("[Power] 进入 Deep Sleep %d 分钟...\n", cfg.refresh_interval);
        DisplayUI::getInstance().showToast("进入睡眠模式...", 0x07E0);
        delay(1500);
        esp_sleep_enable_timer_wakeup((uint64_t)cfg.refresh_interval * 60ULL * 1000000ULL);
        #ifdef PIN_BUTTON_1
        #if SOC_PM_SUPPORT_EXT0_WAKEUP
        esp_sleep_enable_ext0_wakeup((gpio_num_t)PIN_BUTTON_1, 0); // 允许按键唤醒 (ESP32 / ESP32-S3)
        #elif SOC_GPIO_SUPPORT_DEEP_SLEEP_WAKEUP
        esp_deep_sleep_enable_gpio_wakeup(1ULL << PIN_BUTTON_1, ESP_GPIO_WAKEUP_GPIO_LOW); // 允许按键唤醒 (ESP32-C3)
        #endif
        #endif
        esp_deep_sleep_start();
    }
}

void handleSerialCommands() {
    if (!Serial.available()) return;
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;

    Serial.printf("\n[CMD] 收到串口指令: '%s'\n", cmd.c_str());

    if (cmd == "help" || cmd == "?") {
        Serial.println("可用串口指令:");
        Serial.println("  scan                      - 扫描周围蓝牙墨水屏");
        Serial.println("  bind <MAC> [NAME]         - 绑定指定墨水屏");
        Serial.println("  calendar                  - 切换墨水屏至日历模式 (显示农历、节气与月历)");
        Serial.println("  clock                     - 切换墨水屏至时钟模式");
        Serial.println("  test                      - 向墨水屏发送当前规格内置测试图案");
        Serial.println("  clear                     - 向墨水屏发送全白清屏指令");
        Serial.println("  screen <MODEL>            - 设置屏幕规格 (4.2_bwr, 2.9_bwr, 2.13_bwr, 7.5_bwr 等)");
        Serial.println("  sync                      - 立即触发一次拉取与同步");
        Serial.println("  wifi <SSID> <PASSWORD>    - 配置并连接 WiFi");
        Serial.println("  ap                        - 切换至 AP 配网模式");
        Serial.println("  status                    - 查看当前配置与运行状态");
        Serial.println("  reboot                    - 重启设备");
    } else if (cmd == "scan") {
        Serial.println("[BLE] 正在扫描墨水屏 (5秒)...");
        DisplayUI::getInstance().showToast("正在扫描BLE...", 0x067F);
        BleEpdClient::getInstance().startScan(5, []() {
            auto list = BleEpdClient::getInstance().getScanResults();
            Serial.printf("[BLE] 扫描完成，共找到 %d 个设备:\n", list.size());
            for (const auto& d : list) {
                Serial.printf("  %s [%s] RSSI:%d %s\n", 
                              d.name.c_str(), d.address.c_str(), d.rssi, d.isEpd ? "<-- [墨水屏]" : "");
            }
        });
    } else if (cmd.startsWith("bind ")) {
        int sp1 = cmd.indexOf(' ');
        int sp2 = cmd.indexOf(' ', sp1 + 1);
        String mac = (sp2 > 0) ? cmd.substring(sp1 + 1, sp2) : cmd.substring(sp1 + 1);
        String name = (sp2 > 0) ? cmd.substring(sp2 + 1) : "EPD-Screen";
        mac.trim();
        name.trim();
        AppConfig& cfg = ConfigManager::getInstance().config;
        cfg.ble_mac = mac;
        cfg.ble_name = name;
        ConfigManager::getInstance().save();
        Serial.printf("[Config] 已绑定墨水屏: %s (%s)\n", name.c_str(), mac.c_str());
        DisplayUI::getInstance().showToast("已绑定: " + name, 0x07E0);
    } else if (cmd == "calendar" || cmd == "cal") {
        AppConfig& cfg = ConfigManager::getInstance().config;
        if (cfg.ble_mac.length() == 0) {
            Serial.println("[Error] 未绑定墨水屏，请先执行 bind <MAC>");
        } else {
            Serial.printf("[BLE] 开始向 %s 切换至日历模式 (农历/节气)...\n", cfg.ble_mac.c_str());
            DisplayUI::getInstance().showToast("切换至日历模式...", 0x0596);
            if (BleEpdClient::getInstance().setCalendarMode(cfg.ble_mac, 0, 8, [](int pct, const String& msg) {
                DisplayUI::getInstance().showProgress(pct, msg);
            })) {
                cfg.last_sync_status = "已切至日历模式";
                ConfigManager::getInstance().save();
                Serial.println("[BLE] 墨水屏日历模式切换成功！");
            } else {
                Serial.println("[BLE] 墨水屏日历模式切换失败");
            }
        }
    } else if (cmd == "clock") {
        AppConfig& cfg = ConfigManager::getInstance().config;
        if (cfg.ble_mac.length() == 0) {
            Serial.println("[Error] 未绑定墨水屏，请先执行 bind <MAC>");
        } else {
            Serial.printf("[BLE] 开始向 %s 切换至时钟模式...\n", cfg.ble_mac.c_str());
            DisplayUI::getInstance().showToast("切换至时钟模式...", 0x0284);
            if (BleEpdClient::getInstance().setClockMode(cfg.ble_mac, 0, 8, [](int pct, const String& msg) {
                DisplayUI::getInstance().showProgress(pct, msg);
            })) {
                cfg.last_sync_status = "已切至时钟模式";
                ConfigManager::getInstance().save();
                Serial.println("[BLE] 墨水屏时钟模式切换成功！");
            } else {
                Serial.println("[BLE] 墨水屏时钟模式切换失败");
            }
        }
    } else if (cmd == "test") {
        AppConfig& cfg = ConfigManager::getInstance().config;
        if (cfg.ble_mac.length() == 0) {
            Serial.println("[Error] 未绑定墨水屏，请先执行 bind <MAC>");
        } else {
            Serial.printf("[BLE] 开始向 %s 发送测试图案 (%dx%d, %d色)...\n", 
                          cfg.ble_mac.c_str(), cfg.screen_width, cfg.screen_height, cfg.screen_colors);
            BleEpdClient::getInstance().sendTestPattern(cfg.ble_mac, cfg.screen_width, cfg.screen_height, cfg.screen_colors, [](int pct, const String& st) {
                DisplayUI::getInstance().showProgress(pct, st);
                Serial.printf("[TestPattern %d%%] %s\n", pct, st.c_str());
            });
        }
    } else if (cmd == "clear") {
        AppConfig& cfg = ConfigManager::getInstance().config;
        if (cfg.ble_mac.length() == 0) {
            Serial.println("[Error] 未绑定墨水屏，请先执行 bind <MAC>");
        } else {
            Serial.printf("[BLE] 正在向 %s 发送清屏指令...\n", cfg.ble_mac.c_str());
            BleEpdClient::getInstance().clearScreen(cfg.ble_mac);
        }
    } else if (cmd.startsWith("screen ")) {
        String model = cmd.substring(7);
        model.trim();
        AppConfig& cfg = ConfigManager::getInstance().config;
        cfg.screen_model = model;
        if (model == "4.2_bwr") { cfg.screen_width = 400; cfg.screen_height = 300; cfg.screen_colors = 3; }
        else if (model == "4.2_bw") { cfg.screen_width = 400; cfg.screen_height = 300; cfg.screen_colors = 2; }
        else if (model == "2.9_bwr") { cfg.screen_width = 296; cfg.screen_height = 128; cfg.screen_colors = 3; }
        else if (model == "2.9_bw") { cfg.screen_width = 296; cfg.screen_height = 128; cfg.screen_colors = 2; }
        else if (model == "2.13_bwr") { cfg.screen_width = 250; cfg.screen_height = 122; cfg.screen_colors = 3; }
        else if (model == "2.13_bw") { cfg.screen_width = 250; cfg.screen_height = 122; cfg.screen_colors = 2; }
        else if (model == "5.83_bwr") { cfg.screen_width = 648; cfg.screen_height = 480; cfg.screen_colors = 3; }
        else if (model == "7.5_bwr") { cfg.screen_width = 800; cfg.screen_height = 480; cfg.screen_colors = 3; }
        else if (model == "7.5_bw") { cfg.screen_width = 800; cfg.screen_height = 480; cfg.screen_colors = 2; }
        ConfigManager::getInstance().save();
        Serial.printf("[Config] 已更新屏幕规格: %s (%dx%d, %d色)\n", 
                      cfg.screen_model.c_str(), cfg.screen_width, cfg.screen_height, cfg.screen_colors);
    } else if (cmd == "sync") {
        syncRequested = true;
    } else if (cmd.startsWith("wifi ")) {
        String args = cmd.substring(5);
        args.trim();
        int sp = args.indexOf(' ');
        String ssid = (sp > 0) ? args.substring(0, sp) : args;
        String pass = (sp > 0) ? args.substring(sp + 1) : "";
        ssid.trim(); pass.trim();
        if (ssid.length() > 0) {
            AppConfig& cfg = ConfigManager::getInstance().config;
            cfg.wifi_ssid = ssid;
            cfg.wifi_pass = pass;
            ConfigManager::getInstance().save();
            Serial.printf("[Config] 已保存 WiFi: %s (密码: %s)，正在连接...\n", 
                          ssid.c_str(), pass.length() > 0 ? "已配置" : "无密码/开放网络");
            if (!startStaMode()) startApMode();
        } else {
            Serial.println("格式: wifi <SSID> [PASSWORD] (无密码则不填密码)");
        }
    } else if (cmd == "ap") {
        startApMode();
    } else if (cmd == "status") {
        AppConfig& cfg = ConfigManager::getInstance().config;
        time_t now = time(nullptr);
        struct tm ti;
        localtime_r(&now, &ti);
        char timeBuf[32];
        strftime(timeBuf, sizeof(timeBuf), "%Y-%m-%d %H:%M:%S", &ti);

        Serial.printf("当前状态:\n  系统时间: %s (ts=%u%s)\n  WiFi: %s (%s)\n  IP: %s (模式: %s)\n  mDNS: http://%s.local\n  BLE 设备: %s (%s)\n  屏幕规格: %s (%dx%d, %d色)\n  Server: %s\n  Interval: %d min\n  Last Status: %s\n",
                      timeBuf, (uint32_t)now, now > 1700000000 ? ", NTP已校准" : ", 未校准",
                      cfg.wifi_ssid.c_str(), WiFi.isConnected() ? "已连接" : "未连接",
                      isApMode ? WiFi.softAPIP().toString().c_str() : WiFi.localIP().toString().c_str(),
                      isApMode ? "AP" : "STA",
                      cfg.mdns_host.c_str(),
                      cfg.ble_name.c_str(), cfg.ble_mac.c_str(),
                      cfg.screen_model.c_str(), cfg.screen_width, cfg.screen_height, cfg.screen_colors,
                      cfg.server_url.c_str(), cfg.refresh_interval, cfg.last_sync_status.c_str());
    } else if (cmd == "reboot") {
        Serial.println("设备即将重启...");
        delay(500);
        ESP.restart();
    } else {
        Serial.println("未知指令，输入 help 或 ? 查看帮助");
    }
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n\n>>> ESP32 墨水屏网关系统启动 <<<");

    #ifdef PIN_BUTTON_1
    pinMode(PIN_BUTTON_1, INPUT_PULLUP);
    #endif

    // 初始化核心模块
    ConfigManager::getInstance().begin();
    ConfigManager::getInstance().load();
    DisplayUI::getInstance().begin();
    BleEpdClient::getInstance().begin();

    // 注册 Web 界面远程触发同步回调
    WebPortal::getInstance().setTriggerCallback([]() {
        Serial.println("[Web] 收到网页手动触发刷新请求");
        syncRequested = true;
    });

    // 联网流程
    if (!startStaMode()) {
        startApMode();
    } else {
        // 联网成功后，首次启动自动执行一次拉取
        syncRequested = true;
    }

    lastSyncMillis = millis();
}

void loop() {
    // 1. 处理 WebServer 客户端请求
    WebPortal::getInstance().handleClient();

    // 2. 处理串口调试控制指令
    handleSerialCommands();

    // 3. 处理实体按键 (GPIO 0)
    #ifdef PIN_BUTTON_1
    int btnState = digitalRead(PIN_BUTTON_1);
    if (btnState == LOW) {
        if (!btn1Pressed) {
            btn1Pressed = true;
            btn1PressTime = millis();
            btn1LongHandled = false;
        } else if (!btn1LongHandled && (millis() - btn1PressTime >= 3000)) {
            // 长按 3 秒：切换到 AP 配网模式
            btn1LongHandled = true;
            Serial.println("[BTN1] 检测到长按 3 秒，强制进入 AP 配网模式！");
            DisplayUI::getInstance().showToast("进入 AP 配网模式...", 0xFD20);
            delay(1000);
            startApMode();
        }
    } else {
        if (btn1Pressed) {
            if (!btn1LongHandled && (millis() - btn1PressTime >= 50)) {
                // 短按：立即触发一次同步
                Serial.println("[BTN1] 检测到短按，立即触发同步！");
                DisplayUI::getInstance().showToast("手动触发同步...", 0x07E0);
                delay(500);
                syncRequested = true;
            }
            btn1Pressed = false;
            btn1LongHandled = false;
        }
    }
    #endif

    // 4. 执行同步任务 (若收到按键或网页请求)
    if (syncRequested && !syncInProgress) {
        syncRequested = false;
        performSync();
    }

    // 5. 定时拉取检查 (STA 模式下根据 refresh_interval 自动同步)
    if (!isApMode && !syncInProgress) {
        AppConfig& cfg = ConfigManager::getInstance().config;
        if (cfg.refresh_interval > 0) {
            unsigned long intervalMillis = (unsigned long)cfg.refresh_interval * 60UL * 1000UL;
            if (millis() - lastSyncMillis >= intervalMillis) {
                Serial.println("[Timer] 定时器到期，自动触发刷新任务");
                performSync();
            }
        }
    }

    // 6. 定期刷新屏幕 Dashboard 倒计时 (每秒 1 次)
    if (!isApMode && !syncInProgress && (millis() - lastUiUpdateMillis >= 1000)) {
        lastUiUpdateMillis = millis();
        AppConfig& cfg = ConfigManager::getInstance().config;
        String displayName = cfg.ble_name.length() > 0 ? cfg.ble_name : 
                            (cfg.ble_mac.length() > 0 ? cfg.ble_mac : "未绑定");
        DisplayUI::getInstance().showDashboard(WiFi.localIP().toString(), displayName, cfg.last_sync_status, getRemainingSec());
    }

    delay(10);
}
