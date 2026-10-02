#pragma once

#include <Arduino.h>
#include "config.h"

class DisplayUI {
public:
    static DisplayUI& getInstance();

    void begin();
    void showBoot();
    void showConnecting(const String& ssid);
    void showApMode(const String& apSsid, const String& apPass, const String& apIp);
    void showDashboard(const String& ip, const String& epdName, const String& status, int nextSyncSec = -1);
    void showProgress(int percent, const String& message);
    void showToast(const String& msg, uint16_t color = 0xFFFF);

private:
    DisplayUI();
    bool initialized = false;
};
