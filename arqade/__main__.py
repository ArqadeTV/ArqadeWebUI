"""`python -m arqade` - start the web UI."""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser

from . import __version__


def _free_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) != 0:
                return port
    return preferred


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="arqade", description="Local AI model workbench")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    ap.add_argument("--version", action="version", version=f"arqade {__version__}")
    args = ap.parse_args(argv)

    try:
        import uvicorn

        from .app import app
    except ImportError as exc:
        print(f"Missing dependency: {exc.name}.\nRun the setup script (setup.sh / setup.bat) to install everything.", file=sys.stderr)
        return 1

    port = _free_port(args.host, args.port)
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{port}"
    print(f"\n  Arqade {__version__} -> {url}\n  Ctrl+C to stop\n")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
