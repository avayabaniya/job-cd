import json
from unittest.mock import MagicMock
from typer.testing import CliRunner
from job_cd.main import app
from job_cd.core.config import ConfigManager

runner = CliRunner()


def test_init_command(tmp_path, monkeypatch):
    """Test the 'init' command bootstrapping process."""
    base_dir = tmp_path / "jobcd_test"
    test_cm = ConfigManager(base_path=base_dir)

    print(f"\n[Test] Using temporary directory: {base_dir}")

    # Mock the global config_manager in main.py
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)
    # Mock the global config_manager in providers to avoid real path creation
    monkeypatch.setattr("job_cd.providers.database.config_manager", test_cm)
    monkeypatch.setattr("job_cd.providers.cache.config_manager", test_cm)

    # Mock typer.prompt to provide automated inputs
    user_inputs = (
        "mock-google-key\n"
        "mock-apollo-key\n"
        "smtp.gmail.com\n"
        "587\n"
        "user@example.com\n"
        "mock-password\n"
    )

    # Inject the inputs directly into the runner
    result = runner.invoke(app, ["init"], input=user_inputs)

    # Print the exact terminal output captured by the runner
    print("\n--- CLI Terminal Output ---")
    print(result.stdout)
    print("-------------------------------\n")

    assert result.exit_code == 0
    assert "Initializing job-cd Global Configuration" in result.stdout
    assert "Configuration saved" in result.stdout

    # Verify files were created
    assert (base_dir / ".env").exists()
    assert (base_dir / ".cache" / "profiles.json").exists()

    # Verify .env content
    with open(base_dir / ".env", "r") as f:
        content = f.read()
        print("--- Generated .env File ---")
        print(content)
        print("------------------------------\n")
        assert "GOOGLE_API_KEY=mock-google-key" in content
        assert "APOLLO_API_KEY=mock-apollo-key" in content
        assert "SMTP_USERNAME=user@example.com" in content

    # Verify profiles.json content
    with open(base_dir / ".cache" / "profiles.json", "r") as f:
        profile = json.load(f)
        print("--- Generated profiles.json File ---")
        print(json.dumps(profile, indent=2))
        print("---------------------------------------\n")
        assert "default" in profile
        assert profile["default"]["email"] == "ted.lasso@afcrichmond.com"


def test_config_view_mode(tmp_path, monkeypatch):
    """Test that 'config' displays the .env file content."""
    base_dir = tmp_path / "jobcd_test"
    base_dir.mkdir()
    env_file = base_dir / ".env"
    env_file.write_text("GOOGLE_API_KEY=test-key\nSMTP_SERVER=smtp.example.com\n")

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["config"])

    print("\n--- test_config_view_mode ---")
    print(result.stdout)
    print("-----------------------------\n")

    assert result.exit_code == 0
    assert "GOOGLE_API_KEY=test-key" in result.stdout
    assert "SMTP_SERVER=smtp.example.com" in result.stdout


def test_config_view_mode_missing_env(tmp_path, monkeypatch):
    """Test that 'config' shows an error when .env does not exist."""
    base_dir = tmp_path / "jobcd_test"
    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["config"])

    print("\n--- test_config_view_mode_missing_env ---")
    print(result.stdout)
    print("-----------------------------------------\n")

    assert result.exit_code == 1
    assert "Please run 'jobcd init' first" in result.stdout


def test_config_edit_mode(tmp_path, monkeypatch):
    """Test that 'config --edit' opens the .env file and prints a warning."""
    base_dir = tmp_path / "jobcd_test"
    base_dir.mkdir()
    env_file = base_dir / ".env"
    env_file.write_text("GOOGLE_API_KEY=test-key\n")

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    launch_mock = MagicMock()
    monkeypatch.setattr("typer.launch", launch_mock)

    result = runner.invoke(app, ["config", "--edit"])

    print("\n--- test_config_edit_mode ---")
    print(result.stdout)
    print("-----------------------------\n")

    assert result.exit_code == 0
    assert "WARNING" in result.stdout
    assert "sensitive credentials" in result.stdout
    launch_mock.assert_called_once_with(str(env_file))


def test_config_edit_alias(tmp_path, monkeypatch):
    """Test that 'config --open' behaves identically to '--edit'."""
    base_dir = tmp_path / "jobcd_test"
    base_dir.mkdir()
    env_file = base_dir / ".env"
    env_file.write_text("GOOGLE_API_KEY=test-key\n")

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    launch_mock = MagicMock()
    monkeypatch.setattr("typer.launch", launch_mock)

    result = runner.invoke(app, ["config", "--open"])

    print("\n--- test_config_edit_alias ---")
    print(result.stdout)
    print("-----------------------------\n")

    assert result.exit_code == 0
    assert "WARNING" in result.stdout
    launch_mock.assert_called_once_with(str(env_file))