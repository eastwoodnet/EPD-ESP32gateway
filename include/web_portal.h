#pragma once

#include <Arduino.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <functional>

class WebPortal {
public:
    static WebPortal& getInstance();

    void begin(bool isApMode);
    void handleClient();
    void setTriggerCallback(std::function<void()> cb);

private:
    WebPortal();
    WebServer server;
    DNSServer dnsServer;
    bool inApMode = false;
    std::function<void()> triggerCallback = nullptr;

    void setupRoutes();
    void handleRoot();
    void handleApiStatus();
    void handleApiBleScan();
    void handleApiBleResults();
    void handleApiBleBind();
    void handleApiBleClear();
    void handleApiBleTestPattern();
    void handleApiBleCalendar();
    void handleApiBleClock();
    void handleApiConfig();
    void handleApiWifi();
    void handleApiTrigger();
};
