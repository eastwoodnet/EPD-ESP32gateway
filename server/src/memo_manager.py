import json
import os
import time
from typing import Optional

from src.models import MemoState
from persistence import atomic_write_json
from src.renderer import render_memo_image


class MemoManager:
    def __init__(self, data_dir: str):
        self.memo_file = os.path.join(data_dir, "memo.json")
        self._cached_bin: Optional[bytes] = None
        self._state = self._load()

    def _load(self) -> MemoState:
        if not os.path.exists(self.memo_file):
            return MemoState()
        try:
            with open(self.memo_file, "r", encoding="utf-8") as handle:
                state = MemoState(**json.load(handle))
        except Exception as exc:
            raise RuntimeError(f"读取 memo.json 失败: {exc}") from exc
        if not state.active and (state.title or state.text or state.sender or state.created_at or state.expire_at):
            state = MemoState()
            atomic_write_json(self.memo_file, state.model_dump())
        return state

    def _write_state(self, state: MemoState) -> None:
        atomic_write_json(self.memo_file, state.model_dump())

    def set_memo(self, text: str, title: str = "📌 桌面备忘提醒", duration_min: int = 120, sender: str = "手机推送", theme: str = "red_alert") -> MemoState:
        now = time.time()
        state = MemoState(
            active=True,
            title=title,
            text=text,
            created_at=now,
            expire_at=now + duration_min * 60,
            duration_min=duration_min,
            sender=sender,
            theme=theme
        )
        rendered = render_memo_image(state.title, state.text, state.sender, state.expire_at)
        self._write_state(state)
        self._state = state
        self._cached_bin = rendered
        return state

    def clear_memo(self):
        state = MemoState()
        self._write_state(state)
        self._state = state
        self._cached_bin = None

    def is_active(self, now: Optional[float] = None) -> bool:
        if not self._state.active:
            return False
        current_time = time.time() if now is None else now
        if current_time < self._state.expire_at:
            return True
        try:
            self.clear_memo()
        except Exception as exc:
            self._state = MemoState()
            self._cached_bin = None
            print(f"[MemoManager] 持久化过期便签状态失败: {exc}")
        return False

    def get_state(self) -> MemoState:
        self.is_active()
        return self._state if self._state.active else MemoState()

    def get_bin_data(self) -> Optional[bytes]:
        if not self.is_active():
            return None
        if self._cached_bin is None:
            rendered = render_memo_image(
                self._state.title,
                self._state.text,
                self._state.sender,
                self._state.expire_at
            )
            self._cached_bin = rendered
        return self._cached_bin
