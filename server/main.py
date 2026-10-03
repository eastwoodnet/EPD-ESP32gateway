import os
import hashlib
from typing import Optional
from fastapi import FastAPI, Request, Response, HTTPException, Body, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, JSONResponse

from src.models import ScheduleConfig, MemoRequest, ServerSettings
from src.scheduler import Scheduler
from src.memo_manager import MemoManager
from src.album_manager import AlbumManager, TOTAL_SLOTS
from src.settings_manager import SettingsManager
from src.gateway_notifier import GatewayNotifier
from src.renderer import render_clock_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "photos"), exist_ok=True)

app = FastAPI(title="EPD-ESP32gateway Server", description="墨水屏数据中继服务端")

# 挂载静态资源与模板
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# 初始化各核心管理器
settings_mgr = SettingsManager(DATA_DIR)
scheduler = Scheduler(DATA_DIR)
album_mgr = AlbumManager(DATA_DIR)
memo_mgr = MemoManager(DATA_DIR)
notifier = GatewayNotifier(settings_mgr.settings.gateway_url)

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

    # 1. 第一优先级: 即时便签插播
    if memo_mgr.is_active():
        bin_data = memo_mgr.get_bin_data()
        memo_state = memo_mgr.get_state()
        remain_sec = int(memo_state.expire_at - request.state.__dict__.get("time", 0))
        import time
        remain_sec = max(30, int(memo_state.expire_at - time.time()))
        next_pull_sec = min(remain_sec, 3600)

    # 2. 第二优先级: 24小时自由排程
    if bin_data is None:
        active_rule, active_mode, sched_next_pull = scheduler.get_current_rule()
        next_pull_sec = sched_next_pull

        if active_mode == "photo_album":
            rotate_interval = active_rule.config.get("rotate_interval_min", 60) if active_rule else 60
            slot_id, photo_bytes = album_mgr.get_active_photo_info(rotate_interval)
            if photo_bytes and len(photo_bytes) >= 15000:
                bin_data = photo_bytes
            else:
                # 尚未上传照片，回退到优雅时钟画面提示用户
                bin_data = render_clock_image(info="相册卡槽未配置，请在 Web 后台上传照片")

        elif active_mode == "sleep_dnd":
            # 免打扰模式：返回 304 让网关继续睡眠，或者保持最后画面
            # 如果客户端带有 ETag，直接 304；否则给一张极简黑白睡眠提示
            bin_data = render_clock_image(info="🌙 夜间免打扰模式中")

        elif active_mode == "clock":
            bin_data = render_clock_image()

        else:
            # 未来扩展的 calendar_todo 或 weather_date
            bin_data = render_clock_image(info=f"模式: {active_mode}")

    if not bin_data:
        bin_data = render_clock_image()

    # 计算内容 ETag 哈希
    content_hash = hashlib.md5(bin_data).hexdigest()
    etag = f'"{content_hash}"'

    # 检查客户端 If-None-Match 缓存头
    client_etag = request.headers.get("if-none-match")
    if client_etag and client_etag.strip() == etag:
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
    state = memo_mgr.set_memo(
        text=req.text,
        title=req.title,
        duration_min=req.duration_min,
        sender=req.sender,
        theme=req.theme
    )
    # 异步触发 ESP32 网关即刻同步
    notifier.set_gateway_url(settings_mgr.settings.gateway_url)
    notifier.trigger_sync_background()

    return {"status": "ok", "message": "便签已激活，并已通知网关立即同步", "memo": state.model_dump()}

@app.get("/api/push")
async def push_memo_get(
    text: str = Query(..., description="便签正文"),
    title: str = Query("📌 桌面备忘提醒", description="便签标题"),
    duration_min: int = Query(120, description="展示时长(分钟)"),
    sender: str = Query("快捷指令", description="发送者")
):
    """
    GET 方式推送便签（专为 iPhone 快捷指令与 Bark 风格设计）
    """
    state = memo_mgr.set_memo(
        text=text,
        title=title,
        duration_min=duration_min,
        sender=sender
    )
    notifier.set_gateway_url(settings_mgr.settings.gateway_url)
    notifier.trigger_sync_background()

    return {"status": "ok", "message": "便签已推送", "memo": state.model_dump()}

@app.delete("/api/push")
async def clear_memo():
    """
    手动撤回/清除当前便签
    """
    memo_mgr.clear_memo()
    notifier.set_gateway_url(settings_mgr.settings.gateway_url)
    notifier.trigger_sync_background()
    return {"status": "ok", "message": "便签已清除，已通知网关恢复常规排程"}

@app.get("/api/memo/status")
async def get_memo_status():
    return memo_mgr.get_state().model_dump()

# ----------------- 相册管理 API (3 卡槽) -----------------

@app.get("/api/album/slots")
async def list_album_slots():
    return {"slots": album_mgr.list_slots()}

@app.post("/api/album/slot/{slot_id}")
async def upload_album_slot(slot_id: int, request: Request):
    """
    接收前端 Canvas 调优后生成的 30,000 字节点阵并保存
    """
    body = await request.body()
    if len(body) != 30000:
        raise HTTPException(status_code=400, detail=f"点阵大小必须恰好为 30000 字节，当前为 {len(body)} 字节")

    album_mgr.save_slot(slot_id, body)
    return {"status": "ok", "message": f"卡槽 {slot_id} 保存成功"}

@app.delete("/api/album/slot/{slot_id}")
async def delete_album_slot(slot_id: int):
    success = album_mgr.delete_slot(slot_id)
    if not success:
        raise HTTPException(status_code=404, detail="卡槽不存在或未上传")
    return {"status": "ok", "message": f"卡槽 {slot_id} 已删除"}

@app.get("/api/album/preview/{slot_id}.png")
async def get_album_preview(slot_id: int):
    png_path = os.path.join(album_mgr.photos_dir, f"slot_{slot_id}.png")
    if not os.path.exists(png_path):
        raise HTTPException(status_code=404, detail="预览图不存在")
    return FileResponse(png_path, media_type="image/png")

# ----------------- 排程规则 API -----------------

@app.get("/api/schedule")
async def get_schedule():
    active_rule, active_mode, next_pull = scheduler.get_current_rule()
    return {
        "config": scheduler.config.model_dump(),
        "active_rule": active_rule.model_dump() if active_rule else None,
        "active_mode": active_mode,
        "next_pull_sec": next_pull
    }

@app.post("/api/schedule")
async def update_schedule(config: ScheduleConfig):
    scheduler.save_config(config)
    return {"status": "ok", "message": "排程配置已保存"}

# ----------------- 系统设置与网关联动 API -----------------

@app.get("/api/settings")
async def get_settings():
    return settings_mgr.settings.model_dump()

@app.post("/api/settings")
async def update_settings(settings: ServerSettings):
    settings_mgr.save(settings)
    notifier.set_gateway_url(settings.gateway_url)
    return {"status": "ok", "message": "系统设置已更新"}

@app.post("/api/trigger")
async def manual_trigger_gateway():
    """
    手动触发网关立即拉取同步
    """
    notifier.set_gateway_url(settings_mgr.settings.gateway_url)
    success = await notifier.trigger_sync()
    return {
        "status": "ok" if success else "failed",
        "message": "已成功向网关发送触发指令" if success else "网关连接超时或未响应"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

