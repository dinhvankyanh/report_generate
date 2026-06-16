"""
Build the analytical narrative for the monthly business report. The report's
style/layout/logic was learned from a reference report during development and is
now fixed in code (STYLE_GUIDE here + the renderer in step6_generate_report.py).

Flow:
  build_report_data(context, month, year, data_source) -> structured dict
  generate_narrative(report_data) -> dict of LLM-written prose sections

The narrative is written by the LLM (GreenNode) following STYLE_GUIDE; numbers
and tables are computed deterministically so figures stay accurate.
"""
import json
import re

import pandas as pd

from .. import config
from . import extractor  # reuse the configured LLM client + parsing helpers
from .extractor import llm_available
from ..steps.metrics_format import meta_for, is_pct

SECTION_NAMES = ("strategic unlock", "incremental improvements")

STYLE_GUIDE = """\
You are writing a Cash Loan (CL) monthly business report. Mirror this house style:
- Executive, concise, analytical. British/US business English. Use "pp" for
  percentage-points and "%" for percentages; money in VNDm.
- Lead sentences with a short bold-like label then the point, e.g.
  "Headline. ...", "MoM bridge (fact). ...", "Plan-miss bridge (fact). ...".
- Decompose growth into multiplicative levers WITH the arithmetic
  (e.g. "Eligible Base x1.84 and Approval Rate x1.18; 1.84 x 1.18 ~= 2.17, i.e. +117%").
- Map every metric movement to a NAMED initiative from the tracker (owner/persona,
  status, timing). Split into "Structural ceiling unlocks" (eligible base, approval
  rate, scoring models) vs "Incremental acquisition / retention improvements"
  (traffic, submission, ticket).
- Be specific and quantified; never invent numbers not provided. Forward-looking
  with risks tied to specific initiatives.
- Use the FULL official metric / initiative names exactly as in the tracker and
  Metrics sheet (e.g. "%Approval Rate", "new score model version"). Do NOT use
  abbreviations or shorthand (no "AR", no "v-next") and do NOT invent your own
  translated phrases for a metric — always use its canonical name.
"""


# --------------------------------------------------------------------------- #
# Data assembly
# --------------------------------------------------------------------------- #
def _f(v, default=0.0):
    try:
        x = float(v)
        return default if pd.isna(x) else x
    except (TypeError, ValueError):
        return default


def _split_initiatives(initiatives_df):
    """Split the tracker into (structural, incremental) initiative dicts."""
    structural, incremental, current = [], [], None
    if initiatives_df is None or initiatives_df.empty:
        return structural, incremental
    for _, row in initiatives_df.iterrows():
        name = str(row.get("Initiative Names", "")).strip()
        low = name.lower()
        no = row.get("No")
        has_no = not (pd.isna(no) or str(no).strip().lower() in ("", "nan"))
        # A section header has NO number. Only such rows switch the current bucket;
        # never match on a real initiative whose NAME happens to contain the word
        # "incremental" (e.g. "... allows incremental more Eligible ...").
        if not has_no:
            if "strategic unlock" in low:
                current = structural
            elif "incremental improvement" in low:
                current = incremental
            continue
        if name == "" or low == "nan":
            continue
        item = {
            "no": str(row.get("No")),
            "name": name,
            "timing": str(row.get("Timing", "") or "").strip(),
            "expected_impact": str(row.get("Expected impact", "") or "").strip(),
            "pic": str(row.get("PIC", "") or "").strip(),
            "status": str(row.get("Status", "") or "").strip(),
            "new_timing": str(row.get("New timing (if applicable)", "") or "").strip(),
            "details": str(row.get("Details from that month", "") or "").strip(),
            "confidence": str(row.get("How confident", "") or "").strip(),
        }
        if current is not None:
            current.append(item)
    return structural, incremental


def _signed(v, suffix):
    """Signed integer with a unit suffix, avoiding negative zero ('-0pp')."""
    n = round(v)
    if n == 0:
        return f"0{suffix}"
    return f"{n:+d}{suffix}"


def _n(s) -> str:
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


