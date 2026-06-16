"""
Shared writer for the Initiatives Tracker file.

Writes a month X tracker that preserves the month X-1 template: the title row,
the hint row and the real header row are kept verbatim (only the title's
month/year is refreshed), then the computed data rows (including the section
rows) are appended below.

Both Step 1 (initial fill) and Step 2 (after Status change is computed) call
this so the file on disk always reflects the latest state.
"""
import pandas as pd

from .. import config


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str) and v.strip().lower() == "nan":
        return None
    return v


def write_tracker(raw: pd.DataFrame, header_idx: int,
                  current: pd.DataFrame, month: int, year: int):
    """Write month X tracker preserving the template; returns the output Path."""
    from openpyxl import Workbook

    out_path = config.INITIATIVES_TRACKER_DIR / f"Initiatives tracker thang {month}-{year}.xlsx"
    config.INITIATIVES_TRACKER_DIR.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Initiatives tracker {month}-{year}"

    # Preserve template rows 0..header_idx (title, hints, header), refreshing
    # only the title cell with the current month/year.
    for r in range(header_idx + 1):
        values = [_clean(v) for v in raw.iloc[r].tolist()]
        if r == 0:
            values[0] = (f"Initiatives Tracker - status as of end "
                         f"{config.get_month_name(month)} {year}")
        ws.append(values)

    # Data rows, positional to match the preserved header order.
    n_cols = raw.shape[1]
    for _, row in current.iterrows():
        values = []
        for c in range(n_cols):
            col_name = current.columns[c] if c < len(current.columns) else None
            values.append(_clean(row[col_name]) if col_name is not None else None)
        ws.append(values)

    try:
        wb.save(out_path)
    except PermissionError:
        # Reuse/overwrite the first writable "(n)" alternate (avoid spawning many)
        for n in range(1, 100):
            alt = out_path.with_name(f"{out_path.stem} ({n}){out_path.suffix}")
            try:
                wb.save(alt)
                return alt
            except PermissionError:
                continue
        raise
    return out_path
