import clsx from "clsx";
import { Loader2, X } from "lucide-react";
import { type ButtonHTMLAttributes, type ReactNode, type Ref, useEffect } from "react";
import { STATUS_LABEL } from "../lib/format";
import type { RunStatus } from "../lib/types";

// ---------------------------------------------------------------------------- Button
// primary: pieno inchiostro · cta: bordo con il gradiente del brand (azione principale della pagina)
type Variant = "primary" | "cta" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-canvas hover:bg-ink/85",
  cta: "border-[1.5px] border-transparent text-ink [background:linear-gradient(var(--surface),var(--surface))_padding-box,var(--brand-gradient)_border-box] hover:[background:var(--mesh),linear-gradient(var(--surface),var(--surface))_padding-box,var(--brand-gradient)_border-box]",
  secondary: "border border-line-strong bg-surface text-ink hover:border-ink",
  ghost: "text-ink-2 hover:bg-subtle hover:text-ink",
  danger: "bg-bad text-white hover:bg-bad/90",
};
const SIZES: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-[13px]",
  md: "h-10 gap-2 px-4 text-[14px]",
  lg: "h-12 gap-2 px-6 text-[15px]",
};

export const buttonClass = (variant: Variant = "primary", size: Size = "md", className?: string) =>
  clsx(
    "inline-flex shrink-0 cursor-pointer items-center justify-center rounded-lg font-display font-medium tracking-[-0.01em] transition-[background,border-color,color,opacity] disabled:cursor-not-allowed disabled:opacity-45",
    VARIANTS[variant],
    SIZES[size],
    className,
  );

