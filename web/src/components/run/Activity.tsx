import clsx from "clsx";
import { Check } from "lucide-react";
import { compact, usd } from "../../lib/format";
import type { LiveCall, LogEntry, Run } from "../../lib/types";
import { Panel, Progress, Tag } from "../ui";

export const STAGE_LABEL: Record<string, string> = {
  bando: "Lettura del bando",
  cv: "Lettura dei CV",
  match: "Abbinamento ai profili",
  template: "Analisi del template",
  write: "Scrittura dei contenuti",
  fit: "Impaginazione sul template",
  render: "Creazione delle anteprime",
  critic: "Controllo grafico",
  done: "Completato",
  error: "Errore",
};

const CALL_STAGE: Record<string, string> = {
  bando: "Bando",
  cv_parse: "CV",
  match: "Abbinamento",
  write: "Scrittura",
  verify: "Verifica",
  critic: "Controllo grafico",
  translate_labels: "Etichette",
  template: "Template",
};

// ---------------------------------------------------------------------------- indice delle fasi
const PHASES = [
  { n: "01", label: "Analisi", hint: "bando e CV" },
  { n: "02", label: "Controllo", hint: "abbinamenti e nomi" },
  { n: "03", label: "Presentazione", hint: "generazione e download" },
];

function phaseOf(run: Run): { idx: number; fill: number } {
  if (run.status === "done") return { idx: 2, fill: 1 };
  if (run.status === "generating") return { idx: 2, fill: run.progress };
  if (run.bando && run.cvs.length && run.status !== "analyzing" && run.status !== "queued") return { idx: 1, fill: 0.5 };
  return { idx: 0, fill: run.progress };
}

export function PhaseIndex({ run }: { run: Run }) {
  const { idx, fill } = phaseOf(run);
  const failed = run.status === "error" || run.status === "interrupted";
  return (
    <ol className="grid grid-cols-3 gap-3 sm:gap-6">
      {PHASES.map((p, i) => {
        const done = i < idx || (run.status === "done" && i === idx);
        const active = i === idx && !done;
        const w = done ? 1 : active ? Math.max(fill, 0.04) : 0;
        return (
          <li key={p.n} className="min-w-0">
            <div className="h-1 overflow-hidden rounded-full bg-subtle">
              <div className={clsx("h-full rounded-full transition-[width] duration-700", failed && active ? "bg-bad" : "brand-line")} style={{ width: `${w * 100}%` }} />
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className={clsx("font-display text-sm font-semibold tabular", done || active ? "text-violet-ink" : "text-ink-3")}>{p.n}</span>
              <span className={clsx("truncate font-display text-[15px] font-semibold", !done && !active && "text-ink-3")}>{p.label}</span>
              {done && <Check className="size-3.5 shrink-0 text-violet" />}
            </div>
            <div className="hidden truncate text-[13px] text-ink-3 sm:block">{p.hint}</div>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------- attivita' in corso
export function ActivityPanel({ run, calls }: { run: Run; calls: LiveCall[] }) {
  const generating = run.status === "generating";
  const timeline = generating ? ["write", "fit", "render", ...(run.options.visual_critic ? ["critic"] : [])] : ["bando", "cv", "match"];
  const curIdx = timeline.indexOf(run.stage);
  const total = run.cost.totals;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <Panel className="p-6">
        <div className="font-mono text-[11px] tracking-wider text-ink-3 uppercase">&gt;_ {generating ? "generazione" : "analisi"} in corso</div>
        <h2 className="mt-1 text-[26px] font-bold">{generating ? "Stiamo preparando la presentazione" : "Stiamo leggendo bando e CV"}</h2>
        <p className="mt-1 text-[15px] text-ink-2">{run.message || "Avvio…"}</p>
        <Progress value={run.progress} className="mt-5" />
        <ol className="mt-6 space-y-3">
          {timeline.map((s, i) => {
            const done = curIdx > i;
            const active = curIdx === i || (curIdx === -1 && i === 0);
            return (
              <li key={s} className="flex items-center gap-3 text-[15px]">
                <span
                  className={clsx(
                    "grid size-5 place-items-center rounded-full",
                    done ? "bg-violet text-white" : active ? "border-2 border-violet" : "border border-line-strong",
                  )}
                >
                  {done && <Check className="size-3" />}
                  {active && <span className="size-1.5 animate-pulse rounded-full bg-violet" />}
                </span>
                <span className={clsx(active ? "font-medium" : done ? "text-ink-2" : "text-ink-3")}>{STAGE_LABEL[s]}</span>
              </li>
            );
          })}
        </ol>
        <LogList log={run.log.slice(-10)} className="mt-6" />
      </Panel>

      <Panel className="p-6">
        <div className="eyebrow">Costo in tempo reale</div>
        <div className="tabular mt-3 font-display text-[40px] leading-none font-bold">{usd(total.cost_usd)}</div>
        <div className="mt-2 text-[13px] text-ink-3">
          {total.calls} chiamate AI · {compact(total.input_tokens)} token letti · {compact(total.output_tokens)} scritti
        </div>
        <ul className="mt-5 max-h-80 space-y-1 overflow-y-auto">
          {calls.length === 0 && <li className="text-[13px] text-ink-3">In attesa della prima chiamata…</li>}
          {calls.map((c, i) => (
            <li key={i} className="flex items-center gap-2 border-b border-line py-1.5 text-[13px] animate-rise last:border-0">
              <span className="w-24 shrink-0 font-medium">{CALL_STAGE[c.stage] ?? c.stage}</span>
              <span className="min-w-0 flex-1 truncate text-ink-3" title={c.task}>
                {c.task.split(":").slice(1).join(":") || c.model}
              </span>
              {c.local_cache_hit ? <Tag tone="ok">riuso</Tag> : <span className="tabular">{usd(c.cost_usd)}</span>}
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

export function LogList({ log, className }: { log: LogEntry[]; className?: string }) {
  if (!log.length) return null;
  return (
    <div className={clsx("rounded-lg bg-subtle p-4 font-mono text-[12px] leading-relaxed", className)}>
      {log.map((l, i) => (
        <div key={i} className={clsx("flex gap-3", l.level === "error" ? "text-bad" : "text-ink-2")}>
          <span className="shrink-0 text-ink-3">{new Date(l.ts).toLocaleTimeString("it-IT")}</span>
          <span className="min-w-0 break-words">{l.msg}</span>
        </div>
      ))}
    </div>
  );
}
