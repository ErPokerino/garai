import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Pencil, RotateCcw, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { Button, Empty, Field, Metric, Modal, PageTitle, Panel, SectionTitle, Spinner, Tag } from "../components/ui";
import { api } from "../lib/api";
import { compact, dateTime, dayLabel, int, usd } from "../lib/format";
import type { CostSummary, PriceRow } from "../lib/types";

const PERIODS = [
  { days: 7, label: "7 giorni" },
  { days: 30, label: "30 giorni" },
  { days: 90, label: "90 giorni" },
  { days: 0, label: "Sempre" },
];
const SLOTS = 7; // oltre: "Altri modelli"

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter((p) => p.value > 0);
  const total = rows.reduce((a, p) => a + p.value, 0);
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-[13px] shadow-lg">
      <div className="mb-1 font-display font-semibold">{label && /^\d{4}-/.test(label) ? dayLabel(label) : label}</div>
      {rows.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="size-2 rounded-[2px]" style={{ background: p.color }} />
          <span className="flex-1 text-ink-2">{p.name}</span>
          <span className="tabular font-medium">{usd(p.value)}</span>
        </div>
      ))}
      {rows.length > 1 && (
        <div className="mt-1 flex justify-between border-t border-line pt-1 font-medium">
          <span>Totale</span>
          <span className="tabular">{usd(total)}</span>
        </div>
      )}
    </div>
  );
}

/** Colore per modello: stabile (ordine alfabetico su tutto lo storico), mai per rango di spesa. */
function useModelColors() {
  const { data } = useQuery({ queryKey: ["costs", 0], queryFn: () => api.costs(0) });
  return useMemo(() => {
    const names = (data?.by_model ?? []).map((m) => m.key ?? "").filter(Boolean).sort();
    const map = new Map<string, string>();
    names.forEach((n, i) => map.set(n, i < SLOTS ? `var(--series-${i + 1})` : "var(--series-other)"));
    return (m: string) => map.get(m) ?? "var(--series-other)";
  }, [data]);
}

