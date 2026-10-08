import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, CheckCircle2, Eye, EyeOff, Lock, XCircle } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { toast } from "sonner";
import { useConfirm } from "../components/Confirm";
import { Button, Field, PageTitle, Select, Spinner, Tag } from "../components/ui";
import { ApiError, type Me, api } from "../lib/api";
import { usd } from "../lib/format";
import type { PriceRow, Provider, SettingsView, Tier } from "../lib/types";

const PROVIDERS: { id: Provider; name: string; desc: string; keyHint: string; keyUrl: string }[] = [
  { id: "gemini", name: "Google Gemini", desc: "Flash e Flash-Lite: ottimo rapporto qualità/prezzo", keyHint: "AIza…", keyUrl: "https://aistudio.google.com/apikey" },
  { id: "anthropic", name: "Anthropic Claude", desc: "Sonnet, Haiku, Opus", keyHint: "sk-ant-…", keyUrl: "https://platform.claude.com/settings/keys" },
  { id: "openai", name: "OpenAI", desc: "GPT-5, GPT-5 mini", keyHint: "sk-…", keyUrl: "https://platform.openai.com/api-keys" },
];

const TIER_INFO: Record<Tier, { title: string; desc: string }> = {
  strong: { title: "Modello principale", desc: "Legge bando e CV, scrive i contenuti, controllo grafico" },
  fast: { title: "Modello veloce", desc: "Abbina i candidati, verifica la fedeltà, traduce le etichette" },
};

const REASONING_LABEL: Record<string, string> = {
  auto: "Predefinito del modello",
  minimal: "Minimo",
  low: "Basso",
  medium: "Medio",
  high: "Alto",
};

function PriceHint({ model, prices }: { model: string; prices?: PriceRow[] }) {
  const p = prices?.find((x) => x.model === model) ?? prices?.find((x) => model.startsWith(x.model));
  if (!model) return null;
  if (!p?.current) return <span className="text-warn">Prezzo non a listino: aggiungilo in Costi → Prezzi dei modelli</span>;
  return (
    <span className="tabular">
      {usd(p.current.input)} letti · {usd(p.current.output)} scritti, per milione di token
    </span>
  );
}

function Block({ n, title, text, children, id }: { n: string; title: string; text?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="grid scroll-mt-28 gap-4 border-t border-line pt-8 md:grid-cols-[64px_1fr]">
      <span className="font-display text-[28px] leading-none font-bold text-violet tabular">{n}</span>
      <div className="min-w-0">
        <h2 className="text-[22px] font-bold">{title}</h2>
        {text && <p className="mt-1 mb-5 text-[15px] text-ink-2">{text}</p>}
        {children}
      </div>
    </section>
  );
}

function PasswordForm() {
  const qc = useQueryClient();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const mismatch = again.length > 0 && next !== again;
  const short = next.length > 0 && next.length < 10;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!cur || !next || mismatch || short) return;
    setBusy(true);
    setErr(null);
    try {
      await api.changePassword(cur, next);
      setCur("");
      setNext("");
      setAgain("");
      qc.invalidateQueries({ queryKey: ["me"] });
      toast.success("Password aggiornata", { description: "Le altre sessioni aperte sono state chiuse." });
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Aggiornamento non riuscito.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="grid max-w-2xl gap-5 sm:grid-cols-3" noValidate>
      {/* campo utente nascosto: aiuta i gestori di password ad associare la nuova password all'account */}
      <input type="text" name="username" autoComplete="username" value={qc.getQueryData<Me>(["me"])?.user ?? ""} readOnly hidden />
      <Field label="Password attuale">
        <input className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
      </Field>
      <Field label="Nuova password" hint={short ? <span className="text-warn">Almeno 10 caratteri.</span> : "Almeno 10 caratteri."}>
        <input className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
      </Field>
      <Field label="Ripeti la nuova" hint={mismatch ? <span className="text-bad">Le due password non coincidono.</span> : undefined}>
        <input className="input" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
      </Field>
      <div className="flex flex-wrap items-center gap-4 sm:col-span-3">
        <Button type="submit" variant="secondary" loading={busy} disabled={!cur || !next || !again || mismatch || short}>
          Aggiorna la password
        </Button>
        {err && (
          <span role="alert" className="text-sm text-bad">
            {err}
          </span>
        )}
      </div>
    </form>
  );
}

