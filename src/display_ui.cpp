#include "display_ui.h"

#if ENABLE_T_DISPLAY_S3
#include <TFT_eSPI.h>

static TFT_eSPI tft = TFT_eSPI();

DisplayUI::DisplayUI() {}

DisplayUI& DisplayUI::getInstance() {
    static DisplayUI instance;
    return instance;
}

void DisplayUI::begin() {
    if (initialized) return;

    pinMode(PIN_LCD_POWER, OUTPUT);
    digitalWrite(PIN_LCD_POWER, HIGH);
    delay(50);

    tft.init();
    tft.setRotation(1); // 320x170 横屏
    tft.fillScreen(TFT_BLACK);
    
    #ifdef TFT_BL
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);
    #endif

    initialized = true;
    showBoot();
}

void DisplayUI::showBoot() {
    if (!initialized) return;
    tft.fillScreen(0x0821); // 深蓝灰背景
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, 0x0821);
    tft.drawString("ESP32 EPD Gateway", 160, 50, 4);

    tft.setTextColor(0x067F, 0x0821); // 亮蓝
    tft.drawString("BLE 4.2\" E-Paper Controller", 160, 85, 2);

    tft.setTextColor(0x9CD3, 0x0821); // 浅灰
    tft.drawString("Initializing system...", 160, 125, 2);
}

void DisplayUI::showConnecting(const String& ssid) {
    if (!initialized) return;
    tft.fillScreen(0x0821);
    
    // 标题条
    tft.fillRect(0, 0, 320, 30, 0x18C3);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(TFT_WHITE, 0x18C3);
    tft.drawString("  WiFi Connecting...", 10, 15, 2);

    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0x067F, 0x0821);
    tft.drawString("Connecting to SSID:", 160, 65, 2);

    tft.setTextColor(TFT_WHITE, 0x0821);
    tft.drawString(ssid, 160, 95, 4);

    tft.setTextColor(0x9CD3, 0x0821);
    tft.drawString("Please wait or hold BTN1 to AP mode", 160, 140, 2);
}

void DisplayUI::showApMode(const String& apSsid, const String& apPass, const String& apIp) {
    if (!initialized) return;
    tft.fillScreen(0x0821);

    // 顶部橙黄色告警/热点标题
    tft.fillRect(0, 0, 320, 28, 0xD4A0);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(TFT_BLACK, 0xD4A0);
    tft.drawString("  [AP 配网模式] Hotspot Mode", 10, 14, 2);

    tft.setTextColor(0x9CD3, 0x0821);
    tft.drawString("WiFi 热点:", 20, 50, 2);
    tft.setTextColor(TFT_WHITE, 0x0821);
    tft.drawString(apSsid, 110, 50, 2);

    tft.setTextColor(0x9CD3, 0x0821);
    tft.drawString("热点密码:", 20, 75, 2);
    tft.setTextColor(TFT_WHITE, 0x0821);
    tft.drawString(apPass, 110, 75, 2);

    tft.setTextColor(0x9CD3, 0x0821);
    tft.drawString("配置网址:", 20, 100, 2);
    tft.setTextColor(0x07E0, 0x0821); // 亮绿色
    tft.drawString(String("http://") + apIp, 110, 100, 2);

    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xFD20, 0x0821); // 橙色提示
    tft.drawString("手机连接上述WiFi后浏览器打开网址配网", 160, 145, 2);
}

