import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.renderer import raw_to_image

TOTAL_SLOTS = 3  # 用户指定：3个相册卡槽

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
            exists = os.path.exists(bin_path)
            updated_at = ""
            size = 0
            if exists:
                stat = os.stat(bin_path)
                size = stat.st_size
                updated_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

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

        # 400x300 三色点阵应为 30,000 字节
        bin_path = self._get_bin_path(slot_id)
        with open(bin_path, "wb") as f:
            f.write(bin_data)

        # 同时生成一份 PNG 预览图，供前端直接展示
        try:
            png_path = self._get_png_path(slot_id)
            img = raw_to_image(bin_data, 400, 300)
            img.save(png_path, "PNG")
        except Exception as e:
            print(f"[AlbumManager] 生成预览图失败: {e}")

        return True

    def delete_slot(self, slot_id: int) -> bool:
        if slot_id < 1 or slot_id > TOTAL_SLOTS:
            return False
        bin_path = self._get_bin_path(slot_id)
        png_path = self._get_png_path(slot_id)
        if os.path.exists(bin_path):
            os.remove(bin_path)
        if os.path.exists(png_path):
            os.remove(png_path)
        return True

    def get_existing_slots(self) -> List[int]:
        existing = []
        for i in range(1, TOTAL_SLOTS + 1):
            if os.path.exists(self._get_bin_path(i)):
                existing.append(i)
        return existing

    def get_active_photo_info(self, rotate_interval_min: int = 60) -> tuple[Optional[int], Optional[bytes]]:
        """
        无状态轮换算法：
        根据当前时间和轮播间隔，数学计算当前应展示哪张照片
        """
        existing = self.get_existing_slots()
        if not existing:
            return None, None

        if rotate_interval_min <= 0:
            rotate_interval_min = 60

        interval_sec = rotate_interval_min * 60
        idx = int(time.time() // interval_sec) % len(existing)
        slot_id = existing[idx]

        bin_path = self._get_bin_path(slot_id)
        if os.path.exists(bin_path):
            with open(bin_path, "rb") as f:
                return slot_id, f.read()
        return None, None
