import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronDown, KeyRound, LogOut, Menu, Moon, Sun, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Logo } from "./components/Brand";
import { Spinner } from "./components/ui";
import { ApiError, type Me, UNAUTHORIZED_EVENT, api } from "./lib/api";
import { PROVIDER_LABEL } from "./lib/format";
import CostsPage from "./pages/CostsPage";
import LoginPage from "./pages/LoginPage";
import NewRunPage from "./pages/NewRunPage";
import RunPage from "./pages/RunPage";
import RunsPage from "./pages/RunsPage";
import SettingsPage from "./pages/SettingsPage";

const NAV = [
  { to: "/", label: "Pratiche", end: true },
  { to: "/new", label: "Nuova pratica" },
  { to: "/costs", label: "Costi" },
  { to: "/settings", label: "Impostazioni" },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("garai-theme", dark ? "dark" : "light");
    } catch {
      /* storage non disponibile */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

function NavItem({ to, label, end, onClick }: { to: string; label: string; end?: boolean; onClick?: () => void }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        clsx("group relative pb-1.5 font-display text-[15px] font-medium transition-colors", isActive ? "text-ink" : "text-ink-2 hover:text-ink")
      }
    >
      {({ isActive }) => (
        <>
          {label}
          <span
            className={clsx(
              "absolute bottom-0 left-0 h-px transition-all duration-300",
              isActive ? "brand-line h-0.5 w-full rounded-full" : "w-[18px] bg-ink-3 group-hover:w-full group-hover:bg-ink",
            )}
          />
        </>
      )}
    </NavLink>
  );
}

function ProviderChip() {
  const { data: s } = useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: 30_000 });
  if (!s) return null;
  return (
    <Link
      to="/settings"
      title={s.configured ? `${s.models.strong ?? ""}${s.models.fast ? ` · ${s.models.fast}` : ""}` : "Configura un modello AI"}
      className="hidden items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-[13px] text-ink-2 transition-colors hover:border-line-strong md:flex"
    >
      <span className={clsx("size-1.5 rounded-full", s.configured ? "bg-ok" : "bg-orange")} />
      {s.configured ? (PROVIDER_LABEL[s.provider] ?? s.provider).replace("Google ", "") : "Collega un modello AI"}
    </Link>
  );
}

function UserMenu({ me }: { me: Me }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);
  const logout = async () => {
    await api.logout().catch(() => undefined);
    qc.clear();
    qc.setQueryData(["me"], null);
    nav("/");
  };
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex cursor-pointer items-center gap-2 rounded-lg py-1 pr-1.5 pl-1 transition-colors hover:bg-subtle"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="grid size-7 place-items-center rounded-full bg-ink font-display text-xs font-semibold text-canvas uppercase">{me.user[0]}</span>
        <span className="hidden text-sm sm:inline">{me.user}</span>
        <ChevronDown className="size-3.5 text-ink-3" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-56 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-xl animate-rise">
          <div className="border-b border-line px-4 py-2.5 text-[13px] text-ink-3">
            Connesso come <b className="font-medium text-ink">{me.user}</b>
          </div>
          <Link role="menuitem" to="/settings#account" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-4 py-2.5 text-sm hover:bg-subtle">
            <KeyRound className="size-4 text-ink-3" /> Cambia password
          </Link>
          <button role="menuitem" onClick={logout} className="flex w-full cursor-pointer items-center gap-2.5 px-4 py-2.5 text-left text-sm hover:bg-subtle">
            <LogOut className="size-4 text-ink-3" /> Esci
          </button>
        </div>
      )}
    </div>
  );
}

/** Mostra la schermata di accesso finche' non c'e' una sessione valida; una 401 da qualsiasi API riporta qui. */
export default function App() {
  const qc = useQueryClient();
  const { data: me, isLoading, error } = useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    retry: false,
    staleTime: Infinity,
  });
  useEffect(() => {
    const h = () => qc.setQueryData(["me"], null);
    window.addEventListener(UNAUTHORIZED_EVENT, h);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, h);
  }, [qc]);

  if (isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner />
      </div>
    );
  }
  if (error) {
    return <div className="grid min-h-dvh place-items-center px-6 text-center text-ink-2">Il server non risponde. Ricarica la pagina tra qualche istante.</div>;
  }
  if (!me) return <LoginPage />;
  return <Shell me={me} />;
}

function Shell({ me }: { me: Me }) {
  const [dark, setDark] = useTheme();
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    setMenu(false);
  }, [loc.pathname]);

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 bg-canvas/90 backdrop-blur-md">
        <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between gap-6 px-5 lg:px-8">
          <Link to="/" aria-label="garai, home">
            <Logo />
          </Link>
          <nav className="hidden items-center gap-8 md:flex">
            {NAV.map((n) => (
              <NavItem key={n.to} {...n} />
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <ProviderChip />
            <UserMenu me={me} />
            <button
              onClick={() => setDark(!dark)}
              className="grid size-9 cursor-pointer place-items-center rounded-lg text-ink-2 transition-colors hover:bg-subtle hover:text-ink"
              aria-label={dark ? "Tema chiaro" : "Tema scuro"}
              title={dark ? "Tema chiaro" : "Tema scuro"}
            >
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
            <button className="grid size-9 cursor-pointer place-items-center rounded-lg hover:bg-subtle md:hidden" onClick={() => setMenu(!menu)} aria-label="Menu">
              {menu ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </div>
        </div>
        <div className="brand-line h-px w-full opacity-80" />
        {menu && (
          <nav className="flex flex-col gap-4 border-b border-line bg-canvas px-5 py-5 md:hidden">
            {NAV.map((n) => (
              <NavItem key={n.to} {...n} />
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-5 pt-10 pb-20 lg:px-8">
        <Routes>
          <Route path="/" element={<RunsPage />} />
          <Route path="/new" element={<NewRunPage />} />
          <Route path="/runs/:id" element={<RunPage />} />
          <Route path="/costs" element={<CostsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<RunsPage />} />
        </Routes>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-5 py-6 text-xs text-ink-3 lg:px-8">
          <span className="font-mono">&gt;_ garai</span>
          <span>Strumento interno Abstract</span>
        </div>
      </footer>
    </div>
  );
}
