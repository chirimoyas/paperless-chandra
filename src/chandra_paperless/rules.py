"""Routing / filtering rules for deciding which documents to re-OCR."""
from __future__ import annotations

import logging
import re
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def _has_embedded_text(data: bytes) -> bool:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.debug("Cannot open as PDF: %s", exc)
        return False
    try:
        for page in doc:
            text = page.get_text()
            if text and text.strip():
                return True
        return False
    finally:
        doc.close()


def _embedded_text_ratio(data: bytes) -> float:
    """Return approximate ratio of pages that have embedded text."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.debug("Cannot open as PDF: %s", exc)
        return 0.0
    try:
        if not doc.page_count:
            return 0.0
        with_text = sum(1 for page in doc if page.get_text().strip())
        return with_text / doc.page_count
    finally:
        doc.close()


def _page_count(data: bytes) -> int:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return 1  # treat non-PDF as single image/page
    try:
        return doc.page_count or 1
    finally:
        doc.close()


def _looks_garbled(text: str) -> bool:
    if not text:
        return True
    printable_ratio = sum(1 for ch in text if ch.isprintable() or ch.isspace()) / max(len(text), 1)
    if printable_ratio < 0.85:
        return True
    # High ratio of non-word, non-space punctuation suggests garbage.
    weird = re.findall(r"[^\w\s\n\r\t\-\.,;:!?()'\"/&@$%#*=+_\[\]{}|\\<><`~]", text)
    if len(weird) / max(len(text), 1) > 0.05:
        return True
    # Very short content is suspicious (image only, no extractable text).
    alpha_count = sum(1 for ch in text if ch.isalpha())
    if alpha_count < 10:
        return True
    return False


class Router:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def should_process(self, doc: dict[str, Any]) -> tuple[bool, str]:
        """Return (should_process, reason)."""
        raw_tags = doc.get("tags", [])
        tags: set[str | int] = set()
        if raw_tags and isinstance(raw_tags[0], dict):
            tags = {t.get("name", t.get("id")) for t in raw_tags}
        else:
            tags = set(raw_tags)

        processed_tag = self.settings.processed_tag
        if processed_tag in tags:
            return False, f"already has processed tag '{processed_tag}'"

        if self.settings.tag_chandra_ocr and self.settings.tag_chandra_ocr not in tags:
            return False, f"missing required tag '{self.settings.tag_chandra_ocr}'"

        return True, "selected for processing"

    def apply_content_rules(self, doc: dict[str, Any], data: bytes) -> tuple[bool, str]:
        """Apply rules that require the original file bytes / existing content."""
        pages = _page_count(data)
        min_pages = self.settings.min_pages
        if pages < min_pages:
            return False, f"page count {pages} < min {min_pages}"
        max_pages = self.settings.max_pages
        if max_pages and pages > max_pages:
            return False, f"page count {pages} > max {max_pages}"

        if self.settings.skip_native_text_pdfs:
            ratio = _embedded_text_ratio(data)
            if ratio >= 0.8:
                return False, f"PDF has embedded text on {ratio:.0%} of pages"

        if self.settings.reocr_when_garbled:
            content = doc.get("content", "") or ""
            if not _looks_garbled(content):
                return False, "Tesseract content does not look garbled"

        return True, f"file passes filters ({pages} pages)"

    def decide(
        self,
        doc: dict[str, Any],
        data: bytes,
    ) -> tuple[bool, str]:
        ok, reason = self.should_process(doc)
        if not ok:
            return ok, reason
        return self.apply_content_rules(doc, data)
