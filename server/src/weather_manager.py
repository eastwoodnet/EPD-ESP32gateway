import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import httpx
from persistence import atomic_write_json

logger = logging.getLogger(__name__)

WEATHER_CODE_MAP: Dict[int, str] = {
    113: "晴",
    116: "多云",
    119: "阴天",
    122: "阴天",
    143: "薄雾",
    176: "局部小雨",
    179: "局部小雪",
    182: "雨夹雪",
    185: "局部冻雨",
    200: "雷阵雨",
    227: "阵雪",
    230: "暴风雪",
    248: "大雾",
    260: "冻雾",
    263: "局部细雨",
    266: "毛毛雨",
    281: "冻雨",
    284: "大冻雨",
    293: "细雨",
    296: "小雨",
    299: "阵中雨",
    302: "中雨",
    305: "阵大雨",
    308: "暴雨",
    311: "小冻雨",
    314: "大冻雨",
    317: "小雨夹雪",
    320: "中雨夹雪",
    323: "局部小雪",
    326: "小雪",
    329: "中雪",
    332: "大雪",
    335: "局地大雪",
    338: "暴雪",
    350: "冰雹",
    353: "小阵雨",
    356: "中强阵雨",
    359: "大阵雨",
    362: "阵雨夹雪",
    365: "强雨夹雪",
    368: "阵雪",
    371: "强阵雪",
    374: "微量冰雹",
    377: "大冰雹",
    386: "雷阵雨",
    389: "雷暴大雨",
    392: "雷阵雪",
    395: "雷暴雪",
}

WIND_DIR_MAP: Dict[str, str] = {
    "N": "北风", "NNE": "东北风", "NE": "东北风", "ENE": "东北风",
    "E": "东风", "ESE": "东南风", "SE": "东南风", "SSE": "东南风",
    "S": "南风", "SSW": "西南风", "SW": "西南风", "WSW": "西南风",
    "W": "西风", "WNW": "西北风", "NW": "西北风", "NNW": "西北风",
}

DEFAULT_CACHE_TTL_SEC = 1800  # 30 分钟缓存