void DisplayUI::showDashboard(const String& ip, const String& epdName, const String& status, int nextSyncSec) {
    if (!initialized) return;
    tft.fillScreen(0x0000); // 黑色底

    // 顶部状态栏
    tft.fillRect(0, 0, 320, 26, 0x18E3);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(TFT_WHITE, 0x18E3);
    tft.drawString(" EPD Gateway", 8, 13, 2);

    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(0x07E0, 0x18E3);
    tft.drawString(ip.length() > 0 ? (String("IP: ") + ip) : "No IP", 312, 13, 2);

    // 中部卡片区域
    tft.setTextDatum(ML_DATUM);

    // 绑定墨水屏设备
    tft.setTextColor(0x9CD3, 0x0000);
    tft.drawString("墨水屏:", 16, 45, 2);
    if (epdName.length() > 0 && epdName != "未绑定") {
        tft.setTextColor(0x067F, 0x0000); // 蓝色
        tft.drawString(epdName, 80, 45, 2);
    } else {
        tft.setTextColor(0xF800, 0x0000); // 红色未绑定
        tft.drawString("未绑定 (请进网页配对)", 80, 45, 2);
    }

    // 状态
    tft.setTextColor(0x9CD3, 0x0000);
    tft.drawString("状态:", 16, 75, 2);
    tft.setTextColor(TFT_WHITE, 0x0000);
    tft.drawString(status.length() > 0 ? status : "就绪", 80, 75, 2);

    // 下次刷新倒计时
    tft.setTextColor(0x9CD3, 0x0000);
    tft.drawString("倒计时:", 16, 105, 2);
    tft.setTextColor(0xFD20, 0x0000);
    if (nextSyncSec > 0) {
        int m = nextSyncSec / 60;
        int s = nextSyncSec % 60;
        char buf[32];
        snprintf(buf, sizeof(buf), "%d 分 %02d 秒 后自动拉取", m, s);
        tft.drawString(buf, 80, 105, 2);
    } else if (nextSyncSec == 0) {
        tft.drawString("正在执行拉取同步...", 80, 105, 2);
    } else {
        tft.drawString("定时休眠/关闭", 80, 105, 2);
    }

    // 底部控制提示栏
    tft.fillRect(0, 142, 320, 28, 0x10A2);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0x9CD3, 0x10A2);
    tft.drawString("短按BTN1: 立即同步 | 长按: AP配网", 160, 156, 2);
}

void DisplayUI::showProgress(int percent, const String& message) {
    if (!initialized) return;

    // 清理进度条区域 (y: 120 ~ 140)
    int barX = 20;
    int barY = 125;
    int barW = 280;
    int barH = 12;

    tft.fillRect(0, 100, 320, 42, 0x0000);

    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(0x067F, 0x0000);
    tft.drawString(message, barX, barY - 12, 2);

    tft.drawRect(barX, barY, barW, barH, TFT_WHITE);
    int fillW = (barW - 4) * percent / 100;
    if (fillW > 0) {
        tft.fillRect(barX + 2, barY + 2, fillW, barH - 4, 0x07E0);
    }
}

void DisplayUI::showToast(const String& msg, uint16_t color) {
    if (!initialized) return;
    tft.fillRect(20, 55, 280, 50, 0x2124);
    tft.drawRect(20, 55, 280, 50, color);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(color, 0x2124);
    tft.drawString(msg, 160, 80, 2);
}

#else

// 纯 ESP32 裸板无屏幕实现 (宏 ENABLE_T_DISPLAY_S3=0)
DisplayUI::DisplayUI() {}
DisplayUI& DisplayUI::getInstance() {
    static DisplayUI instance;
    return instance;
}
void DisplayUI::begin() {}
void DisplayUI::showBoot() { Serial.println("[UI] System Initializing..."); }
void DisplayUI::showConnecting(const String& ssid) { Serial.printf("[UI] Connecting to WiFi: %s\n", ssid.c_str()); }
void DisplayUI::showApMode(const String& s, const String& p, const String& ip) { 
    Serial.printf("[UI] AP Mode: %s, Pass: %s, Web: http://%s\n", s.c_str(), p.c_str(), ip.c_str()); 
}
void DisplayUI::showDashboard(const String& ip, const String& epd, const String& st, int nextSec) {
    Serial.printf("[UI] IP: %s, EPD: %s, Status: %s, NextSec: %d\n", ip.c_str(), epd.c_str(), st.c_str(), nextSec);
}
void DisplayUI::showProgress(int percent, const String& msg) {
    Serial.printf("[UI Progress %d%%] %s\n", percent, msg.c_str());
}
void DisplayUI::showToast(const String& msg, uint16_t color) {
    Serial.printf("[UI Toast] %s\n", msg.c_str());
}

#endif
