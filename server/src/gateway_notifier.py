import asyncio
import json
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

    async def trigger_sync(self) -> bool:
        if self._trigger_lock.locked():
            return False
        target_url = f"{self.gateway_url}/api/trigger"
        async with self._trigger_lock:
            try:
                timeout = httpx.Timeout(5.0, connect=3.0, read=3.0, write=3.0, pool=1.0)
                limits = httpx.Limits(max_connections=2, max_keepalive_connections=0)
                async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False) as client:
                    async with client.stream("POST", target_url) as response:
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
                print(f"[GatewayNotifier] 触发网关失败: {exc}")
                return False

    def trigger_sync_background(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.trigger_sync())
            return
        if self._background_task is not None and not self._background_task.done():
            return
        self._background_task = loop.create_task(self.trigger_sync())
