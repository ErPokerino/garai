import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { LiveCall, LogEntry, Run } from "./types";

/**
 * Stream SSE di un run: aggiorna in tempo reale log, avanzamento e costo nella cache di react-query
 * e raccoglie le chiamate LLM per il feed "in diretta". Al cambio di stato ricarica il run completo.
 */
export function useRunEvents(runId: string | undefined, since: number | undefined, enabled: boolean) {
  const qc = useQueryClient();
  const [calls, setCalls] = useState<LiveCall[]>([]);
  const sinceRef = useRef(since ?? 0);
  sinceRef.current = Math.max(sinceRef.current, since ?? 0);

  useEffect(() => {
    if (!runId || !enabled) return;
    const es = new EventSource(`/api/runs/${runId}/events?since=${sinceRef.current}`);
    const key = ["run", runId];

    es.addEventListener("log", (ev) => {
      const d = JSON.parse((ev as MessageEvent).data) as LogEntry & { progress: number };
      qc.setQueryData<Run>(key, (r) =>
        r ? { ...r, log: [...r.log, d], stage: d.stage, message: d.msg, progress: d.progress ?? r.progress } : r,
      );
    });
    es.addEventListener("llm_call", (ev) => {
      const c = JSON.parse((ev as MessageEvent).data) as LiveCall;
      setCalls((prev) => [c, ...prev].slice(0, 100));
      qc.setQueryData<Run>(key, (r) =>
        r
          ? {
              ...r,
              cost: {
                ...r.cost,
                totals: {
                  ...r.cost.totals,
                  calls: r.cost.totals.calls + 1,
                  cost_usd: r.cost.totals.cost_usd + c.cost_usd,
                  input_tokens: r.cost.totals.input_tokens + c.input_tokens,
                  output_tokens: r.cost.totals.output_tokens + c.output_tokens,
                },
              },
            }
          : r,
      );
    });
    es.addEventListener("status", () => {
      qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: ["runs"] });
    });
    // gli eventi hanno un id: in caso di riconnessione il browser riprende da Last-Event-ID
    return () => es.close();
  }, [runId, enabled, qc]);

  return { calls };
}
