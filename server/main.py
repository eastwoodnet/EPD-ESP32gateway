import hashlib
import io
import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.models import MemoRequest, ScheduleConfig, ServerSettingsUpdate
from src.scheduler import Scheduler
from src.memo_manager import MemoManager
from src.album_manager import AlbumManager, FRAME_BYTES, TOTAL_SLOTS
from src.settings_manager import SettingsManager
from src.gateway_notifier import GatewayNotifier
from src.renderer import render_clock_image, render_sleep_image, render_weather_image, render_calendar_image, raw_to_image
from src.weather_manager import WeatherManager
from src.calendar_manager import CalendarManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("EPD_DATA_DIR", os.path.join(BASE_DIR, "data"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "photos"), exist_ok=True)

class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                response = JSONResponse({"detail": "Content-Length 无效"}, status_code=400)
                await response(scope, receive, send)
                return
            if declared_length < 0:
                response = JSONResponse({"detail": "Content-Length 无效"}, status_code=400)
                await response(scope, receive, send)
                return
            if declared_length > self.max_bytes:
                response = JSONResponse({"detail": "请求体过大"}, status_code=413)
                await response(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                response = JSONResponse({"detail": "请求体过大"}, status_code=413)
                await response(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        sent = False

        async def replay_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)


app = FastAPI(title="EPD-ESP32gateway Server", description="墨水屏数据中继服务端")
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=65536)

# 挂载静态资源与模板
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# 初始化各核心管理器
settings_mgr = SettingsManager(DATA_DIR)
scheduler = Scheduler(DATA_DIR)
album_mgr = AlbumManager(DATA_DIR)
memo_mgr = MemoManager(DATA_DIR)
weather_mgr = WeatherManager(DATA_DIR, default_city=settings_mgr.settings.weather_city)
calendar_mgr = CalendarManager(DATA_DIR, default_ical_url=settings_mgr.settings.calendar_ical_url)
notifier = GatewayNotifier(settings_mgr.settings.gateway_url)


def etag_matches(header_value: Optional[str], etag: str) -> bool:
    if not header_value:
        return False
    for candidate in header_value.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:].strip()
        if candidate == etag:
            return True
    return False


def validate_slot_id(slot_id: int) -> None:
    if not 1 <= slot_id <= TOTAL_SLOTS:
        raise HTTPException(status_code=422, detail=f"卡槽 ID 必须在 1~{TOTAL_SLOTS} 之间")


def activate_memo(req: MemoRequest):
    state = memo_mgr.set_memo(
        text=req.text,
        title=req.title,
        duration_min=req.duration_min,
        sender=req.sender,
        theme=req.theme
    )
    notifier.trigger_sync_background()
    return state


@app.get("/")
async def index_page(request: Request):
    """
    Web 后台管理界面
    """
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "total_slots": TOTAL_SLOTS,
            "settings": settings_mgr.settings.model_dump()
        }
    )

@app.get("/screen.bin")
async def get_screen_bin(request: Request):
    """
    ESP32 网关拉取墨水屏点阵的核心入口
    优先级: 即时便签 (Priority Override) > 24h排程规则 > 兜底时钟
    """
    next_pull_sec = 1800  # 默认 30 分钟
    bin_data: Optional[bytes] = None
    now_ts = time.time()

    # 1. 第一优先级: 即时便签插播
    if memo_mgr.is_active(now_ts):
        bin_data = memo_mgr.get_bin_data()
        memo_state = memo_mgr.get_state()
        remain_sec = max(30, int(memo_state.expire_at - now_ts))
        next_pull_sec = min(remain_sec, 3600)

    # 2. 第二优先级: 24小时自由排程
    if bin_data is None:
        active_rule, active_mode, sched_next_pull = scheduler.get_current_rule(
            fallback_rotate_min=settings_mgr.settings.rotate_interval_min
        )
        next_pull_sec = sched_next_pull

        if active_mode == "photo_album":
            rotate_interval = active_rule.config.get("rotate_interval_min", 60) if active_rule else settings_mgr.settings.rotate_interval_min
            slot_id, photo_bytes = album_mgr.get_active_photo_info(rotate_interval, now_ts)
            if photo_bytes and len(photo_bytes) == FRAME_BYTES:
                bin_data = photo_bytes
            else:
                # 尚未上传照片，回退到优雅时钟画面提示用户
                bin_data = render_clock_image(info="相册卡槽未配置，请在 Web 后台上传照片")

        elif active_mode == "sleep_dnd":
            # 免打扰模式：返回一张静态睡眠提示图（ETag 恒定）。
            # 网关首次拉取全刷一次，之后因 ETag 不变持续收到 304，不再打扰屏幕。
            bin_data = render_sleep_image()

        elif active_mode == "clock":
            bin_data = render_clock_image()

        elif active_mode == "weather_date":
            rule_city = active_rule.config.get("city") if active_rule else None
            city = rule_city if rule_city else settings_mgr.settings.weather_city
            weather_data = weather_mgr.get_weather(city)
            bin_data = render_weather_image(
                weather_data,
                width=settings_mgr.settings.screen_width,
                height=settings_mgr.settings.screen_height
            )

        elif active_mode == "calendar_todo":
            calendar_data = calendar_mgr.fetch_calendar_data()
            bin_data = render_calendar_image(
                calendar_data,
                width=settings_mgr.settings.screen_width,
                height=settings_mgr.settings.screen_height
            )

        else:
            # 未来扩展模式
            bin_data = render_clock_image(info=f"模式: {active_mode}")

    if not bin_data:
        bin_data = render_clock_image()

    # 计算内容 ETag 哈希
    content_hash = hashlib.md5(bin_data).hexdigest()
    etag = f'"{content_hash}"'

    # 检查客户端 If-None-Match 缓存头
    client_etag = request.headers.get("if-none-match")
    if etag_matches(client_etag, etag):
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "X-Next-Pull": str(next_pull_sec),
                "Cache-Control": "no-cache"
            }
        )

    return Response(
        content=bin_data,
        media_type="application/octet-stream",
        headers={
            "ETag": etag,
            "X-Next-Pull": str(next_pull_sec),
            "Cache-Control": "no-cache"
        }
    )

