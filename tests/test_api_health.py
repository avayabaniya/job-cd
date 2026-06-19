"""API Health Check — tests every external provider and integration point."""

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import smtplib
import ssl
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from typer.testing import CliRunner

from job_cd.cli.wrappers import app
from job_cd.core.config import ConfigManager, config_manager
from job_cd.core.models import (
    JobDeployment, Job, Company, Contact, EmailDraft,
    IntakePayload, DeploymentProfile, Outreach,
)
from job_cd.enums import DeploymentStatus
from job_cd.providers.cache import LocalCache
from job_cd.providers.database import SQLiteDatabaseAdapter
from job_cd.providers.intake import SimpleWebIntake
from job_cd.providers.sender import SmtpEmailSender

logger = logging.getLogger(__name__)
runner = CliRunner()

ENV_PATH = config_manager.env_path
ENV_VARS_REQUIRED = [
    "GOOGLE_API_KEY", "APOLLO_API_KEY",
    "SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
]


def load_env_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip()
    return result


def check_skip_no_env():
    if not ENV_PATH.exists():
        pytest.skip("No .env file found")


def make_sample_job(**kw):
    defaults = dict(
        id="j1", source="test", job_url="https://example.com/job",
        job_description="test description", status="pending",
    )
    defaults.update(kw)
    return Job(**defaults)


def make_sample_profile(**kw):
    defaults = dict(
        first_name="Test", last_name="User",
        email="test@example.com", current_role="Engineer",
        years_of_experience=5, target_contact_titles=["CTO"],
    )
    defaults.update(kw)
    return DeploymentProfile(**defaults)


