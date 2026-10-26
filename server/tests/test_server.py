import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

_import_dir = tempfile.TemporaryDirectory()
os.environ["EPD_DATA_DIR"] = _import_dir.name

import main
from src.album_manager import FRAME_BYTES, AlbumManager
from src.gateway_notifier import GatewayNotifier
from src.memo_manager import MemoManager
from src.models import MemoRequest, MemoState, ScheduleConfig, ServerSettings, validate_gateway_url
from src.renderer import render_memo_image, render_sleep_image
from src.scheduler import Scheduler
from src.settings_manager import SettingsManager
from src.calendar_manager import CalendarManager


def tearDownModule():
    _import_dir.cleanup()


class ModelTests(unittest.TestCase):
    def test_schedule_rejects_invalid_values(self):
        base_rule = {
            "id": "rule_1",
            "name": "test",
            "start": "08:00",
            "end": "09:00",
            "mode": "photo_album",
            "config": {"rotate_interval_min": 60},
        }
        for changes in (
            {"start": "25:00"},
            {"end": "8:60"},
            {"start": "08:00", "end": "08:00"},
            {"mode": "unknown"},
            {"config": {"rotate_interval_min": "60"}},
            {"config": {"rotate_interval_min": 0}},
        ):
            rule = {**base_rule, **changes}
            with self.assertRaises(ValidationError):
                ScheduleConfig(rules=[rule])
        with self.assertRaises(ValidationError):
            ScheduleConfig(rules=[base_rule, base_rule])
        with self.assertRaises(ValidationError):
            ScheduleConfig(rules=[base_rule] * 65)

    def test_memo_rejects_unbounded_values(self):
        with self.assertRaises(ValidationError):
            MemoRequest(text="x" * 4001)
        with self.assertRaises(ValidationError):
            MemoRequest(text="ok", duration_min=10**12)
        with self.assertRaises(ValidationError):
            MemoState(active=True, text="ok", created_at=1, expire_at=float("inf"))

    def test_gateway_url_validation(self):
        self.assertEqual(validate_gateway_url("http://192.168.1.2/"), "http://192.168.1.2")
        for value in (
            "http://localhost",
            "http://127.0.0.1",
            "http://[::1]",
            "http://169.254.1.2",
            "http://user:pass@192.168.1.2",
            "http://192.168.1.2/path",
            "http://192.168.1.2?x=1",
            "http://192.168.1.2#fragment",
            "file:///tmp/gateway",
        ):
            with self.assertRaises(ValueError):
                validate_gateway_url(value)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.scheduler = Scheduler(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_first_rule_wins_and_cross_midnight(self):
        config = ScheduleConfig(rules=[
            {"id": "a", "name": "A", "start": "22:00", "end": "10:00", "mode": "clock", "config": {}},
            {"id": "b", "name": "B", "start": "23:00", "end": "23:30", "mode": "sleep_dnd", "config": {}},
        ])
        self.scheduler.save_config(config)
        active, mode, _ = self.scheduler.get_current_rule(datetime(2026, 1, 1, 23, 15))
        self.assertEqual(active.id, "a")
        self.assertEqual(mode, "clock")
        active, _, _ = self.scheduler.get_current_rule(datetime(2026, 1, 2, 9, 59))
        self.assertEqual(active.id, "a")

    def test_imminent_event_returns_minimum_delay(self):
        config = ScheduleConfig(rules=[
            {"id": "a", "name": "A", "start": "08:00", "end": "09:00", "mode": "clock", "config": {}},
            {"id": "b", "name": "B", "start": "09:00", "end": "10:00", "mode": "sleep_dnd", "config": {}},
        ])
        self.scheduler.save_config(config)
        _, _, delay = self.scheduler.get_current_rule(datetime(2026, 1, 1, 8, 59, 59))
        self.assertEqual(delay, 30)

    def test_fallback_album_rotation_is_a_candidate(self):
        self.scheduler.save_config(ScheduleConfig(rules=[], fallback_mode="photo_album"))
        now = datetime(2026, 1, 1, 0, 0, 30)
        _, mode, delay = self.scheduler.get_current_rule(now, fallback_rotate_min=10)
        expected = max(30, 600 - int(now.timestamp() % 600))
        self.assertEqual(mode, "photo_album")
        self.assertEqual(delay, min(3600, expected))

    def test_save_failure_does_not_change_memory(self):
        original = self.scheduler.config
        updated = ScheduleConfig(rules=[], fallback_mode="clock")
        with patch("src.scheduler.atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.scheduler.save_config(updated)
        self.assertIs(self.scheduler.config, original)

    def test_corrupt_file_is_not_overwritten(self):
        with open(self.scheduler.config_file, "w", encoding="utf-8") as handle:
            handle.write("{broken")
        with self.assertRaises(RuntimeError):
            Scheduler(self.temp.name)
        with open(self.scheduler.config_file, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "{broken")


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = SettingsManager(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_partial_update_preserves_other_fields(self):
        original_duration = self.manager.settings.default_memo_duration_min
        updated = self.manager.update({"gateway_url": "http://192.168.1.50"})
        self.assertEqual(updated.default_memo_duration_min, original_duration)
        self.assertEqual(updated.gateway_url, "http://192.168.1.50")

    def test_save_failure_preserves_current_settings(self):
        original = self.manager.settings
        with patch("src.settings_manager.atomic_write_json", side_effect=OSError("read only")):
            with self.assertRaises(OSError):
                self.manager.save(ServerSettings(gateway_url="http://192.168.1.60"))
        self.assertIs(self.manager.settings, original)


class MemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = MemoManager(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_lifecycle_clears_sensitive_content(self):
        with patch("src.memo_manager.render_memo_image", return_value=b"x" * FRAME_BYTES):
            state = self.manager.set_memo("secret", title="title", sender="sender")
            self.assertTrue(self.manager.is_active(state.created_at + 1))
            self.manager.clear_memo()
        current = self.manager.get_state()
        self.assertFalse(current.active)
        self.assertEqual(current.text, "")
        self.assertEqual(current.title, "")
        with open(self.manager.memo_file, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        self.assertEqual(saved["text"], "")
        self.assertNotIn("secret", json.dumps(saved))

    def test_natural_expiry_clears_state(self):
        with patch("src.memo_manager.render_memo_image", return_value=b"x" * FRAME_BYTES):
            state = self.manager.set_memo("secret")
        self.assertFalse(self.manager.is_active(state.expire_at))
        self.assertEqual(self.manager.get_state().text, "")

    def test_render_or_write_failure_preserves_previous_state(self):
        with patch("src.memo_manager.render_memo_image", return_value=b"x" * FRAME_BYTES):
            original = self.manager.set_memo("old")
        with patch("src.memo_manager.render_memo_image", side_effect=ValueError("render")):
            with self.assertRaises(ValueError):
                self.manager.set_memo("new")
        self.assertEqual(self.manager.get_state().text, "old")
        with patch("src.memo_manager.render_memo_image", return_value=b"x" * FRAME_BYTES):
            with patch("src.memo_manager.atomic_write_json", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    self.manager.set_memo("new")
        self.assertEqual(self.manager.get_state().text, "old")


class AlbumTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = AlbumManager(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_slot_round_trip_and_delete_semantics(self):
        self.assertFalse(self.manager.delete_slot(1))
        data = b"\xff" * FRAME_BYTES
        self.manager.save_slot(1, data)
        _, loaded = self.manager.get_active_photo_info(60, now=0)
        self.assertEqual(loaded, data)
        self.assertTrue(self.manager.delete_slot(1))
        self.assertFalse(self.manager.delete_slot(1))

    def test_invalid_length_does_not_create_files(self):
        with self.assertRaises(ValueError):
            self.manager.save_slot(1, b"short")
        self.assertFalse(os.path.exists(self.manager._get_bin_path(1)))
        self.assertFalse(os.path.exists(self.manager._get_png_path(1)))


class RendererTests(unittest.TestCase):
    def test_sleep_cache_is_keyed_by_dimensions(self):
        default = render_sleep_image()
        taller = render_sleep_image(400, 301)
        self.assertEqual(len(default), FRAME_BYTES)
        self.assertEqual(len(taller), 30100)
        self.assertNotEqual(default, taller)
        self.assertIs(render_sleep_image(), default)

    def test_long_memo_fields_render_with_fixed_length(self):
        data = render_memo_image("title" * 80, "body\n" * 1000, "sender" * 80, 4102444800)
        self.assertEqual(len(data), FRAME_BYTES)


class FakeStreamResponse:
    def __init__(self):
        self.status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        await asyncio.sleep(0.02)
        yield b'{"status":"ok"}'


class FakeAsyncClient:
    urls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url):
        self.urls.append(url)
        return FakeStreamResponse()


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_endpoint_and_single_flight(self):
        notifier = GatewayNotifier("http://192.168.1.70")
        FakeAsyncClient.urls = []
        with patch("src.gateway_notifier.httpx.AsyncClient", FakeAsyncClient):
            results = await asyncio.gather(notifier.trigger_sync(), notifier.trigger_sync())
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(FakeAsyncClient.urls, ["http://192.168.1.70/api/trigger"])

    async def test_invalid_url_is_rejected_before_network(self):
        notifier = GatewayNotifier()
        with self.assertRaises(ValueError):
            notifier.set_gateway_url("http://127.0.0.1")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        main.settings_mgr = SettingsManager(self.temp.name)
        main.scheduler = Scheduler(self.temp.name)
        main.scheduler.save_config(ScheduleConfig(rules=[], fallback_mode="photo_album"))
        main.album_mgr = AlbumManager(self.temp.name)
        main.memo_mgr = MemoManager(self.temp.name)
        main.calendar_mgr = CalendarManager(self.temp.name)
        main.notifier = Mock()
        main.notifier.trigger_sync = AsyncMock(return_value=True)
        self.render_patcher = patch("src.memo_manager.render_memo_image", return_value=b"\x00" * FRAME_BYTES)
        self.render_patcher.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.render_patcher.stop()
        self.temp.cleanup()

    def test_invalid_schedule_is_not_persisted(self):
        before = main.scheduler.config_file
        with open(before, "r", encoding="utf-8") as handle:
            original = handle.read()
        response = self.client.post("/api/schedule", json={
            "rules": [{"id": "bad", "name": "bad", "start": "99:99", "end": "10:00", "mode": "clock", "config": {}}],
            "fallback_mode": "clock",
        })
        self.assertEqual(response.status_code, 422)
        with open(before, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)

    def test_request_body_limit_and_slot_validation(self):
        response = self.client.post("/api/album/slot/1", content=b"x" * 65537)
        self.assertEqual(response.status_code, 413)
        response = self.client.post("/api/album/slot/1", content=iter([b"x" * 40000, b"x" * 30000]))
        self.assertEqual(response.status_code, 413)
        response = self.client.post("/api/album/slot/4", content=b"x" * FRAME_BYTES)
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/album/slot/1", content=b"short")
        self.assertEqual(response.status_code, 400)

    def test_upload_etag_and_next_pull_contract(self):
        data = b"\xff" * FRAME_BYTES
        response = self.client.post("/api/album/slot/1", content=data)
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/screen.bin")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, data)
        self.assertTrue(30 <= int(response.headers["X-Next-Pull"]) <= 3600)
        etag = response.headers["ETag"]
        response = self.client.get("/screen.bin", headers={"If-None-Match": f'"other", W/{etag}'})
        self.assertEqual(response.status_code, 304)
        response = self.client.get("/screen.bin", headers={"If-None-Match": "*"})
        self.assertEqual(response.status_code, 304)

    def test_memo_validation_default_duration_and_clear(self):
        response = self.client.post("/api/push", json={"text": "ok", "duration_min": 10**12})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/settings", json={"default_memo_duration_min": 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(main.settings_mgr.settings.gateway_url, "http://192.168.1.118")
        response = self.client.post("/api/push", json={"text": "secret"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["memo"]["duration_min"], 5)
        response = self.client.delete("/api/push")
        self.assertEqual(response.status_code, 200)
        status = self.client.get("/api/memo/status").json()
        self.assertFalse(status["active"])
        self.assertEqual(status["text"], "")

    def test_invalid_gateway_url_does_not_replace_settings(self):
        original = main.settings_mgr.settings.gateway_url
        response = self.client.post("/api/settings", json={"gateway_url": "http://127.0.0.1"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(main.settings_mgr.settings.gateway_url, original)
        response = self.client.post("/api/settings", json={"default_memo_duration_min": None})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(main.settings_mgr.settings.gateway_url, original)

    def test_weather_feature_and_screen_rendering(self):
        # 1. 测试 Settings 设置天气城市
        response = self.client.post("/api/settings", json={"weather_city": "Beijing"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(main.settings_mgr.settings.weather_city, "Beijing")
        self.assertEqual(main.weather_mgr.default_city, "Beijing")

        # 2. Mock 天气数据注入缓存
        fake_weather = {
            "city": "Beijing",
            "temp_c": "22",
            "feels_like_c": "22",
            "humidity": "45",
            "weather_desc": "晴",
            "wind": "北风 15km/h",
            "temp_min": "12",
            "temp_max": "24",
            "forecast": [
                {"label": "今天", "date": "2026-10-25", "desc": "晴", "temp_min": "12", "temp_max": "24"},
                {"label": "明天", "date": "2026-10-26", "desc": "多云", "temp_min": "11", "temp_max": "21"}
            ],
            "update_time": "12:00",
            "stale": False,
            "source": "wttr.in"
        }
        main.weather_mgr._save_cache("Beijing", fake_weather)

        # 3. GET /api/weather 接口测试
        response = self.client.get("/api/weather")
        self.assertEqual(response.status_code, 200)
        w_data = response.json()
        self.assertEqual(w_data["city"], "Beijing")
        self.assertEqual(w_data["temp_c"], "22")
        self.assertEqual(w_data["weather_desc"], "晴")

        # 4. 渲染天气画面测试
        from src.renderer import render_weather_image
        raw = render_weather_image(fake_weather, 400, 300)
        self.assertEqual(len(raw), 30000)

        # 5. 排程切换为 weather_date 并在 /screen.bin 输出
        rule = {
            "rules": [
                {
                    "id": "rule_weather",
                    "name": "白天天气模式",
                    "start": "00:00",
                    "end": "23:59",
                    "mode": "weather_date",
                    "config": {}
                }
            ],
            "fallback_mode": "weather_date"
        }
        sched_resp = self.client.post("/api/schedule", json=rule)
        self.assertEqual(sched_resp.status_code, 200)

        # 清除任何置顶便签确保进入排程
        self.client.delete("/api/push")

        screen_resp = self.client.get("/screen.bin")
        self.assertEqual(screen_resp.status_code, 200)
        self.assertEqual(len(screen_resp.content), 30000)

    def test_calendar_integration(self):
        from src.calendar_manager import CalendarManager
        from src.renderer import render_calendar_image

        # 1. 测试 URL 规范化
        self.assertEqual(
            CalendarManager.normalize_url("webcal://example.com/cal.ics"),
            "https://example.com/cal.ics"
        )
        self.assertEqual(
            CalendarManager.normalize_url("https://example.com/cal.ics"),
            "https://example.com/cal.ics"
        )

        # 2. 测试 mock 日程获取
        cm = CalendarManager(self.temp.name)
        cal_data = cm.fetch_calendar_data()
        self.assertEqual(cal_data["status"], "ok")
        self.assertTrue(len(cal_data["events"]) > 0)

        # 3. 测试 400x300 日历点阵渲染
        raw = render_calendar_image(cal_data, 400, 300)
        self.assertEqual(len(raw), 30000)

        # 4. 测试 API 接口
        resp = self.client.get("/api/calendar")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

        preview_resp = self.client.get("/api/calendar/preview.png")
        self.assertEqual(preview_resp.status_code, 200)
        self.assertEqual(preview_resp.headers["content-type"], "image/png")