class WeatherManager:
    def __init__(self, data_dir: str, default_city: str = "", cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC):
        self.data_dir = data_dir
        self.default_city = default_city.strip()
        self.cache_ttl_sec = cache_ttl_sec
        self.cache_file = os.path.join(data_dir, "weather.json")
        self._memory_cache: Optional[Dict[str, Any]] = None
        self._load_cache()

    def _load_cache(self) -> None:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._memory_cache = json.load(f)
            except Exception as e:
                logger.warning(f"读取天气缓存失败: {e}")
                self._memory_cache = None

    def _save_cache(self, city: str, data: Dict[str, Any]) -> None:
        cache_obj = {
            "city": city,
            "fetched_at": time.time(),
            "data": data
        }
        self._memory_cache = cache_obj
        try:
            atomic_write_json(self.cache_file, cache_obj)
        except Exception as e:
            logger.warning(f"保存天气缓存失败: {e}")

    @staticmethod
    def _translate_weather_desc(code: Optional[int], raw_desc: str) -> str:
        if code and code in WEATHER_CODE_MAP:
            return WEATHER_CODE_MAP[code]
        raw = raw_desc.strip().lower()
        if "haze" in raw or "smoke" in raw:
            return "轻度雾霾"
        if "dust" in raw or "sand" in raw:
            return "沙尘"
        if "rain" in raw or "shower" in raw:
            return "有雨"
        if "snow" in raw:
            return "有雪"
        if "cloud" in raw or "overcast" in raw:
            return "多云"
        if "sun" in raw or "clear" in raw:
            return "晴"
        if "fog" in raw or "mist" in raw:
            return "雾"
        return raw_desc.strip() or "晴"

    @staticmethod
    def _parse_wttr_json(raw_json: Dict[str, Any], query_city: str) -> Dict[str, Any]:
        cc = raw_json.get("current_condition", [{}])[0]
        weather_days = raw_json.get("weather", [])
        nearest_area = raw_json.get("nearest_area", [{}])[0]

        # 城市名提取
        city_name = query_city.strip()
        if not city_name:
            area_name = nearest_area.get("areaName", [{}])[0].get("value", "")
            region_name = nearest_area.get("region", [{}])[0].get("value", "")
            city_name = area_name or region_name or "当前定位"

        city_map = {
            "tianjin": "天津",
            "beijing": "北京",
            "shanghai": "上海",
            "chongqing": "重庆",
            "guangzhou": "广州",
            "shenzhen": "深圳",
            "hangzhou": "杭州",
            "nanjing": "南京",
            "wuhan": "武汉",
            "chengdu": "成都",
            "xian": "西安",
        }
        city_name = city_map.get(city_name.lower(), city_name)

        # 当前温度与天气
        temp_c = cc.get("temp_C", "--")
        feels_like_c = cc.get("FeelsLikeC", temp_c)
        humidity = cc.get("humidity", "--")

        raw_code = cc.get("weatherCode")
        code = int(raw_code) if raw_code and str(raw_code).isdigit() else None
        raw_desc = cc.get("weatherDesc", [{}])[0].get("value", "")
        weather_desc = WeatherManager._translate_weather_desc(code, raw_desc)

        wind_dir_raw = cc.get("winddir16Point", "")
        wind_dir = WIND_DIR_MAP.get(wind_dir_raw, wind_dir_raw)
        wind_speed = cc.get("windspeedKmph", "")
        wind_str = f"{wind_dir} {wind_speed}km/h" if wind_speed else wind_dir or "--"

        # 今日最高/最低
        today_min = "--"
        today_max = "--"
        if weather_days:
            today_min = weather_days[0].get("mintempC", "--")
            today_max = weather_days[0].get("maxtempC", "--")

        # 未来 2 天简报
        forecast_list: List[Dict[str, str]] = []
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for day in weather_days[:3]:
            d_date = day.get("date", "")
            # 解析日期转为简短的 周几 或 MM-DD
            label = d_date[-5:] if len(d_date) >= 5 else d_date
            try:
                dt_obj = time.strptime(d_date, "%Y-%m-%d")
                label = weekday_names[dt_obj.tm_wday]
            except Exception:
                pass

            d_min = day.get("mintempC", "--")
            d_max = day.get("maxtempC", "--")
            # 取中午/下午的时段描述
            hourly = day.get("hourly", [])
            noon_hour = hourly[len(hourly) // 2] if hourly else {}
            h_code_raw = noon_hour.get("weatherCode")
            h_code = int(h_code_raw) if h_code_raw and str(h_code_raw).isdigit() else None
            h_desc = noon_hour.get("weatherDesc", [{}])[0].get("value", "")
            day_desc = WeatherManager._translate_weather_desc(h_code, h_desc)

            forecast_list.append({
                "label": label,
                "date": d_date,
                "desc": day_desc,
                "temp_min": str(d_min),
                "temp_max": str(d_max)
            })

        update_time_str = time.strftime("%H:%M")

        return {
            "city": city_name,
            "temp_c": str(temp_c),
            "feels_like_c": str(feels_like_c),
            "humidity": str(humidity),
            "weather_desc": weather_desc,
            "wind": wind_str,
            "temp_min": str(today_min),
            "temp_max": str(today_max),
            "forecast": forecast_list,
            "update_time": update_time_str,
            "stale": False,
            "source": "wttr.in"
        }

    def fetch_from_remote(self, city: str) -> Dict[str, Any]:
        """通过免费且免 API Key 的 wttr.in 获取气象 JSON"""
        target_city = city.strip() or self.default_city
        encoded_city = quote(target_city, safe="")
        url = f"https://wttr.in/{encoded_city}?format=j1" if encoded_city else "https://wttr.in/?format=j1"

        headers = {
            "User-Agent": "curl/7.88.1",
            "Accept": "application/json"
        }

        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_wttr_json(data, target_city)

    def get_weather(self, city: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
        target_city = (city if city is not None else self.default_city).strip()
        now = time.time()

        # 检查内存/磁盘缓存
        if not force_refresh and self._memory_cache:
            cache_city = str(self._memory_cache.get("city", "")).strip()
            fetched_at = self._memory_cache.get("fetched_at", 0)
            if cache_city.lower() == target_city.lower() and (now - fetched_at) < self.cache_ttl_sec:
                return self._memory_cache.get("data", {})

        # 发起线上请求
        try:
            weather_data = self.fetch_from_remote(target_city)
            self._save_cache(target_city, weather_data)
            return weather_data
        except Exception as exc:
            logger.error(f"获取 wttr.in 天气数据失败: {exc}")
            # 如果有匹配的陈旧缓存，降级使用并标记为 stale
            if self._memory_cache and "data" in self._memory_cache:
                cache_city = str(self._memory_cache.get("city", "")).strip()
                if not target_city or cache_city.lower() == target_city.lower():
                    fallback_data = dict(self._memory_cache["data"])
                    fallback_data["stale"] = True
                    return fallback_data

            # 毫无缓存时的兜底安全结构
            return {
                "city": target_city or "本地",
                "temp_c": "--",
                "feels_like_c": "--",
                "humidity": "--",
                "weather_desc": "天气获取中",
                "wind": "--",
                "temp_min": "--",
                "temp_max": "--",
                "forecast": [],
                "update_time": "--:--",
                "stale": True,
                "source": "wttr.in"
            }
