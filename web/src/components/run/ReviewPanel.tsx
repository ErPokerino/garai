import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, ChevronDown, PenLine, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { LANG_LABEL, usd } from "../../lib/format";
import type { Assignment, BandoSpec, CVCanonical, Run } from "../../lib/types";
import { ExpandableText } from "../ExpandableText";
import { Button, NextStep, Panel, Select, Spinner, Switch, Tag } from "../ui";

const reliability = (c: number) =>
  c >= 0.75 ? { label: "Abbinamento sicuro", tone: "ok" as const } : c >= 0.5 ? { label: "Da verificare", tone: "warn" as const } : { label: "Incerto", tone: "bad" as const };

function since(cv: CVCanonical): string | null {
  const years = cv.experiences.flatMap((e) => [e.start, e.end].filter(Boolean).map((d) => Number(String(d).slice(0, 4))));
  return years.length ? `in attività dal ${Math.min(...years)}` : null;
}

function CandidateRow({ cv, bando, value, name, onAssign, onName, index }: {
  cv: CVCanonical;
  bando: BandoSpec;
  value: Assignment;
  name: string;
  onAssign: (a: Assignment) => void;
  onName: (n: string) => void;
  index: number;
}) {
  const prof = bando.profiles.find((p) => p.id === value.profile_id);
  const subs = prof?.subprofiles.map((s) => s.name) ?? [];
  const rel = reliability(value.confidence);
  const missing = !cv.full_name;
  return (
    <li className="grid gap-x-8 gap-y-4 py-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
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
                  missing && !name.trim()
                    ? "border-orange bg-orange-soft placeholder:text-orange-ink focus:ring-3 focus:ring-orange/20"
                    : "border-transparent bg-transparent hover:border-line-strong focus:border-violet focus:bg-surface focus:ring-3 focus:ring-violet/15",
                )}
              />
              <PenLine className="pointer-events-none absolute top-3 right-3 size-4 text-ink-3" />
            </div>
          </label>
          {missing && (
            <p className={clsx("mt-1.5 px-3 text-[13px]", name.trim() ? "text-ink-3" : "text-orange-ink")}>
              {name.trim() ? "Nome inserito a mano (il CV non lo riporta)." : "Il CV non riporta il nome: inseriscilo, oppure ne verrà inventato uno."}
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
            onChange={(pid) => onAssign({ ...value, profile_id: pid, subprofile: null })}
            options={bando.profiles.map((p) => ({ value: p.id, label: `${p.id} · ${p.name_local || p.name}` }))}
          />
          {subs.length > 0 && (
            <Select
              ariaLabel="Variante del profilo"
              className="sm:w-48"
              value={value.subprofile ?? ""}
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

export function ReviewPanel({ run }: { run: Run }) {
  const qc = useQueryClient();
  const bando = run.bando!;
  const initialNames = useMemo(() => Object.fromEntries(run.cvs.map((c) => [c.source_file, c.full_name ?? ""])), [run.cvs]);
  const [assign, setAssign] = useState<Record<string, Assignment>>(run.assignments);
  const [names, setNames] = useState<Record<string, string>>(initialNames);
  const [critic, setCritic] = useState(run.options.visual_critic);
  useEffect(() => {
    setAssign(run.assignments);
  }, [run.assignments]);
  useEffect(() => {
    setNames(initialNames);
  }, [initialNames]);

  const changedNames = Object.fromEntries(Object.entries(names).filter(([k, v]) => v.trim() !== (initialNames[k] ?? "").trim()));
  const assignDirty = Object.entries(assign).some(
    ([k, a]) => a.profile_id !== run.assignments[k]?.profile_id || (a.subprofile ?? null) !== (run.assignments[k]?.subprofile ?? null),
  );
  const dirty = assignDirty || Object.keys(changedNames).length > 0;

  const est = useQuery({ queryKey: ["estimate", run.id, critic, run.updated_at], queryFn: () => api.estimate(run.id, critic) });

  const persist = () => api.setAssignments(run.id, assignDirty ? assign : {}, changedNames);
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
      return api.generate(run.id, critic);
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
  const uncertain = Object.values(assign).filter((a) => a.confidence < 0.5).length;
  const nameless = run.cvs.filter((c) => !c.full_name && !names[c.source_file]?.trim()).length;

  const todo = [
    uncertain && `${uncertain} abbinament${uncertain === 1 ? "o incerto" : "i incerti"}`,
    nameless && `${nameless} nom${nameless === 1 ? "e mancante" : "i mancanti"}`,
  ].filter(Boolean);

  return (
    <div className="space-y-8">
      {/* un solo comando di generazione (nel riquadro con la stima dei costi): qui solo l'indicazione */}
      <NextStep
        tone={todo.length ? "warn" : "violet"}
        title={todo.length ? `Controlla ${todo.join(" e ")}` : "Tutto pronto per generare la presentazione"}
      >
        {todo.length
          ? "Gli elementi da verificare sono evidenziati qui sotto. Poi usa «Genera la presentazione»: puoi procedere anche senza correggerli."
          : "Gli abbinamenti proposti sono affidabili. Controlla la stima dei costi e usa «Genera la presentazione»."}
      </NextStep>

      <div className="grid gap-8 xl:grid-cols-[1fr_340px]">
        <section>
          <div className="mb-2 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold">Candidati e profili</h2>
              <p className="mt-1 text-[15px] text-ink-2">Ogni CV è abbinato al profilo del bando più adatto per ruoli, seniority e tecnologie.</p>
            </div>
            {dirty && (
              <Button variant="secondary" size="sm" icon={<Save className="size-3.5" />} loading={save.isPending} onClick={() => save.mutate()}>
                Salva modifiche
              </Button>
            )}
          </div>
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
            </div>
            <Button size="lg" className="mt-5 w-full" loading={generate.isPending} onClick={() => generate.mutate()}>
              Genera la presentazione <ArrowRight className="size-4" />
            </Button>
            <p className="mt-2 text-center text-[13px] text-ink-3">{run.cvs.length} candidati · profilo + esperienze per ognuno</p>
          </Panel>
          <BandoSummary bando={bando} />
        </aside>
      </div>
    </div>
  );
}
