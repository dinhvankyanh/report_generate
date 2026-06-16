"""
Lock-resilient Excel sheet writer.

If the target workbook is open (locked) in Excel, writing normally raises
PermissionError. save_sheet() falls back to an alternate "<name> (n).xlsx" so
a generated sheet is never silently lost.
"""
import pandas as pd


def save_sheet(df: pd.DataFrame, file_path, sheet_name: str):
    """Write df to `sheet_name` in file_path (append/replace), returning the
    Path actually written (an alternate name if the original was locked)."""
    def _write(p):
        if p.exists():
            with pd.ExcelWriter(p, mode="a", if_sheet_exists="replace") as w:
                df.to_excel(w, sheet_name=sheet_name, index=False, na_rep="")
        else:
            with pd.ExcelWriter(p, mode="w") as w:
                df.to_excel(w, sheet_name=sheet_name, index=False, na_rep="")

    try:
        _write(file_path)
        return file_path
    except PermissionError:
        # Reuse/overwrite the first writable "(n)" alternate (avoid spawning many)
        for n in range(1, 100):
            alt = file_path.with_name(f"{file_path.stem} ({n}){file_path.suffix}")
            try:
                _write(alt)
                return alt
            except PermissionError:
                continue
        raise
