"""Deterministic local website used as the scanner's test target. No internet access needed."""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SLOW_SECONDS = 6
# ".invalid" is reserved (RFC 2606) and never resolves, so these always fail the same way.
UNRESOLVABLE = "http://fixify-scanner-test.invalid"

_HEAD = '<meta name="viewport" content="width=device-width"><link rel="icon" href="/icon.png">'


def _page(title: str, body: str, head: str = _HEAD) -> str:
    return (
        f"<!doctype html><html lang=en><head><meta charset=utf-8><title>{title}</title>"
        f"{head}</head><body>{body}</body></html>"
    )


def build_routes(blocked_origin: str) -> dict[str, tuple[int, str, str]]:
    html = "text/html; charset=utf-8"
    return {
        "/ok": (200, html, _page("Fixture OK", '<h1>Fine</h1><a href="/ok-target">next</a>')),
        "/ok-target": (200, html, _page("Target", "<h1>Target</h1>")),
        "/icon.png": (200, "image/png", ""),
        "/missing": (404, html, _page("Not found", "<h1>Missing</h1>")),
        "/server-error": (500, html, _page("Error", "<h1>Server error</h1>")),
        "/console-error": (
            200,
            html,
            _page(
                "Console",
                "<h1>Console</h1><script>"
                "console.error('fixture console failure');"
                "console.error('fixture console failure');"
                "console.warn('only a warning');</script>",
            ),
        ),
        "/exception": (
            200,
            html,
            _page(
                "Exception",
                "<h1>Exception</h1><script>"
                "function explode(){ throw new TypeError('fixture uncaught failure'); }"
                "explode();</script>",
            ),
        ),
        "/failed-script": (
            200,
            html,
            _page(
                "Scripts",
                '<h1>Scripts</h1><script src="/does-not-exist.js"></script>'
                f'<script src="{UNRESOLVABLE}/library.js"></script>'
                f'<img src="{blocked_origin}/internal.png" alt="">',
            ),
        ),
        "/broken-links": (
            200,
            html,
            _page(
                "Links",
                '<h1>Links</h1><a href="/ok">ok</a><a href="/ok#section">ok again</a>'
                '<a href="/gone">gone</a><a href="/flaky">flaky</a>'
                '<a href="mailto:test@example.com">mail</a><a href="tel:+100">tel</a>'
                '<a href="javascript:void(0)">js</a><a href="#top">top</a>'
                f'<a href="{UNRESOLVABLE}/page">nowhere</a>'
                f'<a href="{blocked_origin}/admin">internal</a>'
                '<a href="/redirect-to-gone">redirect</a>',
            ),
        ),
        "/gone": (404, html, _page("Gone", "<h1>Gone</h1>")),
        "/flaky": (503, html, _page("Unavailable", "<h1>Unavailable</h1>")),
        "/no-title": (200, html, _page("", "<p>No heading here.</p>", head="")),
    }


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, str, str]] = {}
    blocked_origin = ""

    def log_message(self, *_args: object) -> None:
        pass

    def _respond(self, include_body: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/slow":
            time.sleep(SLOW_SECONDS)
            status, content_type, body = 200, "text/html", _page("Slow", "<h1>Slow</h1>")
        elif path == "/redirect-internal":
            self.send_response(302)
            self.send_header("Location", f"{self.blocked_origin}/secret")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        elif path == "/redirect-to-gone":
            self.send_response(301)
            self.send_header("Location", "/gone")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        else:
            status, content_type, body = self.routes.get(
                path, (404, "text/plain", "not found")
            )
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._respond(include_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._respond(include_body=False)


@contextmanager
def serve_site() -> Iterator[tuple[str, str]]:
    """Yield (site base URL, a second loopback origin the scanner must NOT be allowed to reach)."""
    blocked = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    blocked_origin = f"http://127.0.0.1:{blocked.server_address[1]}"
    handler = type(
        "Handler",
        (_Handler,),
        {"routes": build_routes(blocked_origin), "blocked_origin": blocked_origin},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", blocked_origin
    finally:
        server.shutdown()
        server.server_close()
        blocked.server_close()
