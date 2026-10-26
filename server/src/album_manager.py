import io
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from persistence import atomic_write_bytes
from src.renderer import raw_to_image

TOTAL_SLOTS = 3
FRAME_BYTES = 30000

class AlbumManager:
    def __init__(self, data_dir: str):
        self.photos_dir = os.path.join(data_dir, "photos")
        os.makedirs(self.photos_dir, exist_ok=True)

    def _get_bin_path(self, slot_id: int) -> str:
        return os.path.join(self.photos_dir, f"slot_{slot_id}.bin")

    def _get_png_path(self, slot_id: int) -> str:
        return os.path.join(self.photos_dir, f"slot_{slot_id}.png")

    def list_slots(self) -> List[Dict[str, Any]]:
        slots = []
        for i in range(1, TOTAL_SLOTS + 1):
            bin_path = self._get_bin_path(i)
            updated_at = ""
            size = 0
            try:
                stat = os.stat(bin_path)
                exists = True
                size = stat.st_size
                updated_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except FileNotFoundError:
                exists = False

            slots.append({
                "id": i,
                "exists": exists,
                "size": size,
                "updated_at": updated_at,
                "preview_url": f"/api/album/preview/{i}.png" if exists else None
            })
        return slots

    def save_slot(self, slot_id: int, bin_data: bytes) -> bool:
        if slot_id < 1 or slot_id > TOTAL_SLOTS:
            raise ValueError(f"卡槽 ID 必须在 1~{TOTAL_SLOTS} 之间")
        if len(bin_data) != FRAME_BYTES:
            raise ValueError(f"点阵大小必须恰好为 {FRAME_BYTES} 字节")

        preview = io.BytesIO()
        raw_to_image(bin_data, 400, 300).save(preview, "PNG")
        atomic_write_bytes(self._get_png_path(slot_id), preview.getvalue())
        atomic_write_bytes(self._get_bin_path(slot_id), bin_data)
        return True

    def delete_slot(self, slot_id: int) -> bool:
        if slot_id < 1 or slot_id > TOTAL_SLOTS:
            return False
        existed = False
        try:
            os.unlink(self._get_bin_path(slot_id))
            existed = True
        except FileNotFoundError:
            pass
        try:
            os.unlink(self._get_png_path(slot_id))
        except FileNotFoundError:
            pass
        return existed

    def get_existing_slots(self) -> List[int]:
        existing = []
        for i in range(1, TOTAL_SLOTS + 1):
            if os.path.exists(self._get_bin_path(i)):
                existing.append(i)
        return existing

    def get_active_photo_info(self, rotate_interval_min: int = 60, now: Optional[float] = None) -> tuple[Optional[int], Optional[bytes]]:
        existing = self.get_existing_slots()
        if not existing:
            return None, None

        if type(rotate_interval_min) is not int or not 10 <= rotate_interval_min <= 1440:
            raise ValueError("相册轮换间隔必须是 10~1440 分钟之间的整数")
        interval_sec = rotate_interval_min * 60
        current_time = time.time() if now is None else now
        idx = int(current_time // interval_sec) % len(existing)
        slot_id = existing[idx]

        try:
            with open(self._get_bin_path(slot_id), "rb") as handle:
                return slot_id, handle.read(FRAME_BYTES + 1)
        except FileNotFoundError:
            return None, None