# Each conversion-stage absolute metric and the rate that drives it
_RULE7_PAIRS = [
    ("Eligible Base For Cash Loan", "%Eligible/Total User Base"),
    ("Traffic to Landing Page", "%Traffic/Eligible"),
    ("Submission", "%Submission/Traffic"),
    ("Approved", "%Approval Rate"),
]


def _movement_notes(perf) -> list:
    """
    Rule 7: distinguish real vs mechanical movement. For each conversion-stage
    metric, if the absolute moved but its conversion rate stayed flat, the move
    is base-driven (mechanical); if the rate itself moved, it is real.
    """
    if perf is None or getattr(perf, "empty", True):
        return []
    vals = {}
    for _, r in perf.iterrows():
        vals[_n(r.get("Metric", ""))] = (_f(r.get("Actual (Previous)")),
                                         _f(r.get("Actual (Current)")))
    notes = []
    for abs_name, rate_name in _RULE7_PAIRS:
        a = vals.get(_n(abs_name))
        rt = vals.get(_n(rate_name))
        if not a or not rt:
            continue
        (ap, ac), (rp, rc) = a, rt
        abs_mom = (ac / ap - 1) * 100 if ap else 0.0
        rate_pp = (rc - rp) * 100  # rates stored as ratios (0..1)
        if abs(abs_mom) >= 5 and abs(rate_pp) < 1:
            notes.append(f"{abs_name} {abs_mom:+.0f}% — MECHANICAL "
                         f"(base-driven; {rate_name} flat).")
        elif abs(rate_pp) >= 1:
            notes.append(f"{abs_name} — REAL ({rate_name} {rate_pp:+.0f}pp).")
    return notes


def _impact_score(impact_str: str) -> float:
    """Largest +Xpp / +X% magnitude in an expected-impact string (0 if none)."""
    nums = re.findall(r'\+?(\d+(?:\.\d+)?)\s*(?:pp|%)', str(impact_str))
    return max((float(n) for n in nums), default=0.0)


def _parse_impacts(impact_str: str) -> list:
    """Parse an Expected-impact cell into [(metric, target, unit)] where unit is 'pp' or '%'.
    Handles separators like newline / '/' / '(1)(2)' (e.g.
    '(1) %Eligible/Total User Base +5pp / (2) %Approval Rate +10pp')."""
    out = []
    for part in re.split(r'[\n;]|\(\d+\)', str(impact_str or "")):
        part = part.strip()
        if not part:
            continue
        m = re.search(r'\+?\s*(\d+(?:\.\d+)?)\s*(pp|%)', part)
        if not m:
            continue
        metric = part[:m.start()].strip(" .:+/")
        if metric:
            out.append((metric, float(m.group(1)), m.group(2)))
    return out


_MON3 = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
         7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}


def _rate_series(actual_df) -> dict:
    """{normalized metric: {(year, month): value}} from the Actual performance sheet."""
    series = {}
    if actual_df is None or getattr(actual_df, "empty", True):
        return series
    for _, r in actual_df.iterrows():
        key = _n(r.get("Metric", ""))
        if not key:
            continue
        mm = {}
        for col in actual_df.columns:
            if hasattr(col, "year") and getattr(col, "month", None):
                v = _f(r.get(col))
                if v is not None:
                    mm[(col.year, col.month)] = v
        if mm:
            series[key] = mm
    return series


