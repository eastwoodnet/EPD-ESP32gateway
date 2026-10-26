import json
import os

from src.models import ServerSettings
from persistence import atomic_write_json


class SettingsManager:
    def __init__(self, data_dir: str):
        self.settings_file = os.path.join(data_dir, "settings.json")
        self.settings = self._load()

    def _load(self) -> ServerSettings:
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as handle:
                    return ServerSettings(**json.load(handle))
            except Exception as exc:
                raise RuntimeError(f"读取 settings.json 失败: {exc}") from exc
        settings = ServerSettings()
        atomic_write_json(self.settings_file, settings.model_dump())
        return settings

    def save(self, settings: ServerSettings) -> None:
        atomic_write_json(self.settings_file, settings.model_dump())
        self.settings = settings

    def update(self, changes: dict) -> ServerSettings:
        data = self.settings.model_dump()
        data.update(changes)
        settings = ServerSettings(**data)
        self.save(settings)
        return settings
