import json
from unittest.mock import MagicMock
from typer.testing import CliRunner
from job_cd.main import app
from job_cd.core.config import ConfigManager

runner = CliRunner()


def _profile(first_name: str) -> dict:
    """Return the minimum complete profile payload accepted by DeploymentProfile."""
    return {
        "first_name": first_name,
        "last_name": "Example",
        "email": f"{first_name.lower()}@example.com",
        "current_role": "Engineer",
        "years_of_experience": 5,
        "target_contact_titles": ["Hiring Manager"],
        "resume_text": "Example resume"
    }


def _write_profiles(base_dir, profiles: dict) -> None:
    cache_dir = base_dir / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "profiles.json").write_text(json.dumps(profiles), encoding="utf-8")


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


def test_profile_view_mode(tmp_path, monkeypatch):
    """Test that 'profile' displays the profiles.json content."""
    base_dir = tmp_path / "jobcd_test"
    cache_dir = base_dir / ".cache"
    cache_dir.mkdir(parents=True)
    profiles_file = cache_dir / "profiles.json"
    profiles_data = {
        "default": {
            "first_name": "Ted",
            "last_name": "Lasso",
            "email": "ted.lasso@afcrichmond.com"
        }
    }
    profiles_file.write_text(json.dumps(profiles_data, indent=2))

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile"])

    print("\n--- test_profile_view_mode ---")
    print(result.stdout)
    print("------------------------------\n")

    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "ted.lasso@afcrichmond.com" in result.stdout


def test_profile_view_mode_missing_profiles(tmp_path, monkeypatch):
    """Test that 'profile' shows an error when profiles.json does not exist."""
    base_dir = tmp_path / "jobcd_test"
    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile"])

    print("\n--- test_profile_view_mode_missing_profiles ---")
    print(result.stdout)
    print("----------------------------------------------\n")

    assert result.exit_code == 1
    assert "Please run 'jobcd init' first" in result.stdout


def test_profile_view_specific_profile(tmp_path, monkeypatch):
    """Test that 'profile <name>' displays only the specified profile."""
    base_dir = tmp_path / "jobcd_test"
    cache_dir = base_dir / ".cache"
    cache_dir.mkdir(parents=True)
    profiles_file = cache_dir / "profiles.json"
    profiles_data = {
        "default": {
            "first_name": "Ted",
            "last_name": "Lasso",
            "email": "ted.lasso@afcrichmond.com"
        },
        "engineer": {
            "first_name": "Coach",
            "last_name": "Beard",
            "email": "coach.beard@afcrichmond.com"
        }
    }
    profiles_file.write_text(json.dumps(profiles_data, indent=2))

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile", "default"])

    print("\n--- test_profile_view_specific_profile ---")
    print(result.stdout)
    print("------------------------------------------\n")

    assert result.exit_code == 0
    assert "ted.lasso@afcrichmond.com" in result.stdout
    assert "coach.beard@afcrichmond.com" not in result.stdout


def test_profile_view_specific_profile_not_found(tmp_path, monkeypatch):
    """Test that 'profile <name>' exits with error if profile does not exist."""
    base_dir = tmp_path / "jobcd_test"
    cache_dir = base_dir / ".cache"
    cache_dir.mkdir(parents=True)
    profiles_file = cache_dir / "profiles.json"
    profiles_data = {
        "default": {
            "first_name": "Ted",
            "last_name": "Lasso",
            "email": "ted.lasso@afcrichmond.com"
        }
    }
    profiles_file.write_text(json.dumps(profiles_data, indent=2))

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile", "nonexistent"])

    print("\n--- test_profile_view_specific_profile_not_found ---")
    print(result.stdout)
    print("----------------------------------------------------\n")

    assert result.exit_code == 1
    assert "Profile 'nonexistent' not found" in result.stdout


def test_profile_edit_mode(tmp_path, monkeypatch):
    """Test that 'profile --edit' opens profiles.json in default editor."""
    base_dir = tmp_path / "jobcd_test"
    cache_dir = base_dir / ".cache"
    cache_dir.mkdir(parents=True)
    profiles_file = cache_dir / "profiles.json"
    profiles_file.write_text("{}")

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    launch_mock = MagicMock()
    monkeypatch.setattr("typer.launch", launch_mock)

    result = runner.invoke(app, ["profile", "--edit"])

    print("\n--- test_profile_edit_mode ---")
    print(result.stdout)
    print("------------------------------\n")

    assert result.exit_code == 0
    launch_mock.assert_called_once_with(str(profiles_file))


