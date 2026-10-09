import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Download, Hammer } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api, fileUrl } from "../../lib/api";
import { compact, dateTime, int, usd } from "../../lib/format";
import type { PersonReport, Run } from "../../lib/types";
import { Button, Metric, NextStep, Panel, Tabs, Tag, buttonClass } from "../ui";
import { LogList } from "./Activity";
import { CoverageBar, PersonDrawer } from "./PersonDrawer";
import { SlideGallery } from "./SlideGallery";

const STAGE_NAMES: Record<string, string> = {
  bando: "Lettura del bando",
  cv_parse: "Lettura dei CV",
  match: "Abbinamento",
  write: "Scrittura contenuti",
  verify: "Verifica di fedeltà",
  critic: "Controllo grafico",
  translate_labels: "Traduzione etichette",
  template: "Analisi template",
};

function PersonRow({ p, index, onOpen }: { p: PersonReport; index: number; onOpen: () => void }) {
  const c = p.content;
  const toCheck = p.faith_issues.filter((f) => f.severity === "high").length;
  return (
    <li className="group grid cursor-pointer gap-x-8 gap-y-3 py-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" onClick={onOpen}>
      <div className="flex min-w-0 gap-4">
        <span className="pt-0.5 font-display text-sm font-semibold text-ink-3 tabular">{String(index + 1).padStart(2, "0")}</span>
        <div className="min-w-0">
          <div className="truncate font-display text-[18px] font-semibold transition-colors group-hover:text-violet-ink">{c.full_name}</div>
          <div className="truncate text-[13px] text-ink-2">{c.profile_name}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {c.total_experience && <Tag>{c.total_experience} di esperienza</Tag>}
            {c.name_is_placeholder && <Tag tone="warn">nome inventato</Tag>}
            {p.fit_issues.length > 0 && <Tag tone="bad">impaginazione da rivedere</Tag>}
            {toCheck > 0 && <Tag tone="bad">{toCheck} affermazioni da verificare</Tag>}
            {p.fit_notes.length > 0 && <Tag>{p.fit_notes.length === 1 ? "1 taglio" : `${p.fit_notes.length} tagli`} per spazio</Tag>}
          </div>
        </div>
      </div>
      <div className="pl-9 md:pl-0 md:pt-1">
        <div className="mb-2 text-xs font-medium tracking-wide text-ink-3 uppercase">Requisiti del profilo</div>
        <CoverageBar cov={c.coverage} />
      </div>
      <div className="hidden items-center md:flex">
        <span className="link-more">
          Dettagli <ArrowRight className="size-4" />
        </span>
      </div>
    </li>
  );
}

