import json
import math
import os
from datetime import datetime, time as dtime, timedelta
from typing import Optional, Tuple

from src.models import ScheduleConfig, ScheduleRule
from persistence import atomic_write_json

DEFAULT_SCHEDULE = {
    "rules": [
        {
            "id": "rule_morning_photo",
            "name": "白天相册轮播",
            "start": "08:30",
            "end": "22:30",
            "mode": "photo_album",
            "config": {
                "rotate_interval_min": 60
            }
        },
        {
            "id": "rule_night_sleep",
            "name": "夜间休眠免打扰",
            "start": "22:30",
            "end": "08:30",
            "mode": "sleep_dnd",
            "config": {}
        }
    ],
    "fallback_mode": "photo_album"
}

class Scheduler:
    def __init__(self, data_dir: str):
        self.config_file = os.path.join(data_dir, "schedule.json")
        self.config = self._load()

    def _load(self) -> ScheduleConfig:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as handle:
                    return ScheduleConfig(**json.load(handle))
            except Exception as exc:
                raise RuntimeError(f"读取 schedule.json 失败: {exc}") from exc
        cfg = ScheduleConfig(**DEFAULT_SCHEDULE)
        atomic_write_json(self.config_file, cfg.model_dump())
        return cfg

    def save_config(self, config: ScheduleConfig):
        atomic_write_json(self.config_file, config.model_dump())
        self.config = config

    @staticmethod
    def _parse_hm(hm_str: str) -> dtime:
        return datetime.strptime(hm_str, "%H:%M").time()

    def is_time_in_range(self, now_t: dtime, start_t: dtime, end_t: dtime) -> bool:
        """
        判断当前时间是否处于 [start, end) 范围内，支持跨午夜
        """
        if start_t <= end_t:
            return start_t <= now_t < end_t
        else:
            # 跨午夜，如 23:00 ~ 07:30
            return now_t >= start_t or now_t < end_t

    def get_current_rule(self, now: Optional[datetime] = None, fallback_rotate_min: int = 60) -> Tuple[Optional[ScheduleRule], str, int]:
        if now is None:
            now = datetime.now()

        now_t = now.time()
        active_rule = None
        for rule in self.config.rules:
            if self.is_time_in_range(now_t, self._parse_hm(rule.start), self._parse_hm(rule.end)):
                active_rule = rule
                break

        active_mode = active_rule.mode if active_rule else self.config.fallback_mode
        next_pull_sec = self._calc_next_event_seconds(now, active_rule, active_mode, fallback_rotate_min)
        return active_rule, active_mode, next_pull_sec

    def _calc_next_event_seconds(self, now: datetime, active_rule: Optional[ScheduleRule], active_mode: str, fallback_rotate_min: int) -> int:
        candidates = []

        def add_candidate(target: datetime):
            seconds = (target - now).total_seconds()
            if seconds > 0:
                candidates.append(max(1, math.ceil(seconds)))

        if active_rule:
            end_dt = datetime.combine(now.date(), self._parse_hm(active_rule.end))
            if end_dt <= now:
                end_dt += timedelta(days=1)
            add_candidate(end_dt)

        for rule in self.config.rules:
            start_dt = datetime.combine(now.date(), self._parse_hm(rule.start))
            if start_dt <= now:
                start_dt += timedelta(days=1)
            add_candidate(start_dt)

        if active_mode == "photo_album":
            rotate_min = active_rule.config.get("rotate_interval_min", 60) if active_rule else fallback_rotate_min
            if type(rotate_min) is not int or not 10 <= rotate_min <= 1440:
                rotate_min = 60
            rotate_sec = rotate_min * 60
            candidates.append(rotate_sec - int(now.timestamp() % rotate_sec))
        elif active_mode == "weather_date":
            # 天气预报建议每 30~60 分钟同步一次，默认 30 分钟
            interval_min = active_rule.config.get("interval_min", 30) if active_rule else 30
            if type(interval_min) is not int:
                interval_min = 30
            interval_sec = max(10, min(1440, interval_min)) * 60
            candidates.append(interval_sec - int(now.timestamp() % interval_sec))
            next_midnight = datetime.combine(now.date() + timedelta(days=1), dtime(0, 0))
            add_candidate(next_midnight)
        elif active_mode == "calendar_todo":
            # 日程看板默认每 30 分钟同步一次
            interval_min = active_rule.config.get("interval_min", 30) if active_rule else 30
            if type(interval_min) is not int:
                interval_min = 30
            interval_sec = max(10, min(1440, interval_min)) * 60
            candidates.append(interval_sec - int(now.timestamp() % interval_sec))
            next_midnight = datetime.combine(now.date() + timedelta(days=1), dtime(0, 0))
            add_candidate(next_midnight)
        elif active_mode == "clock":
            next_midnight = datetime.combine(now.date() + timedelta(days=1), dtime(0, 0))
            add_candidate(next_midnight)

        if not candidates:
            return 1800
        return max(30, min(3600, min(candidates)))
