import os
import json
from datetime import datetime, time as dtime, timedelta
from typing import Optional, Tuple
from src.models import ScheduleConfig, ScheduleRule

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
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return ScheduleConfig(**data)
            except Exception as e:
                print(f"[Scheduler] 读取 schedule.json 失败: {e}")
        # 保存默认配置
        cfg = ScheduleConfig(**DEFAULT_SCHEDULE)
        self.save_config(cfg)
        return cfg

    def save_config(self, config: ScheduleConfig):
        self.config = config
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Scheduler] 保存 schedule.json 失败: {e}")

    @staticmethod
    def _parse_hm(hm_str: str) -> dtime:
        parts = hm_str.strip().split(":")
        h = int(parts[0]) if len(parts) > 0 else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        return dtime(h, m)

    def is_time_in_range(self, now_t: dtime, start_t: dtime, end_t: dtime) -> bool:
        """
        判断当前时间是否处于 [start, end) 范围内，支持跨午夜
        """
        if start_t <= end_t:
            return start_t <= now_t < end_t
        else:
            # 跨午夜，如 23:00 ~ 07:30
            return now_t >= start_t or now_t < end_t

    def get_current_rule(self, now: Optional[datetime] = None) -> Tuple[Optional[ScheduleRule], str, int]:
        """
        计算当前时刻应命中的排程规则
        返回: (命中的规则对象, 最终展示mode, 距离下一次状态变动的秒数 next_pull_seconds)
        """
        if now is None:
            now = datetime.now()

        now_t = now.time()
        active_rule = None

        for rule in self.config.rules:
            try:
                s_t = self._parse_hm(rule.start)
                e_t = self._parse_hm(rule.end)
                if self.is_time_in_range(now_t, s_t, e_t):
                    active_rule = rule
                    break
            except Exception as e:
                print(f"[Scheduler] 解析规则 {rule.name} 时间失败: {e}")

        active_mode = active_rule.mode if active_rule else self.config.fallback_mode

        # 计算下一次状态变动秒数 (Next Pull Interval)
        next_pull_sec = self._calc_next_event_seconds(now, active_rule)

        return active_rule, active_mode, next_pull_sec

    def _calc_next_event_seconds(self, now: datetime, active_rule: Optional[ScheduleRule]) -> int:
        """
        精确计算下一次时段切换或轮换的秒数
        """
        candidates = []

        # 1. 距离当前规则结束的秒数
        if active_rule:
            e_t = self._parse_hm(active_rule.end)
            end_dt = datetime.combine(now.date(), e_t)
            if end_dt <= now:
                # 结束时间跨到了明天
                end_dt += timedelta(days=1)
            diff = int((end_dt - now).total_seconds())
            if diff > 5:
                candidates.append(diff)

            # 如果当前是相册模式，且配置了轮换间隔，还要考虑相册下一次切图时间
            if active_rule.mode == "photo_album":
                rotate_min = active_rule.config.get("rotate_interval_min", 60)
                if rotate_min > 0:
                    rotate_sec = rotate_min * 60
                    cur_ts = now.timestamp()
                    remain_in_slot = rotate_sec - int(cur_ts % rotate_sec)
                    if remain_in_slot > 10:
                        candidates.append(remain_in_slot)

        # 2. 距离所有其它规则起点的秒数
        for rule in self.config.rules:
            s_t = self._parse_hm(rule.start)
            start_dt = datetime.combine(now.date(), s_t)
            if start_dt <= now:
                start_dt += timedelta(days=1)
            diff = int((start_dt - now).total_seconds())
            if diff > 5:
                candidates.append(diff)

        # 默认兜底 30 分钟 (1800s)
        if not candidates:
            return 1800

        # 取最近的一个事件触发点，并设置合理边界 [30s, 3600s]
        best_sec = min(candidates)
        return max(30, min(3600, best_sec))