def _expected_vs_realized(structural, incremental, perf, actual_df, month, year) -> list:
    """
    Rules 4/5/9/13 anchor: an initiative's realized impact is the actual movement of
    its promised metric **at the month it went live, vs the month before** (launch
    MoM) — NOT the current-month MoM and NOT actual-vs-plan.

    Why launch-month MoM: that delta isolates what the initiative actually changed
    when it shipped. e.g. #5 (live May): %Approval Rate 55% (Apr) -> 65% (May) = +10pp
    = exactly its promise, so it DELIVERED its +10pp impact — even though the absolute
    65% is still below the 70% plan target (a separate planning-gap fact). Measuring
    the current MoM would wrongly show ~0pp for an already-landed initiative.

    Realized uses the RATE change (pp) or the volume change (%). Returns one
    structured row per initiative: {no, name, status, promised, realized, verdict}.
    """
    import difflib
    from .extractor import _parse_month

    series = _rate_series(actual_df)
    names = list(series.keys())

    def _key(metric):
        k = _n(metric)
        if k in series:
            return k
        m = difflib.get_close_matches(k, names, n=1, cutoff=0.6)
        return m[0] if m else None

    def _eff_month(it):
        """Effective go-live (month, year): New timing if set, else planned Timing."""
        for t in (it.get("new_timing", ""), it.get("timing", "")):
            p = _parse_month(t)
            if p and p[1]:
                return p[0], p[1]
        return None

    def movement_at(key, eff):
        """Total movement of metric `key` at launch month `eff`, and whether it still
        holds at the report month. Returns (launch_month, total_jump_value_dict) or None."""
        if key is None or eff is None:
            return None
        mon, yr = eff
        prev = (yr - 1, 12) if mon == 1 else (yr, mon - 1)
        s = series[key]
        cur_v, prev_v = s.get((yr, mon)), s.get(prev)
        if cur_v is None or prev_v is None:
            return None
        rep_v = s.get((year, month))  # actual at the report month
        return mon, cur_v, prev_v, rep_v

    # PASS 1: a metric's launch-month move must be SHARED across all live/done
    # initiatives that launched in the SAME month targeting that metric (so the
    # +15pp May eligible jump splits into #1's +10pp and #5's +5pp, not +15pp each).
    group_promise = {}  # (metric_key, eff) -> sum of promised targets
    parsed = []         # per initiative: (it, landed, [(metric,target,unit,key,eff)])
    for it in structural + incremental:
        landed = it["status"].strip().lower() in ("live", "done")
        eff = _eff_month(it)
        plist = []
        for metric, target, unit in _parse_impacts(it["expected_impact"]):
            key = _key(metric)
            plist.append((metric, target, unit, key, eff))
            if landed and key is not None and eff is not None:
                gk = (key, eff)
                group_promise[gk] = group_promise.get(gk, 0.0) + target
        parsed.append((it, landed, plist))

    rep_tag = _MON3.get(month, "")
    rows = []
    for it, landed, plist in parsed:
        promised_parts, realized_parts, verdict_parts = [], [], []
        for metric, target, unit, key, eff in plist:
            promised_parts.append(f"{metric} +{target:g}{unit}")
            if not landed:
                realized_parts.append("—")
                verdict_parts.append(f"not due ({it['status']})")
                continue
            mv = movement_at(key, eff)
            if mv is None:
                realized_parts.append("n/a")
                verdict_parts.append("realized n/a (no data)")
                continue
            mon, cur_v, prev_v, rep_v = mv
            if unit == "pp":
                total = (cur_v - prev_v) * 100
                held = rep_v is not None and (rep_v - prev_v) > 0.005
            else:
                total = (cur_v / prev_v - 1) * 100 if prev_v else 0.0
                held = rep_v is not None and prev_v and (rep_v / prev_v - 1) > 0.005
            # Split the shared move proportionally to this initiative's promise.
            gsum = group_promise.get((key, eff), target)
            rz = total * (target / gsum) if gsum else total
            tag = f" in {_MON3[mon]}"
            hold = "held" if held else "reverted since launch"
            if abs(rz) < 0.5:
                realized_parts.append(f"~0{unit}{tag}")
                verdict_parts.append(f"shipped{tag}, no measurable movement")
            elif rz + 0.5 < target:
                realized_parts.append(f"{rz:+.0f}{unit}{tag}, {hold}")
                verdict_parts.append(f"PARTIAL (+{rz:.0f}{unit} of +{target:g}{unit})")
            else:
                realized_parts.append(f"{rz:+.0f}{unit}{tag}, {hold}")
                verdict_parts.append(f"realized{tag} ({hold} through {rep_tag})")
        rows.append({
            "no": it["no"], "name": it["name"], "status": it["status"],
            "promised": "; ".join(promised_parts) or "—",
            "realized": "; ".join(realized_parts) or "—",
            "verdict": "; ".join(verdict_parts) or "no quantified promise",
        })
    return rows


