import clsx from "clsx";
import { FileText, Plus, X } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";

const sizeLabel = (b: number) => (b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

/** Area di caricamento: trascina o scegli i file; elenco dei file scelti con rimozione. */
export function Dropzone({
  hint,
  accept,
  multiple,
  files,
  onChange,
  empty,
}: {
  hint: ReactNode;
  accept: string[];
  multiple?: boolean;
  files: File[];
  onChange: (files: File[]) => void;
  empty: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);

  const add = (list: FileList | null) => {
    if (!list) return;
    const isOk = (f: File) => accept.includes("." + (f.name.split(".").pop() ?? "").toLowerCase());
    const all = Array.from(list);
    const ok = all.filter(isOk);
    setRejected(all.filter((f) => !isOk(f)).map((f) => f.name));
    if (!ok.length) return;
    if (multiple) {
      const names = new Set(files.map((f) => f.name));
      onChange([...files, ...ok.filter((f) => !names.has(f.name))]);
    } else onChange([ok[0]]);
  };

  const showZone = multiple || files.length === 0;
  return (
    <div>
      {files.length > 0 && (
        <ul className={clsx("grid gap-2", multiple && "sm:grid-cols-2", showZone && "mb-3")}>
          {files.map((f) => (
            <li key={f.name} className="flex items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2.5 animate-rise">
              <FileText className="size-4 shrink-0 text-violet" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium" title={f.name}>
                  {f.name}
                </span>
                <span className="tabular text-xs text-ink-3">{sizeLabel(f.size)}</span>
              </span>
              <button
                className="cursor-pointer rounded-md p-1 text-ink-3 hover:bg-subtle hover:text-ink"
                onClick={() => onChange(files.filter((x) => x !== f))}
                aria-label={`Rimuovi ${f.name}`}
              >
                <X className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {showZone && (
        <div
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") input.current?.click();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            add(e.dataTransfer.files);
          }}
          className={clsx(
            "flex cursor-pointer items-center gap-4 rounded-xl border border-dashed px-5 transition-colors",
            files.length ? "py-3.5" : "py-7",
            over ? "border-violet bg-violet-soft" : "border-line-strong hover:border-ink hover:bg-subtle/60",
          )}
        >
          <span className={clsx("grid size-10 shrink-0 place-items-center rounded-full", over ? "bg-violet text-white" : "bg-subtle text-ink")}>
            <Plus className="size-5" />
          </span>
          <span>
            <span className="block font-display text-[15px] font-medium">{files.length ? "Aggiungi altri file" : empty}</span>
            <span className="block text-[13px] text-ink-3">{hint}</span>
          </span>
          <input
            ref={input}
            type="file"
            className="hidden"
            accept={accept.join(",")}
            multiple={multiple}
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      )}
      {rejected.length > 0 && <p className="mt-2 text-[13px] text-bad">Formato non supportato: {rejected.join(", ")}</p>}
    </div>
  );
}
