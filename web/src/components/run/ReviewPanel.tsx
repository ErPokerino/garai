import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, ChevronDown, PenLine, Save, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { LANG_LABEL, usd } from "../../lib/format";
import type { Assignment, BandoSpec, CandidateDetails, CVCanonical, Run } from "../../lib/types";
import { ExpandableText } from "../ExpandableText";
import { Button, Field, NextStep, Panel, Select, Spinner, Switch, Tag } from "../ui";

const reliability = (c: number) =>
  c >= 0.75 ? { label: "Abbinamento sicuro", tone: "ok" as const } : c >= 0.5 ? { label: "Da verificare", tone: "warn" as const } : { label: "Incerto", tone: "bad" as const };

function since(cv: CVCanonical): string | null {
  const years = cv.experiences.flatMap((e) => [e.start, e.end].filter(Boolean).map((d) => Number(String(d).slice(0, 4))));
  return years.length ? `in attività dal ${Math.min(...years)}` : null;
}

/** Valori del modulo "Dati e indicazioni" di un candidato. */
type Details = Required<Pick<CandidateDetails, "location" | "email" | "phone" | "current_role" | "instructions" | "excluded">>;

function detailsOf(run: Run, cv: CVCanonical): Details {
  const ed = run.candidates?.[cv.source_file];
  return {
    location: cv.location ?? "",
    email: cv.email ?? "",
    phone: cv.phone ?? "",
    current_role: ed?.current_role ?? "",
    instructions: ed?.instructions ?? "",
    excluded: ed?.excluded ?? false,
  };
}

/** Solo i campi cambiati rispetto allo stato salvato (testi confrontati senza spazi agli estremi). */
function diff(now: Details, before: Details): CandidateDetails | null {
  const out: CandidateDetails = {};
  for (const k of Object.keys(now) as (keyof Details)[]) {
    const a = now[k];
    const b = before[k];
    if (typeof a === "string" ? a.trim() !== String(b).trim() : a !== b) Object.assign(out, { [k]: a });
  }
  return Object.keys(out).length ? out : null;
}

function DetailsForm({ cv, value, onChange, canExclude }: { cv: CVCanonical; value: Details; onChange: (d: Details) => void; canExclude: boolean }) {
  const set = (k: keyof Details, v: string | boolean) => onChange({ ...value, [k]: v });
  return (
    <div className="mt-4 space-y-4 rounded-xl border border-line bg-subtle/60 p-4 sm:p-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Ruolo attuale" hint="Lascia vuoto per farlo scrivere all'AI dal CV.">
          <input className="input" value={value.current_role} maxLength={120} placeholder={cv.headline ?? "dal CV"} onChange={(e) => set("current_role", e.target.value)} />
        </Field>
        <Field label="Sede">
          <input className="input" value={value.location} maxLength={120} placeholder="Città" onChange={(e) => set("location", e.target.value)} />
        </Field>
        <Field label="Email">
          <input className="input" type="email" value={value.email} maxLength={120} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Telefono">
          <input className="input" value={value.phone} maxLength={120} onChange={(e) => set("phone", e.target.value)} />
        </Field>
      </div>
      <Field label="Indicazioni per la scrittura" hint="L'AI le segue senza mai aggiungere informazioni che il CV non contiene.">
        <textarea
          className="input"
          rows={3}
          maxLength={2000}
          value={value.instructions}
          placeholder="Es. metti in evidenza i progetti SAP per la PA; non citare il cliente X; al massimo tre esperienze."
          onChange={(e) => set("instructions", e.target.value)}
        />
      </Field>
      <Switch
        checked={!value.excluded}
        disabled={!value.excluded && !canExclude}
        onChange={(v) => set("excluded", !v)}
        label="Includi nella presentazione"
        hint={!value.excluded && !canExclude ? "Almeno un candidato deve restare nella presentazione." : "Se lo escludi non verrà generato e non avrà costi."}
      />
    </div>
  );
}

