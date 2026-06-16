"""
Step 8: Cross-file consistency check (quality_rules.md Rules 17-19).

ADVISORY validation pass — it never fails the run. It checks that:
  - the three ground-truth sources (Actual, KPI, Tracker X-1) are internally
    consistent (funnel identities + MoM-growth rows hold);  [Rule 17]
  - each derived file is reproducible from its declared inputs;             [Rule 18]
  - the same fact matches across Actual / Performance analysis / Forecast.   [Rule 19]

Any divergence is logged as a warning and collected in context["consistency_issues"].
"""
import re
from datetime import datetime
from typing import Dict, Any, List

import pandas as pd

from .base import BaseStep, StepResult
from .. import config

STATUS_VOCAB = {"not started", "on track", "delay", "deprioritized", "done", "live"}


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _f(v):
    try:
        x = float(v)
        return None if pd.isna(x) else x
    except (TypeError, ValueError):
        return None


def _month_col(df, month, year):
    for col in df.columns:
        if isinstance(col, (datetime, pd.Timestamp)) and col.year == year and col.month == month:
            return col
    return None


def _vals_by_metric(df, col) -> dict:
    out = {}
    if df is None or col is None:
        return out
    for _, row in df.iterrows():
        nm = row.get("Metric")
        if nm is None or (isinstance(nm, float) and pd.isna(nm)):
            continue
        v = _f(row.get(col))
        if v is not None:
            out[_norm(nm)] = v
    return out


# Normalized metric keys
M_TUB = _norm("Total User Base")
M_MOMUB = _norm("%mom growth user base")
M_ELIG = _norm("Eligible Base For Cash Loan")
M_PELIG = _norm("%Eligible/Total User Base")
M_TRAF = _norm("Traffic to Landing Page")
M_PTRAF = _norm("%Traffic/Eligible")
M_SUB = _norm("Submission")
M_PSUB = _norm("%Submission/Traffic")
M_APPR = _norm("Approved")
M_PAPPR = _norm("%Approval Rate")
M_TICK = _norm("Average Ticket Size")
M_MOMTICK = _norm("%mom growth ticket size")
M_DISB = _norm("Disbursement Volume")


def _rel_off(a, b, rel=0.02) -> bool:
    """True if a deviates from b by more than rel (relative)."""
    if a is None or b is None:
        return False
    if abs(b) < 1e-9:
        return abs(a) >= 1e-6
    return abs(a - b) / abs(b) > rel


def _check_funnel(vals: dict, label: str, issues: List[str]):
    """Rule 17: the conversion chain must hold inside one month of one file."""
    identities = [
        ("Eligible Base = Total User Base x %Eligible/Total", vals.get(M_ELIG),
         (vals.get(M_TUB) or 0) * (vals.get(M_PELIG) or 0)),
        ("Traffic = Eligible Base x %Traffic/Eligible", vals.get(M_TRAF),
         (vals.get(M_ELIG) or 0) * (vals.get(M_PTRAF) or 0)),
        ("Submission = Traffic x %Submission/Traffic", vals.get(M_SUB),
         (vals.get(M_TRAF) or 0) * (vals.get(M_PSUB) or 0)),
        ("Approved = Submission x %Approval Rate", vals.get(M_APPR),
         (vals.get(M_SUB) or 0) * (vals.get(M_PAPPR) or 0)),
    ]
    for name, lhs, rhs in identities:
        if lhs is None:
            continue
        if _rel_off(lhs, rhs):
            issues.append(f"[{label}] funnel identity off: {name} — file says {lhs:.4g}, "
                          f"chain implies {rhs:.4g}")


