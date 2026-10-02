from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ScheduleRule(BaseModel):
    id: str
    name: str
    start: str  # "HH:MM", e.g. "09:00"
    end: str    # "HH:MM", e.g. "13:30"
    mode: str   # "photo_album", "calendar_todo", "weather_date", "clock", "sleep_dnd"
    config: Dict[str, Any] = Field(default_factory=dict)

class ScheduleConfig(BaseModel):
    rules: List[ScheduleRule] = Field(default_factory=list)
    fallback_mode: str = "photo_album"

class MemoRequest(BaseModel):
    title: str = "📌 桌面备忘提醒"
    text: str
    duration_min: int = 120  # 可自主设定时长（分钟）
    sender: str = "手机推送"
    theme: str = "red_alert"

class MemoState(BaseModel):
    active: bool = False
    title: str = ""
    text: str = ""
    created_at: float = 0.0
    expire_at: float = 0.0
    duration_min: int = 120
    sender: str = ""
    theme: str = "red_alert"

class ServerSettings(BaseModel):
    gateway_url: str = "http://192.168.1.118"
    default_memo_duration_min: int = 120
    screen_width: int = 400
    screen_height: int = 300
    rotate_interval_min: int = 60
