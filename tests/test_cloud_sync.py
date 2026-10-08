"""Replica della cartella dati su Cloud Storage (deploy su Cloud Run), con un bucket simulato in memoria."""
import sqlite3
from pathlib import Path

from app.cloud_sync import GcsMirror


class NotFound(Exception):
    pass


class FakeBlob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def upload_from_filename(self, path):
        self.store[self.name] = Path(path).read_bytes()

    def download_to_filename(self, path):
        Path(path).write_bytes(self.store[self.name])

    def delete(self):
        if self.name not in self.store:
            raise NotFound(self.name)
        del self.store[self.name]


class FakeBucket:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def blob(self, name):
        return FakeBlob(self.store, name)

    def list_blobs(self, prefix=""):
        return [FakeBlob(self.store, n) for n in sorted(self.store) if n.startswith(prefix)]


def test_upload_change_delete_and_restore(tmp_path):
    bucket, local = FakeBucket(), tmp_path / "data"
    (local / "runs" / "r1" / "work").mkdir(parents=True)
    (local / "settings.json").write_text("{}")
    (local / "runs" / "r1" / "state.json").write_text('{"a": 1}')
    (local / "runs" / "r1" / "work" / "tmp.png").write_bytes(b"x")  # intermedio: non replicato
    (local / "runs" / "r1" / "state.json.tmp").write_text("parziale")
    m = GcsMirror(bucket, local)
    assert m.sync_once() == (2, 0)
    assert set(bucket.store) == {"data/settings.json", "data/runs/r1/state.json"}
    assert m.sync_once() == (0, 0)  # nulla di cambiato

    (local / "runs" / "r1" / "state.json").write_text('{"a": 22}')
    (local / "settings.json").unlink()
    assert m.sync_once() == (1, 1)
    assert bucket.store["data/runs/r1/state.json"] == b'{"a": 22}'

    fresh = tmp_path / "fresh"
    m2 = GcsMirror(bucket, fresh)
    assert m2.restore() == 1
    assert (fresh / "runs" / "r1" / "state.json").read_text() == '{"a": 22}'
    assert m2.sync_once() == (0, 0)  # cio' che e' stato appena ripristinato non viene ricaricato


def test_sqlite_is_copied_consistently(tmp_path):
    bucket, local = FakeBucket(), tmp_path / "data"
    local.mkdir()
    db = sqlite3.connect(local / "garai.db")
    db.execute("create table t (x)")
    db.execute("insert into t values (42)")
    db.commit()
    GcsMirror(bucket, local).sync_once()
    db.close()
    out = tmp_path / "copy.db"
    out.write_bytes(bucket.store["data/garai.db"])
    assert sqlite3.connect(out).execute("select x from t").fetchone() == (42,)
