#include "http_puller.h"

static const size_t MAX_IMAGE_BYTES = 200UL * 1024UL;
static const uint32_t IDLE_TIMEOUT_MS = 8000;
static const uint32_t TOTAL_TIMEOUT_MS = 30000;

static uint32_t parseNextPullSec(const String& value) {
    if (value.length() == 0) return 0;
    char* end = nullptr;
    unsigned long seconds = strtoul(value.c_str(), &end, 10);
    if (end == nullptr || *end != '\0' || seconds < 30 || seconds > 86400) return 0;
    return (uint32_t)seconds;
}

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
    resp.nextPullSec = 0;

    if (url.length() == 0) {
        resp.errorMsg = "服务器 URL 为空";
        return resp;
    }

    HTTPClient http;
    WiFiClient client;
    WiFiClientSecure secureClient;
    bool isHttps = url.startsWith("https://");
    if (isHttps) secureClient.setInsecure();
    bool began = isHttps ? http.begin(secureClient, url) : http.begin(client, url);
    if (!began) {
        resp.errorMsg = "无法初始化 HTTP 连接";
        return resp;
    }

    http.setTimeout(12000);
    http.addHeader("Connection", "close");
    if (token.length() > 0) {
        String headerName = (tokenHeader.length() > 0) ? tokenHeader : "Authorization";
        String headerVal = token;
        if (headerName.equalsIgnoreCase("Authorization") && !token.startsWith("Bearer ") && !token.startsWith("Basic ")) {
            headerVal = "Bearer " + token;
        }
        http.addHeader(headerName, headerVal);
    }
    if (lastEtag.length() > 0) http.addHeader("If-None-Match", lastEtag);

    const char* headerKeys[] = {"ETag", "Content-Length", "X-Next-Pull"};
    http.collectHeaders(headerKeys, 3);

    Serial.printf("[HTTP] 请求: %s\n", url.c_str());
    int httpCode = http.GET();
    resp.httpCode = httpCode;
    resp.nextPullSec = parseNextPullSec(http.header("X-Next-Pull"));

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
        http.end();
        return resp;
    }

    resp.newEtag = http.header("ETag");
    int len = http.getSize();
    WiFiClient* stream = http.getStreamPtr();
    if (stream == nullptr || len > (int)MAX_IMAGE_BYTES) {
        resp.result = PULL_HTTP_ERR;
        resp.errorMsg = len > (int)MAX_IMAGE_BYTES ? "图像数据超过大小限制" : "无法读取 HTTP 响应流";
        http.end();
        return resp;
    }

    unsigned long startedAt = millis();
    unsigned long lastReadAt = startedAt;
    bool failed = false;
    String failure;

    if (len > 0) {
        resp.data = (uint8_t*)malloc((size_t)len);
        if (resp.data == nullptr) {
            resp.errorMsg = "内存分配失败";
            http.end();
            return resp;
        }

        size_t bytesRead = 0;
        while (bytesRead < (size_t)len) {
            if (millis() - startedAt >= TOTAL_TIMEOUT_MS || millis() - lastReadAt >= IDLE_TIMEOUT_MS) {
                failed = true;
                failure = "下载超时或数据不完整";
                break;
            }
            int available = stream->available();
            if (available > 0) {
                size_t remaining = (size_t)len - bytesRead;
                size_t readNow = stream->readBytes(&resp.data[bytesRead], remaining);
                if (readNow == 0) {
                    failed = true;
                    failure = "下载数据不完整";
                    break;
                }
                bytesRead += readNow;
                lastReadAt = millis();
            } else {
                if (!http.connected()) break;
                delay(1);
            }
        }
        if (bytesRead != (size_t)len) {
            failed = true;
            if (failure.length() == 0) failure = "下载数据不完整";
        }
        if (!failed) resp.length = bytesRead;
    } else {
        size_t cap = 32768;
        resp.data = (uint8_t*)malloc(cap);
        if (resp.data == nullptr) {
            resp.errorMsg = "内存分配失败";
            http.end();
            return resp;
        }

        size_t total = 0;
        while (!failed) {
            if (millis() - startedAt >= TOTAL_TIMEOUT_MS || millis() - lastReadAt >= IDLE_TIMEOUT_MS) {
                failed = true;
                failure = "下载超时或数据不完整";
                break;
            }
            while (stream->available() > 0) {
                if (total >= MAX_IMAGE_BYTES) {
                    failed = true;
                    failure = "图像数据超过大小限制";
                    break;
                }
                if (total >= cap) {
                    size_t newCap = cap + 32768;
                    if (newCap > MAX_IMAGE_BYTES) newCap = MAX_IMAGE_BYTES;
                    uint8_t* newPtr = (uint8_t*)realloc(resp.data, newCap);
                    if (newPtr == nullptr) {
                        failed = true;
                        failure = "内存扩容失败";
                        break;
                    }
                    resp.data = newPtr;
                    cap = newCap;
                }
                int value = stream->read();
                if (value < 0) break;
                resp.data[total++] = (uint8_t)value;
                lastReadAt = millis();
            }
            if (failed) break;
            if (!http.connected() && stream->available() <= 0) break;
            delay(1);
        }
        if (!failed) resp.length = total;
    }

    http.end();
    if (failed) {
        free(resp.data);
        resp.data = nullptr;
        resp.length = 0;
        resp.result = PULL_HTTP_ERR;
        resp.errorMsg = failure;
        return resp;
    }
    if (resp.length == 0) {
        free(resp.data);
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
