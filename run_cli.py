"""CLI: bando + CV (+ template) -> PPTX.

Esempi:
  python run_cli.py --bando samples/"Annex B ITA - Profili professionali.docx" --cv samples/CV_DEV.docx samples/CV_PM.docx
  python run_cli.py --bando ... --cv ... --fixtures samples/fixtures     # senza API key (risposte LLM prefabbricate)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.llm.client import build_client
from app.pipeline.run import Pipeline
from app.template.spec import load_spec


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bando", required=True, type=Path)
    ap.add_argument("--cv", required=True, nargs="+", type=Path)
    ap.add_argument("--spec", type=Path, default=None, help="Template Spec JSON (default: template Abstract)")
    ap.add_argument("--out", type=Path, default=settings.out_dir / "run")
    ap.add_argument("--fixtures", type=Path, default=None, help="cartella con risposte LLM prefabbricate (test/demo)")
    ap.add_argument("--no-critic", action="store_true", help="salta il critico visivo (LLM con visione)")
    args = ap.parse_args()

    def progress(stage: str, frac: float, msg: str) -> None:
        print(f"[{stage}] {msg}", flush=True)

    llm = build_client(fixtures_dir=args.fixtures)
    pipe = Pipeline(llm, spec=load_spec(args.spec) if args.spec else None, progress=progress)
    _, bando = pipe.read_bando(args.bando)
    print(f"Bando: lingua={bando.language}, profili={len(bando.profiles)}")
    items = pipe.parse_cvs(args.cv, args.out)
    assignments = pipe.assign(items, bando)
    for it in items:
        a = assignments[it.cv.source_file]
        print(f"  {it.cv.source_file} -> {a.profile_id} {a.subprofile or ''} (conf {a.confidence:.2f})")
    res = pipe.generate(bando, items, assignments, args.out, visual_critic=not args.no_critic)
    print(f"\nPPTX: {res.pptx_path}\nReport: {res.report_md_path}")
    bad = [p for p in res.report.people if p.fit_issues]
    if bad:
        print("ATTENZIONE: problemi di impaginazione residui per", [p.content.source_file for p in bad])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
