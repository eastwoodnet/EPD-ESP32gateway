import asyncio
import httpx

class GatewayNotifier:
    def __init__(self, default_gateway_url: str = "http://192.168.1.118"):
        self.gateway_url = default_gateway_url.rstrip("/")

    def set_gateway_url(self, url: str):
        self.gateway_url = url.rstrip("/")

    async def trigger_sync(self) -> bool:
        """
        向 ESP32 网关发送 /api/trigger 触发即时同步拉取
        """
        target_url = f"{self.gateway_url}/api/trigger"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(target_url)
                if res.status_code == 200:
                    print(f"[GatewayNotifier] 成功触发网关同步: {target_url}")
                    return True
                else:
                    print(f"[GatewayNotifier] 触发网关返回异常状态: {res.status_code}")
                    return False
        except Exception as e:
            print(f"[GatewayNotifier] 触发网关失败 ({target_url}): {e}")
            return False

    def trigger_sync_background(self):
        """
        在后台异步触发，不阻塞主接口响应
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.trigger_sync())
        except RuntimeError:
            asyncio.run(self.trigger_sync())
