"""Render report.pdf and tracker.pdf to PNG pages for in-browser viewing."""
import sys
from pathlib import Path
import fitz  # PyMuPDF

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
ASSETS = HERE / "assets"
ZOOM = 2.5  # ~180 dpi -> crisp at 1080p

def render(pdf_name, prefix):
    doc = fitz.open(str(ASSETS / pdf_name))
    out = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        fn = f"{prefix}_{i:02d}.png"
        pix.save(str(ASSETS / fn))
        out.append(fn)
    doc.close()
    print(f"{pdf_name}: {len(out)} pages -> {out}")
    return out

render("report.pdf", "report")
render("tracker.pdf", "tracker")
