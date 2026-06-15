from typing import Optional

from job_cd.core.config import config_manager
from job_cd.core.interfaces import CacheStrategy
from job_cd.core.io import read_json, write_json


class LocalCache(CacheStrategy):
    """
    Stores key-value pairs in a local JSON file.
    """
    def __init__(self, filename: str = 'contacts.json') -> None:
        self.filepath = config_manager.get_cache_path(filename)

    def get(self, key: str) -> Optional[dict]:
        data = read_json(self.filepath)
        return data.get(key)

    def set(self, key: str, value: dict) -> None:
        data = read_json(self.filepath)
        data[key] = value
        write_json(self.filepath, data)