export function Button({
  variant = "primary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ref,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; icon?: ReactNode; ref?: Ref<HTMLButtonElement> }) {
  return (
    <button ref={ref} className={buttonClass(variant, size, className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------- etichette e stati
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx("eyebrow", className)}>{children}</span>;
}

type Tone = "neutral" | "violet" | "ok" | "warn" | "bad";
const TONE: Record<Tone, string> = {
  neutral: "bg-subtle text-ink-2",
  violet: "bg-violet-soft text-violet-ink",
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
};

export function Tag({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={clsx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium", TONE[tone], className)}>{children}</span>;
}

const DOT: Record<RunStatus, string> = {
  queued: "bg-ink-3",
  analyzing: "bg-violet",
  review: "bg-orange",
  generating: "bg-violet",
  done: "bg-ok",
  error: "bg-bad",
  interrupted: "bg-ink-3",
};

export function StatusDot({ status, className }: { status: RunStatus; className?: string }) {
  const busy = status === "analyzing" || status === "generating" || status === "queued";
  return (
    <span className={clsx("inline-flex items-center gap-2 text-sm text-ink-2", className)}>
      <span className="relative flex size-2">
        {busy && <span className={clsx("absolute inline-flex size-full animate-ping rounded-full opacity-60", DOT[status])} />}
        <span className={clsx("relative inline-flex size-2 rounded-full", DOT[status])} />
      </span>
      {STATUS_LABEL[status]}
    </span>
  );
}

// ---------------------------------------------------------------------------- struttura
export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("panel", className)}>{children}</div>;
}

export function PanelHead({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5">{eyebrow}</div>}
        <h3 className="text-[17px] font-semibold">{title}</h3>
        {subtitle && <p className="mt-0.5 text-sm text-ink-3">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function PageTitle({ eyebrow, title, subtitle, actions }: { eyebrow?: ReactNode; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <div className="mb-3">{typeof eyebrow === "string" ? <Eyebrow>{eyebrow}</Eyebrow> : eyebrow}</div>}
        <h1 className="text-[34px] leading-[1.1] font-bold sm:text-[40px]">{title}</h1>
        {subtitle && <p className="mt-3 text-[17px] leading-relaxed text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ eyebrow, title, aside }: { eyebrow?: string; title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <Eyebrow className="mb-2">{eyebrow}</Eyebrow>}
        <h2 className="text-2xl font-bold">{title}</h2>
      </div>
      {aside}
    </div>
  );
}

export function Metric({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "warn" }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium tracking-wide text-ink-3 uppercase">{label}</div>
      <div className={clsx("tabular mt-1 font-display text-[28px] leading-tight font-semibold", tone === "warn" && "text-warn")}>{value}</div>
      {hint && <div className="mt-0.5 text-[13px] text-ink-3">{hint}</div>}
    </div>
  );
}

/** Pannello "Prossimo passo": dice in chiaro cosa fare adesso. */
export function NextStep({ title, children, action, tone = "violet" }: { title: ReactNode; children?: ReactNode; action?: ReactNode; tone?: "violet" | "warn" | "ok" | "bad" }) {
  const bar = { violet: "brand-line", warn: "bg-orange", ok: "bg-ok", bad: "bg-bad" }[tone];
  return (
    <div className="panel relative flex flex-wrap items-center gap-x-6 gap-y-3 overflow-hidden py-4 pr-5 pl-6 animate-rise">
      <span className={clsx("absolute inset-y-0 left-0 w-1", bar)} />
      <div className="min-w-0 flex-1">
        <div className="mb-1 font-mono text-[11px] tracking-wider text-ink-3 uppercase">&gt;_ prossimo passo</div>
        <div className="font-display text-[17px] font-semibold">{title}</div>
        {children && <div className="mt-0.5 text-sm text-ink-2">{children}</div>}
      </div>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------------------- form
export function Switch({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; hint?: ReactNode; disabled?: boolean }) {
  return (
    <label className={clsx("flex items-start gap-3", disabled ? "opacity-60" : "cursor-pointer")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx("relative mt-0.5 inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors", checked ? "bg-violet" : "bg-line-strong")}
      >
        <span className={clsx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-4.5" : "translate-x-0.5")} />
      </button>
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-[13px] leading-snug text-ink-3">{hint}</span>}
      </span>
    </label>
  );
}

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-[13px] leading-snug text-ink-3">{hint}</span>}
    </label>
  );
}

export function Select({ value, onChange, options, className, disabled, ariaLabel }: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  return (
    <select aria-label={ariaLabel} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={clsx("input", className)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------- feedback
export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={clsx("h-1 w-full overflow-hidden rounded-full bg-subtle", className)}>
      <div className="brand-line h-full rounded-full transition-[width] duration-700" style={{ width: `${Math.max(3, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("size-5 animate-spin text-ink-3", className)} />;
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 font-mono text-lg text-ink-3">
        &gt;_<span className="animate-cursor">▍</span>
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      {children && <p className="mt-1 max-w-md text-sm text-ink-3">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Callout({ tone = "warn", icon, title, children }: { tone?: "warn" | "bad" | "violet" | "ok"; icon?: ReactNode; title?: ReactNode; children?: ReactNode }) {
  const t = {
    warn: "bg-warn-soft text-ink",
    bad: "bg-bad-soft text-ink",
    violet: "bg-violet-soft text-ink",
    ok: "bg-ok-soft text-ink",
  }[tone];
  const ic = { warn: "text-warn", bad: "text-bad", violet: "text-violet-ink", ok: "text-ok" }[tone];
  return (
    <div className={clsx("flex gap-3 rounded-xl px-4 py-3.5 text-sm", t)}>
      {icon && <div className={clsx("mt-0.5 shrink-0", ic)}>{icon}</div>}
      <div className="min-w-0">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={clsx(title && "mt-0.5", "text-ink-2")}>{children}</div>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- Tabs (sottolineatura con il gradiente)
export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode; count?: number }[] }) {
  return (
    <div className="flex gap-6 overflow-x-auto border-b border-line" role="tablist">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "relative flex cursor-pointer items-center gap-2 whitespace-nowrap py-3 font-display text-[15px] font-medium transition-colors",
            value === it.value ? "text-ink" : "text-ink-3 hover:text-ink",
          )}
        >
          {it.label}
          {it.count !== undefined && <span className="tabular text-xs text-ink-3">{it.count}</span>}
          {value === it.value && <span className="brand-line absolute inset-x-0 -bottom-px h-0.5 rounded-full" />}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------- Drawer / Modal
function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
}

export function Drawer({ open, onClose, title, subtitle, children, footer, width = "max-w-2xl" }: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  useEscape(open, onClose);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/35 backdrop-blur-[2px]" onClick={onClose} />
      <div className={clsx("relative flex h-full w-full flex-col bg-surface shadow-2xl animate-rise", width)}>
        <div className="brand-line h-0.5 w-full" />
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div className="min-w-0">
            <h2 className="truncate text-2xl font-bold">{title}</h2>
            {subtitle && <p className="mt-1 text-sm text-ink-3">{subtitle}</p>}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Chiudi" icon={<X className="size-4" />} />
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-6">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}

export function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  useEscape(open, onClose);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={onClose} />
      <div className="relative animate-rise">{children}</div>
    </div>
  );
}
