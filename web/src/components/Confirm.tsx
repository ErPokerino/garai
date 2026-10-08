import { AlertTriangle } from "lucide-react";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import { Button } from "./ui";

export interface ConfirmOptions {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "default";
}

type Ask = (o: ConfirmOptions) => Promise<boolean>;
const Ctx = createContext<Ask>(async () => false);

/** Conferma con il dialogo dell'app (non quello del browser): `if (await confirm({...})) ...` */
export const useConfirm = () => useContext(Ctx);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null);
  const ask = useCallback<Ask>((o) => new Promise((resolve) => setState({ ...o, resolve })), []);
  const close = (v: boolean) => {
    state?.resolve(v);
    setState(null);
  };
  return (
    <Ctx.Provider value={ask}>
      {children}
      {state && <Dialog {...state} onClose={close} />}
    </Ctx.Provider>
  );
}

function Dialog({ title, message, confirmLabel = "Conferma", cancelLabel = "Annulla", tone = "default", onClose }: ConfirmOptions & { onClose: (v: boolean) => void }) {
  const titleId = useId();
  const descId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(document.activeElement);

  useEffect(() => {
    // per le azioni distruttive il focus parte da "Annulla": un Invio distratto non elimina nulla
    cancelRef.current?.focus();
    const el = opener.current;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose(false);
      if (e.key === "Tab" && boxRef.current) {
        // focus trap: il tab resta dentro il dialogo
        const f = boxRef.current.querySelectorAll<HTMLElement>("button");
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (el instanceof HTMLElement) el.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={() => onClose(false)} />
      <div
        ref={boxRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={message ? descId : undefined}
        className="relative w-full max-w-md overflow-hidden rounded-xl border border-line bg-surface shadow-2xl animate-rise"
      >
        <div className={tone === "danger" ? "h-0.5 bg-bad" : "brand-line h-0.5"} />
        <div className="flex gap-4 p-6">
          {tone === "danger" && (
            <span className="grid size-10 shrink-0 place-items-center rounded-full bg-bad-soft text-bad">
              <AlertTriangle className="size-5" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id={titleId} className="text-xl font-bold">
              {title}
            </h2>
            {message && (
              <div id={descId} className="mt-2 text-[15px] leading-relaxed text-ink-2">
                {message}
              </div>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-line bg-subtle/50 px-6 py-4">
          <Button ref={cancelRef} variant="secondary" onClick={() => onClose(false)}>
            {cancelLabel}
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={() => onClose(true)}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