export default function SettingsPage() {
  const { hash } = useLocation();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const { data: s, isLoading } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const { data: prices } = useQuery({ queryKey: ["pricing"], queryFn: api.pricing });
  const [form, setForm] = useState<SettingsView | null>(null);
  const [keys, setKeys] = useState<Record<Provider, string>>({ gemini: "", anthropic: "", openai: "" });
  const [show, setShow] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    if (s) setForm(structuredClone(s));
  }, [s]);
  useEffect(() => {
    if (form && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [hash, !!form]);

  const provider = (form?.provider === "auto" || !form ? s?.resolved_provider : form.provider) as Provider | "none";
  const active: Provider = provider && provider !== "none" ? provider : "gemini";
  const modelOptions = useMemo(() => (prices ?? []).filter((p) => p.provider === active).map((p) => p.model), [prices, active]);

  const clearKeys = () => setKeys({ gemini: "", anthropic: "", openai: "" });
  const saveM = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.saveSettings(patch),
    onSuccess: (d) => {
      qc.setQueryData(["settings"], d);
      qc.invalidateQueries({ queryKey: ["status"] });
      clearKeys();
      toast.success("Impostazioni salvate");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const testM = useMutation({
    mutationFn: async () => {
      if (keys[active]) await api.saveSettings({ api_keys: { [active]: keys[active] }, provider: active, models: form!.models, reasoning: form!.reasoning });
      return api.testProvider(active);
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["status"] });
      clearKeys();
      setTest(
        r.ok
          ? { ok: true, text: Object.values(r.tiers ?? {}).map((t) => `${t.model} risponde in ${(t.latency_ms / 1000).toFixed(1)}s`).join(" · ") }
          : { ok: false, text: r.error ?? "Errore sconosciuto" },
      );
    },
    onError: (e: Error) => setTest({ ok: false, text: e.message }),
  });

  if (isLoading || !form || !s) {
    return (
      <div className="grid place-items-center py-24">
        <Spinner />
      </div>
    );
  }

  const setModel = (tier: Tier, m: string) => setForm({ ...form, models: { ...form.models, [active]: { ...form.models[active], [tier]: m } } });
  const save = () =>
    saveM.mutate({
      provider: active,
      models: form.models,
      reasoning: form.reasoning,
      run_budget_usd: form.run_budget_usd,
      monthly_budget_usd: form.monthly_budget_usd,
      max_experiences: form.max_experiences,
      max_fit_iterations: form.max_fit_iterations,
      ...(Object.values(keys).some(Boolean) ? { api_keys: Object.fromEntries(Object.entries(keys).filter(([, v]) => v)) } : {}),
    });

  const info = PROVIDERS.find((p) => p.id === active)!;
  const keyState = s.keys[active];

  return (
    <div className="animate-rise">
      <PageTitle
        eyebrow="Impostazioni"
        title="Modello AI e limiti di spesa"
        subtitle="Scegli quale AI usare, collega la tua chiave e decidi quanto puoi spendere."
        actions={
          <Button size="lg" loading={saveM.isPending} onClick={save}>
            Salva le impostazioni
          </Button>
        }
      />

      <div className="space-y-12">
        <Block n="01" title="Quale AI usare" text="Vale per tutte le nuove pratiche.">
          <div className="grid gap-3 md:grid-cols-3">
            {PROVIDERS.map((p) => {
              const sel = active === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => {
                    setForm({ ...form, provider: p.id });
                    setTest(null);
                  }}
                  className={clsx(
                    "relative cursor-pointer rounded-xl border p-4 text-left transition",
                    sel ? "border-transparent [background:linear-gradient(var(--surface),var(--surface))_padding-box,var(--brand-gradient)_border-box] [border-width:1.5px]" : "border-line hover:border-line-strong",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-display text-[17px] font-semibold">{p.name}</span>
                    {sel && (
                      <span className="grid size-5 place-items-center rounded-full bg-ink text-canvas">
                        <Check className="size-3" />
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[13px] text-ink-3">{p.desc}</p>
                  <div className="mt-3">{s.keys[p.id].set ? <Tag tone="ok">chiave collegata</Tag> : <Tag>nessuna chiave</Tag>}</div>
                </button>
              );
            })}
          </div>
        </Block>

        <Block
          n="02"
          title={`La chiave ${info.name}`}
          text={
            <>
              Viene conservata sul server e non è mai mostrata per intero.{" "}
              <a href={info.keyUrl} target="_blank" rel="noreferrer" className="font-medium text-violet-ink underline-offset-2 hover:underline">
                Dove trovarla
              </a>
            </>
          }
        >
          <div className="flex max-w-2xl flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <input
                className="input h-11 pr-10 font-mono"
                type={show ? "text" : "password"}
                autoComplete="off"
                spellCheck={false}
                aria-label={`API key ${info.name}`}
                placeholder={keyState.set ? `Collegata (${keyState.masked}): incolla una nuova chiave per sostituirla` : `Incolla la chiave (${info.keyHint})`}
                value={keys[active]}
                onChange={(e) => setKeys({ ...keys, [active]: e.target.value })}
              />
              <button className="absolute top-3 right-3 cursor-pointer text-ink-3 hover:text-ink" onClick={() => setShow(!show)} aria-label="Mostra o nascondi" type="button">
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            <Button variant="cta" size="lg" loading={testM.isPending} disabled={!keyState.set && !keys[active]} onClick={() => testM.mutate()}>
              Prova la connessione
            </Button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            {test && (
              <span className={clsx("flex items-start gap-2 text-sm", test.ok ? "text-ok" : "text-bad")}>
                {test.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
                <span className="break-all">{test.ok ? `Funziona: ${test.text}` : test.text}</span>
              </span>
            )}
            {keyState.set && (
              <button
                className="link-more text-[13px] text-ink-3"
                onClick={async () => {
                  const ok = await confirm({
                    title: `Rimuovere la chiave ${info.name}?`,
                    message: "Le nuove pratiche non potranno usare questo provider finché non inserisci un'altra chiave. Le pratiche già generate restano disponibili.",
                    confirmLabel: "Rimuovi la chiave",
                    tone: "danger",
                  });
                  if (ok) saveM.mutate({ api_keys: { [active]: "" } });
                }}
              >
                Rimuovi la chiave
              </button>
            )}
          </div>
        </Block>

        <Block n="03" title="Quali modelli" text="Due livelli: uno più capace per leggere e scrivere, uno più economico per i controlli.">
          <div className="grid gap-8 md:grid-cols-2">
            {(["strong", "fast"] as Tier[]).map((tier) => (
              <div key={tier}>
                <div className="font-display text-[17px] font-semibold">{TIER_INFO[tier].title}</div>
                <p className="mt-0.5 mb-4 text-[13px] text-ink-3">{TIER_INFO[tier].desc}</p>
                <Field label="Modello" hint={<PriceHint model={form.models[active][tier]} prices={prices} />}>
                  <input className="input font-mono" list={`models-${active}`} value={form.models[active][tier]} placeholder={s.default_models[active][tier]} onChange={(e) => setModel(tier, e.target.value.trim())} />
                </Field>
                <Field label="Quanto ragiona" className="mt-4" hint="Più ragionamento: risultati più accurati nei casi difficili, ma più token pagati.">
                  <Select
                    value={form.reasoning[tier]}
                    onChange={(v) => setForm({ ...form, reasoning: { ...form.reasoning, [tier]: v } })}
                    options={s.reasoning_levels.map((l) => ({ value: l, label: REASONING_LABEL[l] ?? l }))}
                  />
                </Field>
              </div>
            ))}
            <datalist id={`models-${active}`}>
              {modelOptions.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </div>
          {active === "gemini" && (
            <p className="mt-6 max-w-3xl rounded-lg bg-subtle px-4 py-3 text-[13px] leading-relaxed text-ink-2">
              Consigliato: <b>gemini-3.8-flash</b> come principale e <b>gemini-3.5-flash-lite</b> come veloce. Per spendere il meno possibile puoi usare
              Flash-Lite per entrambi. Il listino di Gemini 3.8 Flash raddoppia dal 1° gennaio 2027.
            </p>
          )}
        </Block>

        <Block n="04" title="Limiti di spesa" text="Al raggiungimento di un limite le chiamate si fermano e puoi decidere se proseguire. 0 = nessun limite.">
          <div className="grid max-w-2xl gap-5 sm:grid-cols-2">
            <Field label="Per pratica (USD)">
              <input className="input tabular" type="number" min={0} step={0.5} value={form.run_budget_usd} onChange={(e) => setForm({ ...form, run_budget_usd: +e.target.value })} />
            </Field>
            <Field label="Al mese (USD)">
              <input className="input tabular" type="number" min={0} step={1} value={form.monthly_budget_usd} onChange={(e) => setForm({ ...form, monthly_budget_usd: +e.target.value })} />
            </Field>
          </div>
        </Block>

        <Block n="05" title="Generazione">
          <div className="grid max-w-2xl gap-5 sm:grid-cols-2">
            <Field label="Esperienze per candidato" hint="Quante esperienze al massimo nelle slide.">
              <input className="input tabular" type="number" min={1} max={12} value={form.max_experiences} onChange={(e) => setForm({ ...form, max_experiences: +e.target.value })} />
            </Field>
            <Field label="Riscritture per l'impaginazione" hint="Se un testo non entra, quante volte farlo riscrivere all'AI prima di accorciarlo automaticamente.">
              <input className="input tabular" type="number" min={1} max={6} value={form.max_fit_iterations} onChange={(e) => setForm({ ...form, max_fit_iterations: +e.target.value })} />
            </Field>
          </div>
        </Block>

        <Block n="06" id="account" title="Il tuo account" text="Cambiare la password chiude tutte le altre sessioni aperte.">
          <PasswordForm />
        </Block>

        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-8">
          <p className="flex items-center gap-2 text-[13px] text-ink-3">
            <Lock className="size-3.5" /> Le chiavi sono conservate sul server e non vengono mai mostrate per intero.
          </p>
          <Button size="lg" loading={saveM.isPending} onClick={save}>
            Salva le impostazioni
          </Button>
        </div>
      </div>
    </div>
  );
}