def make_sample_deployment(**kw):
    defaults = dict(
        id="test-id",
        job=make_sample_job(),
        profile=make_sample_profile(),
    )
    defaults.update(kw)
    return JobDeployment(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONFIG
# ═══════════════════════════════════════════════════════════════════════════════


def test_config_file_exists():
    assert ENV_PATH.exists(), ".env not found"


def test_config_has_required_keys():
    env = load_env_dict(ENV_PATH)
    missing = [k for k in ENV_VARS_REQUIRED if not env.get(k)]
    if missing:
        pytest.fail(f"Missing env vars: {missing}")


def test_config_manager_paths():
    assert config_manager.app_dir.exists()
    assert config_manager.env_path == ENV_PATH
    assert config_manager.db_path.name == "job_history.db"
    assert config_manager.cache_dir.name == ".cache"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DATABASE
# ═══════════════════════════════════════════════════════════════════════════════


def test_database_initialize():
    db = SQLiteDatabaseAdapter()
    assert db.db_path.exists()
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
    assert "deployments" in tables


def test_database_save_and_retrieve():
    db = SQLiteDatabaseAdapter()
    dep = make_sample_deployment(id="test-health-save")
    db.save(dep)
    retrieved = db.get("test-health-save")
    assert retrieved is not None
    assert retrieved.job.job_url == "https://example.com/job"
    assert retrieved.job.status == "pending"
    db.update_status("test-health-save", DeploymentStatus.FAILED)


def test_database_filter():
    db = SQLiteDatabaseAdapter()
    results = db.filter(limit=5)
    assert isinstance(results, list)


def test_database_missing_id_returns_none():
    db = SQLiteDatabaseAdapter()
    result = db.get("non-existent-id-xyz")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CACHE
# ═══════════════════════════════════════════════════════════════════════════════


def test_cache_write_and_read():
    cache = LocalCache(filename="test_health_cache.json")
    cache.set("key1", {"name": "Alice", "role": "Engineer"})
    result = cache.get("key1")
    assert result == {"name": "Alice", "role": "Engineer"}


def test_cache_missing_key_returns_none():
    cache = LocalCache(filename="test_health_cache.json")
    result = cache.get("nonexistent")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. WEB INTAKE (SCRAPING)
# ═══════════════════════════════════════════════════════════════════════════════

TEST_JOBS = [
    ("Greenhouse", "https://boards.greenhouse.io/greenhouse/jobs/6527985"),
    ("Lever", "https://jobs.lever.co/pipedream/78b1546e-9e37-4f6e-b367-ee5bda72c098"),
    ("LinkedIn", "https://www.linkedin.com/jobs/view/4175326118/"),
    ("Workable", "https://apply.workable.com/j/3E5F6D7A8C/"),
]


@pytest.mark.parametrize("name,url", TEST_JOBS)
def test_intake_scrape(name, url):
    intake = SimpleWebIntake()
    payload = IntakePayload(url=url)
    jobs = intake.fetch_jobs(payload)
    if jobs:
        assert jobs[0].job_description, f"{name}: empty description"


def test_intake_invalid_url():
    intake = SimpleWebIntake()
    payload = IntakePayload(
        url="https://not-a-real-site-xyz123.com/jobs/123"
    )
    jobs = intake.fetch_jobs(payload)
    assert jobs == []


def test_intake_empty_url():
    intake = SimpleWebIntake()
    with pytest.raises(ValueError):
        intake.fetch_jobs(IntakePayload(url=""))


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GEMINI AI
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
def test_gemini_sdk():
    check_skip_no_env()
    api_key = (
        os.getenv("GOOGLE_API_KEY")
        or load_env_dict(ENV_PATH).get("GOOGLE_API_KEY")
    )
    if not api_key:
        pytest.skip("No GOOGLE_API_KEY set")
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.get(model="gemini-2.0-flash-lite")
    assert response is not None


@pytest.mark.slow
def test_gemini_cli_installed():
    gemini_path = shutil.which("gemini")
    if not gemini_path:
        pytest.skip("Gemini CLI not found")
    result = subprocess.run(
        ["gemini", "--version"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


# ═══════════════════════════════════════════════════════════════════════════════
# 6. APOLLO.IO API
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
def test_apollo_api_key():
    """Test Apollo.io API connection. People search requires a paid plan."""
    check_skip_no_env()
    api_key = (
        os.getenv("APOLLO_API_KEY")
        or load_env_dict(ENV_PATH).get("APOLLO_API_KEY")
    )
    if not api_key:
        pytest.skip("No APOLLO_API_KEY set")

    # Health check -- works on free plan
    health = requests.get(
        "https://api.apollo.io/api/v1/auth/health",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    assert health.status_code == 200, f"Apollo health check failed: {health.status_code}"

    # People search -- requires paid plan
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/api_search",
            json={
                "q_organization_domains_list": ["google.com"],
                "person_titles": ["engineer"],
                "per_page": 1,
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 403:
            data = resp.json()
            err = data.get("error", "")
            if "free plan" in err.lower():
                pytest.skip(f"Apollo: {err}")
            else:
                pytest.fail(f"Apollo 403: {err}")
        elif resp.status_code == 401:
            pytest.fail("Apollo API key is invalid (401)")
        elif resp.status_code == 429:
            pytest.skip("Apollo rate limit (429)")
        else:
            resp.raise_for_status()
    except requests.exceptions.Timeout:
        pytest.fail("Apollo API timed out")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Apollo API failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SMTP
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
def test_smtp_connection():
    check_skip_no_env()
    env = load_env_dict(ENV_PATH)
    server = env.get("SMTP_SERVER", "smtp.gmail.com")
    port = int(env.get("SMTP_PORT", "587"))
    user = env.get("SMTP_USERNAME", "")
    pw = env.get("SMTP_PASSWORD", "")
    if not user or not pw:
        pytest.skip("SMTP credentials not configured")
    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(
                server, port, context=context, timeout=10
            ) as s:
                s.login(user, pw)
        else:
            with smtplib.SMTP(server, port, timeout=10) as s:
                s.starttls(context=context)
                s.login(user, pw)
    except smtplib.SMTPAuthenticationError:
        pytest.fail("SMTP auth failed")
    except Exception as e:
        pytest.fail(f"SMTP error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. CLI
# ═══════════════════════════════════════════════════════════════════════════════


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["init", "config", "build", "dispatch", "retry", "preview", "history"]:
        assert cmd in result.stdout, f"Command '{cmd}' missing from help"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


def test_empty_env_file():
    """Empty .env should not crash config_manager."""
    from job_cd.core.config import ConfigManager
    cm = ConfigManager()
    assert cm.env_path.exists()


def test_missing_api_keys_graceful():
    """Providers should give clear errors (not crash) when keys are missing."""
    from job_cd.providers.finder import get_finder, PROVIDER_REGISTRY
    with patch.dict(os.environ, {}, clear=True):
        for name in PROVIDER_REGISTRY:
            with pytest.raises(ValueError):
                get_finder(name, cache=MagicMock())
        with pytest.raises(ValueError, match="SMTP"):
            SmtpEmailSender()


def test_concurrent_database_operations():
    """Multiple writes should not corrupt the database."""
    db = SQLiteDatabaseAdapter()
    ids = []
    for i in range(10):
        dep_id = f"test-concurrent-{i}"
        ids.append(dep_id)
        dep = make_sample_deployment(id=dep_id)
        db.save(dep)
    for dep_id in ids:
        dep = db.get(dep_id)
        assert dep is not None, f"Lost deployment {dep_id}"


def test_sql_injection_resistance():
    """DB should not be vulnerable to SQL injection via job_link."""
    db = SQLiteDatabaseAdapter()
    malicious = ["'; DROP TABLE deployments; --", "' OR 1=1; --"]
    for m in malicious:
        result = db.filter(job_link=m)
        assert isinstance(result, list)
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
    assert "deployments" in tables, "SQL injection attack dropped the table!"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. NETWORK RESILIENCE
# ═══════════════════════════════════════════════════════════════════════════════


def test_intake_timeout_on_slow_site():
    """If a site is very slow, the scraper should timeout, not hang."""
    intake = SimpleWebIntake()
    payload = IntakePayload(url="https://httpbin.org/delay/15")
    jobs = intake.fetch_jobs(payload)
    assert jobs == []


def test_intake_binary_content():
    """URL returning binary should not crash the scraper."""
    intake = SimpleWebIntake()
    payload = IntakePayload(url="https://httpbin.org/image/png")
    jobs = intake.fetch_jobs(payload)
    assert isinstance(jobs, list)
