import pytest
from pathlib import Path
from job_cd.providers.database import SQLiteDatabaseAdapter
from job_cd.providers.cache import LocalCache
from job_cd.core.config import ConfigManager


def test_database_adapter_uses_config_path(tmp_path, monkeypatch):
    """Test that SQLiteDatabaseAdapter uses the path from ConfigManager by default."""

    # 1. ARRANGE: Set up an isolated temporary directory for this specific test
    base_dir = tmp_path / "jobcd_test"
    test_cm = ConfigManager(base_path=base_dir)

    print(f"\n--- test_database_adapter ---")
    print(f"Mocked Base Dir: {base_dir}")

    # Intercept the global config_manager inside the database module
    # and replace it with our test_cm so it doesn't touch the real OS.
    monkeypatch.setattr("job_cd.providers.database.config_manager", test_cm)

    # 2. ACT: Initialize the database (This triggers _initialize_db under the hood)
    db = SQLiteDatabaseAdapter()

    print(f"Database Path Generated: {db.db_path}")
    print(f"Database Created on Init? {db.db_path.exists()}")
    print("--------------------------------\n")

    # 3. ASSERT: Verify the path routing and that the SQLite file was actually generated
    assert db.db_path == base_dir / "job_history.db"
    assert db.db_path.exists()


def test_cache_uses_config_path(tmp_path, monkeypatch):
    """Test that LocalCache uses the path from ConfigManager and creates files lazily."""

    # 1. ARRANGE: Set up an isolated temporary directory
    base_dir = tmp_path / "jobcd_test"
    test_cm = ConfigManager(base_path=base_dir)

    print(f"\n--- test_cache_uses_config_path ---")

    # Intercept the global config_manager inside the cache module
    monkeypatch.setattr("job_cd.providers.cache.config_manager", test_cm)

    # 2. ACT (Phase 1): Initialize the cache instance
    cache = LocalCache(filename="test_cache.json")
    expected_path = base_dir / ".cache" / "test_cache.json"

    print(f"Expected Cache Path: {expected_path}")
    print(f"File Exists on Init? {expected_path.exists()} (Expected: False - Lazy Init)")

    # 3. ASSERT (Phase 1): Verify the path is routed correctly, but the disk is UNTOUCHED.
    assert cache.filepath == expected_path
    assert not expected_path.exists()

    # 4. ACT (Phase 2): Trigger an atomic save to the disk
    print("Saving data to cache...")
    cache.set("test_key", {"status": "success"})

    print(f"File Exists after Set? {expected_path.exists()} (Expected: True)")
    print(f"Retrieved Data: {cache.get('test_key')}")
    print("--------------------------------------\n")

    # 5. ASSERT (Phase 2): Verify the new io.py utility safely created the file and saved the data
    assert expected_path.exists()
    assert cache.get("test_key") == {"status": "success"}