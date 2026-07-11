"""Tests for config loading."""
import os

import pytest

from chandra_paperless.config import Settings, load_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key in Settings.model_fields:
            monkeypatch.delenv(key, raising=False)


def test_defaults():
    s = Settings()
    assert s.paperless_base_url == "http://localhost:8000"
    assert s.chandra_model == "chandra"
    assert s.poll_interval == 60


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPERLESS_API_TOKEN", "from-env")
    s = Settings()
    assert s.paperless_api_token == "from-env"


def test_load_settings_from_json(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"paperless_base_url": "http://paperless.example.com"}')
    s = load_settings(str(cfg))
    assert s.paperless_base_url == "http://paperless.example.com"


def test_load_settings_env_wins(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("paperless_api_token: file-token\n")
    monkeypatch.setenv("PAPERLESS_API_TOKEN", "env-token")
    s = load_settings(str(cfg))
    assert s.paperless_api_token == "env-token"


def test_trailing_slash_stripped():
    s = Settings(paperless_base_url="http://example.com/")
    assert s.paperless_base_url == "http://example.com"


def test_log_level_uppercased():
    s = Settings(log_level="debug")
    assert s.log_level == "DEBUG"


def test_headers():
    s = Settings(paperless_api_token="abc", chandra_api_key="def")
    assert s.paperless_api_headers()["Authorization"] == "Token abc"
    assert s.chandra_api_headers()["Authorization"] == "Bearer def"
