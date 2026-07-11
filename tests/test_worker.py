"""Tests for DocumentProcessor end-to-end."""
from __future__ import annotations

import io

import fitz
import responses

from chandra_paperless.config import Settings
from chandra_paperless.daemon import Daemon


def _empty_pdf() -> bytes:
    bio = io.BytesIO()
    doc = fitz.open()
    doc.new_page()
    doc.save(bio)
    doc.close()
    return bio.getvalue()


def _make_daemon(tmp_path):
    settings = Settings(
        paperless_base_url="http://paperless.test",
        paperless_api_token="token",
        chandra_base_url="http://chandra.test/v1",
        chandra_model="chandra",
        dry_run=True,
        tag_chandra_ocr="chandra-ocr",
        processed_tag="chandra-processed",
    )
    return Daemon(settings)


@responses.activate
def test_daemon_run_once(tmp_path):
    daemon = _make_daemon(tmp_path)
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/",
        json={"results": [{"id": 1, "title": "Doc 1", "tags": ["chandra-ocr"]}]},
        status=200,
    )
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/1/download/",
        body=_empty_pdf(),
        status=200,
    )
    responses.add(
        responses.POST,
        "http://chandra.test/v1/chat/completions",
        json={"choices": [{"message": {"content": "# OCR"}}]},
        status=200,
    )
    responses.add(
        responses.GET,
        "http://paperless.test/api/tags/",
        json={"results": [{"id": 42, "name": "chandra-processed"}]},
        status=200,
    )
    results = daemon.run_once()
    assert results[0]["action"] == "processed"
    assert results[0]["content_length"] == len("# OCR")


@responses.activate
def test_process_specific_id(tmp_path):
    daemon = _make_daemon(tmp_path)
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/2/",
        json={"id": 2, "title": "Doc 2", "tags": ["chandra-ocr"]},
        status=200,
    )
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/2/download/",
        body=_empty_pdf(),
        status=200,
    )
    responses.add(
        responses.POST,
        "http://chandra.test/v1/chat/completions",
        json={"choices": [{"message": {"content": "OCR text"}}]},
        status=200,
    )
    responses.add(
        responses.GET,
        "http://paperless.test/api/tags/",
        json={"results": [{"id": 42, "name": "chandra-processed"}]},
        status=200,
    )
    result = daemon.processor.process({"id": 2, "title": "Doc 2", "tags": ["chandra-ocr"]})
    assert result["action"] == "processed"


def test_skip_already_processed():
    daemon = _make_daemon(io.BytesIO())
    doc = {"id": 3, "title": "Doc 3", "tags": ["chandra-ocr", "chandra-processed"]}
    result = daemon.processor.process(doc)
    assert result["action"] == "skip"
    assert "already has processed tag" in result["reason"]