# ----------------- 即时便签推送 API -----------------

@app.post("/api/push")
async def push_memo_post(req: MemoRequest):
    """
    JSON POST 方式推送便签
    """
    if "duration_min" not in req.model_fields_set:
        req = MemoRequest(
            **req.model_dump(exclude={"duration_min"}),
            duration_min=settings_mgr.settings.default_memo_duration_min
        )
    state = activate_memo(req)
    return {"status": "ok", "message": "便签已激活，并已通知网关立即同步", "memo": state.model_dump()}

@app.get("/api/push")
async def push_memo_get(
    text: str = Query(..., description="便签正文", min_length=1, max_length=4000),
    title: str = Query("📌 桌面备忘提醒", description="便签标题", min_length=1, max_length=80),
    duration_min: Optional[int] = Query(None, description="展示时长(分钟)", ge=1, le=10080),
    sender: str = Query("快捷指令", description="发送者", min_length=1, max_length=80)
):
    """
    GET 方式推送便签（专为 iPhone 快捷指令与 Bark 风格设计）
    """
    req = MemoRequest(
        text=text,
        title=title,
        duration_min=duration_min if duration_min is not None else settings_mgr.settings.default_memo_duration_min,
        sender=sender
    )
    state = activate_memo(req)
    return {"status": "ok", "message": "便签已推送", "memo": state.model_dump()}

@app.delete("/api/push")
async def clear_memo():
    """
    手动撤回/清除当前便签
    """
    memo_mgr.clear_memo()
    notifier.trigger_sync_background()
    return {"status": "ok", "message": "便签已清除，已通知网关恢复常规排程"}

@app.get("/api/memo/status")
async def get_memo_status():
    state = memo_mgr.get_state()
    data = state.model_dump()
    data["remaining_sec"] = max(0, int(state.expire_at - time.time())) if state.active else 0
    return data

# ----------------- 相册管理 API (3 卡槽) -----------------

@app.get("/api/album/slots")
async def list_album_slots():
    return {"slots": album_mgr.list_slots()}

@app.post("/api/album/slot/{slot_id}")
async def upload_album_slot(slot_id: int, request: Request):
    """
    接收前端 Canvas 调优后生成的 30,000 字节点阵并保存
    """
    validate_slot_id(slot_id)
    body = await request.body()
    if len(body) != FRAME_BYTES:
        raise HTTPException(status_code=400, detail=f"点阵大小必须恰好为 {FRAME_BYTES} 字节，当前为 {len(body)} 字节")

    album_mgr.save_slot(slot_id, body)
    notifier.trigger_sync_background()
    return {"status": "ok", "message": f"卡槽 {slot_id} 保存成功"}

@app.delete("/api/album/slot/{slot_id}")
async def delete_album_slot(slot_id: int):
    validate_slot_id(slot_id)
    success = album_mgr.delete_slot(slot_id)
    if not success:
        raise HTTPException(status_code=404, detail="卡槽不存在或未上传")
    notifier.trigger_sync_background()
    return {"status": "ok", "message": f"卡槽 {slot_id} 已删除"}

