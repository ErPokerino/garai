"""Garanzia: i test non usano mai la cartella dati reale (impostazioni, chiavi, pratiche, utenti, costi)."""
from app.config import ROOT, settings


def test_tests_never_touch_real_data():
    real = (ROOT / "data").resolve()
    assert settings.data_dir.resolve() != real
    assert real not in settings.data_dir.resolve().parents
    assert settings.cache_dir.resolve() != (ROOT / ".cache" / "llm").resolve()


def test_server_singletons_use_test_data():
    from app.api import server

    real = (ROOT / "data").resolve()
    for p in (server.runs.base, server.auth.dir):
        assert not p.resolve().is_relative_to(real)


def test_no_real_api_keys_loaded():
    assert not any(settings.api_keys.values())
