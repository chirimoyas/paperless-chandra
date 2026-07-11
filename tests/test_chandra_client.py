"""Tests for ChandraClient (Datalab + vLLM backends)."""
from __future__ import annotations

import json

import pytest
import responses

from chandra_paperless.chandra_client import (
    ChandraError,
    DatalabClient,
    VLLMClient,
    create_chandra_client,
)
from chandra_paperless.config import Settings


# --- vLLM backend tests ---

@pytest.fixture
def vllm_client():
    return VLLMClient(
        Settings(
            chandra_backend="vllm",
            chandra_base_url="http://chandra.test/v1",
            chandra_model="chandra",
            chandra_api_key="key",
        )
    )


@responses.activate
def test_vllm_health(vllm_client):
    responses.add(
        responses.GET,
        "http://chandra.test/v1/models",
        json={"data": [{"id": "chandra"}]},
        status=200,
    )
    assert vllm_client.health()["data"][0]["id"] == "chandra"


@responses.activate
def test_vllm_ocr_bytes(vllm_client):
    responses.add(
        responses.POST,
        "http://chandra.test/v1/chat/completions",
        json={"choices": [{"message": {"content": "# Title\n\nBody text"}}]},
        status=200,
    )
    text = vllm_client.ocr_bytes(b"pdf-bytes", filename="file.pdf")
    assert text == "# Title\n\nBody text"


@responses.activate
def test_vllm_ocr_bytes_bad_response(vllm_client):
    responses.add(
        responses.POST,
        "http://chandra.test/v1/chat/completions",
        json={"unexpected": "shape"},
        status=200,
    )
    with pytest.raises(ChandraError):
        vllm_client.ocr_bytes(b"pdf-bytes")


@responses.activate
def test_vllm_request_body_has_image(vllm_client):
    responses.add(
        responses.POST,
        "http://chandra.test/v1/chat/completions",
        json={"choices": [{"message": {"content": "ok"}}]},
        status=200,
    )
    vllm_client.ocr_bytes(b"pdf-bytes", filename="file.pdf")
    body = json.loads(responses.calls[0].request.body)
    image_url = body["messages"][1]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:application/pdf;base64,")
    assert "Authorization" in responses.calls[0].request.headers


# --- Datalab backend tests ---

@pytest.fixture
def datalab_client():
    return DatalabClient(
        Settings(
            chandra_backend="datalab",
            chandra_base_url="https://www.datalab.to",
            chandra_api_key="dl-key",
        )
    )


@responses.activate
def test_datalab_ocr_bytes(datalab_client):
    # Step 1: submit returns request_id
    responses.add(
        responses.POST,
        "https://www.datalab.to/api/v1/convert",
        json={
            "success": True,
            "request_id": "req-123",
            "request_check_url": "https://www.datalab.to/api/v1/convert/req-123",
        },
        status=200,
    )
    # Step 2: poll returns complete with markdown
    responses.add(
        responses.GET,
        "https://www.datalab.to/api/v1/convert/req-123",
        json={
            "status": "complete",
            "markdown": "# OCR Result\n\nSome text",
            "page_count": 2,
        },
        status=200,
    )
    text = datalab_client.ocr_bytes(b"pdf-bytes", filename="doc.pdf")
    assert text == "# OCR Result\n\nSome text"
    # Verify X-API-Key header was sent
    assert responses.calls[0].request.headers["X-API-Key"] == "dl-key"
    # Verify content type was included in file upload
    body = responses.calls[0].request.body
    assert b"application/pdf" in body


@responses.activate
def test_datalab_ocr_bytes_polling(datalab_client):
    responses.add(
        responses.POST,
        "https://www.datalab.to/api/v1/convert",
        json={
            "success": True,
            "request_id": "req-456",
            "request_check_url": "https://www.datalab.to/api/v1/convert/req-456",
        },
        status=200,
    )
    # First poll: still processing
    responses.add(
        responses.GET,
        "https://www.datalab.to/api/v1/convert/req-456",
        json={"status": "processing"},
        status=200,
    )
    # Second poll: complete
    responses.add(
        responses.GET,
        "https://www.datalab.to/api/v1/convert/req-456",
        json={"status": "complete", "markdown": "Done"},
        status=200,
    )
    # Speed up the test
    datalab_client.poll_interval = 0
    text = datalab_client.ocr_bytes(b"pdf-bytes")
    assert text == "Done"


@responses.activate
def test_datalab_ocr_bytes_failed(datalab_client):
    responses.add(
        responses.POST,
        "https://www.datalab.to/api/v1/convert",
        json={
            "success": True,
            "request_id": "req-789",
            "request_check_url": "https://www.datalab.to/api/v1/convert/req-789",
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.datalab.to/api/v1/convert/req-789",
        json={"status": "failed", "error": "corrupt PDF"},
        status=200,
    )
    with pytest.raises(ChandraError, match="corrupt PDF"):
        datalab_client.ocr_bytes(b"pdf-bytes")


def test_datalab_requires_api_key():
    with pytest.raises(ChandraError, match="CHANDRA_API_KEY"):
        DatalabClient(Settings(chandra_backend="datalab", chandra_api_key=""))


# --- Factory tests ---

def test_factory_auto_detect_datalab():
    s = Settings(
        chandra_backend="auto",
        chandra_base_url="https://www.datalab.to",
        chandra_api_key="x",
    )
    client = create_chandra_client(s)
    assert isinstance(client, DatalabClient)


def test_factory_auto_detect_vllm():
    s = Settings(chandra_backend="auto", chandra_base_url="http://localhost:8000/v1")
    client = create_chandra_client(s)
    assert isinstance(client, VLLMClient)


def test_factory_explicit_datalab():
    s = Settings(chandra_backend="datalab", chandra_base_url="https://www.datalab.to", chandra_api_key="x")
    client = create_chandra_client(s)
    assert isinstance(client, DatalabClient)


def test_factory_explicit_vllm():
    s = Settings(chandra_backend="vllm", chandra_base_url="http://localhost:8000/v1")
    client = create_chandra_client(s)
    assert isinstance(client, VLLMClient)