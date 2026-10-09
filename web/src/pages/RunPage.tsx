import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ActivityPanel, LogList, PhaseIndex } from "../components/run/Activity";
import { ResultPanel } from "../components/run/ResultPanel";
import { ReviewPanel } from "../components/run/ReviewPanel";
import { Button, Callout, NextStep, Spinner, StatusDot } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { LANG_LABEL, PROVIDER_LABEL, isBusy, usd } from "../lib/format";
import type { Run } from "../lib/types";
import { useRunEvents } from "../lib/useRunEvents";

/** Nome della pratica: modificabile in ogni momento (l'analisi del bando non lo sovrascrive più). */
function RunTitle({ run }: { run: Run }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(run.title);
  const save = useMutation({
    mutationFn: (title: string) => api.setOptions(run.id, { title }),
    onSuccess: (r) => {
      qc.setQueryData(["run", run.id], r);
      qc.invalidateQueries({ queryKey: ["runs"] });
      setEditing(false);
      toast.success("Nome della pratica aggiornato");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  if (!editing) {
    return (
      <div className="group flex items-start gap-2">
        <h1 className="min-w-0 text-[32px] leading-[1.1] font-bold break-words sm:text-[40px]">{run.title}</h1>
        <button
          className="mt-2 shrink-0 cursor-pointer rounded-md p-1.5 text-ink-3 transition hover:bg-subtle hover:text-ink sm:mt-3"
          onClick={() => {
            setValue(run.title);
            setEditing(true);
          }}
          aria-label="Rinomina la pratica"
          title="Rinomina la pratica"
        >
          <Pencil className="size-4" />
        </button>
      </div>
    );
  }
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) save.mutate(value.trim());
      }}
    >
      <input
        className="input min-w-0 flex-1 font-display text-[22px] font-bold sm:text-[26px]"
        autoFocus
        maxLength={160}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
        aria-label="Nome della pratica"
      />
      <Button type="submit" size="sm" loading={save.isPending} disabled={!value.trim()}>
        Salva
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
        Annulla
      </Button>
    </form>
  );
}

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { data: run, isLoading, error } = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.run(id!),
    // rete di sicurezza se lo stream SSE si interrompe
    refetchInterval: (q) => (q.state.data && isBusy(q.state.data.status) ? 8000 : false),
  });
  const busy = !!run && isBusy(run.status);
  const { calls } = useRunEvents(id, run?.event_seq, busy);
  // da una presentazione generata si puo' tornare al controllo (abbinamenti, dati, indicazioni) e rigenerare
  const [reviewing, setReviewing] = useState(false);
  useEffect(() => {
    if (run?.status !== "done") setReviewing(false);
  }, [run?.status]);

  const retry = useMutation({
    mutationFn: () => (run?.bando && run.cvs.length ? api.generate(run.id, run.options.visual_critic) : api.reanalyze(run!.id)),
    onSuccess: (r) => qc.setQueryData(["run", id], r),
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return (
      <div className="grid place-items-center py-24">
        <Spinner />
      </div>
    );
  }
  if (error || !run) {
    return (
      <Callout tone="bad" title={error instanceof ApiError && error.status === 404 ? "Pratica non trovata" : "Errore di caricamento"}>
        <Link to="/" className="underline">
          Torna alle pratiche
        </Link>
      </Callout>
    );
  }

  const failed = run.status === "error" || run.status === "interrupted";
  const canReview = !!run.bando && run.cvs.length > 0;
  const model = run.models.strong ? `${run.models.strong}${run.models.fast && run.models.fast !== run.models.strong ? ` + ${run.models.fast}` : ""}` : null;

  return (
    <div className="animate-rise">
      <Link to="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-ink-3 transition-colors hover:text-ink">
        <ArrowLeft className="size-4" /> Tutte le pratiche
      </Link>

      <header className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0 max-w-3xl">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <StatusDot status={run.status} />
          </div>
          <RunTitle run={run} />
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[15px] text-ink-2">
            <span>{run.cv_files.length} candidati</span>
            {run.bando && <span>{LANG_LABEL[run.bando.language] ?? run.bando.language}</span>}
            <span>{PROVIDER_LABEL[run.provider] ?? run.provider}</span>
            {model && <span className="hidden text-ink-3 md:inline">{model}</span>}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs font-medium tracking-wide text-ink-3 uppercase">Spesa della pratica</div>
          <div className="tabular font-display text-[30px] leading-tight font-bold">{usd(run.cost.totals.cost_usd)}</div>
          <div className="text-[13px] text-ink-3">{run.cost.totals.calls} chiamate AI</div>
        </div>
      </header>

      <div className="mb-10">
        <PhaseIndex run={run} />
      </div>

      {failed && (
        <div className="mb-8">
          <NextStep
            tone="bad"
            title={run.status === "interrupted" ? "L'elaborazione si è interrotta" : "Qualcosa non è andato a buon fine"}
            action={
              run.result == null && (
                <Button variant="secondary" icon={<RotateCcw className="size-4" />} loading={retry.isPending} onClick={() => retry.mutate()}>
                  {canReview ? "Riprova la generazione" : "Riprova l'analisi"}
                </Button>
              )
            }
          >
            <span className="break-words">{run.error}</span>
          </NextStep>
        </div>
      )}

      {busy && <ActivityPanel run={run} calls={calls} />}
      {!busy && run.status === "done" && run.result && !reviewing && <ResultPanel run={run} onReview={() => setReviewing(true)} />}
      {!busy && canReview && (run.status !== "done" || reviewing) && (
        <ReviewPanel run={run} onBack={reviewing ? () => setReviewing(false) : undefined} />
      )}
      {!busy && !canReview && failed && <LogList log={run.log} />}
    </div>
  );
}
