"""Persistenza su Cloud Storage per il deploy su Cloud Run, dove il filesystem del container e' effimero.

L'app continua a lavorare sulla cartella dati locale, come in desktop. All'avvio la cartella viene ripristinata dal
bucket; poi un thread replica ogni pochi secondi i file nuovi, modificati ed eliminati. Il registro costi SQLite viene
copiato con l'API di backup, quindi la copia e' coerente anche durante le scritture.
Attivo solo con GCS_BUCKET impostato; pensato per una sola istanza (max-instances=1), che e' l'unica a scrivere.
"""
from __future__ import annotations

import logging
import sqlite3
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("garai.sync")

SKIP_DIRS = {"work"}  # file intermedi rigenerabili (testo/immagini estratti dai documenti)
SKIP_SUFFIXES = (".tmp", "-journal", "-wal", "-shm")


class GcsMirror:
    def __init__(self, bucket, local: Path, prefix: str = "data", interval_s: float = 5.0):
        """`bucket`: nome del bucket oppure un oggetto con l'interfaccia di google.cloud.storage.Bucket (test)."""
        if isinstance(bucket, str):
            from google.cloud import storage

            bucket = storage.Client().bucket(bucket)
        self.bucket = bucket
        self.local = Path(local)
        self.prefix = prefix.strip("/")
        self.interval = interval_s
        self._seen: dict[str, tuple[int, int]] = {}  # percorso relativo -> (dimensione, mtime) gia' caricati
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _blob(self, rel: str):
        return self.bucket.blob(f"{self.prefix}/{rel}")

    # ------------------------------------------------------------------ avvio
    def restore(self) -> int:
        """Scarica nel disco locale tutto cio' che e' nel bucket. Da chiamare prima di avviare l'app."""
        self.local.mkdir(parents=True, exist_ok=True)
        n = 0
        for blob in self.bucket.list_blobs(prefix=self.prefix + "/"):
            rel = blob.name[len(self.prefix) + 1:]
            if not rel or rel.endswith("/"):
                continue
            dest = self.local / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(dest))
            st = dest.stat()
            self._seen[rel] = (st.st_size, st.st_mtime_ns)
            n += 1
        return n

    # ------------------------------------------------------------------ replica
    def _local_files(self) -> dict[str, Path]:
        out: dict[str, Path] = {}
        for p in self.local.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(self.local).as_posix()
            if rel.endswith(SKIP_SUFFIXES) or any(d in SKIP_DIRS for d in rel.split("/")[:-1]):
                continue
            out[rel] = p
        return out

    def _upload(self, rel: str, p: Path) -> None:
        if p.suffix == ".db":
            with tempfile.TemporaryDirectory() as td:
                snap = Path(td) / p.name
                src, dst = sqlite3.connect(p), sqlite3.connect(snap)
                try:
                    src.backup(dst)
                finally:
                    src.close()
                    dst.close()
                self._blob(rel).upload_from_filename(str(snap))
        else:
            self._blob(rel).upload_from_filename(str(p))

    def sync_once(self) -> tuple[int, int]:
        """Carica i file nuovi o modificati ed elimina dal bucket quelli rimossi. Restituisce (caricati, eliminati)."""
        with self._lock:
            files = self._local_files()
            uploaded = 0
            for rel, p in files.items():
                try:
                    st = p.stat()
                except FileNotFoundError:
                    continue
                sig = (st.st_size, st.st_mtime_ns)
                if self._seen.get(rel) == sig:
                    continue
                try:
                    self._upload(rel, p)
                except FileNotFoundError:
                    continue  # eliminato durante la copia: se ne occupa il giro successivo
                except Exception:  # noqa: BLE001 - rete/permessi: si riprova al giro successivo
                    log.exception("Caricamento di %s non riuscito", rel)
                    continue
                # firma letta prima della copia: se il file cambia durante il caricamento, il giro dopo lo ricarica
                self._seen[rel] = sig
                uploaded += 1
            removed = 0
            for rel in [r for r in self._seen if r not in files]:
                try:
                    self._blob(rel).delete()
                except Exception as e:  # noqa: BLE001
                    if type(e).__name__ != "NotFound":
                        log.exception("Eliminazione di %s non riuscita", rel)
                        continue
                self._seen.pop(rel, None)
                removed += 1
            return uploaded, removed

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self.interval):
                try:
                    self.sync_once()
                except Exception:  # noqa: BLE001
                    log.exception("Sincronizzazione non riuscita")

        self._thread = threading.Thread(target=loop, name="gcs-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ferma il thread ed esegue un'ultima replica (allo spegnimento dell'istanza)."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)
        self.sync_once()
