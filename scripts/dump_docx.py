"""Dump leggibile di un DOCX (paragrafi + tabelle in ordine documento) per ispezione."""
import sys

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def iter_blocks(doc):
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def main(path):
    doc = Document(path)
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            t = block.text.strip()
            if t:
                print(f"[{block.style.name}] {t}")
        else:
            print("<TABLE>")
            for row in block.rows:
                cells = []
                prev = None
                for c in row.cells:
                    if c._tc is prev:
                        continue
                    prev = c._tc
                    cells.append(c.text.strip().replace("\n", " / "))
                print(" | ".join(cells))
            print("</TABLE>")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
