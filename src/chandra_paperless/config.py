"""Configuration layer: env vars + optional config file."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_extra_config(path: Path | str | None) -> dict[str, Any]:
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    suffix = p.suffix.lower()
    with p.open() as f:
        if suffix in {".json"}:
            return json.load(f)
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(f) or {}
        if suffix == ".toml":
            try:
                import tomllib  # type: ignore[import-not-found]
            except ImportError:  # pragma: no cover - py3.10 fallback
                import tomli as tomllib  # type: ignore[import-not-found]
            with p.open("rb") as fb:
                data = tomllib.load(fb)
            return data.get("tool", {}).get("chandra-paperless", {})
    return {}


def _coerce_env_value(key: str, value: str) -> Any:
    field_name = key.lower()
    field = Settings.model_fields[field_name]
    annotation = field.annotation
    # Pydantic handles bool parsing from strings when receiving a real string,
    # but model_copy(update=...) performs limited validation. We pre-coerce booleans.
    if annotation is bool:
        return value.lower() in {"1", "true", "yes", "on"}
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paperless-NGX
    paperless_base_url: str = "http://localhost:8000"
    paperless_api_token: str = ""
    paperless_timeout: int = 30

    # Chandra 2 backend: 'datalab' (hosted API) or 'vllm' (OpenAI-compatible)
    chandra_backend: str = "auto"  # auto-detect: datalab.to URL -> datalab, else vllm
    chandra_base_url: str = "http://localhost:8000/v1"
    chandra_model: str = "chandra"
    chandra_api_key: str | None = None
    chandra_timeout: int = 300
    chandra_max_tokens: int = 8192
    chandra_temperature: float = 0.0

    # Prompt / extraction
    chandra_system_prompt: str | None = None
    chandra_user_prompt_template: str | None = None

    # Polling behavior
    poll_interval: int = Field(default=60, ge=5)
    once: bool = False
    dry_run: bool = False

    # Routing
    tag_chandra_ocr: str = "chandra-ocr"
    processed_tag: str = "chandra-processed"
    min_pages: int = Field(default=1, ge=1)
    max_pages: int = Field(default=0, ge=0)
    skip_native_text_pdfs: bool = True
    reocr_when_garbled: bool = False

    # Optional Paperless-AI re-analyze trigger
    paperless_ai_reanalyze_url: str | None = None

    # Logging
    log_level: str = "INFO"

    @field_validator(
        "paperless_base_url",
        "chandra_base_url",
        "paperless_ai_reanalyze_url",
        mode="before",
    )
    @classmethod
    def _strip_trailing_slash(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.rstrip("/")
        return v

    @field_validator("log_level", mode="after")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    def paperless_api_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.paperless_api_token:
            headers["Authorization"] = f"Token {self.paperless_api_token}"
        return headers

    def chandra_api_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.chandra_api_key:
            headers["Authorization"] = f"Bearer {self.chandra_api_key}"
        return headers


def load_settings(config_path: str | None = None) -> Settings:
    """Load settings from optional file, then env vars (env wins).

    If you want a `.env` file, load it externally (e.g. python-dotenv) before
    calling this function.
    """
    file_values = _load_extra_config(config_path) if config_path else {}
    if not config_path:
        file_values.update(_load_extra_config(Path("chandra-paperless.toml")))
        file_values.update(_load_extra_config(Path("pyproject.toml")))

    # Build base from file values without reading environment.
    base = Settings(**file_values)
    # Apply explicit environment overrides.
    env_values = {
        k.lower(): _coerce_env_value(k, os.environ[k])
        for k in os.environ
        if k.lower() in Settings.model_fields
    }
    if env_values:
        return base.model_copy(update=env_values)
    return base
