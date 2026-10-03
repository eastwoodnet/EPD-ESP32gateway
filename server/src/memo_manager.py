import os
import json
import time
from typing import Optional
from src.models import MemoState
from src.renderer import render_memo_image

class MemoManager:
    def __init__(self, data_dir: str):
        self.memo_file = os.path.join(data_dir, "memo.json")
        self._cached_bin: Optional[bytes] = None
        self._state = self._load()

    def _load(self) -> MemoState:
        if os.path.exists(self.memo_file):
            try:
                with open(self.memo_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return MemoState(**data)
            except Exception as e:
                print(f"[MemoManager] 读取 memo.json 失败: {e}")
        return MemoState()

    def _save(self):
        try:
            with open(self.memo_file, "w", encoding="utf-8") as f:
                json.dump(self._state.model_dump(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[MemoManager] 保存 memo.json 失败: {e}")

    def set_memo(self, text: str, title: str = "📌 桌面备忘提醒", duration_min: int = 120, sender: str = "手机推送", theme: str = "red_alert") -> MemoState:
        now = time.time()
        # 用户可自主设定时长（分钟）
        if duration_min <= 0:
            duration_min = 120

        expire_at = now + (duration_min * 60)

        self._state = MemoState(
            active=True,
            title=title,
            text=text,
            created_at=now,
            expire_at=expire_at,
            duration_min=duration_min,
            sender=sender,
            theme=theme
        )
        self._save()

        # 即刻预生成 30,000 字节点阵
        try:
            self._cached_bin = render_memo_image(title, text, sender, expire_at)
        except Exception as e:
            print(f"[MemoManager] 渲染便签点阵失败: {e}")
            self._cached_bin = None

        return self._state

    def clear_memo(self):
        self._state.active = False
        self._cached_bin = None
        self._save()

    def is_active(self) -> bool:
        if not self._state.active:
            return False
        if time.time() >= self._state.expire_at:
            # 已到期，自动退出插播
            self._state.active = False
            self._cached_bin = None
            self._save()
            return False
        return True

    def get_state(self) -> MemoState:
        # 实时同步过期判定
        self.is_active()
        return self._state

    def get_bin_data(self) -> Optional[bytes]:
        if not self.is_active():
            return None
        if self._cached_bin is None:
            self._cached_bin = render_memo_image(
                self._state.title,
                self._state.text,
                self._state.sender,
                self._state.expire_at
            )
        return self._cached_bin