def _realized_line(r) -> str:
    """One prompt line from an expected-vs-realized row."""
    return (f"#{r['no']} {r['name']} ({r['status']}): promised {r['promised']}; "
            f"realized {r['realized']} -> {r['verdict']}")


def _unaddressed_gaps(perf, structural, incremental) -> list:
    """
    A metric that is BELOW plan but has NO active (On Track / Delay / Not started)
    initiative targeting it is an unaddressed gap — the thing causing the plan miss
    with nothing in the pipeline to close it. Typically its linked initiative already
    shipped (Live/Done) yet the metric is still short of plan (a residual / target
    gap that needs a new remediation initiative). Surfacing this is the whole point
    of the report: e.g. %Approval Rate 65% vs 70% plan with only the Live #5 behind
    it — absent from both Top Priorities (not actionable) and Escalations (not delayed).
    """
    if perf is None or getattr(perf, "empty", True):
        return []
    targeted_any, targeted_actionable, shipped = set(), set(), {}
    for it in structural + incremental:
        st = it["status"].strip().lower()
        for metric, _t, _u in _parse_impacts(it["expected_impact"]):
            k = _n(metric)
            targeted_any.add(k)
            if st in ("on track", "delay", "not started"):
                targeted_actionable.add(k)
            elif st in ("live", "done"):
                shipped.setdefault(k, []).append(f"#{it['no']} {it['name']}")
    gaps = []
    for i, (_, r) in enumerate(perf.iterrows()):
        name = str(r.get("Metric", ""))
        k = _n(name)
        if k not in targeted_any:          # only levers an initiative was meant to move
            continue
        if not is_pct(meta_for(name, i)["unit"]):
            continue
        actual, kpi = _f(r.get("Actual (Current)")), _f(r.get("KPI"))
        if actual is None or kpi is None:
            continue
        gap = (actual - kpi) * 100
        if gap <= -1 and k not in targeted_actionable:
            gaps.append({
                "metric": name,
                "actual": f"{actual * 100:.0f}%",
                "plan": f"{kpi * 100:.0f}%",
                "gap": f"{gap:+.0f}pp",
                "shipped": shipped.get(k, []),
            })
    return gaps


def _reconcile_claims(claims, perf) -> list:
    """
    Rule 3: compare numeric LEVELS asserted in emails against the actuals sheet.
    Returns conflict dicts {metric, email_value, sheet_value, owner, initiative}
    only when a confident metric match differs beyond tolerance.
    """
    import difflib
    if not claims or perf is None or getattr(perf, "empty", True):
        return []

    # Build {normalized metric name: (display, current_value, is_pct)}
    sheet = {}
    for i, (_, r) in enumerate(perf.iterrows()):
        name = str(r.get("Metric", ""))
        unit = meta_for(name, i)["unit"]
        sheet[_n(name)] = (name, _f(r.get("Actual (Current)")), is_pct(unit))
    names = list(sheet.keys())

    conflicts = []
    for c in claims:
        m = re.search(r'-?\d+(?:[.,]\d+)?', str(c.get("level", "")))
        if not m:
            continue
        num = float(m.group(0).replace(",", ""))
        has_pct = "%" in str(c.get("level", ""))
        key = _n(c.get("metric", ""))
        if key not in sheet:
            match = difflib.get_close_matches(key, names, n=1, cutoff=0.6)
            if not match:
                continue
            key = match[0]
        disp, cur, pct = sheet[key]
        if pct:
            claim_pct = num if (has_pct or num > 1.5) else num * 100
            sheet_pct = cur * 100
            if abs(claim_pct - sheet_pct) > 2:  # >2pp apart
                conflicts.append({"metric": disp, "email_value": f"{claim_pct:.0f}%",
                                  "sheet_value": f"{sheet_pct:.0f}%",
                                  "owner": c.get("owner", ""), "initiative": c.get("initiative", "")})
        elif cur and abs(num - cur) / abs(cur) > 0.10:  # >10% apart
            conflicts.append({"metric": disp, "email_value": f"{num:,.0f}",
                              "sheet_value": f"{cur:,.0f}",
                              "owner": c.get("owner", ""), "initiative": c.get("initiative", "")})
    return conflicts


