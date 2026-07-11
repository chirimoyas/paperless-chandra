"""Tests for routing rules."""
from __future__ import annotations

import io

import fitz
import pytest

from chandra_paperless.config import Settings
from chandra_paperless.rules import Router, _looks_garbled


def _pdf_with_text(num_pages: int = 1) -> bytes:
    bio = io.BytesIO()
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i+1}")
    doc.save(bio)
    doc.close()
    return bio.getvalue()


def _pdf_without_text(num_pages: int = 1) -> bytes:
    bio = io.BytesIO()
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    doc.save(bio)
    doc.close()
    return bio.getvalue()


@pytest.fixture
def settings():
    return Settings(
        tag_chandra_ocr="chandra-ocr",
        processed_tag="chandra-processed",
        min_pages=1,
        max_pages=0,
        skip_native_text_pdfs=True,
        reocr_when_garbled=False,
    )


@pytest.fixture
def router(settings):
    return Router(settings)


def test_should_process_requires_tag(router):
    doc = {"id": 1, "tags": ["chandra-ocr"]}
    ok, reason = router.should_process(doc)
    assert ok
    assert "selected" in reason


def test_should_process_missing_tag(router):
    doc = {"id": 1, "tags": []}
    ok, reason = router.should_process(doc)
    assert not ok
    assert "missing required tag" in reason


def test_should_process_already_processed(router):
    doc = {"id": 1, "tags": ["chandra-ocr", "chandra-processed"]}
    ok, reason = router.should_process(doc)
    assert not ok
    assert "already has processed tag" in reason


def test_should_process_tag_objects(router):
    doc = {"id": 1, "tags": [{"id": 1, "name": "chandra-ocr"}]}
    ok, reason = router.should_process(doc)
    assert ok


def test_apply_content_rules_skip_native_text(router):
    data = _pdf_with_text()
    ok, reason = router.apply_content_rules({"id": 1}, data)
    assert not ok
    assert "embedded text" in reason


def test_apply_content_rules_process_scanned(router):
    data = _pdf_without_text()
    ok, reason = router.apply_content_rules({"id": 1}, data)
    assert ok
    assert "passes filters" in reason


def test_apply_content_rules_page_count(settings):
    settings.max_pages = 2
    router = Router(settings)
    data = _pdf_with_text(num_pages=3)
    ok, reason = router.apply_content_rules({"id": 1}, data)
    assert not ok
    assert "page count 3 > max 2" in reason


def test_reocr_when_garbled(settings):
    settings.reocr_when_garbled = True
    settings.skip_native_text_pdfs = False
    router = Router(settings)
    data = _pdf_with_text()
    ok, reason = router.apply_content_rules({"id": 1, "content": "Readable text"}, data)
    assert not ok
    assert "does not look garbled" in reason


def test_reocr_when_garbled_true(settings):
    settings.reocr_when_garbled = True
    settings.skip_native_text_pdfs = False
    router = Router(settings)
    data = _pdf_with_text()
    ok, reason = router.apply_content_rules({"id": 1, "content": "asdf 1234 !@#$"}, data)
    assert ok


def test_looks_garbled():
    assert _looks_garbled("") is True
    assert _looks_garbled("normal readable sentence") is False
    assert _looks_garbled("\x00\x01\x02\x03") is True
    assert _looks_garbled("!@#$% ^&*()" * 10) is True


def test_decide_full_pipeline(router):
    doc = {"id": 1, "tags": ["chandra-ocr"]}
    data = _pdf_without_text()
    ok, reason = router.decide(doc, data)
    assert ok
    assert "passes filters" in reason
