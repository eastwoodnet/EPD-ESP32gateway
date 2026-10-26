import ipaddress
import math
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

DisplayMode = Literal["photo_album", "calendar_todo", "weather_date", "clock", "sleep_dnd"]


def validate_gateway_url(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 512:
        raise ValueError("网关地址不能为空且不能超过 512 个字符")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("网关地址格式无效") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("网关地址仅支持 HTTP(S) 且必须包含主机")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("网关地址不能包含用户信息")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("网关地址只能包含协议、主机和端口")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("网关端口无效")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("网关地址不能指向本机回环地址")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified):
        raise ValueError("网关地址不能指向回环、链路本地、组播或未指定地址")
    return value.rstrip("/")


class ScheduleRule(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    mode: DisplayMode
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "name", "start", "end", mode="before")
    @classmethod
    def strip_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("config")
    @classmethod
    def validate_config(cls, value):
        if "rotate_interval_min" in value:
            interval = value["rotate_interval_min"]
            if type(interval) is not int or not 10 <= interval <= 1440:
                raise ValueError("相册轮换间隔必须是 10~1440 分钟之间的整数")
        if "interval_min" in value:
            interval = value["interval_min"]
            if type(interval) is not int or not 10 <= interval <= 1440:
                raise ValueError("同步间隔必须是 10~1440 分钟之间的整数")
        if "city" in value and value["city"] is not None:
            if not isinstance(value["city"], str) or len(value["city"]) > 100:
                raise ValueError("城市名称无效")
        return value

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start == self.end:
            raise ValueError("排程规则开始时间与结束时间不能相同")
        return self


class ScheduleConfig(BaseModel):
    rules: List[ScheduleRule] = Field(default_factory=list, max_length=64)
    fallback_mode: DisplayMode = "photo_album"

    @model_validator(mode="after")
    def validate_rule_ids(self):
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("排程规则 ID 不能重复")
        return self


class MemoRequest(BaseModel):
    title: str = Field(default="📌 桌面备忘提醒", min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)
    duration_min: int = Field(default=120, ge=1, le=10080)
    sender: str = Field(default="手机推送", min_length=1, max_length=80)
    theme: str = Field(default="red_alert", min_length=1, max_length=32)

    @field_validator("title", "sender", "theme", mode="before")
    @classmethod
    def strip_fields(cls, value):
        return value.strip() if isinstance(value, str) else value


class MemoState(BaseModel):
    active: bool = False
    title: str = Field(default="", max_length=80)
    text: str = Field(default="", max_length=4000)
    created_at: float = 0.0
    expire_at: float = 0.0
    duration_min: int = Field(default=120, ge=1, le=10080)
    sender: str = Field(default="", max_length=80)
    theme: str = Field(default="red_alert", min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_active_state(self):
        if self.active:
            if not math.isfinite(self.created_at) or not math.isfinite(self.expire_at):
                raise ValueError("便签时间戳必须是有限数值")
            if self.created_at <= 0 or self.expire_at <= self.created_at or not self.text:
                raise ValueError("活动便签状态无效")
        return self


class ServerSettings(BaseModel):
    gateway_url: str = Field(default="http://192.168.1.118", max_length=512)
    weather_city: str = Field(default="", max_length=100)
    calendar_ical_url: str = Field(default="", max_length=1024)
    default_memo_duration_min: int = Field(default=120, ge=1, le=10080)
    screen_width: int = Field(default=400, ge=1, le=2000)
    screen_height: int = Field(default=300, ge=1, le=2000)
    rotate_interval_min: int = Field(default=60, ge=10, le=1440)

    @field_validator("weather_city", "calendar_ical_url", mode="before")
    @classmethod
    def strip_string_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("gateway_url")
    @classmethod
    def validate_url(cls, value):
        return validate_gateway_url(value)


class ServerSettingsUpdate(BaseModel):
    gateway_url: Optional[str] = Field(default=None, max_length=512)
    weather_city: Optional[str] = Field(default=None, max_length=100)
    calendar_ical_url: Optional[str] = Field(default=None, max_length=1024)
    default_memo_duration_min: Optional[int] = Field(default=None, ge=1, le=10080)
    screen_width: Optional[int] = Field(default=None, ge=1, le=2000)
    screen_height: Optional[int] = Field(default=None, ge=1, le=2000)
    rotate_interval_min: Optional[int] = Field(default=None, ge=10, le=1440)

    @field_validator("weather_city", "calendar_ical_url", mode="before")
    @classmethod
    def strip_string_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("*")
    @classmethod
    def reject_null_values(cls, value):
        if value is None:
            raise ValueError("设置字段不能为 null")
        return value

    @field_validator("gateway_url")
    @classmethod
    def validate_url(cls, value):
        return validate_gateway_url(value) if value is not None else value