def _fmt_mom(prev, cur, unit):
    """MoM as pp for % metrics, % for volume metrics."""
    if is_pct(unit):
        return _signed((cur - prev) * 100, "pp")
    if prev:
        return _signed((cur / prev - 1) * 100, "%")
    return ""


def _fmt_vs_plan(cur, plan, unit):
    if plan in (0, None) or pd.isna(plan):
        return ""
    if is_pct(unit):
        d = (cur - plan) * 100
        return "On plan" if abs(d) < 1 else _signed(d, "pp")
    d = (cur / plan - 1) * 100
    return "On plan" if abs(d) < 2 else _signed(d, "%")


def _fmt_val(v, unit):
    if is_pct(unit):
        return f"{_f(v) * 100:.0f}%"
    return f"{_f(v):,.0f}"


def _disbursement_series(df):
    """Return {month_int: value} for the Disbursement row across month columns."""
    out = {}
    for _, row in df.iterrows():
        name = str(row.get("Metric", "")).lower()
        if "disbursement" in name:
            for col in df.columns:
                if isinstance(col, (pd.Timestamp,)) or hasattr(col, "month"):
                    try:
                        if col.year and col.month:
                            out[(col.year, col.month)] = _f(row.get(col))
                    except AttributeError:
                        pass
            break
    return out


def build_report_data(context, month, year, data_source):
    mn = config.get_month_name
    prev_m, prev_y = data_source.get_previous_month(month, year)
    next_m, next_y = data_source.get_next_month(month, year)

    # Full Actual series — lets expected-vs-realized measure each initiative's
    # impact at the month it went live (launch-month MoM).
    try:
        _actual_for_realized = data_source.get_performance_data()
    except Exception:
        _actual_for_realized = None

    # --- Funnel (KPI snapshot) from the performance analysis frame ---
    perf = context.get("performance_analysis")
    funnel = []
    if perf is not None and not perf.empty:
        for i, (_, r) in enumerate(perf.iterrows()):
            unit = meta_for(r.get("Metric", ""), i)["unit"]
            prev, cur, plan = _f(r.get("Actual (Previous)")), _f(r.get("Actual (Current)")), _f(r.get("KPI"))
            funnel.append({
                "metric": r.get("Metric", ""),
                "unit": unit,
                "prev": _fmt_val(prev, unit),
                "cur": _fmt_val(cur, unit),
                "mom": _fmt_mom(prev, cur, unit),
                "plan": _fmt_val(plan, unit),
                "vs_plan": _fmt_vs_plan(cur, plan, unit),
            })

    # --- Initiatives by section ---
    structural, incremental = _split_initiatives(context.get("initiatives_data"))

    # --- Escalations: delayed / deprioritized initiatives, highest impact first ---
    escalations = []
    for it in structural + incremental:
        if it["status"].strip().lower() in ("delay", "deprioritized"):
            escalations.append({**it, "impact": _impact_score(it["expected_impact"])})
    escalations.sort(key=lambda x: x["impact"], reverse=True)

    # --- Forecast key numbers ---
    forecast = context.get("forecast")
    disb_cur = disb_next = None
    if forecast is not None and not forecast.empty:
        acol = next((c for c in forecast.columns if "(actual)" in str(c).lower()), None)
        fcol = next((c for c in forecast.columns if "(forecast)" in str(c).lower()), None)
        for _, r in forecast.iterrows():
            if "disbursement" in str(r.get("Metric", "")).lower():
                disb_cur = _f(r.get(acol)) if acol else None
                disb_next = _f(r.get(fcol)) if fcol else None
                break

    # --- YTD / FY (Disbursement) from raw actual + KPI ---
    ytd_actual = ytd_plan = fy_plan = None
    try:
        act = data_source.get_performance_data()
        kpi = data_source.get_kpi_data()
        a_series = _disbursement_series(act)
        k_series = _disbursement_series(kpi)
        ytd_actual = sum(v for (yy, mm), v in a_series.items() if yy == year and mm <= month)
        ytd_plan = sum(v for (yy, mm), v in k_series.items() if yy == year and mm <= month)
        fy_plan = sum(v for (yy, mm), v in k_series.items() if yy == year)
        plan_next = k_series.get((next_y, next_m))
    except Exception:
        plan_next = None

    return {
        "meta": {
            "report_month": mn(month), "year": year,
            "prev_month": mn(prev_m), "next_month": mn(next_m),
            "report_code": f"CL - Biz - Report {year}.{month:02d}",
        },
        "funnel": funnel,
        "structural": structural,
        "incremental": incremental,
        "escalations": escalations,
        "movement": _movement_notes(perf),
        "realized_check": _expected_vs_realized(
            structural, incremental, perf, _actual_for_realized, month, year),
        "gaps": _unaddressed_gaps(perf, structural, incremental),
        "conflicts": _reconcile_claims(context.get("email_metric_claims"), perf),
        "forecast": {
            "disb_cur": round(disb_cur) if disb_cur is not None else None,
            "disb_next": round(disb_next) if disb_next is not None else None,
            "plan_next": round(plan_next) if plan_next else None,
        },
        "ytd": {
            "disb_ytd_actual": round(ytd_actual) if ytd_actual is not None else None,
            "disb_ytd_plan": round(ytd_plan) if ytd_plan is not None else None,
            "fy_plan": round(fy_plan) if fy_plan is not None else None,
        },
        "top_priorities": _top_priorities(context),
    }