function CandidateRow({ cv, bando, value, name, onAssign, onName, index, details, onDetails, canExclude }: {
  cv: CVCanonical;
  bando: BandoSpec;
  value: Assignment;
  name: string;
  onAssign: (a: Assignment) => void;
  onName: (n: string) => void;
  index: number;
  details: Details;
  onDetails: (d: Details) => void;
  canExclude: boolean;
}) {
  const [open, setOpen] = useState(false);
  const prof = bando.profiles.find((p) => p.id === value.profile_id);
  const subs = prof?.subprofiles.map((s) => s.name) ?? [];
  const rel = reliability(value.confidence);
  const missing = !cv.full_name;
  const excluded = details.excluded;
  return (
    <li className="py-6">
      <div className={clsx("grid gap-x-8 gap-y-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]", excluded && "opacity-55")}>
        <div className="flex min-w-0 gap-4">
          <span className="pt-2 font-display text-sm font-semibold text-ink-3 tabular">{String(index + 1).padStart(2, "0")}</span>
          <div className="min-w-0 flex-1">
            <label className="block">
              <span className="sr-only">Nome e cognome</span>
              <div className="relative">
                <input
                  value={name}
                  onChange={(e) => onName(e.target.value)}
                  placeholder="Inserisci nome e cognome"
                  maxLength={80}
                  className={clsx(
                    "h-10 w-full rounded-lg border px-3 pr-9 font-display text-[18px] font-semibold outline-none transition placeholder:font-sans placeholder:text-[15px] placeholder:font-normal",
                    missing && !name.trim() && !excluded
                      ? "border-orange bg-orange-soft placeholder:text-orange-ink focus:ring-3 focus:ring-orange/20"
                      : "border-transparent bg-transparent hover:border-line-strong focus:border-violet focus:bg-surface focus:ring-3 focus:ring-violet/15",
                  )}
                />
                <PenLine className="pointer-events-none absolute top-3 right-3 size-4 text-ink-3" />
              </div>
            </label>
            {missing && !excluded && (
              <p className={clsx("mt-1.5 px-3 text-[13px]", name.trim() ? "text-ink-3" : "text-orange-ink")}>
                {name.trim() ? "Nome inserito a mano (il CV non lo riporta)." : "Il CV non riporta il nome: inseriscilo, altrimenti nella presentazione resterà vuoto."}
              </p>
            )}
            <div className="mt-1.5 px-3 text-[13px] text-ink-3">
              <span className="truncate" title={cv.source_file}>
                {cv.source_file}
              </span>
              {(cv.headline || since(cv)) && <div className="mt-0.5 truncate text-ink-2">{[cv.headline, since(cv)].filter(Boolean).join(" · ")}</div>}
            </div>
          </div>
        </div>

        <div className="min-w-0 space-y-2.5 pl-9 lg:pl-0">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Select
              ariaLabel="Profilo del bando"
              className="min-w-0 flex-1"
              value={value.profile_id}
              disabled={excluded}
              onChange={(pid) => onAssign({ ...value, profile_id: pid, subprofile: null })}
              options={bando.profiles.map((p) => ({ value: p.id, label: `${p.id} · ${p.name_local || p.name}` }))}
            />
            {subs.length > 0 && (
              <Select
                ariaLabel="Variante del profilo"
                className="sm:w-48"
                value={value.subprofile ?? ""}
                disabled={excluded}
                onChange={(v) => onAssign({ ...value, subprofile: v || null })}
                options={[{ value: "", label: "Nessuna variante" }, ...subs.map((s) => ({ value: s, label: s }))]}
              />
            )}
          </div>
          <div className="flex items-start gap-2.5 text-[13px]">
            <Tag tone={rel.tone} className="shrink-0">
              {rel.label}
            </Tag>
            <ExpandableText text={value.rationale} className="min-w-0 flex-1 text-ink-2" />
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 pl-9">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 font-display text-[13px] font-medium text-violet-ink transition-colors hover:bg-violet-soft"
        >
          <SlidersHorizontal className="size-3.5" />
          Dati e indicazioni
          <ChevronDown className={clsx("size-3.5 transition", open && "rotate-180")} />
        </button>
        {excluded && <Tag tone="bad">escluso dalla presentazione</Tag>}
        {details.instructions.trim() && <Tag tone="violet">con indicazioni</Tag>}
        {details.current_role.trim() && <Tag>ruolo impostato</Tag>}
      </div>
      {open && (
        <div className="pl-9">
          <DetailsForm cv={cv} value={details} onChange={onDetails} canExclude={canExclude} />
        </div>
      )}
    </li>
  );
}

