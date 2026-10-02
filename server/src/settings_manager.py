import os
import json
from src.models import ServerSettings

class SettingsManager:
    def __init__(self, data_dir: str):
        self.settings_file = os.path.join(data_dir, "settings.json")
        self.settings = self._load()

    def _load(self) -> ServerSettings:
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return ServerSettings(**data)
            except Exception as e:
                print(f"[SettingsManager] 读取 settings.json 失败: {e}")
        s = ServerSettings()
        self.save(s)
        return s

    def save(self, settings: ServerSettings):
        self.settings = settings
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings.model_dump(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SettingsManager] 保存 settings.json 失败: {e}")
