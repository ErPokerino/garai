"""Orchestrazione end-to-end: bando + CV + template -> PPTX."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import Settings, settings
from app.ingestion.loader import SourceDocument, load_document
from app.llm.client import LLMClient, LLMUnavailable
from app.render.estimate import get_renderer
from app.schemas import BandoSpec, CVCanonical, GenerationReport, PersonContent, PersonReport, TemplateSpec, WriterOutput
from app.template.budget import Budgets, compute_budgets, custom_field_labels, template_fields
from app.template.deck import make_meter
from app.template.spec import load_spec, resolve_labels, template_path

from .bando_extract import extract_bando
from .critic import translate_labels, visual_review
from .cv_parse import parse_cv
from .fit import budget_feedback, fit_deck
from .llm_schemas import Assignment
from .matching import assign_profile
from .report import to_markdown
from .tailor import assemble_person, company_mentions, company_names, scrub_companies, write_content
from .verify import verify_full

Progress = Callable[[str, float, str], None]


def _noop(stage: str, frac: float, msg: str) -> None:  # pragma: no cover
    pass


@dataclass
class CVItem:
    doc: SourceDocument
    cv: CVCanonical


@dataclass
class RunResult:
    pptx_path: Path
    report: GenerationReport
    report_md_path: Path
    report_json_path: Path
    slide_images: list[Path] = field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        llm: LLMClient,
        spec: TemplateSpec | None = None,
        cfg: Settings = settings,
        progress: Progress = _noop,
    ):
        self.llm = llm
        self.spec = spec or load_spec()
        self.cfg = cfg
        self.progress = progress
        self.meter = make_meter(self.spec)
        self.hide_companies = False  # riservatezza: nessun nome di azienda/cliente nelle slide (settore al suo posto)
        self.banned: dict[str, set[str]] = {}  # competenze non evidenziate dal CV, per file: escluse anche nelle riscritture

    # ------------------------------------------------------------------ fase 1: analisi
    def read_bando(self, path: Path) -> tuple[SourceDocument, BandoSpec]:
        self._phase("analysis")
        self.progress("bando", 0.0, "Lettura del bando")
        doc = load_document(path)
        self.progress("bando", 0.2, "Estrazione dei profili e dei requisiti (LLM)")
        return doc, extract_bando(self.llm, doc.text)

    def parse_cvs(self, paths: list[Path], work_dir: Path) -> list[CVItem]:
        docs = [load_document(p, work_dir) for p in paths]
        self.progress("cv", 0.0, f"Analisi di {len(docs)} CV (LLM)")
        self._phase("analysis")
        done = [0]

        def work(d):
            cv = parse_cv(self.llm, d)
            done[0] += 1
            self.progress("cv", done[0] / len(docs), f"CV analizzato: {d.filename} ({done[0]}/{len(docs)})")
            return cv

        with ThreadPoolExecutor(max_workers=4) as ex:
            cvs = list(ex.map(work, docs))
        return [CVItem(d, c) for d, c in zip(docs, cvs)]

    def assign(self, items: list[CVItem], bando: BandoSpec) -> dict[str, Assignment]:
        self._phase("analysis")
        self.progress("match", 0.0, "Assegnazione dei CV ai profili del bando")
        with ThreadPoolExecutor(max_workers=4) as ex:
            res = list(ex.map(lambda it: assign_profile(self.llm, it.cv, bando), items))
        return {it.cv.source_file: a for it, a in zip(items, res)}

    # ------------------------------------------------------------------ fase 2: generazione
    def _assemble(self, cv, profile, w, lang, sub, role: str | None) -> PersonContent:
        types = {f.key: f.type for f in self.spec.fields}
        c = assemble_person(cv, profile, w, lang, subprofile=sub, custom_types=types, role_override=role,
                            hide_companies=self.hide_companies, banned_skills=self.banned.get(cv.source_file))
        if self.hide_companies:
            removed = scrub_companies(c, company_names(cv))
            if removed:
                c.warnings.append("Nomi di aziende tolti dai testi (riservatezza): " + ", ".join(removed))
        return c

    def _write_person(
        self, item: CVItem, profile, sub, bando: BandoSpec, budgets: Budgets, instr: str | None = None, role: str | None = None
    ) -> tuple[WriterOutput, PersonContent, list]:
        cv = item.cv
        lang = bando.language
        hide = self.hide_companies
        w = write_content(self.llm, cv, profile, bando, budgets, lang, subprofile=sub, instructions=instr, hide_companies=hide)
        if hide:  # nomi di aziende sfuggiti al writer: una revisione mirata prima della pulizia deterministica
            left = company_mentions(assemble_person(cv, profile, w, lang, subprofile=sub), company_names(cv))
            if left:
                try:
                    w = write_content(self.llm, cv, profile, bando, budgets, lang, subprofile=sub, instructions=instr,
                                      hide_companies=True, previous=w,
                                      feedback=[f"Remove the company/client names {', '.join(left)}: describe them by industry"])
                except LLMUnavailable:
                    pass
        content = self._assemble(cv, profile, w, lang, sub, role)
        # 1) budget: fino a 2 revisioni LLM se il testo supera nettamente i limiti
        for _ in range(2):
            fb = budget_feedback(content, budgets)
            if not fb:
                break
            try:
                w = write_content(self.llm, cv, profile, bando, budgets, lang, feedback=fb, previous=w, subprofile=sub,
                                  instructions=instr, hide_companies=self.hide_companies)
            except LLMUnavailable:
                break  # niente revisione LLM: ci pensano misura reale e trimming deterministico
            content = self._assemble(cv, profile, w, lang, sub, role)
        # 2) fedelta': se ci sono affermazioni non supportate gravi, una revisione
        faith: list = []
        try:
            res = verify_full(self.llm, item.doc.text, content)
            self._ban_skills(cv.source_file, res.unsupported_skills, content)
            faith = res.issues
            severe = [f for f in faith if f.severity == "high"]
            if severe:
                fb = [f"Remove or correct unsupported claim in {f.slot}: '{f.text}' ({f.reason})" for f in severe]
                w = write_content(self.llm, cv, profile, bando, budgets, lang, feedback=fb, previous=w, subprofile=sub,
                                  instructions=instr, hide_companies=self.hide_companies)
                content = self._assemble(cv, profile, w, lang, sub, role)
                res = verify_full(self.llm, item.doc.text, content)
                self._ban_skills(cv.source_file, res.unsupported_skills, content)
                faith = res.issues
        except LLMUnavailable:
            content.warnings.append("Verifica di fedelta' non eseguita (LLM non disponibile).")
        return w, content, faith

    def _ban_skills(self, source_file: str, skills: list[str], content: PersonContent) -> None:
        """Competenze che il CV non evidenzia: tolte dalla slide e da ogni riscrittura successiva."""
        bad = {s.strip().casefold() for s in skills if s.strip()}
        bad &= {s.casefold() for s in content.skills}  # solo quelle davvero presenti (copiate esattamente)
        if not bad:
            return
        self.banned.setdefault(source_file, set()).update(bad)
        removed = [s for s in content.skills if s.casefold() in bad]
        content.skills = [s for s in content.skills if s.casefold() not in bad]
        content.warnings.append("Competenze tolte perché non presenti nel CV: " + ", ".join(removed))

    def _phase(self, name: str) -> None:
        if hasattr(self.llm, "phase"):  # MeteredClient: etichetta le chiamate per fase (analisi/generazione/...)
            self.llm.phase = name

    def generate(
        self,
        bando: BandoSpec,
        items: list[CVItem],
        assignments: dict[str, Assignment],
        out_dir: Path,
        visual_critic: bool = True,
        instructions: dict[str, str] | None = None,
        role_overrides: dict[str, str] | None = None,
        hide_companies: bool = False,
    ) -> RunResult:
        """assignments: nome file CV -> Assignment (profilo e sotto-profilo; modificabile dall'utente).
        instructions: indicazioni del bid manager per CV; role_overrides: ruolo attuale imposto a mano per CV."""
        self._phase("generation")
        self.hide_companies = hide_companies
        lang = bando.language
        budgets = compute_budgets(self.spec, self.meter, self.cfg.max_experiences)

        # ordine: per profilo (ordine del bando), poi nome file
        order = {p.id: i for i, p in enumerate(bando.profiles)}
        items = sorted(items, key=lambda it: (order.get(assignments[it.cv.source_file].profile_id, 999), it.cv.source_file))

        self.progress("write", 0.0, "Scrittura dei contenuti per ogni CV (LLM)")
        profiles = [bando.get(assignments[it.cv.source_file].profile_id) for it in items]
        subs = [assignments[it.cv.source_file].subprofile for it in items]
        instr = [(instructions or {}).get(it.cv.source_file) or None for it in items]
        roles = [(role_overrides or {}).get(it.cv.source_file) for it in items]
        done = [0]

        def work(a):
            r = self._write_person(a[0], a[1], a[2], bando, budgets, a[3], a[4])
            done[0] += 1
            self.progress("write", done[0] / len(items), f"Contenuti pronti: {a[0].cv.source_file} ({done[0]}/{len(items)})")
            return r

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(work, zip(items, profiles, subs, instr, roles)))
        writer_outs = [r[0] for r in results]
        contents = [r[1] for r in results]
        faith_all = [r[2] for r in results]

        def rewriter(person: int, feedback: list[str]) -> PersonContent | None:
            try:
                w = write_content(
                    self.llm, items[person].cv, profiles[person], bando, budgets, lang,
                    feedback=feedback, previous=writer_outs[person], subprofile=subs[person], instructions=instr[person],
                    hide_companies=hide_companies,
                )
            except LLMUnavailable:
                return None
            writer_outs[person] = w
            return self._assemble(items[person].cv, profiles[person], w, lang, subs[person], roles[person])

        return self._finalize(bando, items, contents, faith_all, out_dir, rewriter, visual_critic)

    def rebuild(
        self,
        bando: BandoSpec,
        items: list[CVItem],
        contents: list[PersonContent],
        faith_all: list[list],
        out_dir: Path,
    ) -> RunResult:
        """Ricostruisce deck e report da contenuti modificati a mano: nessuna riscrittura LLM,
        solo impaginazione con misura reale e riduzione deterministica se qualcosa non entra."""
        self._phase("rebuild")
        by_file = {it.cv.source_file: it for it in items}
        ordered = [by_file[c.source_file] for c in contents]
        return self._finalize(bando, ordered, contents, faith_all, out_dir, None, False)

    def _finalize(self, bando, items, contents, faith_all, out_dir, rewriter, visual_critic) -> RunResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        lang = bando.language
        labels = resolve_labels(self.spec, lang, lambda lab, lg: translate_labels(self.llm, lab, lg))

        self.progress("fit", 0.0, "Impaginazione e verifica sul rendering reale")
        renderer = get_renderer(self.meter)
        try:
            pptx_path = out_dir / "CV_presentazione.pptx"
            fit = fit_deck(self.spec, contents, labels, lang, pptx_path, renderer, rewriter,
                           max_llm_iterations=self.cfg.max_fit_iterations)
            self.progress("render", 0.0, f"Rendering delle slide ({renderer.name})")
            images = renderer.render(pptx_path, out_dir / "slides")
            notes_visual: dict[int, list[str]] = {}
            if visual_critic and images:
                self.progress("critic", 0.0, "Critico visivo (LLM con visione)")
                notes_visual = self._critic(renderer, items, fit, images, out_dir)
        finally:
            renderer.close()

        report = GenerationReport(
            language=lang,
            template_name=self.spec.name,
            notes=[f"Renderer: {renderer.name}"],
            fields=template_fields(self.spec),
            field_labels=custom_field_labels(self.spec, labels),
        )
        for i, c in enumerate(contents):
            report.people.append(
                PersonReport(
                    content=c,
                    fit_iterations=fit.iterations,
                    fit_issues=fit.remaining.get(i, []),
                    fit_notes=fit.notes.get(i, []),
                    faith_issues=faith_all[i],
                    visual_notes=notes_visual.get(i, []),
                    slides=[s.slide_no for s in fit.deck.slides if s.person_idx == i],
                )
            )
        md_path = out_dir / "report.md"
        json_path = out_dir / "report.json"
        md_path.write_text(to_markdown(report), encoding="utf-8")
        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        self.progress("done", 1.0, "Presentazione pronta")
        return RunResult(pptx_path, report, md_path, json_path, images)

    def _critic(self, renderer, items, fit, images, out_dir) -> dict[int, list[str]]:
        notes: dict[int, list[str]] = {}
        try:
            tpl_imgs = renderer.render(template_path(self.spec), out_dir / "template_ref")
        except Exception:
            return notes
        for pi, it in enumerate(items):
            mine = [images[s.slide_no - 1] for s in fit.deck.slides if s.person_idx == pi and s.slide_no - 1 < len(images)]
            try:
                notes[pi] = visual_review(self.llm, tpl_imgs, mine, re.sub(r"\W+", "_", it.cv.source_file))
            except LLMUnavailable:
                break
            except Exception as e:  # il critico non deve mai bloccare la generazione
                notes[pi] = [f"Critico visivo non disponibile: {e}"]
        return notes
