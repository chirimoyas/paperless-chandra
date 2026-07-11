"""Paperless-NGX REST API client."""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def _retry_session(total: int = 3, backoff: float = 1.0) -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=total,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET", "HEAD", "OPTIONS", "POST", "PATCH", "PUT"},
    )
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


class PaperlessClient:
    def __init__(self, settings: Any) -> None:
        self.base_url = settings.paperless_base_url
        self.timeout = settings.paperless_timeout
        self.headers = settings.paperless_api_headers()
        self.session = _retry_session()
        self.dry_run = settings.dry_run

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self.base_url}/api/{path}"

    def health(self) -> dict[str, Any]:
        # Hit /api/documents/?limit=1 instead of /api/ — Paperless redirects
        # /api/ to /api/schema/view/ which 406s on Accept: application/json.
        r = self.session.get(
            self._url("documents/"),
            headers=self.headers,
            params={"limit": 1},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return {"status": "ok", "count": r.json().get("count", 0)}

    def list_documents(
        self,
        tag: str | None = None,
        limit: int = 50,
        ordering: str = "-created",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": limit,
            "ordering": ordering,
        }
        if tag:
            params["tags__name__iexact"] = tag
        params.update(filters)
        logger.debug("Listing documents with params: %s", params)
        r = self.session.get(
            self._url("documents/"),
            headers=self.headers,
            params=params,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json().get("results", [])

    def get_document(self, doc_id: int) -> dict[str, Any]:
        r = self.session.get(self._url(f"documents/{doc_id}/"), headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def download_original(self, doc_id: int) -> bytes:
        url = self._url(f"documents/{doc_id}/download/")
        logger.debug("Downloading original: %s", url)
        r = self.session.get(url, headers=self.headers, timeout=self.timeout, stream=True)
        r.raise_for_status()
        bio = BytesIO()
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                bio.write(chunk)
        return bio.getvalue()

    def update_content(self, doc_id: int, content: str, title: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content}
        if title:
            payload["title"] = title
        logger.info("PATCH document %s content (len=%d)", doc_id, len(content))
        if self.dry_run:
            logger.info("DRY-RUN: would PATCH document %s", doc_id)
            return {"id": doc_id, "content": content, "dry_run": True}
        r = self.session.patch(
            self._url(f"documents/{doc_id}/"),
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def add_tags(self, doc_id: int, tag_ids: list[int]) -> dict[str, Any]:
        if not tag_ids:
            return {}
        if self.dry_run:
            logger.info("DRY-RUN: would add tags %s to document %s", tag_ids, doc_id)
            return {"id": doc_id, "tags": tag_ids, "dry_run": True}
        doc = self.get_document(doc_id)
        existing = set(doc.get("tags", []))
        merged = sorted(existing | set(tag_ids))
        r = self.session.patch(
            self._url(f"documents/{doc_id}/"),
            headers={**self.headers, "Content-Type": "application/json"},
            json={"tags": merged},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_or_create_tag(self, name: str) -> int:
        # Try exact slug/name first, then create.
        r = self.session.get(
            self._url("tags/"),
            headers=self.headers,
            params={"name__iexact": name},
            timeout=self.timeout,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            return int(results[0]["id"])
        logger.info("Creating tag '%s'", name)
        if self.dry_run:
            logger.info("DRY-RUN: would create tag '%s'", name)
            return 0
        r = self.session.post(
            self._url("tags/"),
            headers={**self.headers, "Content-Type": "application/json"},
            json={"name": name, "match": "", "is_inbox_tag": False},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return int(r.json()["id"])

    def __enter__(self) -> PaperlessClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.session.close()
