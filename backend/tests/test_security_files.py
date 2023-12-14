from __future__ import annotations

import socket

import pytest

from app.security.url_fetch import (
    UnsafeURLError,
    _html_to_text,
    _PinnedNetworkBackend,
    _resolve_public_url,
    fetch_public_source,
    validate_public_url,
)
from app.services.files import DocumentReadError, extract_document


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/file", "http://localhost/admin", "http://127.0.0.1/", "http://10.0.0.4/",
    "http://169.254.169.254/latest/meta-data/", "https://[::1]/", "https://user:pass@example.com/", "https://example.com:8443/",
])
def test_blocks_unsafe_source_urls(url: str):
    with pytest.raises(UnsafeURLError):
        validate_public_url(url)


def test_blocks_hostname_that_resolves_to_private_address(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.5", 443))])
    with pytest.raises(UnsafeURLError, match="non-public"):
        validate_public_url("https://public-looking.example/page")


def test_http_connection_uses_the_validated_dns_address_without_resolving_again(monkeypatch):
    resolutions = []

    def resolver(host, port, **kwargs):
        resolutions.append((host, port))
        address = "93.184.216.34" if len(resolutions) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    host, port, addresses = _resolve_public_url("https://public-looking.example/article")
    connected = []

    class FakeNetwork:
        def connect_tcp(self, address, tcp_port, timeout=None, local_address=None, socket_options=None):
            connected.append((address, tcp_port))
            return "stream"

    backend = _PinnedNetworkBackend({(host, port): addresses})
    backend._backend = FakeNetwork()
    assert backend.connect_tcp(host, port) == "stream"
    assert connected == [("93.184.216.34", 443)]
    assert len(resolutions) == 1


def test_redirect_target_is_revalidated_before_second_request(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    calls = []

    class FakeResponse:
        status_code = 302
        headers = {"location": "http://127.0.0.1:8000/admin"}
        def __enter__(self): return self
        def __exit__(self, *args): return False

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def stream(self, method, url):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr("app.security.url_fetch.httpx.Client", FakeClient)
    with pytest.raises(UnsafeURLError):
        fetch_public_source("https://public-looking.example/start")
    assert calls == ["https://public-looking.example/start"]


def test_html_extraction_drops_scripts_and_navigation():
    title, text = _html_to_text(b"<html><title>Source title</title><body><nav>menu</nav><main><h1>Evidence</h1><p>Actual passage.</p><script>steal()</script></main></body></html>", 1000)
    assert title == "Source title"
    assert "Actual passage." in text
    assert "steal" not in text
    assert "menu" not in text


def test_document_readers_validate_encoding_type_and_size():
    assert "sample sentence" in extract_document("note.txt", b"A sample sentence.")
    with pytest.raises(DocumentReadError, match="UTF-8"):
        extract_document("note.txt", b"\xff\xfe\x81")
    with pytest.raises(DocumentReadError, match="Supported files"):
        extract_document("payload.exe", b"nope")
    with pytest.raises(DocumentReadError, match="exceeds"):
        extract_document("note.txt", b"A" * 200, max_chars=100)
