import json
import logging
import os
import time
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional
import httpx
from dateutil import tz
from dateutil.rrule import rrulestr
from icalendar import Calendar
from persistence import atomic_write_json

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SEC = 900  # 15 分钟缓存


def get_local_tz():
    return tz.gettz("Asia/Shanghai") or tz.tzlocal()


class CalendarManager:
    def __init__(self, data_dir: str, default_ical_url: str = "", cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC):
        self.data_dir = data_dir
        self.ical_url = default_ical_url.strip()
        self.cache_ttl_sec = cache_ttl_sec
        self.cache_file = os.path.join(data_dir, "calendar.json")
        self._memory_cache: Optional[Dict[str, Any]] = None
        self._load_cache()

    def set_ical_url(self, url: str) -> None:
        clean = url.strip()
        if clean != self.ical_url:
            self.ical_url = clean
            # 如果 URL 变更，失效当前缓存以便重新拉取
            self._memory_cache = None

    def _load_cache(self) -> None:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._memory_cache = json.load(f)
            except Exception as e:
                logger.warning(f"读取日历缓存失败: {e}")
                self._memory_cache = None

    def _save_cache(self, payload: Dict[str, Any]) -> None:
        self._memory_cache = payload
        try:
            atomic_write_json(self.cache_file, payload)
        except Exception as e:
            logger.warning(f"保存日历缓存失败: {e}")

    @staticmethod
    def normalize_url(url: str) -> str:
        url = url.strip()
        if url.startswith("webcal://"):
            return "https://" + url[len("webcal://"):]
        return url

    @staticmethod
    def get_mock_events(target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        生成高质量的测试用当日日程假数据，满足用户实机体验与开发调试需要
        """
        now = datetime.now()
        cur_hour = now.hour

        # 动态将第二项会议设置为当前时段附近的“进行中”日程
        t2_start_h = max(0, cur_hour)
        t2_end_h = min(23, cur_hour + 1)
        start2_str = f"{t2_start_h:02d}:00"
        end2_str = f"{t2_end_h:02d}:00"

        return [
            {
                "title": "项目架构设计与安全审计评审",
                "start_time": "09:30",
                "end_time": "10:30",
                "location": "3号会议室 (Zoom: 882-991)",
                "description": "探讨固件协议安全及低功耗优化",
                "is_all_day": False,
                "is_ongoing": (cur_hour == 9 or (cur_hour == 10 and now.minute <= 30)),
            },
            {
                "title": "墨水屏在线日程表功能联调测试",
                "start_time": start2_str,
                "end_time": end2_str,
                "location": "硬件测试台 / 本机调试",
                "description": "iCal 自动同步与墨水屏原生点阵渲染",
                "is_all_day": False,
                "is_ongoing": True,  # 设定为当前进行中
            },
            {
                "title": "团队周例会与下周排期同步",
                "start_time": "16:30",
                "end_time": "17:30",
                "location": "大会议室",
                "description": "同步各模块发布计划",
                "is_all_day": False,
                "is_ongoing": False,
            },
            {
                "title": "晚间技术复盘与代码重构",
                "start_time": "19:00",
                "end_time": "20:30",
                "location": "书房",
                "description": "梳理网关及中继系统逻辑",
                "is_all_day": False,
                "is_ongoing": False,
            },
        ]

    def _parse_ical_content(self, ical_text: str, target_date: date) -> List[Dict[str, Any]]:
        local_tz = get_local_tz()
        today_start = datetime.combine(target_date, dtime.min).replace(tzinfo=local_tz)
        today_end = datetime.combine(target_date, dtime.max).replace(tzinfo=local_tz)
        now_dt = datetime.now(local_tz)

        cal = Calendar.from_ical(ical_text)
        events: List[Dict[str, Any]] = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            summary = str(component.get("summary", "未命名日程")).strip()
            location = str(component.get("location", "")).strip()
            description = str(component.get("description", "")).strip()

            dtstart_prop = component.get("dtstart")
            if not dtstart_prop:
                continue
            raw_start = dtstart_prop.dt

            dtend_prop = component.get("dtend")
            raw_end = dtend_prop.dt if dtend_prop else None

            # 1. 全天日程 (date 类型)
            if isinstance(raw_start, date) and not isinstance(raw_start, datetime):
                # iCal 全天日程的结束日期通常是次日
                end_date = raw_end if (raw_end and isinstance(raw_end, date) and not isinstance(raw_end, datetime)) else raw_start
                if raw_start <= target_date < end_date or (raw_start == target_date and end_date == target_date):
                    events.append({
                        "title": summary,
                        "start_time": "全天",
                        "end_time": "",
                        "location": location,
                        "description": description,
                        "is_all_day": True,
                        "is_ongoing": True,
                        "_sort_key": (0, 0),
                    })
                continue

            # 2. 时段日程 (datetime 类型)
            start_dt = raw_start
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=local_tz)
            else:
                start_dt = start_dt.astimezone(local_tz)

            duration = timedelta(hours=1)
            if raw_end:
                end_dt = raw_end
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=local_tz)
                else:
                    end_dt = end_dt.astimezone(local_tz)
                duration = max(timedelta(minutes=15), end_dt - start_dt)
            else:
                end_dt = start_dt + duration

            # 检查是否有 RRULE (重复日程)
            rrule_prop = component.get("rrule")
            if rrule_prop:
                try:
                    rule_text = rrule_prop.to_ical().decode("utf-8") if hasattr(rrule_prop, "to_ical") else str(rrule_prop)
                    # 扩展当前日期范围内的复发事件
                    # rrulestr 需要 naive datetime 或同 tzinfo
                    rule = rrulestr(rule_text, dtstart=start_dt)
                    # 搜索窗口：从 target_date - 1天 到 target_date + 1天
                    search_start = today_start - timedelta(days=1)
                    search_end = today_end + timedelta(days=1)
                    occurrences = rule.between(search_start, search_end, inc=True)

                    for occ in occurrences:
                        if occ.tzinfo is None:
                            occ = occ.replace(tzinfo=local_tz)
                        else:
                            occ = occ.astimezone(local_tz)
                        occ_end = occ + duration

                        # 判断是否落在今天
                        if occ < today_end and occ_end > today_start:
                            is_ongoing = occ <= now_dt <= occ_end
                            events.append({
                                "title": summary,
                                "start_time": occ.strftime("%H:%M"),
                                "end_time": occ_end.strftime("%H:%M"),
                                "location": location,
                                "description": description,
                                "is_all_day": False,
                                "is_ongoing": is_ongoing,
                                "_sort_key": (1, occ.hour * 60 + occ.minute),
                            })
                    continue
                except Exception as e:
                    logger.warning(f"解析重复日程 RRULE 失败, 降级为单次日程: {e}")

            # 单次时段事件
            if start_dt < today_end and end_dt > today_start:
                is_ongoing = start_dt <= now_dt <= end_dt
                events.append({
                    "title": summary,
                    "start_time": start_dt.strftime("%H:%M"),
                    "end_time": end_dt.strftime("%H:%M"),
                    "location": location,
                    "description": description,
                    "is_all_day": False,
                    "is_ongoing": is_ongoing,
                    "_sort_key": (1, start_dt.hour * 60 + start_dt.minute),
                })

        # 排序：全天事件排前，然后按时间升序
        events.sort(key=lambda x: x.get("_sort_key", (1, 0)))
        # 清除内部排序 key
        for ev in events:
            ev.pop("_sort_key", None)

        return events

    def fetch_calendar_data(self, force_refresh: bool = False, custom_url: Optional[str] = None) -> Dict[str, Any]:
        """
        获取日程数据 (优先从缓存读取，失效或强制刷新时从网络拉取)
        """
        url = custom_url if custom_url is not None else self.ical_url
        url = self.normalize_url(url)
        now_ts = time.time()
        now_date_str = date.today().isoformat()

        # 1. 检查有效缓存
        if not force_refresh and self._memory_cache:
            cache_ts = self._memory_cache.get("fetched_at", 0)
            cache_date = self._memory_cache.get("today_date", "")
            if (now_ts - cache_ts < self.cache_ttl_sec) and (cache_date == now_date_str):
                # 重新计算每个事件的 is_ongoing 状态 (随时间动态推进)
                events = self._memory_cache.get("events", [])
                cur_hm = datetime.now().strftime("%H:%M")
                for ev in events:
                    if not ev.get("is_all_day"):
                        st = ev.get("start_time", "99:99")
                        et = ev.get("end_time", "99:99")
                        ev["is_ongoing"] = (st <= cur_hm <= et)
                return self._memory_cache

        # 2. 如果未配置 URL，返回高质量测试假数据
        if not url:
            mock_events = self.get_mock_events(date.today())
            res = {
                "fetched_at": now_ts,
                "today_date": now_date_str,
                "ical_url": "",
                "is_mock": True,
                "status": "ok",
                "message": "未配置 iCal URL，当前展示模拟日程数据",
                "events": mock_events,
                "update_time": datetime.now().strftime("%H:%M"),
            }
            self._save_cache(res)
            return res

        # 3. 网络拉取
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; EPD-Gateway-Calendar/1.0)",
                "Accept": "text/calendar, text/plain, */*",
            }
            resp = httpx.get(url, headers=headers, timeout=12.0, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text

            parsed_events = self._parse_ical_content(content, date.today())
            res = {
                "fetched_at": now_ts,
                "today_date": now_date_str,
                "ical_url": url,
                "is_mock": False,
                "status": "ok",
                "message": f"成功拉取并解析 {len(parsed_events)} 项今日日程",
                "events": parsed_events,
                "update_time": datetime.now().strftime("%H:%M"),
            }
            self._save_cache(res)
            return res
        except Exception as e:
            logger.error(f"拉取 iCal 日历失败: {e}")
            err_msg = str(e)
            # 容错：仅当存在同一 URL 的真实历史缓存时，才返回离线旧数据
            if (
                self._memory_cache
                and not self._memory_cache.get("is_mock", False)
                and self._memory_cache.get("ical_url") == url
                and self._memory_cache.get("events") is not None
            ):
                cached_events = self._memory_cache.get("events", [])
                return {
                    "fetched_at": self._memory_cache.get("fetched_at", now_ts),
                    "today_date": now_date_str,
                    "ical_url": url,
                    "is_mock": False,
                    "stale": True,
                    "status": "error",
                    "message": f"同步失败: {err_msg} (当前展示离线缓存)",
                    "error_detail": err_msg,
                    "events": cached_events,
                    "update_time": self._memory_cache.get("update_time", datetime.now().strftime("%H:%M")),
                }

            # 无真实有效缓存：真实报告网络失败，空日程，绝不伪造假日程误导用户
            return {
                "fetched_at": now_ts,
                "today_date": now_date_str,
                "ical_url": url,
                "is_mock": False,
                "stale": True,
                "status": "error",
                "message": f"网络拉取失败: {err_msg}",
                "error_detail": err_msg,
                "events": [],
                "update_time": datetime.now().strftime("%H:%M"),
            }