# Levers that belong to the "Structural ceiling unlocks" half (others -> Incremental).
# Normalized via _n() so punctuation/case in the metric name doesn't matter.
_STRUCTURAL_METRICS = {_n("%Eligible/Total User Base"), _n("%Approval Rate"),
                       _n("Eligible Base For Cash Loan"), _n("Approved")}


def _lever_label(expected_impact: str) -> str:
    """'Structural — %Approval Rate' / 'Incremental — %Submission/Traffic' from the
    first metric in an expected-impact string."""
    imps = _parse_impacts(expected_impact)
    if not imps:
        return ""
    metric = imps[0][0]
    sect = "Structural" if _n(metric) in _STRUCTURAL_METRICS else "Incremental"
    return f"{sect} — {metric}"


def _top_priorities(context):
    top3 = context.get("top_3_priorities")
    out = []
    if top3 is None or (hasattr(top3, "empty") and top3.empty):
        return out
    for _, r in top3.iterrows():
        name = str(r.get("name", ""))
        pic = str(r.get("pic", ""))
        impact = str(r.get("expected_impact", ""))
        out.append({
            "name": name, "status": str(r.get("status", "")),
            "pic": pic, "timing": str(r.get("timing", "")),
            "expected_impact": impact,
            "objective": _lever_label(impact),
            "initiative_owner": f"{name} ({pic})" if pic else name,
        })
    return out


# --------------------------------------------------------------------------- #
# Narrative (LLM)
# --------------------------------------------------------------------------- #
NARRATIVE_KEYS = {
    "kpi_read": "", "headline": "", "mom_bridge": "", "plan_miss_bridge": "",
    "structural_bullets": [], "incremental_bullets": [],
    "runrate": "", "runrate_structural": [], "runrate_incremental": [],
    "top_priorities": [], "annual_structural": [], "annual_incremental": [],
    "ytd_outlook": "", "risks": [],
}


def generate_narrative(report_data):
    """Return the narrative dict; empty strings/lists if the LLM is unavailable."""
    if not llm_available():
        return dict(NARRATIVE_KEYS)

    prompt = _narrative_prompt(report_data)
    messages = [
        {"role": "system", "content": "You write executive business-report prose and return strict JSON only. Do not think out loud."},
        {"role": "user", "content": prompt + "\n\n/no_think"},
    ]
    try:
        client = extractor._client()
        try:
            resp = client.chat.completions.create(
                model=config.LLM_CONFIG["model"], messages=messages,
                temperature=0.2, max_tokens=4000,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception:
            resp = client.chat.completions.create(
                model=config.LLM_CONFIG["model"], messages=messages,
                temperature=0.2, max_tokens=4000,
            )
        content = resp.choices[0].message.content or ""
    except Exception as e:
        print(f"[WARNING] Report narrative LLM failed: {e}")
        return dict(NARRATIVE_KEYS)

    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    data = None
    try:
        data = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict):
        return dict(NARRATIVE_KEYS)

    out = dict(NARRATIVE_KEYS)
    for k in NARRATIVE_KEYS:
        if k in data and data[k] is not None:
            out[k] = data[k]
    return out


