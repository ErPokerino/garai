import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, Check, KeyRound } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Dropzone } from "../components/Dropzone";
import { Button, Callout, Field, PageTitle, Panel, Switch } from "../components/ui";
import { api } from "../lib/api";
import { PROVIDER_LABEL } from "../lib/format";

function Step({ n, title, text, done, children }: { n: string; title: string; text: ReactNode; done: boolean; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-line pt-7 sm:grid-cols-[64px_1fr]">
      <div className="flex items-center gap-3 sm:block">
        <span className={clsx("font-display text-[28px] leading-none font-bold tabular", done ? "text-violet" : "text-ink-3")}>{n}</span>
        {done && <Check className="size-4 text-violet sm:mt-2" />}
      </div>
      <div>
        <h2 className="text-[22px] font-bold">{title}</h2>
        <p className="mt-1 mb-4 text-[15px] text-ink-2">{text}</p>
        {children}
      </div>
    </section>
  );
}

export default function NewRunPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: status } = useQuery({ queryKey: ["status"], queryFn: api.status });
  const [bando, setBando] = useState<File[]>([]);
  const [cvs, setCvs] = useState<File[]>([]);
  const [tpl, setTpl] = useState<File[]>([]);
  const [customTpl, setCustomTpl] = useState(false);
  const [critic, setCritic] = useState(false);
  const [hideCompanies, setHideCompanies] = useState(false);
  const [outputName, setOutputName] = useState("");
  const [title, setTitle] = useState("");

  const create = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("bando", bando[0]);
      cvs.forEach((f) => fd.append("cvs", f));
      if (customTpl && tpl[0]) fd.append("template", tpl[0]);
      fd.append("visual_critic", String(critic));
      fd.append("hide_companies", String(hideCompanies));
      if (outputName.trim()) fd.append("output_name", outputName.trim());
      if (title.trim()) fd.append("title", title.trim());
      return api.createRun(fd);
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      nav(`/runs/${r.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const configured = !!status?.configured;
  const ready = bando.length === 1 && cvs.length > 0 && configured;
  const missing = [!bando.length && "il bando", !cvs.length && "almeno un CV"].filter(Boolean).join(" e ");

  return (
    <div className="animate-rise">
      <PageTitle
        eyebrow="Nuova pratica"
        title="Cosa dobbiamo preparare?"
        subtitle="Carica i documenti e avvia l'analisi. Prima di generare la presentazione potrai controllare tutto e vedere quanto costerà."
      />

      {status && !configured && (
        <div className="mb-8">
          <Callout tone="violet" icon={<KeyRound className="size-4" />} title="Serve un modello AI">
            Aggiungi la API key in{" "}
            <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
              Impostazioni
            </Link>{" "}
            per analizzare documenti reali.
          </Callout>
        </div>
      )}

      <div className="grid gap-10 lg:grid-cols-[1fr_320px]">
        <div className="space-y-10">
          <Step n="01" title="Il bando" text="L'allegato con i profili professionali richiesti (Word o PDF)." done={bando.length > 0}>
            <Dropzone empty="Scegli il bando o trascinalo qui" hint="DOCX o PDF, un solo file" accept={[".docx", ".pdf"]} files={bando} onChange={setBando} />
          </Step>
          <Step n="02" title="I CV dei candidati" text="Tutti insieme, anche in formati e lingue diverse: verranno uniformati." done={cvs.length > 0}>
            <Dropzone empty="Scegli i CV o trascinali qui" hint="DOCX o PDF, più file insieme" accept={[".docx", ".pdf"]} multiple files={cvs} onChange={setCvs} />
          </Step>
          <Step n="03" title="Il template" text="Usa il template PowerPoint richiesto dalla gara. Se la gara non ne prevede uno, garai usa il template CV Abstract." done>
            <div className="space-y-3">
              <label className="flex cursor-pointer items-center gap-3 text-[15px]">
                <input type="radio" className="size-4 accent-[var(--violet)]" checked={customTpl} onChange={() => setCustomTpl(true)} />
                Template richiesto dalla gara
              </label>
              {customTpl && (
                <div className="pb-1 pl-7">
                  <Dropzone empty="Scegli il template della gara" hint="PPTX · la mappatura degli spazi viene proposta dall'AI (sperimentale)" accept={[".pptx"]} files={tpl} onChange={setTpl} />
                </div>
              )}
              <label className="flex cursor-pointer items-center gap-3 text-[15px]">
                <input type="radio" className="size-4 accent-[var(--violet)]" checked={!customTpl} onChange={() => setCustomTpl(false)} />
                Template CV Abstract <span className="text-ink-3">(se la gara non ne prevede uno)</span>
              </label>
            </div>
          </Step>
        </div>

        <aside className="lg:pt-7">
          <Panel className="space-y-5 p-5 lg:sticky lg:top-28">
            <div>
              <div className="eyebrow">Riepilogo</div>
              <ul className="mt-3 space-y-2 text-[15px]">
                <li className="flex justify-between gap-3">
                  <span className="text-ink-2">Bando</span>
                  <span className={clsx("truncate font-medium", !bando.length && "text-ink-3")}>{bando[0]?.name ?? "da caricare"}</span>
                </li>
                <li className="flex justify-between gap-3">
                  <span className="text-ink-2">Candidati</span>
                  <span className={clsx("font-medium tabular", !cvs.length && "text-ink-3")}>{cvs.length || "da caricare"}</span>
                </li>
                <li className="flex justify-between gap-3">
                  <span className="text-ink-2">Template</span>
                  <span className="truncate font-medium">{customTpl ? (tpl[0]?.name ?? "da caricare") : "Abstract"}</span>
                </li>
              </ul>
            </div>
            <div className="border-t border-line pt-5">
              <Switch
                checked={critic}
                onChange={setCritic}
                label="Controllo grafico con AI"
                hint="Confronta le slide finali con il template e segnala difetti visivi. Costo aggiuntivo."
              />
              <div className="mt-4">
                <Switch
                  checked={hideCompanies}
                  onChange={setHideCompanies}
                  label="Non citare le aziende"
                  hint="Al posto dei nomi di datori di lavoro e clienti viene indicato il settore (es. «gruppo bancario»)."
                />
              </div>
            </div>
            <div className="space-y-4 border-t border-line pt-5">
              <Field label="Nome della pratica" hint="Facoltativo: altrimenti si usa il titolo letto dal bando. Modificabile in ogni momento.">
                <input className="input" value={title} maxLength={160} placeholder="Titolo del bando" onChange={(e) => setTitle(e.target.value)} />
              </Field>
              <Field label="Nome del file" hint="Facoltativo: modificabile anche dopo la generazione.">
                <div className="flex items-center gap-2">
                  <input
                    className="input"
                    value={outputName}
                    maxLength={120}
                    placeholder="Titolo del bando - CV"
                    onChange={(e) => setOutputName(e.target.value)}
                  />
                  <span className="shrink-0 text-[13px] text-ink-3">.pptx</span>
                </div>
              </Field>
            </div>
            <div className="border-t border-line pt-5">
              <Button size="lg" className="w-full" disabled={!ready || (customTpl && !tpl.length)} loading={create.isPending} onClick={() => create.mutate()}>
                Avvia l'analisi <ArrowRight className="size-4" />
              </Button>
              <p className="mt-3 text-[13px] leading-snug text-ink-3">
                {missing
                  ? `Manca ${missing}.`
                  : configured
                    ? `Modello: ${PROVIDER_LABEL[status!.provider] ?? status!.provider} · ${status!.models.strong}. Il costo dell'analisi è visibile in tempo reale; quello della generazione ti viene stimato prima di procedere.`
                    : "Configura un modello AI per procedere."}
              </p>
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
