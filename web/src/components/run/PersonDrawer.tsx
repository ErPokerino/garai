import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Check, Minus, Pencil, Plus, Trash2, X } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import type { ExperienceBlock, PersonContent, PersonReport, RequirementCoverage } from "../../lib/types";
import { Button, Drawer, Field, Tabs, Tag } from "../ui";
import { SlideGallery } from "./SlideGallery";

export function coverageStats(cov: RequirementCoverage[]) {
  const met = cov.filter((c) => c.status === "met").length;
  const partial = cov.filter((c) => c.status === "partial").length;
  return { met, partial, missing: cov.length - met - partial, total: cov.length };
}

/** Barra a segmenti: un segmento per requisito (soddisfatto / parziale / non evidenziato). */
export function CoverageBar({ cov }: { cov: RequirementCoverage[] }) {
  const s = coverageStats(cov);
  if (!s.total) return <span className="text-[13px] text-ink-3">Copertura non disponibile</span>;
  const rank = (st: string) => (st === "met" ? 0 : st === "partial" ? 1 : 2);
  const order = [...cov].sort((a, b) => rank(a.status) - rank(b.status));
  return (
    <div>
      <div className="flex gap-[3px]">
        {order.map((r, i) => (
          <span
            key={i}
            title={r.requirement}
            className={clsx("h-2 flex-1 rounded-[2px]", r.status === "met" ? "bg-violet" : r.status === "partial" ? "bg-orange" : "bg-line-strong")}
          />
        ))}
      </div>
      <div className="tabular mt-2 flex flex-wrap gap-x-4 text-[13px] text-ink-2">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-[2px] bg-violet" />
          {s.met} soddisfatti
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-[2px] bg-orange" />
          {s.partial} parziali
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-[2px] bg-line-strong" />
          {s.missing} non evidenziati
        </span>
      </div>
    </div>
  );
}

const COV_ICON: Record<string, ReactNode> = {
  met: (
    <span className="grid size-5 place-items-center rounded-full bg-violet text-white">
      <Check className="size-3" />
    </span>
  ),
  partial: (
    <span className="grid size-5 place-items-center rounded-full bg-orange text-white">
      <Minus className="size-3" />
    </span>
  ),
  not_evidenced: (
    <span className="grid size-5 place-items-center rounded-full border border-line-strong text-ink-3">
      <X className="size-3" />
    </span>
  ),
};

