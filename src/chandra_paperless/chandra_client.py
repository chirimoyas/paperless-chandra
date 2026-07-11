"""Chandra 2 OCR client — supports Datalab hosted API and local vLLM."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ChandraError(Exception):
    pass


class DatalabClient:
    """Client for the Datalab hosted API (https://www.datalab.to/api/v1/convert)."""

    def __init__(self, settings: Any) -> None:
        self.base_url = settings.chandra_base_url or "https://www.datalab.to"
        self.api_key = settings.chandra_api_key or ""
        if not self.api_key:
            raise ChandraError("CHANDRA_API_KEY is required for the Datalab API")
        self.timeout = settings.chandra_timeout
        self.poll_interval = 5  # seconds between polls
        self.max_poll_attempts = 120  # 10 minutes max
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    def health(self) -> dict[str, Any]:
        # Datalab doesn't have a /models endpoint; use the API health check.
        r = self.session.get(
            f"{self.base_url}/api/v1/health",
            headers=self._headers(),
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def ocr_bytes(self, data: bytes, filename: str = "document.pdf") -> str:
        """Submit document to Datalab, poll for result, return markdown."""
        # Step 1: Submit
        files = {"file": (filename, data)}
        form_data: dict[str, Any] = {
            "output_format": "markdown",
            "mode": "balanced",
        }
        logger.info(
            "Submitting %s (%d bytes) to Datalab API",
            filename,
            len(data),
        )
        r = self.session.post(
            f"{self.base_url}/api/v1/convert",
            headers=self._headers(),
            files=files,
            data=form_data,
            timeout=self.timeout,
        )
        r.raise_for_status()
        response = r.json()
        if not response.get("success", True):
            raise ChandraError(
                f"Datalab API rejected request: {response.get('error', 'unknown')}"
            )
        request_id = response["request_id"]
        check_url = response.get("request_check_url", "")

        # Step 2: Poll for result
        return self._poll_result(request_id, check_url)

    def _poll_result(self, request_id: str, check_url: str) -> str:
        url = check_url or f"{self.base_url}/api/v1/convert/{request_id}"
        for attempt in range(self.max_poll_attempts):
            r = self.session.get(url, headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            result = r.json()
            status = result.get("status", "")
            if status == "complete":
                markdown = result.get("markdown")
                if markdown:
                    logger.info(
                        "Datalab conversion complete (%d chars, %d pages)",
                        len(markdown),
                        result.get("page_count", 0),
                    )
                    return markdown.strip()
                raise ChandraError(
                    f"Datalab returned complete but no markdown: {json.dumps(result)[:500]}"
                )
            if status == "failed":
                raise ChandraError(
                    f"Datalab conversion failed: {result.get('error', 'unknown')}"
                )
            logger.debug("Polling Datalab (attempt %d): status=%s", attempt + 1, status)
            time.sleep(self.poll_interval)
        raise ChandraError(
            f"Datalab conversion timed out after {self.max_poll_attempts * self.poll_interval}s"
        )

    def __enter__(self) -> "DatalabClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.session.close()


class VLLMClient:
    """Client for a local/remote Chandra vLLM server (OpenAI-compatible)."""

    DEFAULT_SYSTEM_PROMPT = (
        "You are an OCR engine. Convert the provided document image or PDF page "
        "into clean, well-formatted Markdown. Preserve layout, tables, handwriting, "
        "and form fields. Do not add commentary or explanation."
    )
    DEFAULT_USER_TEMPLATE = "Extract all text from the attached document. Output only Markdown."

    def __init__(self, settings: Any) -> None:
        import base64
        import mimetypes

        self.base_url = settings.chandra_base_url
        self.model = settings.chandra_model
        self.timeout = settings.chandra_timeout
        self.max_tokens = settings.chandra_max_tokens
        self.temperature = settings.chandra_temperature
        self.api_key = settings.chandra_api_key
        self.system_prompt = settings.chandra_system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.user_template = (
            settings.chandra_user_prompt_template or self.DEFAULT_USER_TEMPLATE
        )
        self._base64 = base64
        self._mimetypes = mimetypes
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _encode_bytes(self, data: bytes, filename: str) -> str:
        mt = self._mimetypes.guess_type(filename)[0] or "application/octet-stream"
        b64 = self._base64.b64encode(data).decode("ascii")
        return f"data:{mt};base64,{b64}"

    def health(self) -> dict[str, Any]:
        r = self.session.get(
            f"{self.base_url}/models",
            headers=self._headers(),
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def ocr_bytes(self, data: bytes, filename: str = "document.pdf") -> str:
        url = f"{self.base_url}/chat/completions"
        data_url = self._encode_bytes(data, filename)
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.user_template},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "high"},
                        },
                    ],
                },
            ],
        }
        logger.debug(
            "Sending OCR request to %s for %s (%d bytes)",
            url,
            filename,
            len(data),
        )
        r = self.session.post(
            url, headers=self._headers(), json=payload, timeout=self.timeout
        )
        r.raise_for_status()
        response = r.json()
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ChandraError(
                f"Unexpected vLLM response shape: {json.dumps(response)[:500]}"
            ) from exc
        return content.strip()

    def __enter__(self) -> "VLLMClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.session.close()


def create_chandra_client(settings: Any):
    """Factory: pick the right client based on configuration.

    If chandra_backend is 'datalab', use the Datalab hosted API.
    If 'vllm', use the OpenAI-compatible vLLM server.
    Auto-detect: if base_url contains 'datalab.to', use Datalab.
    """
    backend = getattr(settings, "chandra_backend", "auto")
    base_url = settings.chandra_base_url or ""

    if backend == "datalab" or (backend == "auto" and "datalab.to" in base_url):
        return DatalabClient(settings)
    return VLLMClient(settings)