"""Smoke test del motore di template: contenuto finto -> PPTX -> render PowerPoint -> misure."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.render.base import issues_from_measures
from app.render.powerpoint import PowerPointRenderer
from app.schemas import ExperienceBlock, PersonContent
from app.template.budget import compute_budgets
from app.template.deck import build_deck, make_meter
from app.template.spec import load_spec, resolve_labels

spec = load_spec()
meter = make_meter(spec)
b = compute_budgets(spec, meter)
print("BUDGETS", b.to_prompt_dict())

exps = [
    ExperienceBlock(
        title=f"Energy – Portale clienti {i}",
        role="Solution Architect",
        period="03/2023 – oggi",
        bullets=[
            "Progettazione dell'architettura a microservizi su Azure con Java 17 e Spring Boot",
            "Definizione di pipeline CI/CD e coordinamento tecnico del team di sviluppo",
            "Integrazione di servizi cloud (Databricks, Azure Functions) per l'elaborazione dati",
            "Stime, documentazione tecnica e reportistica sullo stato di avanzamento",
        ],
    )
    for i in range(1, 7)
]
p1 = PersonContent(
    source_file="x.pdf", profile_id="3.4", profile_name="Solution Architect", full_name="Marco Bianchi",
    phone="+39 333 1234567", email="marco.bianchi@example.com", current_role="Solution Architect",
    current_company="Abstract SRL", total_experience="12 anni", domicile="Milano",
    summary="Solution Architect con oltre 12 anni di esperienza nella progettazione di piattaforme web e cloud su Azure. "
    "Esperto di architetture a microservizi, integrazione di dati e metodologie Agile in contesti enterprise.",
    background=["Laurea Magistrale in Informatica – Università di Milano (2018)", "Certificazione Azure Fundamentals AZ-900", "Inglese: B2"],
    skills=["Java 17", "Spring Boot", "Microsoft Azure", "Microservizi", "Agile / Scrum", "Databricks"],
    experiences=exps,
)
p2 = p1.model_copy(update={"full_name": "Giulia Verdi", "phone": None, "domicile": None, "skills": ["Python", "SQL"], "experiences": exps[:2]})

labels = resolve_labels(spec, "it")
out = Path("out/smoke/smoke.pptx")
res = build_deck(spec, [p1, p2], labels, "it", out)
print("slides", [(s.person_idx, s.key, s.slide_no) for s in res.slides], "issues", res.issues)

r = PowerPointRenderer()
try:
    imgs = r.render(out, Path("out/smoke/png"))
    print(imgs)
    ms = r.measure(out)
    for m in ms:
        print(m.slide_no, m.name, round(m.text_top_pt + m.text_height_pt - m.shape_top_pt - m.shape_height_pt, 1), m.n_lines)
    for person, issue, over, extra in issues_from_measures(ms):
        print("ISSUE", person, issue)
finally:
    r.close()
