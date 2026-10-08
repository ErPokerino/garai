"""Avvio dell'applicazione:  python -m app  [--port 8765] [--no-browser]

Con GCS_BUCKET impostato (deploy su Cloud Run) la cartella dati viene ripristinata dal bucket prima di avviare l'app
e poi replicata in continuo (vedi app/cloud_sync.py).
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
import webbrowser
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 per esporla in rete / container")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--reload", action="store_true", help="ricarica il backend a ogni modifica (sviluppo)")
    args = ap.parse_args()

    import uvicorn

    mirror = None
    bucket = os.environ.get("GCS_BUCKET")
    if bucket:
        # prima di importare l'app: impostazioni, utenti e pratiche vengono letti all'import
        from app.cloud_sync import GcsMirror

        logging.basicConfig(level=logging.INFO)
        data_dir = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parent.parent / "data")
        mirror = GcsMirror(bucket, data_dir)
        print(f"Ripristinati {mirror.restore()} file da gs://{bucket}")
        mirror.start()

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"GarAI in ascolto su {url}")
    try:
        uvicorn.run("app.api.server:app", host=args.host, port=args.port, proxy_headers=True, reload=args.reload,
                    log_level="warning", timeout_graceful_shutdown=3)
    finally:
        if mirror:
            mirror.stop()


if __name__ == "__main__":
    main()
