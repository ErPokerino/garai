"""Avvio dell'applicazione:  python -m app  [--port 8765] [--no-browser]"""
from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 per esporla in rete / container")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--reload", action="store_true", help="ricarica il backend a ogni modifica (sviluppo)")
    args = ap.parse_args()

    import uvicorn

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"GarAI in ascolto su {url}")
    uvicorn.run("app.api.server:app", host=args.host, port=args.port, proxy_headers=True, reload=args.reload, log_level="warning")


if __name__ == "__main__":
    main()
