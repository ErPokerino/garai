import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, KeyRound, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useConfirm } from "../components/Confirm";
import { Callout, Empty, Eyebrow, NextStep, SectionTitle, Spinner, StatusDot, buttonClass } from "../components/ui";
import { api } from "../lib/api";
import { LANG_LABEL, isBusy, relative, usd } from "../lib/format";
import type { RunSummary } from "../lib/types";

const STEPS = [
  { n: "01", t: "Carica", d: "Il bando e i CV, in Word o PDF, anche in formati diversi." },
  { n: "02", t: "Controlla", d: "Ogni candidato abbinato al profilo richiesto: verifichi e correggi." },
  { n: "03", t: "Scarica", d: "Un'unica presentazione sul template richiesto dalla gara, con la copertura dei requisiti." },
];

function nextStepFor(r: RunSummary): { title: string; text: string; cta: string } | null {
  switch (r.status) {
    case "review":
      return { title: `Controlla gli abbinamenti di «${r.title}»`, text: `${r.n_cvs} candidati pronti: verifica i profili e genera la presentazione.`, cta: "Controlla" };
    case "analyzing":
    case "queued":
      return { title: `Analisi in corso: «${r.title}»`, text: "Puoi seguire l'avanzamento e il costo in tempo reale.", cta: "Segui" };
    case "generating":
      return { title: `Presentazione in preparazione: «${r.title}»`, text: "Scrittura, impaginazione e verifica sul template.", cta: "Segui" };
    case "error":
    case "interrupted":
      return { title: `«${r.title}» si è interrotta`, text: "Apri la pratica per vedere il motivo e riprovare.", cta: "Apri" };
    default:
      return null;
  }
}

function RunRow({ r, onDelete }: { r: RunSummary; onDelete: () => void }) {
  const nav = useNavigate();
  const confirm = useConfirm();
  return (
    <li
      className="group grid cursor-pointer grid-cols-[1fr_auto] items-center gap-x-6 gap-y-2 py-5 transition-colors sm:grid-cols-[minmax(0,1fr)_150px_90px_64px]"
      onClick={() => nav(`/runs/${r.id}`)}
    >
      <div className="min-w-0">
        <div className="truncate font-display text-[18px] font-semibold transition-colors group-hover:text-violet-ink">{r.title}</div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-3">
          <span>{r.n_cvs} candidati</span>
          {r.language && <span>{LANG_LABEL[r.language] ?? r.language}</span>}
          <span>{relative(r.updated_at)}</span>
        </div>
      </div>
      <StatusDot status={r.status} className="order-3 sm:order-none" />
      <div className="tabular hidden text-right text-sm text-ink-2 sm:block">{usd(r.cost_usd)}</div>
      <div className="flex items-center justify-end gap-3">
        <button
          className="cursor-pointer rounded-md p-1.5 text-ink-3 opacity-0 transition group-hover:opacity-100 hover:bg-bad-soft hover:text-bad focus-visible:opacity-100 disabled:invisible"
          title="Elimina pratica"
          aria-label={`Elimina la pratica ${r.title}`}
          disabled={isBusy(r.status)}
          onClick={async (e) => {
            e.stopPropagation();
            const ok = await confirm({
              title: "Eliminare la pratica?",
              message: (
                <>
                  «{r.title}» verrà eliminata insieme ai documenti caricati e alla presentazione generata. L'operazione non si può annullare.
                  {r.cost_usd > 0 && " I costi già sostenuti restano nel registro dei costi."}
                </>
              ),
              confirmLabel: "Elimina",
              tone: "danger",
            });
            if (ok) onDelete();
          }}
        >
          <Trash2 className="size-4" />
        </button>
        <ArrowRight className="size-4 text-ink-3 transition-transform group-hover:translate-x-1 group-hover:text-ink" />
      </div>
    </li>
  );
}

