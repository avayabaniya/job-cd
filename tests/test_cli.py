import json
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