"""Tests for PaperlessClient."""
from __future__ import annotations

import pytest
import responses

from chandra_paperless.config import Settings
from chandra_paperless.paperless_client import PaperlessClient


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        paperless_base_url="http://paperless.test",
        paperless_api_token="token123",
        dry_run=False,
    )
    return PaperlessClient(settings)


@responses.activate
def test_health(client):
    responses.add(responses.GET, "http://paperless.test/api/", json={"version": "2.0"}, status=200)
    assert client.health()["version"] == "2.0"


@responses.activate
def test_list_documents(client):
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/",
        json={"results": [{"id": 1, "title": "Doc 1"}]},
        status=200,
    )
    docs = client.list_documents(tag="chandra-ocr")
    assert len(docs) == 1
    assert docs[0]["id"] == 1


@responses.activate
def test_get_document(client):
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/1/",
        json={"id": 1, "title": "Doc 1", "content": "hello", "tags": [7]},
        status=200,
    )
    doc = client.get_document(1)
    assert doc["title"] == "Doc 1"


@responses.activate
def test_download_original(client):
    data = b"fake-pdf-bytes"
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/1/download/",
        body=data,
        status=200,
        content_type="application/pdf",
    )
    assert client.download_original(1) == data


@responses.activate
def test_update_content(client):
    responses.add(
        responses.PATCH,
        "http://paperless.test/api/documents/1/",
        json={"id": 1, "content": "new content"},
        status=200,
    )
    result = client.update_content(1, "new content")
    assert result["content"] == "new content"
    body = responses.calls[0].request.body
    assert b"new content" in body


@responses.activate
def test_update_content_dry_run(tmp_path):
    settings = Settings(
        paperless_base_url="http://paperless.test",
        paperless_api_token="token123",
        dry_run=True,
    )
    client = PaperlessClient(settings)
    result = client.update_content(1, "new content")
    assert result["dry_run"] is True


@responses.activate
def test_add_tags(client):
    responses.add(
        responses.GET,
        "http://paperless.test/api/documents/1/",
        json={"id": 1, "tags": [7]},
        status=200,
    )
    responses.add(
        responses.PATCH,
        "http://paperless.test/api/documents/1/",
        json={"id": 1, "tags": [7, 42]},
        status=200,
    )
    client.add_tags(1, [42])
    body = responses.calls[1].request.body
    assert b"42" in body


@responses.activate
def test_get_or_create_tag_existing(client):
    responses.add(
        responses.GET,
        "http://paperless.test/api/tags/",
        json={"results": [{"id": 42, "name": "chandra-processed"}]},
        status=200,
    )
    assert client.get_or_create_tag("chandra-processed") == 42


@responses.activate
def test_get_or_create_tag_new(client):
    responses.add(
        responses.GET,
        "http://paperless.test/api/tags/",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.POST,
        "http://paperless.test/api/tags/",
        json={"id": 99, "name": "chandra-processed"},
        status=201,
    )
    assert client.get_or_create_tag("chandra-processed") == 99
