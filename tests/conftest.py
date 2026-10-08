"""Isolamento dei test: nessun test deve leggere o scrivere i dati reali dell'app (data/, cache LLM, chiavi API).

Le variabili sono impostate prima che i moduli dell'app vengano importati: impostazioni, registro costi,
pratiche, utenti e cache finiscono in una cartella temporanea, e le chiavi reali in .env/ambiente sono ignorate.
"""
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="garai-tests-")
os.environ["DATA_DIR"] = os.path.join(_TMP, "data")
os.environ["LLM_CACHE_DIR"] = os.path.join(_TMP, "cache")
os.environ["OUT_DIR"] = os.path.join(_TMP, "out")
os.environ["LLM_PROVIDER"] = "auto"
for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GARAI_SECRET_KEY", "GARAI_ADMIN_PASSWORD"):
    os.environ[_k] = ""


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