function BandoSummary({ bando }: { bando: BandoSpec }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Panel>
      <div className="px-5 pt-5 pb-3">
        <div className="eyebrow">Il bando</div>
        <h3 className="mt-2 text-[18px] leading-snug font-bold">{bando.title || "Bando"}</h3>
        <p className="mt-1 text-[13px] text-ink-3">
          {bando.profiles.length} profili · {LANG_LABEL[bando.language] ?? bando.language} · i CV verranno scritti in questa lingua
        </p>
      </div>
      <ul className="max-h-[26rem] overflow-y-auto border-t border-line">
        {bando.profiles.map((p) => (
          <li key={p.id} className="border-b border-line last:border-0">
            <button
              className="flex w-full cursor-pointer items-center gap-3 px-5 py-2.5 text-left text-sm hover:bg-subtle"
              onClick={() => setOpen(open === p.id ? null : p.id)}
              aria-expanded={open === p.id}
            >
              <span className="w-8 shrink-0 text-xs text-ink-3 tabular">{p.id}</span>
              <span className="min-w-0 flex-1 truncate">{p.name_local || p.name}</span>
              <ChevronDown className={clsx("size-4 shrink-0 text-ink-3 transition", open === p.id && "rotate-180")} />
            </button>
            {open === p.id && (
              <div className="space-y-3 px-5 pb-4 text-[13px] text-ink-2">
                {p.purpose && <p>{p.purpose}</p>}
                {(
                  [
                    ["Requisiti minimi", p.min_requirements],
                    ["Elementi premianti", p.preferred],
                    ...p.subprofiles.map((sp) => [`Variante ${sp.name}`, sp.min_requirements]),
                  ] as [string, string[]][]
                )
                  .filter(([, items]) => items.length)
                  .map(([t, items]) => (
                    <div key={t}>
                      <div className="mb-1 font-medium text-ink">{t}</div>
                      <ul className="list-disc space-y-0.5 pl-4">
                        {items.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function ReviewPanel({ run, onBack }: { run: Run; onBack?: () => void }) {
  const qc = useQueryClient();
  const bando = run.bando!;
  const initialNames = useMemo(() => Object.fromEntries(run.cvs.map((c) => [c.source_file, c.full_name ?? ""])), [run.cvs]);
  const initialDetails = useMemo(() => Object.fromEntries(run.cvs.map((c) => [c.source_file, detailsOf(run, c)])), [run]);
  const [assign, setAssign] = useState<Record<string, Assignment>>(run.assignments);
  const [names, setNames] = useState<Record<string, string>>(initialNames);
  const [details, setDetails] = useState<Record<string, Details>>(initialDetails);
  const [guidance, setGuidance] = useState(run.guidance ?? "");
  const [critic, setCritic] = useState(run.options.visual_critic);
  const [hideCompanies, setHideCompanies] = useState(!!run.options.hide_companies);
  useEffect(() => {
    setHideCompanies(!!run.options.hide_companies);
  }, [run.options.hide_companies]);
  useEffect(() => {
    setAssign(run.assignments);
  }, [run.assignments]);
  useEffect(() => {
    setNames(initialNames);
  }, [initialNames]);
  useEffect(() => {
    setDetails(initialDetails);
  }, [initialDetails]);
  useEffect(() => {
    setGuidance(run.guidance ?? "");
  }, [run.guidance]);

  const changedNames = Object.fromEntries(Object.entries(names).filter(([k, v]) => v.trim() !== (initialNames[k] ?? "").trim()));
  const changedDetails = Object.fromEntries(
    Object.entries(details)
      .map(([k, d]) => [k, diff(d, initialDetails[k])] as const)
      .filter(([, d]) => d !== null),
  ) as Record<string, CandidateDetails>;
  const guidanceDirty = guidance.trim() !== (run.guidance ?? "").trim();
  const assignDirty = Object.entries(assign).some(
    ([k, a]) => a.profile_id !== run.assignments[k]?.profile_id || (a.subprofile ?? null) !== (run.assignments[k]?.subprofile ?? null),
  );
  const dirty = assignDirty || Object.keys(changedNames).length > 0 || Object.keys(changedDetails).length > 0 || guidanceDirty;

  const est = useQuery({ queryKey: ["estimate", run.id, critic, run.updated_at], queryFn: () => api.estimate(run.id, critic) });

  const persist = () => api.setAssignments(run.id, assignDirty ? assign : {}, changedNames, changedDetails, guidanceDirty ? guidance : undefined);
  const save = useMutation({
    mutationFn: persist,
    onSuccess: (r) => {
      qc.setQueryData(["run", run.id], r);
      toast.success("Modifiche salvate");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const generate = useMutation({
    mutationFn: async () => {
      if (dirty) await persist();
      return api.generate(run.id, critic, hideCompanies);
    },
    onSuccess: (r) => qc.setQueryData(["run", run.id], r),
    onError: (e: Error) => toast.error(e.message),
  });

  // profilo cambiato a mano: abbinamento "sicuro"; tornato a quello proposto: ripristina la motivazione originale
  const pick = (file: string, a: Assignment) => {
    const orig = run.assignments[file];
    const same = a.profile_id === orig?.profile_id;
    setAssign({ ...assign, [file]: { ...a, confidence: same ? orig.confidence : 1, rationale: same ? orig.rationale : "Scelto manualmente" } });
  };

  const order = new Map(bando.profiles.map((p, i) => [p.id, i]));
  const cvs = [...run.cvs].sort((a, b) => (order.get(assign[a.source_file]?.profile_id) ?? 99) - (order.get(assign[b.source_file]?.profile_id) ?? 99));
  const active = run.cvs.filter((c) => !details[c.source_file]?.excluded);
  const nExcluded = run.cvs.length - active.length;
  const uncertain = active.filter((c) => (assign[c.source_file]?.confidence ?? 1) < 0.5).length;
  const nameless = active.filter((c) => !c.full_name && !names[c.source_file]?.trim()).length;
  const failed = run.status === "error" || run.status === "interrupted";

  const todo = [
    uncertain && `${uncertain} abbinament${uncertain === 1 ? "o incerto" : "i incerti"}`,
    nameless && `${nameless} nom${nameless === 1 ? "e mancante" : "i mancanti"}`,
  ].filter(Boolean);

  return (
    <div className="space-y-8">
      {/* un solo comando di generazione (nel riquadro con la stima dei costi): qui solo l'indicazione; in errore parla il riquadro dell'errore */}
      {onBack && (
        <NextStep
          tone="violet"
          title="Stai rivedendo una pratica già generata"
          action={
            <Button variant="secondary" onClick={onBack}>
              Torna alla presentazione
            </Button>
          }
        >
          Cambia abbinamenti, dati o indicazioni e usa «Genera la presentazione»: la nuova versione sostituisce quella attuale, comprese le
          modifiche fatte a mano ai contenuti.
        </NextStep>
      )}
      {!failed && !onBack && (
        <NextStep
          tone={todo.length ? "warn" : "violet"}
          title={todo.length ? `Controlla ${todo.join(" e ")}` : "Tutto pronto per generare la presentazione"}
        >
          {todo.length
            ? "Gli elementi da verificare sono evidenziati qui sotto. Poi usa «Genera la presentazione»: puoi procedere anche senza correggerli."
            : "Gli abbinamenti proposti sono affidabili. Se vuoi, aggiungi indicazioni per la scrittura; poi controlla la stima dei costi e usa «Genera la presentazione»."}
        </NextStep>
      )}

      <div className="grid gap-8 xl:grid-cols-[1fr_340px]">
        <section>
          <div className="mb-2 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold">Candidati e profili</h2>
              <p className="mt-1 text-[15px] text-ink-2">
                Ogni CV è abbinato al profilo del bando più adatto. In «Dati e indicazioni» correggi i dati del candidato e dici all'AI cosa mettere in evidenza.
              </p>
            </div>
            {dirty && (
              <Button variant="secondary" size="sm" icon={<Save className="size-3.5" />} loading={save.isPending} onClick={() => save.mutate()}>
                Salva modifiche
              </Button>
            )}
          </div>

          <Field
            className="my-6"
            label="Indicazioni per tutti i candidati"
            hint="Valgono per ogni CV, insieme alle indicazioni del singolo candidato."
          >
            <textarea
              className="input"
              rows={2}
              maxLength={3000}
              value={guidance}
              placeholder="Es. evidenzia sempre le esperienze nella Pubblica Amministrazione e le certificazioni richieste dal bando."
              onChange={(e) => setGuidance(e.target.value)}
            />
          </Field>

          <ul className="divide-y divide-line border-y border-line">
            {cvs.map((cv, i) => (
              <CandidateRow
                key={cv.source_file}
                index={i}
                cv={cv}
                bando={bando}
                value={assign[cv.source_file]}
                name={names[cv.source_file] ?? ""}
                onAssign={(a) => pick(cv.source_file, a)}
                onName={(n) => setNames({ ...names, [cv.source_file]: n })}
                details={details[cv.source_file]}
                onDetails={(d) => setDetails({ ...details, [cv.source_file]: d })}
                canExclude={active.length > 1}
              />
            ))}
          </ul>
        </section>

        <aside className="space-y-6">
          <Panel className="p-5 xl:sticky xl:top-28">
            <div className="eyebrow">Generazione</div>
            <div className="mt-4">
              <div className="text-[13px] text-ink-3">Costo stimato</div>
              {est.isLoading ? (
                <Spinner className="mt-2 size-4" />
              ) : est.data ? (
                <>
                  <div className="tabular mt-1 font-display text-[34px] leading-none font-bold">~{usd(est.data.expected)}</div>
                  <div className="tabular mt-2 text-[13px] text-ink-3">
                    tra {usd(est.data.min)} e {usd(est.data.max)} · già speso {usd(est.data.spent_so_far)}
                  </div>
                  {dirty && <p className="mt-2 text-[13px] text-ink-3">La stima si aggiorna quando salvi le modifiche.</p>}
                  {est.data.notes.slice(2).map((n, i) => (
                    <p key={i} className="mt-2 text-[13px] text-warn">
                      {n}
                    </p>
                  ))}
                </>
              ) : null}
            </div>
            <div className="mt-5 border-t border-line pt-5">
              <Switch checked={critic} onChange={setCritic} label="Controllo grafico con AI" hint="Segnala difetti visivi confrontando le slide con il template." />
              <div className="mt-4">
                <Switch
                  checked={hideCompanies}
                  onChange={setHideCompanies}
                  label="Non citare le aziende"
                  hint="Al posto dei nomi di datori di lavoro e clienti viene indicato il settore."
                />
              </div>
            </div>
            <Button size="lg" className="mt-5 w-full" loading={generate.isPending} onClick={() => generate.mutate()}>
              Genera la presentazione <ArrowRight className="size-4" />
            </Button>
            <p className="mt-2 text-center text-[13px] text-ink-3">
              {active.length} candidat{active.length === 1 ? "o" : "i"} nella presentazione
              {nExcluded > 0 && ` · ${nExcluded} esclus${nExcluded === 1 ? "o" : "i"}`}
            </p>
          </Panel>
          <BandoSummary bando={bando} />
        </aside>
      </div>
    </div>
  );
}
