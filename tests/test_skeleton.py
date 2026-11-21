import importlib
from pathlib import Path

import pytest

from src.common.config import SYNTHETIC_BANNER, Settings

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    "src.common",
    "src.intake",
    "src.priorauth",
    "src.appeals",
    "src.payer_mock",
    "src.policies",
    "src.workbench",
    "src.mcp_fhir",
    "scripts",
    "evals",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_packages_import(name):
    importlib.import_module(name)


def test_banner_text_is_exact():
    assert SYNTHETIC_BANNER == "Synthetic data. Not for clinical use."


def test_readme_shows_banner():
    assert SYNTHETIC_BANNER in (ROOT / "README.md").read_text(encoding="utf-8")


def test_settings_defaults_offline(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_provider == "fake"
    assert s.fhir_base_url.endswith("/fhir")


def test_secrets_not_in_repr():
    s = Settings(_env_file=None, openai_api_key="sk-test-not-real")
    assert "sk-test-not-real" not in repr(s)


def test_env_is_gitignored_and_example_exists():
    assert ".env" in (ROOT / ".gitignore").read_text().splitlines()
    assert (ROOT / ".env.example").exists()


def test_compose_has_required_services():
    text = (ROOT / "docker-compose.yml").read_text()
    for svc in ("postgres:", "hapi:", "jaeger:"):
        assert f"\n  {svc}" in text