class Step7ConsistencyCheck(BaseStep):
    @property
    def name(self) -> str:
        return "Step 7: Cross-file Consistency Check"

    @property
    def description(self) -> str:
        return "Validate source files + derived files are logically aligned (Rules 17-19)"

    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"Checking cross-file consistency for {config.get_month_name(month)} {year}")
        issues: List[str] = []
        try:
            self._run_checks(month, year, context, issues)
        except Exception as e:  # advisory — never break the run
            self.log(f"Consistency check could not complete: {e}", "warn")

        context["consistency_issues"] = issues
        if issues:
            self.log(f"Found {len(issues)} consistency warning(s):", "warn")
            for msg in issues:
                self.log(f"  • {msg}", "warn")
        else:
            self.log("All files logically aligned — no inconsistencies found.", "success")

        return StepResult(
            success=True,
            data={"issues_count": len(issues)},
            message=f"Consistency check complete ({len(issues)} warning(s))",
        ).__dict__

    # ------------------------------------------------------------------ #
    def _run_checks(self, month, year, context, issues):
        prev_m, prev_y = self.data_source.get_previous_month(month, year)

        actual = self.data_source.get_performance_data()
        kpi = self.data_source.get_kpi_data()

        a_col = _month_col(actual, month, year)
        ap_col = _month_col(actual, prev_m, prev_y)
        k_col = _month_col(kpi, month, year)

        a_x = _vals_by_metric(actual, a_col)
        a_prev = _vals_by_metric(actual, ap_col)
        k_x = _vals_by_metric(kpi, k_col)

        # --- Rule 17: source files internally consistent ---
        _check_funnel(a_x, f"Actual {config.get_month_name(month)[:3]}", issues)
        if a_prev:
            _check_funnel(a_prev, f"Actual {config.get_month_name(prev_m)[:3]}", issues)
        _check_funnel(k_x, f"KPI {config.get_month_name(month)[:3]}", issues)

        # MoM-growth rows must equal the implied growth of their base metric
        self._check_mom_growth(a_x, a_prev, "Actual", issues)

        # Disbursement unit-multiplier must be stable across months (Actual)
        s_x = self._disb_scale(a_x)
        s_prev = self._disb_scale(a_prev)
        if s_x is not None and s_prev is not None and _rel_off(s_x, s_prev):
            issues.append(f"[Actual] Disbursement/(Approved x Ticket) multiplier drifts "
                          f"between months ({s_prev:.4g} vs {s_x:.4g}) — units inconsistent")

        # --- Rule 18/19: Performance analysis reproduces Actual + KPI ---
        perf = context.get("performance_analysis")
        if perf is not None and not perf.empty:
            for _, r in perf.iterrows():
                key = _norm(r.get("Metric", ""))
                if not key:
                    continue
                self._cmp(r.get("Actual (Current)"), a_x.get(key),
                          f"Perf '{r.get('Metric')}' current vs Actual[{config.get_month_name(month)[:3]}]", issues)
                if a_prev:
                    self._cmp(r.get("Actual (Previous)"), a_prev.get(key),
                              f"Perf '{r.get('Metric')}' previous vs Actual[{config.get_month_name(prev_m)[:3]}]", issues)
                self._cmp(r.get("KPI"), k_x.get(key),
                          f"Perf '{r.get('Metric')}' KPI vs KPI sheet", issues)

        # --- Rule 19: Forecast's current-actual column matches Actual[X] ---
        forecast = context.get("forecast")
        if forecast is not None and not forecast.empty:
            acol = next((c for c in forecast.columns if "(actual)" in str(c).lower()), None)
            if acol:
                for _, r in forecast.iterrows():
                    key = _norm(r.get("Metric", ""))
                    if key and key in a_x:
                        self._cmp(r.get(acol), a_x.get(key),
                                  f"Forecast '{r.get('Metric')}' actual vs Actual[{config.get_month_name(month)[:3]}]", issues)

        # --- Rule 18: tracker X must be X-1 + email updates ---
        prev_df = context.get("previous_initiatives_data")
        cur_df = context.get("initiatives_data")
        if context.get("extraction_empty"):
            issues.append("[Tracker] LLM extraction returned NO updates — tracker is a plain "
                          "carry-forward of the previous month, NOT email-updated (check LLM endpoint).")
        elif prev_df is not None and cur_df is not None and self._trackers_identical(prev_df, cur_df):
            issues.append("[Tracker] month-X tracker is byte-identical to month X-1 (status / new "
                          "timing / details) — email updates were not applied.")

        # --- Sanity: tracker statuses use the agreed vocabulary ---
        init_df = context.get("initiatives_data")
        if init_df is not None and not init_df.empty:
            section_names = {"strategic unlock", "incremental improvements"}
            for _, row in init_df.iterrows():
                name = str(row.get("Initiative Names", "") or "").strip()
                # Skip section header / title / hint rows (no real initiative No).
                if _f(row.get("No")) is None or name.lower() in section_names:
                    continue
                st = str(row.get("Status", "") or "").strip()
                if st and st.lower() not in STATUS_VOCAB:
                    issues.append(f"[Tracker {config.get_month_name(month)[:3]}] initiative "
                                  f"'{name[:40]}' has unknown status '{st}'")

    def _check_mom_growth(self, cur, prev, label, issues):
        if not cur or not prev:
            return
        checks = [
            ("%mom growth user base", M_MOMUB, M_TUB),
            ("%mom growth ticket size", M_MOMTICK, M_TICK),
        ]
        for nm, mom_key, base_key in checks:
            stated = cur.get(mom_key)
            b_cur, b_prev = cur.get(base_key), prev.get(base_key)
            if stated is None or not b_prev:
                continue
            implied = b_cur / b_prev - 1
            if abs(stated - implied) > 0.005:  # >0.5pp
                issues.append(f"[{label}] {nm} = {stated:.1%} but base implies "
                              f"{implied:.1%} — MoM-growth row inconsistent")

    @staticmethod
    def _trackers_identical(prev, cur) -> bool:
        """True if X and X-1 agree on every shared initiative's status columns."""
        cols = ["Status", "New timing (if applicable)", "Details from that month", "How confident"]

        def by_no(df):
            out = {}
            for _, r in df.iterrows():
                no = _f(r.get("No"))
                if no is None:
                    continue
                out[int(no)] = tuple(str(r.get(c, "") or "").strip().lower() for c in cols)
            return out

        p, c = by_no(prev), by_no(cur)
        common = set(p) & set(c)
        return bool(common) and all(p[n] == c[n] for n in common)

    @staticmethod
    def _disb_scale(vals):
        if not vals:
            return None
        a, t, d = vals.get(M_APPR), vals.get(M_TICK), vals.get(M_DISB)
        if a and t and d and a * t != 0:
            return d / (a * t)
        return None

    @staticmethod
    def _cmp(derived, source, label, issues, rel=0.01):
        d, s = _f(derived), _f(source)
        if d is None or s is None:
            return
        if _rel_off(d, s, rel):
            issues.append(f"{label}: {d:.4g} vs source {s:.4g} — not aligned")
