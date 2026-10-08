"""Autenticazione: utenti con password hashate (scrypt), sessioni in cookie firmati, limitazione dei tentativi.

Scelte (OWASP ASVS / NIST 800-63B, in versione adatta a un'app interna):
- password mai salvate in chiaro: scrypt con sale casuale per utente, confronto a tempo costante;
- sessione = token firmato HMAC-SHA256 (utente, scadenza, versione password) in un cookie HttpOnly,
  SameSite=Strict, Secure quando servito in HTTPS: niente stato sul server, funziona anche con piu' istanze;
- cambiare la password incrementa la "versione": tutte le sessioni precedenti diventano invalide;
- dopo MAX_FAILURES tentativi falliti per utente+indirizzo (o MAX_FAILURES_IP per indirizzo) blocco temporaneo
  (HTTP 429); il blocco non e' per solo utente, altrimenti chiunque potrebbe tenere fuori l'amministratore;
- messaggio di errore unico ("credenziali non valide") per non rivelare quali utenti esistono.

Credenziali iniziali: admin / 123 (richieste per la fase interna) oppure GARAI_ADMIN_PASSWORD al primo avvio.
La UI segnala che la password iniziale va cambiata prima di mettere l'app online.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

COOKIE_NAME = "garai_session"
SESSION_TTL_S = 12 * 3600
MAX_FAILURES = 5  # per coppia utente + indirizzo
MAX_FAILURES_IP = 20  # per indirizzo, su tutti gli utenti
LOCK_WINDOW_S = 15 * 60
MIN_PASSWORD_LEN = 10
DEFAULT_ADMIN = ("admin", "123")

_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, _unb64(dk))
    except (ValueError, TypeError):
        return False


@dataclass
class Session:
    user: str
    expires: int
    initial_password: bool


class AuthError(Exception):
    def __init__(self, status: int, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.status, self.message, self.retry_after = status, message, retry_after


class AuthService:
    def __init__(self, data_dir: Path | None = None):
        self.dir = Path(data_dir or settings.data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.users_file = self.dir / "users.json"
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}
        self._secret = self._load_secret()
        self._ensure_admin()

    # ------------------------------------------------------------------ persistenza
    def _load_secret(self) -> bytes:
        env = os.environ.get("GARAI_SECRET_KEY")
        if env:
            return env.encode("utf-8")
        f = self.dir / "secret.key"
        if not f.exists():
            f.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        return f.read_text(encoding="utf-8").strip().encode("utf-8")

    def _users(self) -> dict:
        if not self.users_file.exists():
            return {}
        return json.loads(self.users_file.read_text(encoding="utf-8"))

    def _save_users(self, users: dict) -> None:
        tmp = self.users_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
        tmp.replace(self.users_file)

    def _ensure_admin(self) -> None:
        with self._lock:
            users = self._users()
            if users:
                return
            user, default_pw = DEFAULT_ADMIN
            pw = os.environ.get("GARAI_ADMIN_PASSWORD") or default_pw
            users[user] = {"hash": hash_password(pw), "pv": 1, "initial": pw == default_pw}
            self._save_users(users)

    # ------------------------------------------------------------------ token di sessione
    def _sign(self, payload: bytes) -> str:
        return _b64(hmac.new(self._secret, payload, hashlib.sha256).digest())

    def issue(self, user: str) -> str:
        u = self._users()[user]
        payload = json.dumps({"u": user, "e": int(time.time()) + SESSION_TTL_S, "pv": u["pv"]}, separators=(",", ":")).encode()
        return f"{_b64(payload)}.{self._sign(payload)}"

    def session(self, token: str | None) -> Session | None:
        if not token or "." not in token:
            return None
        body, sig = token.rsplit(".", 1)
        try:
            payload = _unb64(body)
        except (ValueError, TypeError):
            return None
        if not hmac.compare_digest(self._sign(payload), sig):
            return None
        try:
            data = json.loads(payload)
        except ValueError:
            return None
        if data.get("e", 0) < time.time():
            return None
        u = self._users().get(data.get("u"))
        if not u or u["pv"] != data.get("pv"):  # utente rimosso o password cambiata
            return None
        return Session(user=data["u"], expires=data["e"], initial_password=bool(u.get("initial")))

    # ------------------------------------------------------------------ login e tentativi
    def _check_lock(self, keys: list[str]) -> None:
        now = time.time()
        for k in keys:
            recent = [t for t in self._failures.get(k, []) if now - t < LOCK_WINDOW_S]
            self._failures[k] = recent
            if len(recent) >= (MAX_FAILURES_IP if k.startswith("ip:") else MAX_FAILURES):
                retry = int(LOCK_WINDOW_S - (now - recent[0])) + 1
                raise AuthError(429, "Troppi tentativi non riusciti. Riprova più tardi.", retry_after=retry)

    def login(self, username: str, password: str, client_ip: str) -> str:
        username = (username or "").strip().lower()
        keys = [f"pair:{username}|{client_ip}", f"ip:{client_ip}"]
        with self._lock:
            self._check_lock(keys)
        u = self._users().get(username)
        # verifica anche per utenti inesistenti: tempi di risposta uniformi
        ok = verify_password(password or "", u["hash"] if u else hash_password("x", b"0" * 16))
        if not (u and ok):
            with self._lock:
                for k in keys:
                    self._failures.setdefault(k, []).append(time.time())
            time.sleep(0.4)  # rallenta i tentativi automatici
            raise AuthError(401, "Nome utente o password non corretti.")
        with self._lock:
            self._failures.pop(keys[0], None)
        return self.issue(username)

    def change_password(self, user: str, current: str, new: str) -> str:
        users = self._users()
        u = users.get(user)
        if not u or not verify_password(current, u["hash"]):
            raise AuthError(400, "La password attuale non è corretta.")
        if len(new) < MIN_PASSWORD_LEN:
            raise AuthError(400, f"La nuova password deve avere almeno {MIN_PASSWORD_LEN} caratteri.")
        if new == current or new.lower() in {user, "password", "1234567890", "abstract", "garai"}:
            raise AuthError(400, "Scegli una password diversa e meno prevedibile.")
        with self._lock:
            u.update(hash=hash_password(new), pv=u["pv"] + 1, initial=False)
            self._save_users(users)
        return self.issue(user)  # nuova sessione per chi ha cambiato la password; le altre decadono