function Section({ title, children, count }: { title: string; children: ReactNode; count?: number }) {
  return (
    <section className="mb-9">
      <h4 className="mb-3 flex items-baseline gap-2 text-lg font-bold">
        {title}
        {count !== undefined && <span className="font-sans text-sm font-normal text-ink-3 tabular">{count}</span>}
      </h4>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------- dettaglio
function Detail({ runId, report, slides, version }: { runId: string; report: PersonReport; slides: string[]; version: string }) {
  const c = report.content;
  const mySlides = report.slides.map((n) => slides[n - 1]).filter(Boolean);
  const alerts = [
    ...(c.name_is_placeholder ? [`Il CV non riporta il nome: «${c.full_name}» è inventato. Puoi correggerlo in «Contenuti».`] : []),
    ...report.fit_issues.map((f) => `Slide ${f.slide}: ${f.detail}`),
  ];
  return (
    <>
      {alerts.length > 0 && (
        <div className="mb-8 space-y-2">
          {alerts.map((a, i) => (
            <div key={i} className="flex gap-2.5 rounded-lg bg-warn-soft px-3.5 py-2.5 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" /> {a}
            </div>
          ))}
        </div>
      )}
      <Section title="Le sue slide">
        <SlideGallery runId={runId} slides={mySlides} version={version} />
      </Section>
      <Section title="Requisiti del profilo" count={c.coverage.length}>
        <CoverageBar cov={c.coverage} />
        <ul className="mt-4 divide-y divide-line border-y border-line">
          {c.coverage.map((r, i) => (
            <li key={i} className="flex gap-3 py-3 text-[15px]">
              <span className="mt-0.5 shrink-0">{COV_ICON[r.status] ?? COV_ICON.not_evidenced}</span>
              <div className="min-w-0">
                <div>{r.requirement}</div>
                {r.evidence && <div className="mt-0.5 text-[13px] text-ink-3">{r.evidence}</div>}
              </div>
            </li>
          ))}
        </ul>
      </Section>
      {report.faith_issues.length > 0 && (
        <Section title="Da verificare rispetto al CV" count={report.faith_issues.length}>
          <ul className="space-y-2.5">
            {report.faith_issues.map((f, i) => (
              <li key={i} className="rounded-lg border border-line px-4 py-3 text-[15px]">
                <div className="mb-1 flex items-center gap-2">
                  <Tag tone={f.severity === "high" ? "bad" : f.severity === "medium" ? "warn" : "neutral"}>
                    {f.severity === "high" ? "importante" : f.severity === "medium" ? "da controllare" : "lieve"}
                  </Tag>
                  <span className="text-[13px] text-ink-3">{f.slot}</span>
                </div>
                «{f.text}»<div className="mt-0.5 text-[13px] text-ink-3">{f.reason}</div>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {(report.fit_notes.length > 0 || c.warnings.length > 0 || report.visual_notes.length > 0) && (
        <Section title="Note">
          <ul className="list-disc space-y-1 pl-5 text-[15px] text-ink-2">
            {[...c.warnings, ...report.fit_notes, ...report.visual_notes].map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </Section>
      )}
      {c.omitted.length > 0 && (
        <Section title="Lasciato fuori per spazio">
          <ul className="list-disc space-y-1 pl-5 text-[15px] text-ink-2">
            {c.omitted.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------- editor
const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

/** Textarea "una voce per riga": conserva il testo digitato (anche le righe vuote mentre si scrive). */
function LinesArea({ value, onChange, rows, placeholder, className = "input" }: {
  value: string[];
  onChange: (v: string[]) => void;
  rows: number;
  placeholder?: string;
  className?: string;
}) {
  const [text, setText] = useState(() => value.join("\n"));
  return (
    <textarea
      className={className}
      rows={rows}
      placeholder={placeholder}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        onChange(lines(e.target.value));
      }}
    />
  );
}

const STANDARD = new Set([
  "full_name", "profile_name", "phone", "email", "current_role", "current_company", "total_experience", "domicile",
  "summary", "background", "skills", "experiences",
]);

/** Editor dei contenuti: mostra solo i campi che il template stampa (tutti, per le pratiche generate prima). */
function Editor({ value, onChange, fields, fieldLabels }: {
  value: PersonContent;
  onChange: (c: PersonContent) => void;
  fields?: string[];
  fieldLabels?: Record<string, string>;
}) {
  const set = <K extends keyof PersonContent>(k: K, v: PersonContent[K]) => onChange({ ...value, [k]: v });
  const setExp = (i: number, patch: Partial<ExperienceBlock>) => set("experiences", value.experiences.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  const shows = (f: string) => !fields?.length || fields.includes(f);
  const custom = (fields ?? []).filter((f) => !STANDARD.has(f));
  const setExtra = (k: string, v: string | string[]) => set("extra", { ...(value.extra ?? {}), [k]: v });

  return (
    <div className="space-y-6">
      <p className="rounded-lg bg-violet-soft px-4 py-3 text-sm text-ink-2">
        Le modifiche vengono impaginate di nuovo sul template, senza nuove chiamate AI. Se un testo non entra nello spazio viene accorciato e lo trovi
        indicato nelle note.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome e cognome" hint={value.name_is_placeholder ? "Nome inventato: sostituiscilo con quello reale." : undefined}>
          <input
            className="input"
            value={value.full_name}
            onChange={(e) => onChange({ ...value, full_name: e.target.value, name_is_placeholder: false })}
          />
        </Field>
        {shows("current_role") && (
          <Field label="Ruolo attuale">
            <input className="input" value={value.current_role ?? ""} onChange={(e) => set("current_role", e.target.value)} />
          </Field>
        )}
        {shows("current_company") && (
          <Field label="Azienda attuale">
            <input className="input" value={value.current_company ?? ""} onChange={(e) => set("current_company", e.target.value)} />
          </Field>
        )}
        {shows("total_experience") && (
          <Field label="Esperienza complessiva">
            <input className="input" value={value.total_experience ?? ""} onChange={(e) => set("total_experience", e.target.value)} />
          </Field>
        )}
        {fields?.includes("domicile") && (
          <Field label="Sede">
            <input className="input" value={value.domicile ?? ""} onChange={(e) => set("domicile", e.target.value)} />
          </Field>
        )}
        {custom.map((k) => {
          const v = value.extra?.[k];
          const label = fieldLabels?.[k] ?? k;
          return Array.isArray(v) ? (
            <Field key={k} label={label} hint="Una voce per riga">
              <LinesArea rows={3} value={v} onChange={(nv) => setExtra(k, nv)} />
            </Field>
          ) : (
            <Field key={k} label={label}>
              <input className="input" value={v ?? ""} onChange={(e) => setExtra(k, e.target.value)} />
            </Field>
          );
        })}
      </div>
      {shows("summary") && (
      <Field
        label={
          <span className="flex justify-between">
            Sintesi del profilo <span className={clsx("tabular text-xs font-normal", value.summary.length > 600 ? "text-warn" : "text-ink-3")}>{value.summary.length} caratteri</span>
          </span>
        }
      >
        <textarea className="input" rows={5} value={value.summary} onChange={(e) => set("summary", e.target.value)} />
      </Field>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {shows("skills") && (
          <Field label="Competenze" hint="Una per riga, le più rilevanti per prime">
            <LinesArea rows={7} value={value.skills} onChange={(v) => set("skills", v)} />
          </Field>
        )}
        {shows("background") && (
          <Field label="Formazione, certificazioni, lingue" hint="Una voce per riga">
            <LinesArea rows={7} value={value.background} onChange={(v) => set("background", v)} />
          </Field>
        )}
      </div>
      {shows("experiences") && (
      <div>
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-medium">Esperienze</span>
          <Button
            variant="ghost"
            size="sm"
            icon={<Plus className="size-3.5" />}
            onClick={() => set("experiences", [...value.experiences, { title: "", role: "", period: "", bullets: [], source_indices: [] }])}
          >
            Aggiungi
          </Button>
        </div>
        <div className="space-y-3">
          {value.experiences.map((e, i) => (
            // la chiave cambia col numero di esperienze: i campi interni ripartono dai valori aggiornati dopo una rimozione
            <div key={`${i}/${value.experiences.length}`} className="rounded-lg border border-line p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="font-display text-sm font-semibold text-ink-3 tabular">{String(i + 1).padStart(2, "0")}</span>
                <button
                  className="cursor-pointer rounded-md p-1 text-ink-3 hover:bg-bad-soft hover:text-bad"
                  onClick={() => set("experiences", value.experiences.filter((_, j) => j !== i))}
                  aria-label="Rimuovi esperienza"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
              <div className="grid gap-2 sm:grid-cols-[2fr_1.4fr_1fr]">
                <input className="input" placeholder="Settore/Cliente – Progetto" value={e.title} onChange={(ev) => setExp(i, { title: ev.target.value })} />
                <input className="input" placeholder="Ruolo" value={e.role} onChange={(ev) => setExp(i, { role: ev.target.value })} />
                <input className="input" placeholder="Periodo" value={e.period ?? ""} onChange={(ev) => setExp(i, { period: ev.target.value })} />
              </div>
              <LinesArea className="input mt-2" rows={3} placeholder="Attività (una per riga)" value={e.bullets} onChange={(v) => setExp(i, { bullets: v })} />
            </div>
          ))}
        </div>
      </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------- drawer
export function PersonDrawer({ runId, report, slides, version, onClose, busy, fields, fieldLabels }: {
  runId: string;
  report: PersonReport | null;
  slides: string[];
  version: string;
  onClose: () => void;
  busy: boolean;
  fields?: string[];
  fieldLabels?: Record<string, string>;
}) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"detail" | "edit">("detail");
  const [draft, setDraft] = useState<PersonContent | null>(null);
  useEffect(() => {
    setDraft(report ? structuredClone(report.content) : null);
    setTab("detail");
  }, [report]);

  const save = useMutation({
    mutationFn: (c: PersonContent) => api.updatePerson(runId, c),
    onSuccess: (r) => {
      qc.setQueryData(["run", runId], r);
      toast.success("Modifiche salvate", { description: "Ricostruisci la presentazione per applicarle alle slide." });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!report || !draft) return null;
  const c = report.content;
  return (
    <Drawer
      open
      onClose={onClose}
      title={c.full_name}
      subtitle={`${c.profile_name} · ${c.source_file}`}
      width="max-w-3xl"
      footer={
        tab === "edit" ? (
          <>
            <Button variant="secondary" onClick={() => setTab("detail")}>
              Annulla
            </Button>
            <Button loading={save.isPending} disabled={busy} onClick={() => save.mutate(draft)}>
              Salva modifiche
            </Button>
          </>
        ) : (
          <Button variant="secondary" icon={<Pencil className="size-4" />} disabled={busy} onClick={() => setTab("edit")}>
            Modifica i contenuti
          </Button>
        )
      }
    >
      <div className="-mt-3 mb-7">
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { value: "detail", label: "Analisi" },
            { value: "edit", label: "Contenuti" },
          ]}
        />
      </div>
      {tab === "detail" ? <Detail runId={runId} report={report} slides={slides} version={version} /> : <Editor value={draft} onChange={setDraft} fields={fields} fieldLabels={fieldLabels} />}
    </Drawer>
  );
}
