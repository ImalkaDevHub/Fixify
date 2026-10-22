"""Local HTTP/CONNECT proxy that enforces the URL policy on every outbound connection.

Chromium and the link checker are configured to send all traffic through this proxy. For each
request the proxy resolves the destination itself, rejects prohibited addresses, and opens the
TCP connection to the exact address it validated. Redirects create new requests, so every hop
is checked. Responses produced by the proxy itself carry an ``X-Fixify-Proxy`` header so they are
never mistaken for responses from the scanned website.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.scanner.url_policy import (
    BlockedDestinationError,
    UnresolvableHostError,
    UrlPolicy,
    normalize_host,
)

logger = logging.getLogger(__name__)

PROXY_HEADER = "x-fixify-proxy"
_MAX_HEAD_BYTES = 32_768
_CONNECT_TIMEOUT_SECONDS = 10
_HOP_BY_HOP = frozenset(
    {"proxy-connection", "proxy-authorization", "connection", "keep-alive", "te", "upgrade"}
)


@dataclass
class ProxyEvents:
    """Outcome per "host:port" for destinations the proxy refused or could not reach."""

    blocked: dict[str, str] = field(default_factory=dict)
    unresolved: set[str] = field(default_factory=set)
    unreachable: set[str] = field(default_factory=set)

    def reason_for(self, host: str, port: int) -> str | None:
        key = f"{normalize_host(host)}:{port}"
        if key in self.blocked:
            return "blocked_by_policy"
        if key in self.unresolved:
            return "dns_failure"
        if key in self.unreachable:
            return "connection_failed"
        return None


class EgressProxy:
    def __init__(self, policy: UrlPolicy) -> None:
        self.policy = policy
        self.events = ProxyEvents()
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.port = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, host="127.0.0.1", port=0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), timeout=2)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await self._serve(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - one bad connection must not stop the proxy
            logger.debug("Proxy connection failed", exc_info=True)
        finally:
            with contextlib.suppress(Exception):
                writer.close()
            if task is not None:
                self._tasks.discard(task)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        if len(head) > _MAX_HEAD_BYTES:
            await self._reply(writer, 431, "request_too_large")
            return
        request_line, *header_lines = head.decode("latin-1").split("\r\n")
        parts = request_line.split(" ")
        if len(parts) != 3:
            await self._reply(writer, 400, "bad_request")
            return
        method, target, version = parts

        if method.upper() == "CONNECT":
            host, _, port_text = target.rpartition(":")
            if not port_text.isdigit():
                await self._reply(writer, 400, "bad_request")
                return
            upstream = await self._open(writer, host, int(port_text))
            if upstream is None:
                return
            upstream_reader, upstream_writer = upstream
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await self._pipe(reader, writer, upstream_reader, upstream_writer)
            return

        url = urlsplit(target)
        if url.scheme != "http" or not url.hostname:
            # Plain-HTTP forwarding only; HTTPS always arrives as CONNECT.
            await self._reply(writer, 400, "bad_request")
            return
        port = url.port or 80
        upstream = await self._open(writer, url.hostname, port)
        if upstream is None:
            return
        upstream_reader, upstream_writer = upstream
        path = url.path or "/"
        if url.query:
            path = f"{path}?{url.query}"
        headers = [
            line
            for line in header_lines
            if line and line.split(":", 1)[0].strip().lower() not in _HOP_BY_HOP
        ]
        # One request per connection keeps the proxy from forwarding a later request on the
        # same client connection to a host it has not validated.
        headers.append("Connection: close")
        upstream_writer.write(
            (f"{method} {path} {version}\r\n" + "\r\n".join(headers) + "\r\n\r\n").encode(
                "latin-1"
            )
        )
        await upstream_writer.drain()
        await self._pipe(reader, writer, upstream_reader, upstream_writer)

    async def _open(
        self, writer: asyncio.StreamWriter, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter] | None:
        key = f"{normalize_host(host)}:{port}"
        try:
            destination = await self.policy.check_destination(host, port)
        except BlockedDestinationError as error:
            self.events.blocked[key] = str(error)
            await self._reply(writer, 403, "blocked_by_policy")
            return None
        except UnresolvableHostError:
            self.events.unresolved.add(key)
            await self._reply(writer, 502, "dns_failure")
            return None
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(destination.address, port),
                timeout=_CONNECT_TIMEOUT_SECONDS,
            )
        except (OSError, TimeoutError):
            self.events.unreachable.add(key)
            await self._reply(writer, 502, "connection_failed")
            return None

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
        body = f"Fixify scanner proxy: {reason}\n".encode()
        writer.write(
            (
                f"HTTP/1.1 {status} {reason}\r\n"
                f"{PROXY_HEADER}: {reason}\r\n"
                "Content-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode()
            + body
        )
        with contextlib.suppress(ConnectionError):
            await writer.drain()

    @staticmethod
    async def _pipe(
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def forward(source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> None:
            try:
                while chunk := await source.read(65_536):
                    sink.write(chunk)
                    await sink.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                with contextlib.suppress(Exception):
                    if sink.can_write_eof():
                        sink.write_eof()

        upstream_to_client = asyncio.create_task(forward(upstream_reader, client_writer))
        client_to_upstream = asyncio.create_task(forward(client_reader, upstream_writer))
        try:
            await upstream_to_client
        finally:
            client_to_upstream.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await client_to_upstream
            with contextlib.suppress(Exception):
                upstream_writer.close()
