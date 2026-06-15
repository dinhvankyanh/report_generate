"""
Step 7: Generate PDF Report

Report structure:
1. Performance Overview of Report Month & Analysis (MoM + vs KPI)
2. Next Month Run Rate & Key initiatives to support such growth
3. Top 3 priorities for the next month
4. Overall Progress toward Annual Planning — (i) Strategic Unlock, (ii) Incremental
"""
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd

from .base import BaseStep, StepResult
from .. import config

# Windows Unicode TTFs so Vietnamese renders correctly
_FONT_REGULAR = Path("C:/Windows/Fonts/arial.ttf")
_FONT_BOLD = Path("C:/Windows/Fonts/arialbd.ttf")
FONT = "AppFont"


def _num(v) -> str:
    """Format a number: thousands separator, 2 decimals for small values."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "" if v is None else str(v)
    if pd.isna(f):
        return ""
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{f:,.2f}"


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


class Step7GeneratePDF(BaseStep):
    @property
    def name(self) -> str:
        return "Step 7: Generate PDF Report"

    @property
    def description(self) -> str:
        return "Generate final PDF report for the month"

    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"Generating PDF report for {config.get_month_name(month)} {year}")
        config.REPORT_DIR.mkdir(parents=True, exist_ok=True)

        pdf_file = config.REPORT_DIR / f"Report thang {month} nam {year}.pdf"

        try:
            try:
                self._generate_pdf(pdf_file, month, year, context)
            except PermissionError:
                # Target is locked (e.g. open in a PDF viewer) — write a copy
                for n in range(1, 100):
                    alt = config.REPORT_DIR / f"Report thang {month} nam {year} ({n}).pdf"
                    if not alt.exists():
                        break
                self.log(f"{pdf_file.name} is locked; writing {alt.name} instead", "warn")
                self._generate_pdf(alt, month, year, context)
                pdf_file = alt
            context["pdf_path"] = str(pdf_file)
            self.log(f"PDF saved to {pdf_file}", "success")
            return StepResult(
                success=True,
                data={"pdf_path": str(pdf_file)},
                message=f"Report generated: {pdf_file.name}"
            ).__dict__
        except Exception as e:
            self.log(f"Error generating PDF: {e}", "error")
            return StepResult(success=False, error=str(e)).__dict__

    # ------------------------------------------------------------------ #
    def _new_pdf(self):
        from fpdf import FPDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        # Register a Unicode font if available, else fall back to a core font
        self._unicode = False
        if _FONT_REGULAR.exists():
            pdf.add_font(FONT, "", str(_FONT_REGULAR))
            pdf.add_font(FONT, "B", str(_FONT_BOLD if _FONT_BOLD.exists() else _FONT_REGULAR))
            self._font = FONT
            self._unicode = True
        else:
            self._font = "Helvetica"
        pdf.add_page()
        return pdf

    def _text(self, s: str) -> str:
        """Sanitize text when no Unicode font is available."""
        if self._unicode:
            return s
        return s.encode("latin-1", "replace").decode("latin-1")

    def _para(self, pdf, txt, size=9, bold=False):
        """Write a full-width paragraph, resetting X to the left margin first
        (the table API can leave the cursor mid-page)."""
        pdf.set_x(pdf.l_margin)
        pdf.set_font(self._font, "B" if bold else "", size)
        pdf.multi_cell(pdf.epw, max(5, size * 0.55), self._text(txt),
                       new_x="LMARGIN", new_y="NEXT")

    def _h1(self, pdf, txt):
        pdf.ln(1)
        self._para(pdf, txt, size=13, bold=True)
        pdf.ln(1)

    def _render_table(self, pdf, headers, rows, widths):
        """Render a bordered table using the fpdf2 table API."""
        pdf.set_x(pdf.l_margin)
        pdf.set_font(self._font, "", 8)
        with pdf.table(col_widths=widths, line_height=5,
                       text_align="LEFT", headings_style=_HEADING_STYLE) as table:
            hrow = table.row()
            for h in headers:
                hrow.cell(self._text(h))
            for r in rows:
                row = table.row()
                for c in r:
                    row.cell(self._text(c))

    def _generate_pdf(self, pdf_file: Path, month: int, year: int, context: Dict[str, Any]):
        next_month, next_year = self.data_source.get_next_month(month, year)
        mname = config.get_month_name(month)
        nname = config.get_month_name(next_month)

        pdf = self._new_pdf()

        pdf.set_font(self._font, "B", 17)
        pdf.cell(0, 12, self._text(f"Monthly Report - {mname} {year}"), ln=True, align="C")
        pdf.ln(2)

        self._section_performance(pdf, context.get("performance_analysis"))
        self._section_forecast(pdf, context.get("forecast"), mname, nname)
        self._section_top3(pdf, context.get("top_3_priorities"), nname, next_year)
        self._section_annual(pdf, context)

        pdf.output(str(pdf_file))

    # ---- Section 1: Performance ---- #
    def _section_performance(self, pdf, perf: Optional[pd.DataFrame]):
        self._h1(pdf, "1. Performance Overview & Analysis")
        if perf is None or perf.empty:
            self._note(pdf, "(no performance data)")
            return
        from .metrics_format import meta_for, fmt_value, fmt_pct
        headers = ["Metric", "Actual", "KPI", "MoM %", "MoM", "vs KPI %", "vs KPI"]
        widths = (52, 20, 20, 16, 18, 18, 18)
        rows = []
        for i, (_, r) in enumerate(perf.iterrows()):
            unit = meta_for(r.get("Metric", ""), i)["unit"]
            rows.append([
                _s(r.get("Metric")),
                fmt_value(r.get("Actual (Current)"), unit, pct_is_ratio=True),
                fmt_value(r.get("KPI"), unit, pct_is_ratio=True),
                fmt_pct(r.get("MoM Change %"), is_ratio=False),
                _s(r.get("MoM Comment")),
                fmt_pct(r.get("vs KPI %"), is_ratio=False),
                _s(r.get("KPI Comment")),
            ])
        self._render_table(pdf, headers, rows, widths)

    # ---- Section 2: Forecast ---- #
    def _section_forecast(self, pdf, fc: Optional[pd.DataFrame], mname: str, nname: str):
        self._h1(pdf, f"2. {nname} Run Rate & Key Initiatives")
        if fc is None or fc.empty:
            self._note(pdf, "(no forecast data)")
            return
        actual_col = next((c for c in fc.columns if "(actual)" in str(c).lower()), None)
        fcast_col = next((c for c in fc.columns if "(forecast)" in str(c).lower()), None)
        notes_col = next((c for c in fc.columns if "note" in str(c).lower()), None)

        headers = ["Metric", f"{mname} (actual)", f"{nname} (forecast)", "Initiative notes"]
        from .metrics_format import meta_for, fmt_value
        widths = (45, 30, 33, 60)
        rows = []
        for i, (_, r) in enumerate(fc.iterrows()):
            unit = meta_for(r.get("Metric", ""), i)["unit"]
            rows.append([
                _s(r.get("Metric")),
                fmt_value(r.get(actual_col), unit, pct_is_ratio=True) if actual_col else "",
                fmt_value(r.get(fcast_col), unit, pct_is_ratio=True) if fcast_col else "",
                _s(r.get(notes_col)) if notes_col else "",
            ])
        self._render_table(pdf, headers, rows, widths)

    # ---- Section 3: Top 3 ---- #
    def _section_top3(self, pdf, top3, nname: str, nyear: int):
        self._h1(pdf, f"3. Top 3 Priorities for {nname} {nyear}")
        if top3 is None or (hasattr(top3, "empty") and top3.empty):
            self._note(pdf, "(no priorities)")
            return
        for i, (_, r) in enumerate(top3.iterrows(), 1):
            self._para(pdf, f"{i}. {_s(r.get('name'))}", size=10, bold=True)
            self._para(pdf,
                       f"    Status: {_s(r.get('status'))}  |  PIC: {_s(r.get('pic'))}  "
                       f"|  Timing: {_s(r.get('timing'))}", size=9)
            self._para(pdf, f"    Expected impact: {_s(r.get('expected_impact'))}", size=9)
            pdf.ln(1)

    # ---- Section 4: Annual progress ---- #
    def _section_annual(self, pdf, context: Dict[str, Any]):
        self._h1(pdf, "4. Overall Progress toward Annual Planning")
        strategic = context.get("annual_progress_strategic") or []
        incremental = context.get("annual_progress_incremental") or []

        for title, items in [("(i) Strategic Unlock", strategic),
                             ("(ii) Incremental Improvements", incremental)]:
            self._para(pdf, title, size=11, bold=True)
            if not items:
                self._note(pdf, "(none)")
                continue
            headers = ["No", "Initiative", "Status", "Comments"]
            widths = (8, 52, 24, 86)
            rows = [[
                self._fmt_no(it.get("No")),
                _s(it.get("Initiative")),
                _s(it.get("Status")),
                self._comment(it),
            ] for it in items]
            self._render_table(pdf, headers, rows, widths)
            pdf.ln(2)

    def _note(self, pdf, txt):
        self._para(pdf, txt, size=10)

    @staticmethod
    def _fmt_no(no) -> str:
        try:
            return str(int(float(no)))
        except (TypeError, ValueError):
            return _s(no)

    @staticmethod
    def _comment(it: dict) -> str:
        status = _s(it.get("Status"))
        details = _s(it.get("Details"))
        new_timing = _s(it.get("New Timing"))
        if status in ("On Track", "Done", "Live"):
            return status
        parts = [p for p in (new_timing, details) if p]
        return status + (" - " + "; ".join(parts) if parts else "")


# Header cell style for tables
def _heading_style():
    from fpdf.fonts import FontFace
    return FontFace(emphasis="BOLD", fill_color=(225, 230, 240))


try:
    _HEADING_STYLE = _heading_style()
except Exception:
    _HEADING_STYLE = None
