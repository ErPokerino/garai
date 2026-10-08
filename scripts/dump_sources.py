"""Dump dei testi estratti da tutti i sorgenti di samples/ con i reader di produzione."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.ingestion.language import detect_language
from app.ingestion.loader import load_document

out = Path("out/sources")
out.mkdir(parents=True, exist_ok=True)
for f in sorted(Path("samples").glob("*")):
    if f.suffix.lower() not in (".docx", ".pdf") or f.name.startswith("_"):
        continue
    d = load_document(f)
    (out / (f.stem + ".txt")).write_text(d.text, encoding="utf-8")
    print(f"{f.name}: {len(d.text)} chars, scanned={d.scanned}, lang={detect_language(d.text)}")
