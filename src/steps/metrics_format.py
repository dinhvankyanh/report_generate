"""
Shared helpers to format agent-generated calculation files like the Metrics
template: add "No" and "Unit" columns, show percentages with a % sign, and
round plain numbers to whole values (no decimals) for a clean look.
"""
import re
import pandas as pd

from .. import config

_metrics_cache = None


def load_metrics() -> list:
    """Return the metric definitions in order: [{no, name, unit}, ...]."""
    global _metrics_cache
    if _metrics_cache is not None:
        return _metrics_cache

    raw = pd.read_excel(config.METRICS_FILE, sheet_name="List of metrics", header=None)
    header_idx = None
    for idx, row in raw.iterrows():
        cells = [str(x).strip().lower() for x in row.tolist()]
        if "no" in cells and "metrics" in cells:
            header_idx = idx
            break
    if header_idx is None:
        header_idx = 1

    df = pd.read_excel(config.METRICS_FILE, sheet_name="List of metrics", header=header_idx)
    df.columns = [str(c).strip() for c in df.columns]
    out = []
    for _, r in df.iterrows():
        name = r.get("Metrics")
        if pd.isna(name) or str(name).strip() == "":
            continue
        out.append({
            "no": _int(r.get("No")),
            "name": str(name).strip(),
            "unit": "" if pd.isna(r.get("Unit")) else str(r.get("Unit")).strip(),
        })
    _metrics_cache = out
    return out


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def meta_for(metric_name: str, position: int) -> dict:
    """
    Resolve (no, unit) for a metric by normalized-name match, falling back to
    positional alignment (all calc files use the Metrics order).
    """
    metrics = load_metrics()
    target = _norm(metric_name)
    for m in metrics:
        if _norm(m["name"]) == target:
            return m
    if 0 <= position < len(metrics):
        return metrics[position]
    return {"no": None, "name": metric_name, "unit": ""}


def is_pct(unit: str) -> bool:
    return str(unit).strip() == "%"


def fmt_num(v) -> str:
    """Round a plain number to a whole value with thousands separators."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _s(v)
    if pd.isna(f):
        return ""
    n = round(f)
    if n == 0:
        n = 0  # avoid "-0"
    return f"{n:,}"


def fmt_pct(v, is_ratio: bool) -> str:
    """Format a percentage with a % sign. is_ratio=True means v is 0..1."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _s(v)
    if pd.isna(f):
        return ""
    if is_ratio:
        f *= 100
    n = round(f)
    if n == 0:
        n = 0  # avoid "-0%"
    return f"{n}%"


def fmt_value(v, unit: str, pct_is_ratio: bool) -> str:
    """Format a metric value column according to its unit."""
    return fmt_pct(v, pct_is_ratio) if is_pct(unit) else fmt_num(v)


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s