def test_profile_edit_alias(tmp_path, monkeypatch):
    """Test that 'profile --open' behaves identically to '--edit'."""
    base_dir = tmp_path / "jobcd_test"
    cache_dir = base_dir / ".cache"
    cache_dir.mkdir(parents=True)
    profiles_file = cache_dir / "profiles.json"
    profiles_file.write_text("{}")

    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    launch_mock = MagicMock()
    monkeypatch.setattr("typer.launch", launch_mock)

    result = runner.invoke(app, ["profile", "--open"])

    print("\n--- test_profile_edit_alias ---")
    print(result.stdout)
    print("-------------------------------\n")

    assert result.exit_code == 0
    launch_mock.assert_called_once_with(str(profiles_file))


def test_profile_use_persists_selection_and_current_reports_it(tmp_path, monkeypatch):
    """`profile use NAME` should select a real profile without changing its data."""
    base_dir = tmp_path / "jobcd_test"
    _write_profiles(base_dir, {"default": _profile("Default"), "engineer": _profile("Engineer")})
    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    use_result = runner.invoke(app, ["profile", "use", "engineer"])
    current_result = runner.invoke(app, ["profile", "current"])

    assert use_result.exit_code == 0
    assert "Active profile set to 'engineer'" in use_result.stdout
    assert current_result.exit_code == 0
    assert current_result.stdout.strip() == "engineer"
    assert json.loads(test_cm.profiles_path.read_text(encoding="utf-8"))["engineer"]["first_name"] == "Engineer"


def test_profile_current_recovers_from_corrupt_active_profile_state(tmp_path, monkeypatch):
    """A corrupt active-profile file should select the documented default safely."""
    base_dir = tmp_path / "jobcd_test"
    _write_profiles(base_dir, {"default": _profile("Default")})
    test_cm = ConfigManager(base_path=base_dir)
    test_cm.config_path.write_text("{corrupt", encoding="utf-8")
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile", "current"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "default"


def test_profile_current_defaults_without_profiles_file(tmp_path, monkeypatch):
    """Current profile can be inspected before profiles have been initialized."""
    test_cm = ConfigManager(base_path=tmp_path / "jobcd_test")
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile", "current"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "default"


def test_profile_list_marks_the_active_profile(tmp_path, monkeypatch):
    """The default profile view should make the active selection visible."""
    base_dir = tmp_path / "jobcd_test"
    _write_profiles(base_dir, {"default": _profile("Default"), "engineer": _profile("Engineer")})
    test_cm = ConfigManager(base_path=base_dir)
    test_cm.set_active_profile("engineer")
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile"])

    assert result.exit_code == 0
    assert "Active profile: engineer" in result.stdout
    assert '"engineer"' in result.stdout


def test_profile_use_rejects_unknown_profile(tmp_path, monkeypatch):
    """Selecting an unknown profile must fail without creating active state."""
    base_dir = tmp_path / "jobcd_test"
    _write_profiles(base_dir, {"default": _profile("Default")})
    test_cm = ConfigManager(base_path=base_dir)
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    result = runner.invoke(app, ["profile", "use", "missing"])

    assert result.exit_code == 1
    assert "Profile 'missing' not found" in result.stdout
    assert not test_cm.config_path.exists()


def test_build_uses_active_profile_but_allows_nonpersistent_override(tmp_path, monkeypatch):
    """Build should consume the saved profile unless --profile selects a one-run override."""
    base_dir = tmp_path / "jobcd_test"
    profiles = {"default": _profile("Default"), "engineer": _profile("Engineer")}
    _write_profiles(base_dir, profiles)
    test_cm = ConfigManager(base_path=base_dir)
    test_cm.set_active_profile("engineer")
    monkeypatch.setattr("job_cd.main.config_manager", test_cm)

    class FakeCache:
        def get(self, key):
            return profiles.get(key)

    captured_profiles = []

    class FakeEngine:
        def __init__(self, **_kwargs):
            pass

        def run(self, payload, profile):
            captured_profiles.append(profile.first_name)
            return []

    fake_db = MagicMock()
    fake_db.filter.return_value = []
    monkeypatch.setattr("job_cd.main.get_db", lambda: fake_db)
    monkeypatch.setattr("job_cd.main.get_cache", lambda filename="contacts.json": FakeCache())
    monkeypatch.setattr("job_cd.main.get_intake", MagicMock())
    monkeypatch.setattr("job_cd.main.get_extractor", MagicMock())
    monkeypatch.setattr("job_cd.main.get_contact_finder", MagicMock())
    monkeypatch.setattr("job_cd.main.get_composer", MagicMock())
    monkeypatch.setattr("job_cd.main.JobPipelineEngine", FakeEngine)

    active_result = runner.invoke(app, ["build", "https://example.com/jobs/1"])
    override_result = runner.invoke(app, ["build", "https://example.com/jobs/1", "--profile", "default"])

    assert active_result.exit_code == 0
    assert override_result.exit_code == 0
    assert captured_profiles == ["Engineer", "Default"]
    assert test_cm.get_active_profile() == "engineer"
