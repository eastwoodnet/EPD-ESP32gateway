#pragma once

#include <Arduino.h>

// ==========================================
// 硬件特性宏开关 (根据硬件需求开启或关闭)
// ==========================================
#ifndef ENABLE_T_DISPLAY_S3
#define ENABLE_T_DISPLAY_S3 1 // 1: 启用 LilyGO T-Display-S3 板载屏幕; 0: 纯ESP32硬件
#endif

// ==========================================
// LilyGO T-Display-S3 引脚定义
// ==========================================
#if ENABLE_T_DISPLAY_S3
#define PIN_LCD_POWER   15  // 必须输出高电平为LCD供电
#define PIN_BUTTON_1    0   // Boot按键 (短按: 立即同步; 长按3秒: 重启并进入AP配网模式)
#define PIN_BUTTON_2    14  // 备用按键
#else
#ifndef PIN_BUTTON_1
#define PIN_BUTTON_1    9   // ESP32-C3 Boot 按键通常位于 GPIO 9
#endif
#endif

// ==========================================
// BLE 墨水屏服务与特征 UUID (与 EPD-nRF5 固件一致)
// ==========================================
#define EPD_SERVICE_UUID        "62750001-d828-918d-fb46-b6c11c675aec"
#define EPD_CHAR_DATA_UUID      "62750002-d828-918d-fb46-b6c11c675aec"
#define EPD_CHAR_VER_UUID       "62750003-d828-918d-fb46-b6c11c675aec"

// EPD 命令定义 (与 EPD_service.h 一致)
enum EpdCmd {
    EPD_CMD_INIT        = 0x01, // 初始化屏幕
    EPD_CMD_CLEAR       = 0x02, // 清屏
    EPD_CMD_SEND_CMD    = 0x03, // 原始命令
    EPD_CMD_SEND_DATA   = 0x04, // 原始数据
    EPD_CMD_REFRESH     = 0x05, // 触发刷新物理屏幕
    EPD_CMD_SLEEP       = 0x06, // 屏幕休眠
    EPD_CMD_SET_TIME    = 0x20, // 设置时间
    EPD_CMD_WRITE_IMAGE = 0x30, // 写入图像数据
};

// ==========================================
// 默认配网与AP设置
// ==========================================
#define DEFAULT_AP_SSID_PREFIX  "EPD-Gateway-"
#define DEFAULT_AP_PASS         "12345678"
#define DEFAULT_HTTP_PORT       80
#define DEFAULT_REFRESH_MINUTES 60
#define BLE_DEFAULT_SCAN_SECONDS 5

