#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

enum HttpPullResult {
    PULL_SUCCESS = 0,      // 获取新数据成功
    PULL_NOT_MODIFIED = 1, // 304 未修改，无需刷新
    PULL_CONNECT_ERR = -1, // 连接或网络错误
    PULL_HTTP_ERR = -2,    // HTTP 状态码异常
    PULL_EMPTY_ERR = -3    // 返回数据为空
};

struct HttpPullResponse {
    HttpPullResult result;
    int httpCode;
    uint8_t* data;
    size_t length;
    String newEtag;
    String errorMsg;
};

class HttpPuller {
public:
    static HttpPullResponse fetchImage(const String& url, 
                                       const String& token, 
                                       const String& tokenHeader, 
                                       const String& lastEtag);
    static void freeResponse(HttpPullResponse& resp);
};
