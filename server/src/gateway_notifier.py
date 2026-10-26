import asyncio
import json
import time
from typing import Optional

import httpx

from src.models import validate_gateway_url


class GatewayNotifier:
    def __init__(self, default_gateway_url: str = "http://192.168.1.118"):
        self.gateway_url = validate_gateway_url(default_gateway_url)
        self._trigger_lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None

    def set_gateway_url(self, url: str):
        self.gateway_url = validate_gateway_url(url)

    async def _post_gateway(
        self,
        path: str,
        payload_data: Optional[dict] = None,
        read_timeout: float = 3.0,
        delay_sec: float = 0.0
    ) -> bool:
        if delay_sec > 0:
            await asyncio.sleep(delay_sec)
        if self._trigger_lock.locked():
            return False
        target_url = f"{self.gateway_url}{path}"
        async with self._trigger_lock:
            try:
                timeout = httpx.Timeout(read_timeout + 2.0, connect=3.0, read=read_timeout, write=3.0, pool=1.0)
                limits = httpx.Limits(max_connections=2, max_keepalive_connections=0)
                async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False) as client:
                    req_kwargs = {"json": payload_data} if payload_data is not None else {}
                    async with client.stream("POST", target_url, **req_kwargs) as response:
                        if response.status_code != 200:
                            return False
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > 4096:
                                return False
                            body.extend(chunk)
                        if body:
                            try:
                                payload = json.loads(body)
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                return False
                            if isinstance(payload, dict) and payload.get("status") not in (None, "ok"):
                                return False
                return True
            except Exception as exc:
                print(f"[GatewayNotifier] 调用网关 {path} 失败: {exc}")
                return False

    async def trigger_sync(self) -> bool:
        return await self._post_gateway("/api/trigger", read_timeout=3.0)

    async def trigger_calendar_mode(
        self,
        timestamp: Optional[int] = None,
        timezone: int = 8,
        delay_sec: float = 0.0
    ) -> bool:
        ts = int(timestamp if timestamp is not None else time.time())
        return await self._post_gateway(
            "/api/ble/calendar",
            payload_data={"timestamp": ts, "timezone": timezone},
            read_timeout=25.0,
            delay_sec=delay_sec
        )

    def _run_background(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        if self._background_task is not None and not self._background_task.done():
            return
        self._background_task = loop.create_task(coro)

    def trigger_sync_background(self):
        self._run_background(self.trigger_sync())

    def trigger_calendar_mode_background(
        self,
        timestamp: Optional[int] = None,
        timezone: int = 8,
        delay_sec: float = 0.0
    ):
        self._run_background(self.trigger_calendar_mode(timestamp=timestamp, timezone=timezone, delay_sec=delay_sec))

