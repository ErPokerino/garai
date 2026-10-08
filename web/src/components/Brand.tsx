import clsx from "clsx";
import { useId } from "react";

/** Marchio di garai: un foglio con l'angolo piegato (il CV) su gradiente arancio -> viola, con il prompt ">_" del logo Abstract. */
export function Mark({ className, animated }: { className?: string; animated?: boolean }) {
  const id = useId();
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff7800" />
          <stop offset="0.5" stopColor="#e58fb0" />
          <stop offset="1" stopColor="#7355ec" />
        </linearGradient>
      </defs>
      <path d="M14 0h29l21 21v29a14 14 0 0 1-14 14H14A14 14 0 0 1 0 50V14A14 14 0 0 1 14 0Z" fill={`url(#${id})`} />
      <path d="M43 0v13a8 8 0 0 0 8 8h13Z" fill="#fff" fillOpacity="0.45" />
      <path d="M15 24.5 26.5 35 15 45.5" fill="none" stroke="#fff" strokeWidth="5.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M32 46h14" stroke="#fff" strokeWidth="5.5" strokeLinecap="round" className={clsx(animated && "animate-cursor")} />
    </svg>
  );
}

/** Logotipo: "gar" + "ai" in grassetto, sul modello di "abstr·act". */
export function Logo({ compact }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <Mark className="size-8" />
      {!compact && (
        <span className="leading-none">
          <span className="block font-sans text-[19px] tracking-[-0.03em] text-ink">
            gar<b className="font-bold">ai</b>
          </span>
          <span className="mt-1 block text-[10.5px] tracking-tight text-ink-3">CV per bandi · by abstract</span>
        </span>
      )}
    </span>
  );
}
