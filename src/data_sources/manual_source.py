"""
Manual Data Source (Phase 1 / Fallback)
Reads data directly from Excel files - no email integration required
"""
import os
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime
from pathlib import Path
from .base import BaseDataSource
from .. import config


class ManualDataSource(BaseDataSource):
    """
    Reads initiatives data from existing Excel files.
    This is the Phase 1 implementation or fallback for Phase 2.
    """

    def __init__(self):
        self.project_root = config.PROJECT_ROOT

    def _find_initiatives_file(self, month: int, year: int, exact: bool = False) -> Optional[Path]:
        """
        Find initiatives tracker file for given month/year

        Args:
            month: Month number (1-12)
            year: Year (e.g., 2026)
            exact: If True, look for exact match. If False, look for most recent file before given month
        """
        tracker_dir = config.INITIATIVES_TRACKER_DIR

        if not tracker_dir.exists():
            return None

        # Get all xlsx files (skip Excel lock/temp files like ~$foo.xlsx)
        files = [f for f in tracker_dir.glob("*.xlsx") if not f.name.startswith("~$")]
        if not files:
            return None

        # Parse filenames to extract month/year
        # Handle: "Initiatives tracker thang 5-2026.xlsx" or "Initiatives tracker tháng 5-2026.xlsx"
        file_dates = []
        for f in files:
            name = f.stem
            # Match pattern like "thang X-YYYY" or "tháng X-YYYY" (with Vietnamese chars)
            match = re.search(r'th[a-z\x00-\xff]*ng\s*(\d+)[-\s](\d{4})', name, re.IGNORECASE)
            if match:
                file_month = int(match.group(1))
                file_year = int(match.group(2))
                file_dates.append((f, file_month, file_year))

        if not file_dates:
            return None

        if exact:
            # Look for exact match
            for f, fm, fy in file_dates:
                if fm == month and fy == year:
                    return f
        else:
            # Look for most recent file before or at the given month
            # Sort by year, then month
            file_dates.sort(key=lambda x: (x[2], x[1]), reverse=True)
            for f, fm, fy in file_dates:
                if fy < year or (fy == year and fm <= month):
                    return f

        return file_dates[0][0] if file_dates else None

    def get_initiatives_data(self, month: int, year: int, exact: bool = False) -> pd.DataFrame:
        """
        Get initiatives data for a month. By default (exact=False) falls back to
        the most recent tracker at/before the month — so the X-1 skeleton uses
        the latest available earlier file if the exact month is missing.
        """
        import re  # Import here to avoid circular import

        # Find the file
        file_path = self._find_initiatives_file(month, year, exact=exact)

        if not file_path:
            print(f"[WARNING] No initiatives tracker file found for {month}/{year}")
            return None

        print(f"[FILE] Using initiatives file: {file_path.name}")

        # Read the Excel file
        try:
            # Get sheet name from file
            xl = pd.ExcelFile(file_path)
            sheet_name = xl.sheet_names[0]  # Use first sheet

            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

            # Find the header row (row with "No", "Initiative Names", etc.)
            header_row = None
            for idx, row in df.iterrows():
                row_str = row.astype(str).str.lower().tolist()
                if "no" in row_str and "initiative names" in row_str:
                    header_row = idx
                    break

            if header_row is None:
                print("[WARNING] Could not find header row in initiatives tracker")
                return None

            # Re-read with proper header
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)

            # Clean up columns
            df.columns = df.columns.str.strip()

            return df

        except Exception as e:
            print(f"[ERROR] Error reading initiatives file: {e}")
            return None

    def get_previous_initiatives_data(self, month: int, year: int) -> Optional[pd.DataFrame]:
        """Get initiatives data from the previous month"""
        prev_month, prev_year = self.get_previous_month(month, year)
        return self.get_initiatives_data(prev_month, prev_year)

    def find_initiatives_file(self, month: int, year: int, exact: bool = False) -> Optional[Path]:
        """Public wrapper around _find_initiatives_file."""
        return self._find_initiatives_file(month, year, exact=exact)

    def get_initiatives_raw(self, month: int, year: int, exact: bool = False):
        """
        Read the initiatives tracker file as a raw grid (header=None) so the
        full template is preserved: title row, hint row, real header row and
        the section rows ("Strategic unlock" / "Incremental improvements").

        Returns:
            (raw_df, header_row_index, sheet_name) or (None, None, None) if not found.
        """
        file_path = self._find_initiatives_file(month, year, exact=exact)
        if not file_path:
            return None, None, None

        xl = pd.ExcelFile(file_path)
        sheet_name = xl.sheet_names[0]
        raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

        header_idx = None
        for idx, row in raw.iterrows():
            row_str = row.astype(str).str.lower().str.strip().tolist()
            if "no" in row_str and "initiative names" in row_str:
                header_idx = idx
                break

        return raw, header_idx, sheet_name

    def get_performance_data(self) -> pd.DataFrame:
        """Get actual performance from Excel file"""
        # Find header row by searching for "No" or "Metric" or "Unit"
        df_raw = pd.read_excel(config.ACTUAL_PERFORMANCE_FILE, sheet_name="Actual performance", header=None)

        header_row = None
        for idx, row in df_raw.iterrows():
            row_str = [str(x).lower() for x in row.tolist()]
            if 'no' in row_str and ('metric' in row_str or 'unit' in row_str):
                header_row = idx
                break

        if header_row is None:
            header_row = 3  # Default

        # Re-read with correct header
        df = pd.read_excel(config.ACTUAL_PERFORMANCE_FILE, sheet_name="Actual performance", header=header_row)

        # Fix column names - first column should be "No", second "Metric", third "Unit"
        cols = list(df.columns)
        new_cols = {}
        for i, col in enumerate(cols):
            if i == 0:
                new_cols[col] = 'No'
            elif i == 1:
                new_cols[col] = 'Metric'
            elif i == 2:
                new_cols[col] = 'Unit'

        if new_cols:
            df = df.rename(columns=new_cols)

        return df

    def get_kpi_data(self) -> pd.DataFrame:
        """Get KPI from Excel file"""
        # Find header row
        df_raw = pd.read_excel(config.KPI_FILE, sheet_name="KPI", header=None)

        header_row = None
        for idx, row in df_raw.iterrows():
            row_str = [str(x).lower() for x in row.tolist()]
            if 'no' in row_str and ('metric' in row_str or 'unit' in row_str):
                header_row = idx
                break

        if header_row is None:
            header_row = 3

        df = pd.read_excel(config.KPI_FILE, sheet_name="KPI", header=header_row)

        cols = list(df.columns)
        new_cols = {}
        for i, col in enumerate(cols):
            if i == 0:
                new_cols[col] = 'No'
            elif i == 1:
                new_cols[col] = 'Metric'
            elif i == 2:
                new_cols[col] = 'Unit'

        if new_cols:
            df = df.rename(columns=new_cols)

        return df

    def get_annual_planning_data(self) -> pd.DataFrame:
        """Get annual planning from Excel file"""
        return pd.read_excel(config.ANNUAL_PLANNING_FILE, sheet_name="Annual Planning", header=2)

    def get_metrics_list(self) -> List[str]:
        """Get list of all metrics from Metrics.xlsx"""
        df = pd.read_excel(config.METRICS_FILE, sheet_name="List of metrics", header=1)
        df = df.dropna(subset=["Metrics"])
        return df["Metrics"].tolist()

    def get_month_column_name(self, df: pd.DataFrame, month: int, year: int) -> str:
        """Get the column name for a specific month in the DataFrame"""
        # Try to find column with the date
        target_date = datetime(year, month, 1)

        for col in df.columns:
            if isinstance(col, datetime):
                if col.year == year and col.month == month:
                    return col
            elif isinstance(col, str):
                # Check if column contains the date
                if str(year) in col and str(month) in col:
                    return col

        return None


import re  # Import at top level


def create_manual_source() -> ManualDataSource:
    """Factory function to create manual data source"""
    return ManualDataSource()