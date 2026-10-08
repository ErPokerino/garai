import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import { fileUrl } from "../../lib/api";
import { Modal } from "../ui";

export function SlideGallery({ runId, slides, version, columns = "sm:grid-cols-2" }: { runId: string; slides: string[]; version: string; columns?: string }) {
  const [open, setOpen] = useState<number | null>(null);
  const src = (p: string) => `${fileUrl(runId, p)}?v=${encodeURIComponent(version)}`;

  useEffect(() => {
    if (open === null) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setOpen((i) => (i === null ? i : Math.min(i + 1, slides.length - 1)));
      if (e.key === "ArrowLeft") setOpen((i) => (i === null ? i : Math.max(i - 1, 0)));
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, slides.length]);

  if (!slides.length) return <p className="text-[15px] text-ink-3">Anteprima non disponibile (serve PowerPoint o LibreOffice per creare le immagini).</p>;
  const nav = "grid size-9 cursor-pointer place-items-center rounded-full bg-white/10 text-white hover:bg-white/20 disabled:opacity-30";
  return (
    <>
      <div className={`grid gap-5 ${columns}`}>
        {slides.map((s, i) => (
          <button key={s} onClick={() => setOpen(i)} className="group cursor-zoom-in text-left">
            <div className="overflow-hidden rounded-lg border border-line bg-white transition group-hover:border-ink">
              <img src={src(s)} alt={`Slide ${i + 1}`} loading="lazy" className="aspect-video w-full object-contain" />
            </div>
            <div className="mt-2 font-display text-sm text-ink-3 tabular">{String(i + 1).padStart(2, "0")}</div>
          </button>
        ))}
      </div>
      <Modal open={open !== null} onClose={() => setOpen(null)}>
        {open !== null && (
          <div>
            <img src={src(slides[open])} alt={`Slide ${open + 1}`} className="max-h-[82vh] max-w-[92vw] rounded-lg bg-white shadow-2xl" />
            <div className="mt-4 flex items-center justify-center gap-3 text-sm text-white">
              <button className={nav} disabled={open === 0} onClick={() => setOpen(open - 1)} aria-label="Precedente">
                <ChevronLeft className="size-4" />
              </button>
              <span className="w-16 text-center font-display tabular">
                {open + 1} / {slides.length}
              </span>
              <button className={nav} disabled={open === slides.length - 1} onClick={() => setOpen(open + 1)} aria-label="Successiva">
                <ChevronRight className="size-4" />
              </button>
              <button className={`${nav} ml-6`} onClick={() => setOpen(null)} aria-label="Chiudi">
                <X className="size-4" />
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