@app.get("/api/album/preview/{slot_id}.png")
async def get_album_preview(slot_id: int):
    validate_slot_id(slot_id)
    png_path = os.path.join(album_mgr.photos_dir, f"slot_{slot_id}.png")
    if not os.path.exists(png_path):
        raise HTTPException(status_code=404, detail="预览图不存在")
    return FileResponse(png_path, media_type="image/png")

# ----------------- 排程规则 API -----------------

@app.get("/api/schedule")
async def get_schedule():
    active_rule, active_mode, next_pull = scheduler.get_current_rule(
        fallback_rotate_min=settings_mgr.settings.rotate_interval_min
    )
    return {
        "config": scheduler.config.model_dump(),
        "active_rule": active_rule.model_dump() if active_rule else None,
        "active_mode": active_mode,
        "next_pull_sec": next_pull
    }

@app.post("/api/schedule")
async def update_schedule(config: ScheduleConfig):
    scheduler.save_config(config)
    notifier.trigger_sync_background()
    return {"status": "ok", "message": "排程配置已保存"}

# ----------------- 系统设置与网关联动 API -----------------

@app.get("/api/settings")
async def get_settings():
    return settings_mgr.settings.model_dump()

@app.post("/api/settings")
async def update_settings(settings: ServerSettingsUpdate):
    changes = settings.model_dump(exclude_unset=True)
    updated = settings_mgr.update(changes)
    notifier.set_gateway_url(updated.gateway_url)
    weather_mgr.default_city = updated.weather_city
    if "calendar_ical_url" in changes:
        calendar_mgr.set_ical_url(updated.calendar_ical_url)
    if "weather_city" in changes or "rotate_interval_min" in changes or "calendar_ical_url" in changes:
        notifier.trigger_sync_background()
    return {"status": "ok", "message": "系统设置已更新"}

# ----------------- 气象信息 API (wttr.in) -----------------

@app.get("/api/weather")
async def get_weather(city: Optional[str] = Query(None, max_length=100)):
    target_city = city if city is not None else settings_mgr.settings.weather_city
    return weather_mgr.get_weather(target_city)

@app.post("/api/weather/refresh")
async def refresh_weather(city: Optional[str] = Query(None, max_length=100)):
    target_city = city if city is not None else settings_mgr.settings.weather_city
    data = weather_mgr.get_weather(target_city, force_refresh=True)
    notifier.trigger_sync_background()
    return {"status": "ok", "message": "天气数据已强制更新并触发网关同步", "data": data}

@app.get("/api/weather/preview.png")
async def get_weather_preview(city: Optional[str] = Query(None, max_length=100)):
    target_city = city if city is not None else settings_mgr.settings.weather_city
    weather_data = weather_mgr.get_weather(target_city)
    raw_bin = render_weather_image(
        weather_data,
        width=settings_mgr.settings.screen_width,
        height=settings_mgr.settings.screen_height
    )
    img = raw_to_image(raw_bin, width=settings_mgr.settings.screen_width, height=settings_mgr.settings.screen_height)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-cache"})

# ----------------- 在线日历看板 API (iCal / Webcal) -----------------

@app.get("/api/calendar")
async def get_calendar(url: Optional[str] = Query(None, max_length=1024)):
    custom_url = url if url is not None else None
    return calendar_mgr.fetch_calendar_data(custom_url=custom_url)

@app.post("/api/calendar/refresh")
async def refresh_calendar(url: Optional[str] = Query(None, max_length=1024)):
    custom_url = url if url is not None else None
    data = calendar_mgr.fetch_calendar_data(force_refresh=True, custom_url=custom_url)
    notifier.trigger_sync_background()
    return {"status": "ok", "message": data.get("message", "日历数据已刷新"), "data": data}

@app.get("/api/calendar/preview.png")
async def get_calendar_preview(url: Optional[str] = Query(None, max_length=1024)):
    custom_url = url if url is not None else None
    calendar_data = calendar_mgr.fetch_calendar_data(custom_url=custom_url)
    raw_bin = render_calendar_image(
        calendar_data,
        width=settings_mgr.settings.screen_width,
        height=settings_mgr.settings.screen_height
    )
    img = raw_to_image(raw_bin, width=settings_mgr.settings.screen_width, height=settings_mgr.settings.screen_height)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-cache"})

@app.post("/api/trigger")
async def manual_trigger_gateway():
    """
    手动触发网关立即拉取同步
    """
    success = await notifier.trigger_sync()
    return {
        "status": "ok" if success else "failed",
        "message": "已成功向网关发送触发指令" if success else "网关连接超时或未响应"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

