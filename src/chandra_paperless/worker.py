"""End-to-end processing of a single document."""
from __future__ import annotations

import logging
from typing import Any

from chandra_paperless.chandra_client import create_chandra_client
from chandra_paperless.paperless_client import PaperlessClient
from chandra_paperless.rules import Router

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        paperless: PaperlessClient,
        chandra: Any,
        router: Router,
        processed_tag: str,
    ) -> None:
        self.paperless = paperless
        self.chandra = chandra
        self.router = router
        self.processed_tag = processed_tag
        self._processed_tag_id: int | None = None

    def process(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc_id = int(doc["id"])
        logger.info("Evaluating document %s (%s)", doc_id, doc.get("title", ""))

        ok, reason = self.router.should_process(doc)
        if not ok:
            logger.info("Skipping document %s: %s", doc_id, reason)
            return {"id": doc_id, "action": "skip", "reason": reason}

        data = self.paperless.download_original(doc_id)
        ok, reason = self.router.apply_content_rules(doc, data)
        if not ok:
            logger.info("Skipping document %s: %s", doc_id, reason)
            return {"id": doc_id, "action": "skip", "reason": reason}

        # Generate filename hint for mime detection.
        original_file = doc.get("original_file_name") or doc.get("file_name") or "document.pdf"
        new_content = self.chandra.ocr_bytes(data, filename=original_file)

        self.paperless.update_content(doc_id, new_content)
        tag_id = self._get_processed_tag_id()
        if tag_id:
            self.paperless.add_tags(doc_id, [tag_id])

        return {
            "id": doc_id,
            "action": "processed",
            "content_length": len(new_content),
            "tag_id": tag_id,
        }

    def _get_processed_tag_id(self) -> int:
        if self._processed_tag_id is None:
            self._processed_tag_id = self.paperless.get_or_create_tag(self.processed_tag)
        return self._processed_tag_id

    def close(self) -> None:
        self.paperless.session.close()
        self.chandra.session.close()
