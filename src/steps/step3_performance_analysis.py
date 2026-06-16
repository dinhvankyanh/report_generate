"""
Step 3: Performance Analysis
Calculate MoM change and vs KPI for each metric
"""
from datetime import datetime
from typing import Dict, Any
import pandas as pd
from .base import BaseStep, StepResult
from .. import config


class Step3PerformanceAnalysis(BaseStep):
    """
    Step 3: Performance Analysis

    a) MoM comparison: Compare each metric between month X and X-1
    b) vs KPI comparison: Compare actual vs KPI for month X
    """

    @property
    def name(self) -> str:
        return "Step 3: Performance Analysis"

    @property
    def description(self) -> str:
        return "Calculate MoM change and compare vs KPI"

    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute step 3"""
        self.log(f"Starting for {config.get_month_name(month)} {year}")

        # Get performance and KPI data
        actual_df = self.data_source.get_performance_data()
        kpi_df = self.data_source.get_kpi_data()

        # Get column names for target month and previous month
        prev_month, prev_year = self.data_source.get_previous_month(month, year)

        # Get month columns
        current_col = self._get_month_column(actual_df, month, year)
        prev_col = self._get_month_column(actual_df, prev_month, prev_year)
        kpi_col = self._get_month_column(kpi_df, month, year)

        if not current_col or not kpi_col:
            return StepResult(
                success=False,
                error=f"Could not find data for {month}/{year}"
            ).__dict__

        # Create analysis DataFrame
        metrics = []
        for idx, row in actual_df.iterrows():
            metric_name = row.get("Metric", "")
            if pd.isna(metric_name) or metric_name == "":
                continue

            actual_current = row.get(current_col, 0)
            actual_prev = row.get(prev_col, 0) if prev_col else 0
            kpi_value = self._get_kpi_for_metric(kpi_df, metric_name, month, year)

            # Calculate MoM change
            if actual_prev and actual_prev != 0:
                mom_change = ((actual_current - actual_prev) / actual_prev) * 100
            else:
                mom_change = 0

            # Calculate vs KPI
            if kpi_value and kpi_value != 0:
                vs_kpi = ((actual_current - kpi_value) / kpi_value) * 100
            else:
                vs_kpi = 0

            # Comment (b): vs KPI -> over / under / reach
            if vs_kpi > 5:
                kpi_comment = "over"
            elif vs_kpi < -5:
                kpi_comment = "under"
            else:
                kpi_comment = "reach"

            # Comment (a): MoM -> increase / decrease / same
            if mom_change > 1:
                mom_comment = "increase"
            elif mom_change < -1:
                mom_comment = "decrease"
            else:
                mom_comment = "same"

            metrics.append({
                "Metric": metric_name,
                "Actual (Previous)": actual_prev,  # May (Actual)
                "KPI": kpi_value,                   # Jun (KPI)
                "Actual (Current)": actual_current, # Jun (Actual)
                "MoM Change %": mom_change,
                "MoM Comment": mom_comment,
                "vs KPI %": vs_kpi,
                "KPI Comment": kpi_comment
            })

        analysis_df = pd.DataFrame(metrics)

        # Save to context
        context["performance_analysis"] = analysis_df

        # Also save to Excel file if it exists, or create new
        self._save_performance_analysis(analysis_df, month, year)

        self.log(f"Analyzed {len(metrics)} metrics", "success")

        return StepResult(
            success=True,
            data={"metrics_count": len(metrics)},
            message=f"Performance analysis complete for {config.get_month_name(month)}"
        ).__dict__

    def _get_month_column(self, df: pd.DataFrame, month: int, year: int) -> str:
        """Find column for specific month - handles datetime columns"""
        for col in df.columns:
            if isinstance(col, datetime):
                if col.year == year and col.month == month:
                    return col
            elif isinstance(col, str):
                # Check string columns
                if str(year) in str(col) and str(month).zfill(2) in str(col):
                    return col
        return None

    def _get_kpi_for_metric(self, kpi_df: pd.DataFrame, metric_name: str, month: int, year: int) -> float:
        """
        Get KPI value for a metric. Matches on a normalized name with a fuzzy
        fallback, so minor source differences still match
        (e.g. Actual "%mom growth use base" vs KPI "%mom growth user base").
        """
        import re
        import difflib

        kpi_col = self._get_month_column(kpi_df, month, year)
        if not kpi_col:
            return None

        def norm(s):
            return re.sub(r"[^a-z0-9]", "", str(s).lower())

        target = norm(metric_name)
        values = {}
        for _, row in kpi_df.iterrows():
            nm = row.get("Metric")
            if nm is None or (isinstance(nm, float) and pd.isna(nm)):
                continue
            values[norm(nm)] = row.get(kpi_col)

        if target in values:
            return values[target]
        match = difflib.get_close_matches(target, list(values.keys()), n=1, cutoff=0.8)
        return values[match[0]] if match else None

    def _build_display_df(self, analysis_df: pd.DataFrame, month: int, year: int) -> pd.DataFrame:
        """Build the clean, Metrics-formatted display frame (No, Unit, % signs,
        whole numbers, month-labelled value columns)."""
        from .metrics_format import meta_for, fmt_value, fmt_pct

        prev_month, prev_year = self.data_source.get_previous_month(month, year)
        prev_abbr = config.get_month_name(prev_month)[:3]
        cur_abbr = config.get_month_name(month)[:3]

        col_prev = f"{prev_abbr} (Actual)"
        col_kpi = f"KPI {cur_abbr}"
        col_cur = f"{cur_abbr} (Actual)"

        rows = []
        for i, (_, r) in enumerate(analysis_df.iterrows()):
            meta = meta_for(r.get("Metric", ""), i)
            unit = meta["unit"]
            rows.append({
                "No": meta["no"],
                "Metric": r.get("Metric", ""),
                "Unit": unit,
                col_prev: fmt_value(r.get("Actual (Previous)"), unit, pct_is_ratio=True),
                col_kpi: fmt_value(r.get("KPI"), unit, pct_is_ratio=True),
                col_cur: fmt_value(r.get("Actual (Current)"), unit, pct_is_ratio=True),
                "MoM change %": fmt_pct(r.get("MoM Change %"), is_ratio=False),
                "MoM Comment": r.get("MoM Comment", ""),
                "Vs KPI": fmt_pct(r.get("vs KPI %"), is_ratio=False),
                "KPI Comment": r.get("KPI Comment", ""),
            })
        return pd.DataFrame(rows)

    def _save_performance_analysis(self, analysis_df: pd.DataFrame, month: int, year: int):
        """Save performance analysis to Excel file (Metrics-formatted)."""
        perf_file = config.DATA_DIR / "Performance analysis.xlsx"
        sheet_name = f"Perf analysis {config.get_month_name(month)} {year}"
        display_df = self._build_display_df(analysis_df, month, year)

        try:
            from .excel_io import save_sheet
            out = save_sheet(display_df, perf_file, sheet_name)
            if out != perf_file:
                self.log(f"{perf_file.name} đang mở/khoá; ghi {out.name}", "warn")
            else:
                self.log(f"Saved to {perf_file}")
        except Exception as e:
            self.log(f"Could not save to Excel: {e}", "warn")