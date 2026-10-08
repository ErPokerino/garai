import clsx from "clsx";
import { useLayoutEffect, useRef, useState } from "react";

/** Testo limitato a `lines` righe; il comando "Leggi tutto" compare solo se il testo e' effettivamente tagliato. */
export function ExpandableText({ text, lines = 2, className }: { text: string; lines?: 2 | 3; className?: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [open, setOpen] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => {
      if (!open) setOverflows(el.scrollHeight > el.clientHeight + 1);
    };
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [text, open]);

  if (!text) return null;
  return (
    <div className={className}>
      <p ref={ref} className={clsx(!open && (lines === 2 ? "line-clamp-2" : "line-clamp-3"))}>
        {text}
      </p>
      {(overflows || open) && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(!open);
          }}
          aria-expanded={open}
          className="mt-1 cursor-pointer font-display text-[13px] font-medium text-violet-ink underline-offset-2 hover:underline"
        >
          {open ? "Riduci" : "Leggi tutto"}
        </button>
      )}
    </div>
  );
}
