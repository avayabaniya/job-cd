import os
from pathlib import Path
import typer

from job_cd.core.io import read_json, write_json

class ConfigManager:
    """
    Manages global configuration paths, directory structures, and state for job-cd.
    """

    def __init__(self, app_name: str = "jobcd", base_path: Path = None):
        # 1. Check for system environment variable override (for CI/CD or power users)
        env_dir = os.environ.get(f"{app_name.upper()}_CONFIG_DIR")

        # 2. Resolve the base directory
        if base_path:
            self.app_dir = Path(base_path)
        elif env_dir:
            self.app_dir = Path(env_dir)
        else:
            self.app_dir = Path(typer.get_app_dir(app_name))

        # 3. Define subdirectories
        self.cache_dir = self.app_dir / ".cache"
        self.prompts_dir = self.app_dir / "prompts"

    def ensure_dirs(self):
        """Explicitly called via `jobcd init` or lazily before writing data."""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    # --- Path Properties ---
    @property
    def db_path(self) -> Path:
        return self.app_dir / "job_history.db"

    @property
    def env_path(self) -> Path:
        return self.app_dir / ".env"

    @property
    def profiles_path(self) -> Path:
        return self.cache_dir / "profiles.json"

    @property
    def contacts_cache_path(self) -> Path:
        return self.cache_dir / "contacts.json"

    def get_cache_path(self, filename: str) -> Path:
        """Returns a Path object for a specific file inside the cache directory."""
        return self.cache_dir / filename

# Export as a singleton to be imported across the application
config_manager = ConfigManager()