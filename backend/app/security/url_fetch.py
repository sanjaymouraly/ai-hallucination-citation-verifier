from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import fitz
import httpcore
import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag


class UnsafeURLError(ValueError):
    pass


@dataclass(frozen=True)
class RetrievedPage:
    url: str
    title: str
    text: str
    content_type: str
    redirect_count: int


def _canonical_host(host: str) -> str:
    candidate = host.rstrip(".").lower()
    try:
        return str(ipaddress.ip_address(candidate.split("%", 1)[0]))
    except ValueError:
        try:
            return candidate.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise UnsafeURLError("The source hostname is malformed.") from exc


def _resolve_public_url(url: str) -> tuple[str, int, tuple[str, ...]]:
    try:
        parsed = urlsplit(url)
        requested_port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError("Malformed URL.") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeURLError("Only HTTP and HTTPS sources can be fetched.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeURLError("The URL must have a hostname and must not contain embedded credentials.")
    if requested_port is not None and requested_port not in {80, 443}:
        raise UnsafeURLError("Only standard HTTP/HTTPS ports are allowed for source retrieval.")

    host = _canonical_host(parsed.hostname)
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeURLError("Local and internal network hosts are blocked.")
    port = requested_port or (443 if scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise UnsafeURLError("The source hostname could not be resolved.") from exc
        addresses = []
        for record in records:
            try:
                addresses.append(ipaddress.ip_address(str(record[4][0]).split("%", 1)[0]))
            except (IndexError, TypeError, ValueError):
                continue
    unique = list(dict.fromkeys(addresses))
    if not unique:
        raise UnsafeURLError("The source hostname resolved to no usable address.")
    for address in unique:
        if not address.is_global or address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
            raise UnsafeURLError("The URL resolves to a non-public IP address; internal and metadata endpoints are blocked.")
    return host, port, tuple(str(address) for address in unique)


def validate_public_url(url: str) -> str:
    _resolve_public_url(url)
    return url


def pinned_transport_for_public_url(url: str) -> httpx.HTTPTransport:
    host, port, addresses = _resolve_public_url(url)
    return _PinnedHTTPTransport(host, port, addresses)


class _PinnedNetworkBackend(httpcore.SyncBackend):
    """Connect only to addresses validated for this exact URL; retain hostname for TLS SNI."""

    def __init__(self, pins: dict[tuple[str, int], tuple[str, ...]]) -> None:
        self._pins = pins
        self._backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        addresses = self._pins.get((_canonical_host(host), port))
        if not addresses:
            raise httpcore.ConnectError("No DNS-pinned public address is available for this host.")
        last_error: httpcore.ConnectError | httpcore.ConnectTimeout | None = None
        for address in addresses:
            try:
                return self._backend.connect_tcp(address, port, timeout, local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise httpcore.ConnectError("Could not connect to a DNS-pinned public address.")

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        return self._backend.connect_unix_socket(path, timeout, socket_options)

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, host: str, port: int, addresses: tuple[str, ...]) -> None:
        super().__init__(trust_env=False, limits=httpx.Limits(max_connections=2, max_keepalive_connections=0))
        # httpx 0.28.1/httpcore 1.0.x expose the connection pool's network backend;
        # replacing it preserves normal URL, Host, certificate, and SNI handling.
        self._pool._network_backend = _PinnedNetworkBackend({(host, port): addresses})


def _html_to_text(data: bytes, max_chars: int) -> tuple[str, str]:
    soup = BeautifulSoup(data, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for element in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header", "aside"]):
        element.decompose()
    main_candidate = soup.find("main") or soup.find("article") or soup.body or soup
    main = main_candidate if isinstance(main_candidate, Tag) else soup
    pieces: list[str] = []
    size = 0
    for node in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "td", "th"]):
        value = node.get_text(" ", strip=True)
        if value and (not pieces or value != pieces[-1]):
            pieces.append(value)
            size += len(value)
        if size >= max_chars:
            break
    text = "\n\n".join(pieces)
    if not text.strip():
        text = main.get_text("\n", strip=True)
    return title[:500], text[:max_chars]


def _pdf_to_text(data: bytes, max_chars: int) -> tuple[str, str]:
    with fitz.open(stream=data, filetype="pdf") as document:
        if document.is_encrypted:
            raise ValueError("Password-protected PDFs cannot be retrieved.")
        if len(document) > 5_000:
            raise ValueError("The PDF exceeds the 5,000-page retrieval limit.")
        pages: list[str] = []
        title = str(document.metadata.get("title") or "")[:500]
        size = 0
        for index, page in enumerate(document, start=1):
            content = page.get_text("text").strip()
            if content:
                chunk = f"[Page {index}]\n{content}"
                if size + len(chunk) > max_chars:
                    remaining = max_chars - size
                    if remaining > 0:
                        pages.append(chunk[:remaining])
                    break
                pages.append(chunk)
                size += len(chunk)
        return title, "\n\n".join(pages)


def fetch_public_source(url: str, max_bytes: int = 5 * 1024 * 1024, max_chars: int = 200_000, max_redirects: int = 5) -> RetrievedPage:
    current = url
    headers = {"User-Agent": "VerityEvidenceChecker/1.0 (+local evidence-support audit)", "Accept": "text/html,application/xhtml+xml,text/plain,application/pdf;q=0.9,*/*;q=0.1"}
    for redirect_count in range(max_redirects + 1):
        host, port, addresses = _resolve_public_url(current)
        transport = _PinnedHTTPTransport(host, port, addresses)
        try:
            with httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False, trust_env=False, headers=headers, transport=transport) as client:
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count >= max_redirects:
                            raise ValueError("The source exceeded the redirect limit.")
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("The source returned a redirect without a destination.")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise ValueError(f"The source returned HTTP {response.status_code}.")
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > max_bytes:
                        raise ValueError(f"The source exceeds the {max_bytes // (1024 * 1024)} MB download limit.")
                    body = bytearray()
                    for part in response.iter_bytes():
                        body.extend(part)
                        if len(body) > max_bytes:
                            raise ValueError(f"The source exceeds the {max_bytes // (1024 * 1024)} MB download limit.")
                    data = bytes(body)
                    content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip().lower()
                    if data.startswith(b"%PDF-") or content_type == "application/pdf":
                        title, text = _pdf_to_text(data, max_chars)
                        content_type = "application/pdf"
                    elif content_type in {"text/html", "application/xhtml+xml"} or b"<html" in data[:512].lower():
                        title, text = _html_to_text(data, max_chars)
                        content_type = "text/html"
                    elif content_type.startswith("text/") or content_type in {"application/xml", "application/json"}:
                        title, text = "", data.decode("utf-8", errors="replace")[:max_chars]
                    else:
                        raise ValueError(f"Unsupported source content type: {content_type or 'unknown'}.")
                    if not text.strip():
                        raise ValueError("The source was reachable but contained no extractable text.")
                    return RetrievedPage(current, title or current, text, content_type, redirect_count)
        except httpx.TimeoutException as exc:
            raise ValueError("The source request timed out.") from exc
        except httpx.RequestError as exc:
            raise ValueError("The source could not be reached over HTTP(S).") from exc
    raise ValueError("Source retrieval did not complete.")
