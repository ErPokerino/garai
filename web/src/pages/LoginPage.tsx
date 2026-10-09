import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { Mark } from "../components/Brand";
import { ApiError, api } from "../lib/api";

const POINTS = [
  { n: "01", t: "Legge il bando", d: "profili, requisiti minimi ed elementi premianti" },
  { n: "02", t: "Abbina i candidati", d: "ogni CV al profilo più adatto, con la motivazione" },
  { n: "03", t: "Prepara la presentazione", d: "CV sintetici e fedeli sul template richiesto dalla gara" },
];

export default function LoginPage() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const userRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    userRef.current?.focus();
  }, []);
  useEffect(() => {
    if (!lockedUntil) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [lockedUntil]);

  const locked = lockedUntil !== null && now < lockedUntil;
  const remaining = locked ? Math.ceil((lockedUntil! - now) / 60000) : 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password || locked) return;
    setBusy(true);
    setError(null);
    try {
      const me = await api.login(username.trim(), password);
      qc.setQueryData(["me"], me);
      qc.invalidateQueries();
    } catch (err) {
      setPassword("");
      if (err instanceof ApiError && err.status === 429) {
        setLockedUntil(Date.now() + (err.retryAfter ?? 900) * 1000);
        setNow(Date.now());
        setError(null);
      } else {
        setError(err instanceof ApiError && err.status === 401 ? "Nome utente o password non corretti." : "Accesso non riuscito: il server non risponde. Riprova tra poco.");
      }
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState("CapsLock"));

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      {/* pannello del marchio */}
      <aside className="mesh relative hidden flex-col justify-between overflow-hidden border-r border-line px-12 py-12 lg:flex">
        <div className="flex items-center gap-3">
          <Mark className="size-10" />
          <span className="leading-none">
            <span className="block text-[22px] tracking-[-0.03em]">
              gar<b className="font-bold">ai</b>
            </span>
            <span className="mt-1 block text-xs text-ink-3">CV per bandi · by abstract</span>
          </span>
        </div>
        <div className="max-w-lg">
          <h2 className="text-[44px] leading-[1.05] font-bold">Dal bando alla presentazione dei CV.</h2>
          <ol className="mt-10 space-y-6">
            {POINTS.map((p) => (
              <li key={p.n} className="flex gap-4">
                <span className="font-display text-[15px] font-semibold text-violet-ink tabular">{p.n}</span>
                <div className="border-l border-ink/15 pl-4">
                  <div className="font-display text-[17px] font-semibold">{p.t}</div>
                  <div className="text-sm text-ink-2">{p.d}</div>
                </div>
              </li>
            ))}
          </ol>
        </div>
        <div className="font-mono text-xs text-ink-3">&gt;_ abstract · IT Experience. Experience it.</div>
      </aside>

      {/* modulo di accesso */}
      <main className="flex flex-col">
        <div className="brand-line h-0.5 w-full lg:hidden" />
        <div className="flex flex-1 items-center justify-center px-6 py-14">
          <div className="w-full max-w-[380px]">
            <div className="mb-10 flex items-center gap-3 lg:hidden">
              <Mark className="size-9" />
              <span className="text-[20px] tracking-[-0.03em]">
                gar<b className="font-bold">ai</b>
              </span>
            </div>

            <span className="eyebrow">Area riservata</span>
            <h1 className="mt-4 text-[38px] leading-tight font-bold">Accedi</h1>
            <p className="mt-2 text-[15px] text-ink-2">Usa le credenziali che ti ha fornito l'amministratore.</p>

            <form className="mt-8 space-y-5" onSubmit={submit} noValidate>
              {(error || locked) && (
                <div role="alert" aria-live="assertive" className="flex gap-2.5 rounded-lg bg-bad-soft px-3.5 py-3 text-sm">
                  <AlertCircle className="mt-0.5 size-4 shrink-0 text-bad" />
                  <span>
                    {locked
                      ? `Troppi tentativi non riusciti. Per sicurezza l'accesso è sospeso: riprova tra ${remaining} minut${remaining === 1 ? "o" : "i"}.`
                      : error}
                  </span>
                </div>
              )}

              <div>
                <label htmlFor="username" className="mb-1.5 block text-sm font-medium">
                  Nome utente
                </label>
                <input
                  id="username"
                  ref={userRef}
                  name="username"
                  className="input h-11"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  aria-invalid={!!error}
                  required
                />
              </div>

              <div>
                <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    name="password"
                    type={show ? "text" : "password"}
                    className="input h-11 pr-11"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyUp={onKey}
                    onKeyDown={onKey}
                    aria-invalid={!!error}
                    aria-describedby={caps ? "caps-hint" : undefined}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShow(!show)}
                    className="absolute top-1/2 right-2 grid size-8 -translate-y-1/2 cursor-pointer place-items-center rounded-md text-ink-3 hover:bg-subtle hover:text-ink"
                    aria-label={show ? "Nascondi password" : "Mostra password"}
                    aria-pressed={show}
                  >
                    {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
                {caps && (
                  <p id="caps-hint" className="mt-1.5 text-[13px] text-warn">
                    Il blocco maiuscole è attivo.
                  </p>
                )}
              </div>

              <button
                type="submit"
                disabled={busy || locked || !username.trim() || !password}
                className="flex h-12 w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-ink font-display text-[15px] font-medium text-canvas transition hover:bg-ink/85 disabled:cursor-not-allowed disabled:opacity-45"
              >
                {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                Accedi
                {!busy && <ArrowRight className="size-4" />}
              </button>
            </form>

            <p className="mt-10 border-t border-line pt-5 text-[13px] text-ink-3">
              Accesso riservato al personale Abstract. Hai problemi ad accedere? Contatta l'amministratore dell'applicazione.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
