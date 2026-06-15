import pytest
from pathlib import Path
from job_cd.core.config import ConfigManager


def test_config_manager_paths(tmp_path):
    """Test that ConfigManager generates correct paths based on the base directory."""
    base_dir = tmp_path / "jobcd_test"
    cm = ConfigManager(base_path=base_dir)

    print(f"\n--- test_config_manager_paths ---")
    print(f"Base Directory: {base_dir}")
    print(f"  -> DB Path:       {cm.db_path}")
    print(f"  -> Env Path:      {cm.env_path}")
    print(f"  -> Profiles Path: {cm.profiles_path}")
    print(f"  -> Cache Path:    {cm.get_cache_path('test.json')}")
    print("------------------------------------\n")

    assert cm.db_path == base_dir / "job_history.db"
    assert cm.env_path == base_dir / ".env"
    assert cm.profiles_path == base_dir / ".cache" / "profiles.json"
    assert cm.contacts_cache_path == base_dir / ".cache" / "contacts.json"
    assert cm.get_cache_path("test.json") == base_dir / ".cache" / "test.json"


def test_config_manager_ensure_dirs(tmp_path):
    """Test that ensure_dirs creates the necessary directory structure."""
    base_dir = tmp_path / "jobcd_test"
    cm = ConfigManager(base_path=base_dir)

    print(f"\n--- test_config_manager_ensure_dirs ---")
    print(f"Base Directory: {base_dir}")
    print(f"  -> Exists BEFORE ensure_dirs(): {base_dir.exists()}")
    assert not base_dir.exists()

    cm.ensure_dirs()

    print(f"  -> Exists AFTER ensure_dirs():  {base_dir.exists()}")
    print(f"  -> Cache folder created?        {(base_dir / '.cache').exists()}")
    print(f"  -> Prompts folder created?      {(base_dir / 'prompts').exists()}")
    print("------------------------------------------\n")

    assert base_dir.exists()
    assert (base_dir / ".cache").exists()
    assert (base_dir / "prompts").exists()


def test_config_manager_default_path(monkeypatch):
    """Test that ConfigManager uses typer.get_app_dir by default."""
    mock_app_dir = "/mock/app/dir"
    monkeypatch.setattr("typer.get_app_dir", lambda name: mock_app_dir)

    cm = ConfigManager()

    print(f"\n--- test_config_manager_default_path ---")
    print(f"Mocked Typer App Dir: {mock_app_dir}")
    print(f"ConfigManager Result: {cm.app_dir}")
    print("-------------------------------------------\n")

    assert cm.app_dir == Path(mock_app_dir)