export default function RunsPage() {
  const qc = useQueryClient();
  const { data: runs, isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: api.runs,
    refetchInterval: (q) => (q.state.data?.some((r) => isBusy(r.status)) ? 3000 : false),
  });
  const { data: status } = useQuery({ queryKey: ["status"], queryFn: api.status });
  const { data: costs } = useQuery({ queryKey: ["costs", 30], queryFn: () => api.costs(30) });

  const del = useMutation({
    mutationFn: api.deleteRun,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      toast.success("Pratica eliminata");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const pending = (runs ?? []).filter((r) => nextStepFor(r)).slice(0, 3);

  return (
    <div className="animate-rise space-y-14">
      <section className="mesh relative overflow-hidden rounded-2xl border border-line px-6 py-10 sm:px-10 sm:py-12">
        <div className="grid gap-10 lg:grid-cols-[1.25fr_1fr] lg:items-end">
          <div>
            <Eyebrow>Bid management · CV</Eyebrow>
            <h1 className="mt-4 text-[38px] leading-[1.05] font-bold sm:text-[52px]">
              Dal bando alla presentazione dei CV, in tre passi.
            </h1>
            <p className="mt-4 max-w-xl text-[17px] leading-relaxed text-ink-2">
              garai legge il bando, abbina ogni candidato al profilo richiesto e scrive CV sintetici e fedeli, impaginati sul template richiesto dalla gara.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link to="/new" className={buttonClass("primary", "lg")}>
                Nuova pratica <ArrowRight className="size-4" />
              </Link>
            </div>
          </div>
          <ol className="space-y-5">
            {STEPS.map((s) => (
              <li key={s.n} className="flex gap-4">
                <span className="font-display text-[15px] font-semibold text-violet-ink tabular">{s.n}</span>
                <div className="border-l border-ink/15 pl-4">
                  <div className="font-display text-[17px] font-semibold">{s.t}</div>
                  <p className="text-sm text-ink-2">{s.d}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {status && !status.configured && (
        <Callout tone="violet" icon={<KeyRound className="size-4" />} title="Collega un modello AI per lavorare su documenti reali">
          Inserisci la API key (Gemini, Claude o OpenAI) in{" "}
          <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
            Impostazioni
          </Link>
          , poi crea la prima pratica caricando il bando e i CV.
        </Callout>
      )}

      {pending.length > 0 && (
        <section className="space-y-3">
          {pending.map((r) => {
            const s = nextStepFor(r)!;
            return (
              <NextStep
                key={r.id}
                tone={r.status === "error" || r.status === "interrupted" ? "bad" : r.status === "review" ? "warn" : "violet"}
                title={s.title}
                action={
                  <Link to={`/runs/${r.id}`} className={buttonClass(r.status === "review" ? "primary" : "secondary")}>
                    {s.cta} <ArrowRight className="size-4" />
                  </Link>
                }
              >
                {s.text}
              </NextStep>
            );
          })}
        </section>
      )}

      <section>
        <SectionTitle
          eyebrow="Archivio"
          title="Le tue pratiche"
          aside={
            costs && (
              <div className="flex items-center gap-5 text-sm text-ink-2">
                <span>
                  Spesa del mese <b className="tabular font-semibold text-ink">{usd(costs.month_to_date)}</b>
                </span>
                <Link to="/costs" className="link-more">
                  Costi
                </Link>
              </div>
            )
          }
        />
        {isLoading ? (
          <div className="grid place-items-center py-16">
            <Spinner />
          </div>
        ) : !runs?.length ? (
          <div className="panel">
            <Empty
              title="Ancora nessuna pratica"
              action={
                <Link to="/new" className={buttonClass("primary")}>
                  Crea la prima pratica
                </Link>
              }
            >
              Ogni pratica raccoglie un bando, i CV dei candidati e la presentazione generata.
            </Empty>
          </div>
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {runs.map((r) => (
              <RunRow key={r.id} r={r} onDelete={() => del.mutate(r.id)} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