function DailyChart({ data, colorOf }: { data: CostSummary; colorOf: (m: string) => string }) {
  const { rows, models } = useMemo(() => {
    const byDay = new Map<string, Record<string, number | string>>();
    const models = new Set<string>();
    for (const r of data.by_day_model) {
      models.add(r.model);
      const row = byDay.get(r.day) ?? { day: r.day };
      row[r.model] = ((row[r.model] as number) ?? 0) + r.cost_usd;
      byDay.set(r.day, row);
    }
    // giorni senza spesa inclusi: l'asse del tempo resta continuo
    const days: string[] = [];
    if (data.start) {
      for (let d = new Date(data.start + "T00:00:00"); d <= new Date(); d.setDate(d.getDate() + 1)) days.push(d.toISOString().slice(0, 10));
    } else days.push(...[...byDay.keys()].sort());
    return { rows: days.map((d) => byDay.get(d) ?? { day: d }), models: [...models].sort() };
  }, [data]);

  if (!data.by_day_model.length) return <Empty title="Nessuna spesa nel periodo" />;
  return (
    <>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="day" tickFormatter={dayLabel} tick={{ fontSize: 12, fill: "var(--chart-axis)" }} tickLine={false} axisLine={false} minTickGap={28} />
            <YAxis tickFormatter={(v) => `$${v < 1 ? v.toFixed(2) : v.toFixed(0)}`} tick={{ fontSize: 12, fill: "var(--chart-axis)" }} tickLine={false} axisLine={false} width={48} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--chart-grid)", opacity: 0.6 }} />
            {models.map((m, i) => (
              <Bar key={m} dataKey={m} name={m} stackId="a" fill={colorOf(m)} stroke="var(--chart-surface)" strokeWidth={1.5} radius={i === models.length - 1 ? [4, 4, 0, 0] : 0} maxBarSize={26} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {models.length > 1 && (
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-ink-2">
          {models.map((m) => (
            <span key={m} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-[2px]" style={{ background: colorOf(m) }} />
              {m}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

const STAGE_SHORT: Record<string, string> = {
  "Estrazione bando": "Lettura bando",
  "Parsing CV": "Lettura CV",
  "Scrittura contenuti": "Scrittura",
  "Verifica fedeltà": "Verifica",
  "Critico visivo": "Controllo grafico",
  "Traduzione etichette": "Etichette",
};

function StageChart({ data }: { data: CostSummary }) {
  const rows = [...data.by_stage].sort((a, b) => b.cost_usd - a.cost_usd).map((s) => ({ name: STAGE_SHORT[s.label] ?? s.label, cost: s.cost_usd }));
  if (!rows.length) return <Empty title="Nessun dato" />;
  return (
    <div style={{ height: Math.max(150, rows.length * 38) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 72, left: 0, bottom: 0 }} barCategoryGap="30%">
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={118} tick={{ fontSize: 13, fill: "var(--chart-axis)" }} tickLine={false} axisLine={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--chart-grid)", opacity: 0.6 }} />
          <Bar dataKey="cost" name="Costo" fill="var(--series-1)" radius={[0, 4, 4, 0]} maxBarSize={18}>
            <LabelList dataKey="cost" position="right" formatter={(v: unknown) => usd(Number(v))} style={{ fontSize: 12, fill: "var(--chart-axis)" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PriceEditor({ row, onClose }: { row: PriceRow; onClose: () => void }) {
  const qc = useQueryClient();
  const [v, setV] = useState({ input: String(row.current?.input ?? 0), output: String(row.current?.output ?? 0), cache_read: String(row.current?.cache_read ?? 0) });
  const save = useMutation({
    mutationFn: () => api.setPrice(row.model, { provider: row.provider, label: row.label, input: +v.input, output: +v.output, cache_read: +v.cache_read }),
    onSuccess: (d) => {
      qc.setQueryData(["pricing"], d);
      qc.invalidateQueries({ queryKey: ["costs"] });
      toast.success("Prezzo aggiornato", { description: "Vale per le chiamate future; lo storico resta invariato." });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onClose={onClose}>
      <div className="w-[min(92vw,28rem)] overflow-hidden rounded-xl bg-surface shadow-2xl">
        <div className="brand-line h-0.5" />
        <div className="p-6">
          <h3 className="text-xl font-bold">{row.label}</h3>
          <p className="mt-1 text-[13px] text-ink-3">{row.model} · dollari per milione di token</p>
          <div className="mt-5 grid grid-cols-3 gap-3">
            {(["input", "output", "cache_read"] as const).map((k) => (
              <Field key={k} label={{ input: "Letti", output: "Scritti", cache_read: "In cache" }[k]}>
                <input className="input tabular" type="number" min={0} step="0.001" value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} />
              </Field>
            ))}
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Annulla
            </Button>
            <Button loading={save.isPending} onClick={() => save.mutate()}>
              Salva
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function PricingTable() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["pricing"], queryFn: api.pricing });
  const [edit, setEdit] = useState<PriceRow | null>(null);
  const reset = useMutation({ mutationFn: api.resetPrice, onSuccess: (d) => qc.setQueryData(["pricing"], d) });
  const groups = ["gemini", "anthropic", "openai", "custom"];
  const today = new Date().toISOString().slice(0, 10);
  return (
    <section>
      <SectionTitle eyebrow="Listino" title="Prezzi dei modelli" aside={<span className="text-sm text-ink-3">dollari per milione di token · il costo usa il prezzo in vigore quel giorno</span>} />
      <div className="overflow-x-auto">
        <table className="w-full text-[15px]">
          <thead>
            <tr className="border-b border-line text-left text-[13px] text-ink-3">
              <th className="py-2.5 pr-3 font-medium">Modello</th>
              <th className="px-3 py-2.5 text-right font-medium">Letti</th>
              <th className="px-3 py-2.5 text-right font-medium">Scritti</th>
              <th className="px-3 py-2.5 text-right font-medium">In cache</th>
              <th className="px-3 py-2.5 font-medium">Fonte</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data
              ?.slice()
              .sort((a, b) => groups.indexOf(a.provider) - groups.indexOf(b.provider))
              .map((r) => (
                <tr key={r.model}>
                  <td className="py-3 pr-3">
                    <div className="font-medium">{r.label}</div>
                    <div className="text-[13px] text-ink-3">{r.model}</div>
                  </td>
                  <td className="tabular px-3 py-3 text-right">${r.current?.input.toFixed(3)}</td>
                  <td className="tabular px-3 py-3 text-right">${r.current?.output.toFixed(2)}</td>
                  <td className="tabular px-3 py-3 text-right text-ink-3">${r.current?.cache_read.toFixed(3)}</td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {r.overridden ? <Tag tone="violet">personalizzato</Tag> : r.verified ? <Tag tone="ok">listino ufficiale</Tag> : <Tag tone="warn">da verificare</Tag>}
                      {r.tiers
                        .filter((t) => t.from > today)
                        .map((t) => (
                          <Tag key={t.from}>
                            dal {new Date(t.from).toLocaleDateString("it-IT")}: ${t.input} / ${t.output}
                          </Tag>
                        ))}
                    </div>
                  </td>
                  <td className="py-3 pl-3 text-right whitespace-nowrap">
                    {r.overridden && (
                      <button className="cursor-pointer rounded-md p-1.5 text-ink-3 hover:bg-subtle hover:text-ink" title="Ripristina il prezzo ufficiale" onClick={() => reset.mutate(r.model)}>
                        <RotateCcw className="size-4" />
                      </button>
                    )}
                    <button className="cursor-pointer rounded-md p-1.5 text-ink-3 hover:bg-subtle hover:text-ink" title="Modifica" onClick={() => setEdit(r)}>
                      <Pencil className="size-4" />
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {edit && <PriceEditor row={edit} onClose={() => setEdit(null)} />}
    </section>
  );
}

export default function CostsPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({ queryKey: ["costs", days], queryFn: () => api.costs(days) });
  const { data: calls } = useQuery({ queryKey: ["calls", "all"], queryFn: () => api.calls(undefined, 50) });
  const colorOf = useModelColors();
  const t = data?.totals;
  const budget = data?.monthly_budget_usd ?? 0;
  const ratio = budget > 0 && data ? data.month_to_date / budget : 0;

  return (
    <div className="animate-rise space-y-14">
      <PageTitle
        eyebrow="Costi"
        title="Quanto stai spendendo"
        subtitle="Ogni chiamata ai modelli AI è registrata con i token usati e il costo. Le risposte già ottenute vengono riusate gratis."
        actions={
          <div className="flex rounded-lg border border-line p-0.5" role="group" aria-label="Periodo">
            {PERIODS.map((p) => (
              <button
                key={p.days}
                onClick={() => setDays(p.days)}
                className={clsx(
                  "cursor-pointer rounded-md px-3 py-1.5 font-display text-[13px] font-medium transition",
                  days === p.days ? "bg-ink text-canvas" : "text-ink-2 hover:text-ink",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        }
      />

      {isLoading || !data || !t ? (
        <div className="grid place-items-center py-20">
          <Spinner />
        </div>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-x-8 gap-y-8 border-y border-line py-8 lg:grid-cols-4">
            <Metric label="Spesa nel periodo" value={usd(t.cost_usd)} hint={`${int(t.calls)} chiamate${t.errors ? ` · ${t.errors} non riuscite` : ""}`} />
            <div>
              <Metric
                label="Mese corrente"
                value={usd(data.month_to_date)}
                tone={ratio >= 0.8 ? "warn" : undefined}
                hint={budget > 0 ? `${Math.round(ratio * 100)}% del budget di ${usd(budget)}` : <Link to="/settings" className="underline-offset-2 hover:underline">imposta un budget mensile</Link>}
              />
              {budget > 0 && (
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-subtle">
                  <div className={clsx("h-full rounded-full", ratio >= 1 ? "bg-bad" : ratio >= 0.8 ? "bg-orange" : "brand-line")} style={{ width: `${Math.min(100, ratio * 100)}%` }} />
                </div>
              )}
            </div>
            <Metric label="Costo medio per CV" value={data.avg_cost_per_cv != null ? usd(data.avg_cost_per_cv) : "–"} hint={`${data.cvs_processed} CV generati nel periodo`} />
            <Metric label="Risparmiato" value={usd(t.saved_usd)} hint={`${t.cache_hits} risposte riusate · ${compact(t.input_tokens)} token letti`} />
          </section>

          {t.unpriced > 0 && (
            <p className="-mt-8 flex items-center gap-2 text-[13px] text-warn">
              <TriangleAlert className="size-4" /> {t.unpriced} chiamate su modelli senza prezzo a listino (contate a 0): aggiungi il prezzo qui sotto.
            </p>
          )}

          <div className="grid gap-10 xl:grid-cols-[1.4fr_1fr]">
            <section>
              <h2 className="mb-5 text-xl font-bold">Spesa giornaliera per modello</h2>
              <DailyChart data={data} colorOf={colorOf} />
            </section>
            <section>
              <h2 className="mb-1 text-xl font-bold">Dove vanno i token</h2>
              <p className="mb-5 text-sm text-ink-3">Spesa per attività della pipeline</p>
              <StageChart data={data} />
            </section>
          </div>

          <div className="grid gap-10 xl:grid-cols-2">
            <section>
              <h2 className="mb-3 text-xl font-bold">Per modello</h2>
              <ul className="divide-y divide-line border-y border-line text-[15px]">
                {data.by_model.map((m) => (
                  <li key={m.key} className="flex items-center gap-4 py-3">
                    <span className="size-2.5 shrink-0 rounded-[2px]" style={{ background: colorOf(m.key ?? "") }} />
                    <span className="min-w-0 flex-1 truncate">{m.key}</span>
                    <span className="tabular text-[13px] text-ink-3">{int(m.calls)} chiamate</span>
                    <span className="tabular w-20 text-right font-medium">{usd(m.cost_usd)}</span>
                  </li>
                ))}
                {!data.by_model.length && <li className="py-6 text-center text-ink-3">Nessuna chiamata nel periodo</li>}
              </ul>
            </section>
            <section>
              <h2 className="mb-3 text-xl font-bold">Per pratica</h2>
              <ul className="divide-y divide-line border-y border-line text-[15px]">
                {data.by_run.slice(0, 10).map((r) => (
                  <li key={r.key ?? "none"} className="flex items-center gap-4 py-3">
                    <span className="min-w-0 flex-1 truncate">
                      {r.key && r.title !== "(eliminato)" ? (
                        <Link to={`/runs/${r.key}`} className="hover:text-violet-ink">
                          {r.title}
                        </Link>
                      ) : (
                        <span className="text-ink-3">{r.title === "(eliminato)" ? "Pratica eliminata" : r.title}</span>
                      )}
                    </span>
                    <span className="tabular text-[13px] text-ink-3">{int(r.calls)} chiamate</span>
                    <span className="tabular w-20 text-right font-medium">{usd(r.cost_usd)}</span>
                  </li>
                ))}
                {!data.by_run.length && <li className="py-6 text-center text-ink-3">Nessuna pratica con costi nel periodo</li>}
              </ul>
            </section>
          </div>

          <section>
            <h2 className="mb-3 text-xl font-bold">Ultime chiamate</h2>
            <Panel className="max-h-96 overflow-auto">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 bg-subtle text-left text-ink-3">
                  <tr>
                    <th className="px-4 py-2 font-medium">Quando</th>
                    <th className="px-3 py-2 font-medium">Attività</th>
                    <th className="px-3 py-2 font-medium">Modello</th>
                    <th className="px-3 py-2 text-right font-medium">Token letti / scritti</th>
                    <th className="px-4 py-2 text-right font-medium">Costo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {calls?.map((c) => (
                    <tr key={c.id} className={c.status === "error" ? "text-bad" : ""}>
                      <td className="px-4 py-2 whitespace-nowrap text-ink-3">{dateTime(c.ts)}</td>
                      <td className="max-w-64 truncate px-3 py-2" title={c.error ?? c.task}>
                        {c.stage_label} <span className="text-ink-3">{c.task.split(":").slice(1).join(":")}</span>
                      </td>
                      <td className="px-3 py-2 text-ink-3">{c.model}</td>
                      <td className="tabular px-3 py-2 text-right">
                        {compact(c.input_tokens + c.cache_read_tokens)} / {compact(c.output_tokens)}
                      </td>
                      <td className="tabular px-4 py-2 text-right">{c.local_cache_hit ? <Tag tone="ok">riuso</Tag> : c.status === "error" ? "errore" : usd(c.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!calls?.length && <Empty title="Nessuna chiamata registrata" />}
            </Panel>
          </section>
        </>
      )}

      <PricingTable />
    </div>
  );
}
