"""Polling daemon / scheduler."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from chandra_paperless.chandra_client import create_chandra_client
from chandra_paperless.config import Settings
from chandra_paperless.paperless_client import PaperlessClient
from chandra_paperless.rules import Router
from chandra_paperless.worker import DocumentProcessor

logger = logging.getLogger(__name__)


class Daemon:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.processor = DocumentProcessor(
            paperless=PaperlessClient(settings),
            chandra=create_chandra_client(settings),
            router=Router(settings),
            processed_tag=settings.processed_tag,
        )

    def health_check(self) -> dict[str, Any]:
        results: dict[str, Any] = {"ok": True, "details": {}}
        try:
            results["details"]["paperless"] = self.processor.paperless.health()
        except Exception as exc:
            results["details"]["paperless"] = {"error": str(exc)}
            results["ok"] = False
        try:
            results["details"]["chandra"] = self.processor.chandra.health()
        except Exception as exc:
            results["details"]["chandra"] = {"error": str(exc)}
            results["ok"] = False
        return results

    def run_once(self) -> list[dict[str, Any]]:
        docs = self.processor.paperless.list_documents(tag=self.settings.tag_chandra_ocr)
        results: list[dict[str, Any]] = []
        for doc in docs:
            try:
                results.append(self.processor.process(doc))
            except requests.HTTPError as exc:
                logger.exception(
                    "HTTP error processing document %s: %s",
                    doc.get("id"),
                    exc.response.text if exc.response else "",
                )
                results.append({"id": doc.get("id"), "action": "error", "reason": str(exc)})
            except Exception as exc:
                logger.exception("Error processing document %s: %s", doc.get("id"), exc)
                results.append({"id": doc.get("id"), "action": "error", "reason": str(exc)})
        return results

    def run(self) -> None:
        hc = self.health_check()
        logger.info("Health check: %s", hc)
        if not hc["ok"]:
            logger.warning("One or more dependencies not healthy; continuing anyway")
        while True:
            logger.info("Polling Paperless for tag '%s'", self.settings.tag_chandra_ocr)
            results = self.run_once()
            processed = [r for r in results if r.get("action") == "processed"]
            skipped = [r for r in results if r.get("action") == "skip"]
            errors = [r for r in results if r.get("action") == "error"]
            logger.info(
                "Poll complete: %d processed, %d skipped, %d errors",
                len(processed),
                len(skipped),
                len(errors),
            )
            if self.settings.once:
                break
            time.sleep(self.settings.poll_interval)

    def stop(self) -> None:
        self.processor.close()
