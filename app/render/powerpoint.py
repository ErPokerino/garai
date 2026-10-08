"""Renderer basato su PowerPoint (COM, solo Windows con Office installato).

Offre la massima fedelta': le immagini sono quelle di PowerPoint e le misure del testo
(BoundHeight/righe) sono quelle reali, usate per rilevare l'overflow in modo deterministico.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .base import ShapeMeasure


class PowerPointRenderer:
    name = "powerpoint"

    def __init__(self) -> None:
        import pythoncom  # noqa: F401
        import win32com.client

        pythoncom.CoInitialize()
        try:  # PowerPoint gia' aperto dall'utente?
            win32com.client.GetActiveObject("PowerPoint.Application")
            self._was_running = True
        except Exception:
            self._was_running = False
        self._app = win32com.client.Dispatch("PowerPoint.Application")

    def _open(self, pptx_path: Path):
        return self._app.Presentations.Open(str(Path(pptx_path).resolve()), ReadOnly=True, WithWindow=False)

    def render(self, pptx_path: Path, out_dir: Path, width_px: int = 1600) -> list[Path]:
        out_dir = Path(out_dir)
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        pres = self._open(pptx_path)
        try:
            ratio = pres.PageSetup.SlideHeight / pres.PageSetup.SlideWidth
            for i in range(1, pres.Slides.Count + 1):
                pres.Slides(i).Export(str((out_dir / f"slide_{i:03d}.png").resolve()), "PNG", width_px, int(width_px * ratio))
        finally:
            pres.Close()
        return sorted(out_dir.glob("slide_*.png"))

    def measure(self, pptx_path: Path) -> list[ShapeMeasure]:
        pres = self._open(pptx_path)
        out: list[ShapeMeasure] = []
        try:
            for si in range(1, pres.Slides.Count + 1):
                slide = pres.Slides(si)
                for shape in slide.Shapes:
                    name = shape.Name
                    if not name.startswith("slot:") or "|chk=" not in name:
                        continue
                    if not shape.HasTextFrame:
                        continue
                    tr = shape.TextFrame2.TextRange
                    if not tr.Text.strip():
                        continue
                    out.append(
                        ShapeMeasure(
                            slide_no=si,
                            name=name,
                            shape_top_pt=float(shape.Top),
                            shape_height_pt=float(shape.Height),
                            text_top_pt=float(tr.BoundTop),
                            text_height_pt=float(tr.BoundHeight),
                            n_lines=int(tr.Lines.Count),
                            font_pt=float(tr.Font.Size) if tr.Font.Size else None,
                        )
                    )
        finally:
            pres.Close()
        return out

    def close(self) -> None:
        try:
            # chiudi PowerPoint solo se l'abbiamo avviato noi (nessun'altra presentazione dell'utente aperta)
            if self._app.Presentations.Count == 0 and not self._was_running:
                self._app.Quit()
        except Exception:
            pass
        self._app = None  # rilascia il proxy COM prima di CoUninitialize (evita RPC_E_DISCONNECTED)
        import gc

        gc.collect()
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception:
            pass


def available() -> bool:
    if os.name != "nt":
        return False
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return Path(r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE").exists() or Path(
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE"
    ).exists()
