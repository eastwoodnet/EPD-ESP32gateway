#include "http_puller.h"

HttpPullResponse HttpPuller::fetchImage(const String& url, 
                                       const String& token, 
                                       const String& tokenHeader, 
                                       const String& lastEtag) {
    HttpPullResponse resp;
    resp.result = PULL_CONNECT_ERR;
    resp.httpCode = 0;
    resp.data = nullptr;
    resp.length = 0;
    resp.newEtag = "";
    resp.errorMsg = "";

    if (url.length() == 0) {
        resp.errorMsg = "服务器 URL 为空";
        return resp;
    }

    HTTPClient http;
    WiFiClient client;
    WiFiClientSecure secureClient;

    bool isHttps = url.startsWith("https://");
    if (isHttps) {
        secureClient.setInsecure(); // 允许自签名或无需校验证书，增强兼容性
        http.begin(secureClient, url);
    } else {
        http.begin(client, url);
    }

    http.setTimeout(12000); // 12秒超时

    // 添加 Token Header
    if (token.length() > 0) {
        String headerName = (tokenHeader.length() > 0) ? tokenHeader : "Authorization";
        String headerVal = token;
        if (headerName.equalsIgnoreCase("Authorization") && !token.startsWith("Bearer ") && !token.startsWith("Basic ")) {
            headerVal = "Bearer " + token;
        }
        http.addHeader(headerName, headerVal);
        Serial.printf("[HTTP] 添加认证头: %s: %s\n", headerName.c_str(), token.substring(0, 4).c_str());
    }

    // 添加 ETag 缓存检测
    if (lastEtag.length() > 0) {
        http.addHeader("If-None-Match", lastEtag);
    }

    // 关注响应头中的 ETag
    const char* headerKeys[] = {"ETag", "Content-Length"};
    http.collectHeaders(headerKeys, 2);

    Serial.printf("[HTTP] 请求: %s\n", url.c_str());
    int httpCode = http.GET();
    resp.httpCode = httpCode;

    if (httpCode == HTTP_CODE_NOT_MODIFIED) {
        Serial.println("[HTTP] 304 Not Modified: 画面无变更，无需刷新");
        resp.result = PULL_NOT_MODIFIED;
        resp.newEtag = lastEtag;
        http.end();
        return resp;
    }

    if (httpCode != HTTP_CODE_OK) {
        resp.result = PULL_HTTP_ERR;
        resp.errorMsg = String("HTTP 状态码: ") + String(httpCode);
        Serial.printf("[HTTP] 请求异常: %s\n", resp.errorMsg.c_str());
        http.end();
        return resp;
    }

    resp.newEtag = http.header("ETag");

    int len = http.getSize();
    WiFiClient* stream = http.getStreamPtr();

    // 墨水屏点阵通常在 5KB ~ 200KB 之间
    if (len > 0) {
        resp.data = (uint8_t*)malloc(len);
        if (!resp.data) {
            resp.result = PULL_CONNECT_ERR;
            resp.errorMsg = "内存分配失败";
            http.end();
            return resp;
        }

        size_t bytesRead = 0;
        unsigned long startWait = millis();
        while (http.connected() && (bytesRead < (size_t)len) && (millis() - startWait < 8000)) {
            size_t available = stream->available();
            if (available) {
                size_t readNow = stream->readBytes(&resp.data[bytesRead], ((size_t)len - bytesRead));
                bytesRead += readNow;
                startWait = millis();
            }
            delay(1);
        }
        resp.length = bytesRead;
    } else {
        // Chunked 或未知 Content-Length
        size_t cap = 32768;
        resp.data = (uint8_t*)malloc(cap);
        size_t total = 0;

        unsigned long startWait = millis();
        while (http.connected() && (millis() - startWait < 8000)) {
            while (stream->available()) {
                if (total >= cap) {
                    cap += 32768;
                    uint8_t* newPtr = (uint8_t*)realloc(resp.data, cap);
                    if (!newPtr) {
                        free(resp.data);
                        resp.data = nullptr;
                        resp.result = PULL_CONNECT_ERR;
                        resp.errorMsg = "内存扩容失败";
                        http.end();
                        return resp;
                    }
                    resp.data = newPtr;
                }
                resp.data[total++] = stream->read();
                startWait = millis();
            }
            delay(1);
        }
        resp.length = total;
    }

    http.end();

    if (resp.length == 0) {
        if (resp.data) free(resp.data);
        resp.data = nullptr;
        resp.result = PULL_EMPTY_ERR;
        resp.errorMsg = "拉取到空数据";
        return resp;
    }

    resp.result = PULL_SUCCESS;
    Serial.printf("[HTTP] 成功下载图像点阵: %d 字节, ETag: %s\n", resp.length, resp.newEtag.c_str());
    return resp;
}

void HttpPuller::freeResponse(HttpPullResponse& resp) {
    if (resp.data) {
        free(resp.data);
        resp.data = nullptr;
    }
    resp.length = 0;
}