function RunCosts({ run }: { run: Run }) {
  const { data: calls } = useQuery({ queryKey: ["calls", run.id, run.updated_at], queryFn: () => api.calls(run.id, 500) });
  const t = run.cost.totals;
  return (
    <div className="space-y-8 py-2">
      <div className="grid grid-cols-2 gap-6 border-b border-line pb-6 md:grid-cols-4">
        <Metric label="Totale" value={usd(t.cost_usd)} hint={`${usd(t.cost_usd / Math.max(run.cvs.length, 1))} per candidato`} />
        <Metric label="Chiamate AI" value={int(t.calls)} hint={t.errors ? `${t.errors} non riuscite` : "tutte riuscite"} />
        <Metric label="Token" value={compact(t.input_tokens + t.output_tokens)} hint={`${compact(t.input_tokens)} letti · ${compact(t.output_tokens)} scritti`} />
        <Metric label="Risparmiato" value={usd(t.saved_usd)} hint={`${t.cache_hits} risposte riusate`} />
      </div>
      <div>
        <h3 className="mb-3 text-lg font-bold">Per attività</h3>
        <ul className="divide-y divide-line border-y border-line text-[15px]">
          {run.cost.by_stage.map((s) => (
            <li key={s.key} className="flex items-center gap-4 py-2.5">
              <span className="flex-1">{STAGE_NAMES[s.key ?? ""] ?? s.key}</span>
              <span className="tabular text-[13px] text-ink-3">{s.calls} chiamate</span>
              <span className="tabular w-24 text-right font-medium">{usd(s.cost_usd)}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="mb-3 text-lg font-bold">Tutte le chiamate</h3>
        <div className="max-h-96 overflow-auto rounded-lg border border-line">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-subtle text-left text-ink-3">
              <tr>
                <th className="px-4 py-2 font-medium">Ora</th>
                <th className="px-3 py-2 font-medium">Attività</th>
                <th className="px-3 py-2 font-medium">Modello</th>
                <th className="px-3 py-2 text-right font-medium">Token</th>
                <th className="px-4 py-2 text-right font-medium">Costo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {calls?.map((c) => (
                <tr key={c.id} className={c.status === "error" ? "text-bad" : ""}>
                  <td className="px-4 py-1.5 text-ink-3">{new Date(c.ts).toLocaleTimeString("it-IT")}</td>
                  <td className="max-w-56 truncate px-3 py-1.5" title={c.error ?? c.task}>
                    {c.task}
                  </td>
                  <td className="px-3 py-1.5 text-ink-3">{c.model}</td>
                  <td className="tabular px-3 py-1.5 text-right">
                    {compact(c.input_tokens + c.cache_read_tokens)} / {compact(c.output_tokens)}
                  </td>
                  <td className="tabular px-4 py-1.5 text-right">{c.local_cache_hit ? <Tag tone="ok">riuso</Tag> : c.status === "error" ? "errore" : usd(c.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

type Tab = "people" | "slides" | "costs" | "log";

export function ResultPanel({ run, onReview }: { run: Run; onReview?: () => void }) {
  const qc = useQueryClient();
  const res = run.result!;
  const [tab, setTab] = useState<Tab>("people");
  const [openFile, setOpenFile] = useState<string | null>(null);
  const busy = run.status === "generating";
  const people = res.report.people;
  const bad = people.filter((p) => p.fit_issues.length).length;
  const toCheck = people.reduce((a, p) => a + p.faith_issues.filter((f) => f.severity === "high").length, 0);
  const invented = people.filter((p) => p.content.name_is_placeholder).length;

  const rebuild = useMutation({
    mutationFn: () => api.rebuild(run.id),
    onSuccess: (r) => qc.setQueryData(["run", run.id], r),
    onError: (e: Error) => toast.error(e.message),
  });

  const checks = [
    bad && `${bad} candidat${bad === 1 ? "o" : "i"} con impaginazione da rivedere`,
    toCheck && `${toCheck} affermazion${toCheck === 1 ? "e" : "i"} da verificare`,
    invented && `${invented} nom${invented === 1 ? "e inventato" : "i inventati"}`,
  ].filter(Boolean) as string[];

  return (
    <div className="space-y-10">
      {res.pending_edits ? (
        <NextStep
          tone="warn"
          title="Applica le modifiche alla presentazione"
          action={
            <Button icon={<Hammer className="size-4" />} loading={rebuild.isPending || busy} onClick={() => rebuild.mutate()}>
              Ricostruisci
            </Button>
          }
        >
          Hai modificato dei contenuti: ricostruisci il PPTX per vederli nelle slide. Non servono nuove chiamate AI.
        </NextStep>
      ) : (
        <NextStep
          tone={checks.length ? "warn" : "ok"}
          title={checks.length ? "Presentazione pronta: dai un'occhiata ai punti segnalati" : "Presentazione pronta"}
          action={
            <a className={buttonClass("primary", "lg")} href={fileUrl(run.id, res.pptx, true)}>
              <Download className="size-4" /> Scarica PPTX
            </a>
          }
        >
          {checks.length ? checks.join(" · ") : "Tutti i testi rientrano nei riquadri del template e non ci sono affermazioni gravi da verificare."}
        </NextStep>
      )}

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px] text-ink-3">
        <span>
          {people.length} candidati · {res.slides.length} slide · generata {dateTime(res.generated_at)}
          {res.edited && " · con modifiche manuali"}
        </span>
        <span className="flex gap-5">
          <a className="link-more text-[13px]" href={fileUrl(run.id, res.report_md, true)}>
            Report
          </a>
          <a className="link-more text-[13px]" href={fileUrl(run.id, res.report_json, true)}>
            Dati JSON
          </a>
          {res.pending_edits && (
            <a className="link-more text-[13px]" href={fileUrl(run.id, res.pptx, true)}>
              PPTX precedente
            </a>
          )}
          {onReview && (
            <button className="link-more cursor-pointer text-[13px]" onClick={onReview} disabled={busy}>
              Rivedi abbinamenti e indicazioni
            </button>
          )}
        </span>
      </div>

      <div>
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { value: "people", label: "Candidati", count: people.length },
            { value: "slides", label: "Slide", count: res.slides.length },
            { value: "costs", label: "Costi" },
            { value: "log", label: "Registro" },
          ]}
        />
        <div className="pt-2">
          {tab === "people" && (
            <ul className="divide-y divide-line">
              {people.map((p, i) => (
                <PersonRow key={p.content.source_file} p={p} index={i} onOpen={() => setOpenFile(p.content.source_file)} />
              ))}
            </ul>
          )}
          {tab === "slides" && (
            <div className="pt-4">
              <SlideGallery runId={run.id} slides={res.slides} version={res.generated_at} columns="sm:grid-cols-2 xl:grid-cols-3" />
            </div>
          )}
          {tab === "costs" && <RunCosts run={run} />}
          {tab === "log" && (
            <Panel className="mt-4 p-1">
              <LogList log={run.log} />
            </Panel>
          )}
        </div>
      </div>

      <PersonDrawer
        runId={run.id}
        report={people.find((p) => p.content.source_file === openFile) ?? null}
        slides={res.slides}
        version={res.generated_at}
        busy={busy}
        fields={res.report.fields}
        fieldLabels={res.report.field_labels}
        onClose={() => setOpenFile(null)}
      />
    </div>
  );
}
