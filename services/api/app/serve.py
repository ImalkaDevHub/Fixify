"""Run the API: ``python -m app.serve``.

Equivalent to ``uvicorn app.main:app`` but always uses a selector event loop, which async
psycopg needs on Windows (uvicorn's default Windows loop is the ProactorEventLoop).
Settings: API_HOST (default 127.0.0.1), API_PORT (8000), FORWARDED_ALLOW_IPS (127.0.0.1: the
Next.js proxy on the same machine), API_RELOAD (development only).
"""

import asyncio
import os
import sys

import uvicorn


def main() -> None:
    config = uvicorn.Config(
        "app.main:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        server_header=False,
        log_config=None,
    )
    if os.environ.get("API_RELOAD") == "1":
        # The reloader runs the app in a subprocess that already selects a compatible loop.
        uvicorn.run("app.main:app", host=config.host, port=config.port, reload=True,
                    proxy_headers=True, forwarded_allow_ips=config.forwarded_allow_ips)
        return
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