def _narrative_prompt(rd):
    meta = rd["meta"]
    funnel_txt = "\n".join(
        f"  {r['metric']} ({r['unit']}): {meta['prev_month'][:3]}={r['prev']}, "
        f"{meta['report_month'][:3]}={r['cur']}, MoM={r['mom']}, Plan={r['plan']}, vsPlan={r['vs_plan']}"
        for r in rd["funnel"])

    def init_txt(items):
        return "\n".join(
            f"  #{it['no']} {it['name']} | owner {it['pic']} | status {it['status']} | "
            f"timing {it['timing']}{(' -> ' + it['new_timing']) if it['new_timing'] else ''} | "
            f"impact {it['expected_impact']} | confidence {it['confidence']} | "
            f"details: {it['details']}" for it in items) or "  (none)"

    tp_txt = "\n".join(
        f"  {i+1}. {t['objective']} | {t['initiative_owner']} | promised {t['expected_impact']} "
        f"| status {t['status']} | timing {t['timing']}"
        for i, t in enumerate(rd["top_priorities"])) or "  (none)"

    fc, ytd = rd["forecast"], rd["ytd"]
    return f"""{STYLE_GUIDE}

REPORT: {meta['report_code']} — reporting month {meta['report_month']} {meta['year']}; latest actual = {meta['report_month']}; forecast month = {meta['next_month']}.

KPI FUNNEL (actuals vs plan; numbers are final — reference them, do not change):
{funnel_txt}

MOVEMENT CHECK (real vs mechanical — use this in the MoM bridge; do not contradict):
{chr(10).join('  - ' + m for m in rd['movement']) or '  (none)'}

EXPECTED vs REALIZED (deterministic — every initiative's promise checked against the
ACTUAL movement of that exact metric; this is authoritative, do not contradict it.
NOTE: an initiative's section (structural/incremental) may differ from the lever its
metric belongs to — attribute each initiative to the lever of ITS OWN metric here,
e.g. a scoring-model initiative targeting %Approval Rate is the approval-rate driver
even if the tracker lists it under incremental):
{chr(10).join('  - ' + _realized_line(r) for r in rd['realized_check']) or '  (none)'}

UNADDRESSED PLAN GAPS (metric below plan with NO active initiative behind it — these
DRIVE the plan miss yet are absent from Top Priorities/Escalations; you MUST surface
each as a risk and, if it is the miss driver, in the headline/plan-miss bridge):
{chr(10).join(f"  - {g['metric']}: {g['actual']} vs {g['plan']} plan ({g['gap']}); linked {', '.join(g['shipped']) or 'none'} already shipped, residual gap unowned" for g in rd['gaps']) or '  (none)'}

STRUCTURAL initiatives (eligible base / approval rate / scoring models):
{init_txt(rd['structural'])}

INCREMENTAL initiatives (traffic / submission / ticket):
{init_txt(rd['incremental'])}

FORECAST (Disbursement VNDm): current {meta['report_month']} = {fc['disb_cur']}; {meta['next_month']} run-rate = {fc['disb_next']}; {meta['next_month']} plan = {fc['plan_next']}.
YTD Disbursement (VNDm): actual = {ytd['disb_ytd_actual']}, plan = {ytd['disb_ytd_plan']}; FY plan = {ytd['fy_plan']}.

TOP PRIORITIES (PRE-SELECTED per the stated rule — active, deliverable initiatives
ranked by promised impact; Live/Done/Deprioritized are EXCLUDED, those go to
Escalations). Write a target_why for EACH, in this EXACT order — do NOT add, drop,
reorder, or substitute a Live/already-shipped initiative:
{tp_txt}

QUALITY RULES (mandatory — a confident wrong number is fatal):
- NEVER invent a number. Use ONLY figures given above. If a figure you need is
  not provided, write "[number needed]" — never a plausible guess.
- Every number states its comparator (vs plan / vs last month / vs target).
- "Shipped" != "worked": state an initiative's status and the metric movement as
  SEPARATE facts. Do not claim a metric moved because an initiative shipped unless
  the funnel numbers support it.
- For each initiative, use the verdict in the EXPECTED vs REALIZED block VERBATIM.
  An initiative's IMPACT is measured at the month it went live: actual[launch] minus
  actual[launch-1]. That impact still counts in later months as long as the metric
  stays uplifted vs the pre-launch baseline ("held"); it only stops counting if the
  metric reverts ("reverted since launch").
  * "realized in <month> (held through <report month>)" -> the initiative delivered
    its promised lift and it is still in effect; say it realized. Do NOT call it a
    failure just because the current MoM is flat — the lift is already in the base.
  * "PARTIAL (+X of +Y)" -> it moved the metric, but by less than promised.
  * "shipped, no measurable movement" -> launched but the metric never moved.
- Distinguish "promise realized" from "absolute level still below plan": a lift can
  be fully delivered yet leave the rate under its plan target — e.g. #5 %Approval
  Rate delivered +10pp at launch (55%->65%, still held), but 65% is still 5pp under
  the 70% plan. Frame that as a TARGET/planning gap, NOT as the initiative failing.
- NEVER write "no initiative landed / has landed" for a lever if ANY initiative on
  that lever has status Live or Done. Name it and report its verdict from the block.
- MoM bridge decomposition: build it from the user-base growth times the CONVERSION
  RATE changes (the % rows), NOT from stacking absolute stage volumes. Absolute stage
  volumes (Traffic/Submission/Approved) already embed the base growth, so multiplying
  them together DOUBLE-COUNTS. Use only levers whose RATE actually changed plus the
  base growth; flat rates contribute x1.00 and must not invent an "offset".
- Keep tentative things tentative; carry confidence (High/Medium/Low) from the data.
- Separate fact vs inference; do not dress an inference as a confirmed fact.
- Run-rate: state its basis (anchored on plan, adjusted for known slips). Do NOT
  bake the impact of a DELAYED initiative into next month unless its new timing is
  exactly {meta['next_month']}.
- "risks": put every unconfirmed / to-verify item here, attributed to its owner.
  INCLUDE every UNADDRESSED PLAN GAP above — name the metric, its gap vs plan, and
  that no active initiative is closing it (recommend a remediation initiative/owner).
- Account for EVERY initiative listed above — including Live/Done (a closing line on
  realized vs expected) and Not started (a status line). Nothing disappears silently.

Write the report as JSON with EXACTLY these keys:
{{
 "kpi_read": "1-3 sentence read of the funnel table",
 "headline": "Headline. ... (this month's disbursement, MoM and vs-plan, the story)",
 "mom_bridge": "MoM bridge (fact). ... decompose MoM with arithmetic of levers",
 "plan_miss_bridge": "Plan-miss bridge (fact). ... decompose gap to plan by named initiative (omit/soften if on/above plan)",
 "structural_bullets": ["bullet per structural lever, mapped to its initiative"],
 "incremental_bullets": ["bullet per incremental lever, mapped to its initiative"],
 "runrate": "Run-rate. ... next-month disbursement run-rate, MoM and vs next-month plan",
 "runrate_structural": ["next-month structural notes"],
 "runrate_incremental": ["next-month incremental notes"],
 "top_priorities": [{{"target_why":"target outcome & why it matters"}}],  // EXACTLY one per PRE-SELECTED priority above, same order; objective & initiative are fixed, only write target_why
 "annual_structural": [{{"lever":"","landed_next":"what landed / what's next","confidence":"High/Medium/Low","status":"On track/Behind/..."}}],
 "annual_incremental": [{{"lever":"","landed_next":"","impact":"e.g. +2pp","status":""}}],
 "ytd_outlook": "YTD vs plan and FY outlook narrative with the conditions to hit FY",
 "risks": ["risk/dependency/escalation tied to a specific initiative"]
}}
Return ONLY the JSON."""
