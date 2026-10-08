import type { RunStatus } from "./types";

const usdFmt = new Intl.NumberFormat("it-IT", { style: "currency", currency: "USD", currencyDisplay: "narrowSymbol", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usdSmall = new Intl.NumberFormat("it-IT", { style: "currency", currency: "USD", currencyDisplay: "narrowSymbol", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const intFmt = new Intl.NumberFormat("it-IT");
const compactFmt = new Intl.NumberFormat("it-IT", { notation: "compact", maximumFractionDigits: 1 });

/** Importi piccoli (< 1$) fino a 4 decimali: le singole chiamate costano frazioni di centesimo. */
export const usd = (v: number | null | undefined) => {
  const n = v ?? 0;
  return n !== 0 && Math.abs(n) < 1 ? usdSmall.format(n) : usdFmt.format(n);
};
export const int = (v: number | null | undefined) => intFmt.format(v ?? 0);
export const compact = (v: number | null | undefined) => compactFmt.format(v ?? 0);
export const pct = (v: number) => `${Math.round(v * 100)}%`;

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
export const dayLabel = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("it-IT", { day: "2-digit", month: "short" });

export function relative(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "adesso";
  if (s < 3600) return `${Math.floor(s / 60)} min fa`;
  if (s < 86400) return `${Math.floor(s / 3600)} h fa`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} g fa`;
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

export const STATUS_LABEL: Record<RunStatus, string> = {
  queued: "In coda",
  analyzing: "Analisi in corso",
  review: "Da revisionare",
  generating: "Generazione",
  done: "Completato",
  error: "Errore",
  interrupted: "Interrotto",
};

export const PROVIDER_LABEL: Record<string, string> = {
  anthropic: "Anthropic Claude",
  openai: "OpenAI",
  gemini: "Google Gemini",
  none: "Nessuno",
  auto: "Automatico",
};

export const LANG_LABEL: Record<string, string> = {
  it: "Italiano", en: "Inglese", es: "Spagnolo", fr: "Francese", de: "Tedesco", pt: "Portoghese", ro: "Rumeno",
};

export const isBusy = (s: RunStatus) => s === "queued" || s === "analyzing" || s === "generating";
