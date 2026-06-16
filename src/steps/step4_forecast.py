"""
Step 4: Forecast Calculation
Calculate forecast for next month using percentage-based chain calculation
"""
from typing import Dict, Any
import pandas as pd
import numpy as np
from .base import BaseStep, StepResult
from .. import config


class Step4Forecast(BaseStep):
    """
    Step 4: Forecast for month X+1

    New Logic:
    i.  If no initiatives in X+1: %metrics stay same as month X
        If initiatives exist: add impact uplift
    ii. Total user base X+1 = Total user base X * (1 + %mom growth user base)
    iii. Eligible Base = %Eligible/Total User Base * Total User Base
    iv. Traffic = %Traffic/Eligible * Eligible Base
    v. Submission = %Submission/Traffic * Traffic
    vi. Approved = %Approval rate * Submission
    vii. Avg Ticket Size X+1 = Avg Ticket Size X * (1 + %mom growth ticket size)
    """

    @property
    def name(self) -> str:
        return "Step 4: Forecast Calculation"

    @property
    def description(self) -> str:
        return "Calculate forecast for next month using percentage chain"

    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute step 4"""
        next_month, next_year = self.data_source.get_next_month(month, year)
        self.log(f"Calculating forecast for {config.get_month_name(next_month)} {next_year}")

        # Get actual performance data for current month (month X)
        actual_df = self.data_source.get_performance_data()
        initiatives_df = context.get("initiatives_data")

        # Get column for current month (X)
        current_col = self._get_month_column(actual_df, month, year)
        self.log(f"Looking for {month}/{year}, found column: {current_col}")
        self.log(f"Available columns: {[str(c)[:15] for c in actual_df.columns]}")

        if not current_col:
            return StepResult(
                success=False,
                error=f"Could not find data for {month}/{year}"
            ).__dict__

        # Get all metrics values for current month
        metrics_data = self._get_metrics_values(actual_df, current_col)

        # Calculate %changes from historical data (last 3 months for %metrics)
        pct_changes = self._calculate_pct_changes(actual_df, month, year, metrics_data)

        # Get initiatives impact for next month
        init_impacts = self._get_initiative_impacts(initiatives_df, next_month, next_year)

        # Calculate forecast using chain logic
        forecast = self._calculate_forecast_chain(
            metrics_data, pct_changes, init_impacts
        )

        # Define the correct metric order as per Metrics.xlsx
        # Mapping from Metrics.xlsx format to pct_changes keys
        metric_to_pct_key = {
            "Total User Base": None,
            "% mom growth user base": "%mom growth user base",
            "Eligible Base For Cash Loan": None,
            "% Eligible/Total User Base": "%Eligible/Total User Base",
            "Traffic to Landing Page": None,
            "%Traffic/Eligible": "%Traffic/Eligible",
            "Submission": None,
            "%Submission/Traffic": "%Submission/Traffic",
            "Approved": None,
            "% Approval Rate": "%Approval rate",
            "Average Ticket Size": None,
            "% mom growth ticket size": "%mom growth ticket size",
            "Disbursement Volume": None
        }

        metric_order = list(metric_to_pct_key.keys())

        # Mapping: which %metric belongs to which base metric
        pct_to_base_map = {
            "% mom growth user base": "Total User Base",
            "% Eligible/Total User Base": "Eligible Base For Cash Loan",
            "%Traffic/Eligible": "Traffic to Landing Page",
            "%Submission/Traffic": "Submission",
            "% Approval Rate": "Approved",
            "% mom growth ticket size": "Average Ticket Size"
        }

        # Build forecast with all 13 metrics in correct order
        forecasts = []
        for metric_name in metric_order:
            # Check if this is a % metric or a regular metric
            if metric_name.startswith("%"):
                # For percentage metrics:
                # - Get the corresponding pct_changes key
                pct_key = metric_to_pct_key.get(metric_name, metric_name)
                # - Jun(actual) = the current % value (from pct_changes)
                # - Jun(forecast) = same as current (no change expected)
                # Stored as a ratio (0.35), matching the Performance analysis file.
                actual_val = pct_changes.get(pct_key, 0) / 100.0
                forecast_val = actual_val  # stays same

                row = {
                    "Metric": metric_name,
                    f"{config.get_month_name(month)} (actual)": actual_val,
                    f"{config.get_month_name(next_month)} (forecast)": forecast_val,
                    "Initiative notes": None
                }
            else:
                # Regular metric - get from forecast calculation
                data = forecast.get(metric_name, {})

                # Build Initiative notes with uplift value
                init_notes = data.get("init_notes", "")
                init_impact = data.get("init_impact", 0)

                # Build initiative notes
                if init_notes and init_impact != 0:
                    initiative_notes = f"{init_notes}: +{init_impact}pp"
                else:
                    initiative_notes = ""

                row = {
                    "Metric": metric_name,
                    f"{config.get_month_name(month)} (actual)": data.get("current", 0),
                    f"{config.get_month_name(next_month)} (forecast)": data.get("final", 0),
                    "Initiative notes": initiative_notes if initiative_notes else None
                }

            forecasts.append(row)

        forecast_df = pd.DataFrame(forecasts)

        # Save to context
        context["forecast"] = forecast_df

        # Save to Excel
        self._save_forecast(forecast_df, next_month, next_year)

        self.log(f"Calculated forecast for {len(forecasts)} metrics", "success")

        return StepResult(
            success=True,
            data={"metrics_count": len(forecasts)},
            message=f"Forecast complete for {config.get_month_name(next_month)} {next_year}"
        ).__dict__

    def _get_month_column(self, df: pd.DataFrame, month: int, year: int) -> str:
        """Find column for specific month - handles both datetime and Timestamp"""
        from datetime import datetime
        for col in df.columns:
            if isinstance(col, (datetime, pd.Timestamp)):
                if col.year == year and col.month == month:
                    return col
        return None

    def _get_metrics_values(self, df: pd.DataFrame, current_col) -> dict:
        """Get all metric values for current month"""
        metrics = {}
        for idx, row in df.iterrows():
            metric_name = row.get("Metric", "")
            if pd.isna(metric_name) or metric_name == "":
                continue
            metrics[metric_name] = row.get(current_col, 0)
        return metrics

    def _calculate_pct_changes(self, df: pd.DataFrame, month: int, year: int, metrics_data: dict) -> dict:
        """
        Calculate percentage metrics for forecast:
        - %mom growth user base
        - %Eligible/Total User Base
        - %Traffic/Eligible
        - %Submission/Traffic
        - %Approval rate
        - %mom growth ticket size
        """
        # Get previous month for comparison
        prev_month, prev_year = self.data_source.get_previous_month(month, year)
        prev_col = self._get_month_column(df, prev_month, prev_year)

        pct_changes = {}

        if prev_col:
            # Get previous month values
            prev_metrics = {}
            for idx, row in df.iterrows():
                metric_name = row.get("Metric", "")
                if pd.isna(metric_name) or metric_name == "":
                    continue
                prev_metrics[metric_name] = row.get(prev_col, 0)

            # Calculate percentage metrics (current month values as percentages)
            current = metrics_data
            prev = prev_metrics

            # %mom growth user base = (Total User Base current - Total User Base prev) / Total User Base prev
            if prev.get("Total User Base", 0) != 0:
                pct_changes["%mom growth user base"] = (
                    (current.get("Total User Base", 0) - prev.get("Total User Base", 0))
                    / prev.get("Total User Base", 0)
                ) * 100

            # %Eligible/Total User Base
            if current.get("Total User Base", 0) != 0:
                pct_changes["%Eligible/Total User Base"] = (
                    current.get("Eligible Base For Cash Loan", 0)
                    / current.get("Total User Base", 0)
                ) * 100

            # %Traffic/Eligible
            if current.get("Eligible Base For Cash Loan", 0) != 0:
                pct_changes["%Traffic/Eligible"] = (
                    current.get("Traffic to Landing Page", 0)
                    / current.get("Eligible Base For Cash Loan", 0)
                ) * 100

            # %Submission/Traffic
            if current.get("Traffic to Landing Page", 0) != 0:
                pct_changes["%Submission/Traffic"] = (
                    current.get("Submission", 0)
                    / current.get("Traffic to Landing Page", 0)
                ) * 100

            # %Approval rate
            if current.get("Submission", 0) != 0:
                pct_changes["%Approval rate"] = (
                    current.get("Approved", 0)
                    / current.get("Submission", 0)
                ) * 100

            # %mom growth ticket size = (Avg Ticket Size current - Avg Ticket Size prev) / Avg Ticket Size prev
            if prev.get("Average Ticket Size", 0) != 0:
                pct_changes["%mom growth ticket size"] = (
                    (current.get("Average Ticket Size", 0) - prev.get("Average Ticket Size", 0))
                    / prev.get("Average Ticket Size", 0)
                ) * 100

        return pct_changes

    def _get_initiative_impacts(self, initiatives_df, next_month: int, next_year: int) -> dict:
        """
        Sum the expected impact uplift of initiatives that launch in month X+1.

        An initiative contributes if its effective timing (New timing if set,
        else planned Timing) falls in next_month/next_year AND it is expected to
        deliver then (status On Track / Delay / Live). Deprioritized / Not started
        items, and items already live in earlier months, are excluded.
        """
        impacts = {
            "%Eligible/Total User Base": {"value": 0, "initiatives": ""},
            "%Traffic/Eligible": {"value": 0, "initiatives": ""},
            "%Submission/Traffic": {"value": 0, "initiatives": ""},
            "%Approval rate": {"value": 0, "initiatives": ""},
            "Average Ticket Size": {"value": 0, "initiatives": ""}
        }

        if initiatives_df is None or initiatives_df.empty:
            return impacts

        for _, row in initiatives_df.iterrows():
            status = str(row.get("Status", "")).strip()
            initiative_name = row.get("Initiative Names", "Unknown")

            # Only initiatives that will newly launch in X+1 add uplift.
            # Live/Done are already reflected in the actuals; Deprioritized /
            # Not started will not launch.
            if status not in ["On Track", "Delay"]:
                continue

            new_timing = str(row.get("New timing (if applicable)", "")).strip()
            has_new = bool(new_timing) and new_timing.lower() != "nan"
            if status == "Delay":
                # A delayed item only counts if it has been re-timed TO X+1;
                # its original planned date is precisely what is slipping.
                timing = new_timing if has_new else ""
            else:
                timing = new_timing if has_new else str(row.get("Timing", "")).strip()

            if not self._timing_matches(timing, next_month, next_year):
                continue

            expected_impact = str(row.get("Expected impact", ""))
            impacts_parsed = self._parse_expected_impact(expected_impact)

            for key, value in impacts_parsed.items():
                if key in impacts:
                    impacts[key]["value"] += value
                    if impacts[key]["initiatives"]:
                        impacts[key]["initiatives"] += f"; {initiative_name}"
                    else:
                        impacts[key]["initiatives"] = initiative_name

        return impacts

    def _timing_matches(self, timing: str, month: int, year: int) -> bool:
        """True if a timing string (e.g. 'Jul-26', 'Q3/2026', '7/2026') is month/year."""
        import re
        t = timing.lower()
        if not t or t == "nan":
            return False

        yy = str(year)[-2:]
        abbr = config.get_month_name(month)[:3].lower()  # 'jul'
        # Month-abbreviation form: "jul-26" / "jul 2026"
        if re.search(rf'{abbr}\b', t) and (yy in t or str(year) in t or not re.search(r'\d', t)):
            return True
        # Numeric form: "7/2026" / "7-26"
        if re.search(rf'\b{month}\b[/\- ]+(?:{year}|{yy})', t):
            return True
        # Quarter form: "q3/2026"
        q = (month - 1) // 3 + 1
        if re.search(rf'q{q}\b', t) and (str(year) in t or yy in t):
            return True
        return False

    def _parse_expected_impact(self, impact_str: str) -> dict:
        """Parse expected impact string to extract percentage impacts"""
        impacts = {}

        # Patterns like "+10pp", "+10%", "+5pp"
        import re

        # %Eligible/Total User Base
        match = re.search(r'%Eligible/Total User Base\s*([+-]?\d+(?:\.\d+)?)\s*(?:pp|%)', impact_str, re.IGNORECASE)
        if match:
            impacts["%Eligible/Total User Base"] = float(match.group(1))

        # %Traffic/Eligible
        match = re.search(r'%Traffic/Eligible\s*([+-]?\d+(?:\.\d+)?)\s*(?:pp|%)', impact_str, re.IGNORECASE)
        if match:
            impacts["%Traffic/Eligible"] = float(match.group(1))

        # %Submission/Traffic
        match = re.search(r'%Submission/Traffic\s*([+-]?\d+(?:\.\d+)?)\s*(?:pp|%)', impact_str, re.IGNORECASE)
        if match:
            impacts["%Submission/Traffic"] = float(match.group(1))

        # %Approval Rate
        match = re.search(r'%Approval Rate\s*([+-]?\d+(?:\.\d+)?)\s*(?:pp|%)', impact_str, re.IGNORECASE)
        if match:
            impacts["%Approval rate"] = float(match.group(1))

        # Average Ticket Size
        match = re.search(r'Average Ticket size\s*([+-]?\d+(?:\.\d+)?)\s*%', impact_str, re.IGNORECASE)
        if match:
            impacts["Average Ticket Size"] = float(match.group(1))

        return impacts

    def _calculate_forecast_chain(self, current: dict, pct_changes: dict, init_impacts: dict) -> dict:
        """Calculate forecast using chain logic"""
        forecast = {}

        # Get percentage values from current month
        pct_mom_growth = pct_changes.get("%mom growth user base", 5.0)  # default 5%
        pct_eligible = pct_changes.get("%Eligible/Total User Base", 0.35)
        pct_traffic = pct_changes.get("%Traffic/Eligible", 0.42)
        pct_submission = pct_changes.get("%Submission/Traffic", 0.14)
        pct_approval = pct_changes.get("%Approval rate", 0.65)
        pct_ticket_growth = pct_changes.get("%mom growth ticket size", 0.0)

        # Apply initiative impacts (if any)
        if init_impacts.get("%Eligible/Total User Base", {}).get("value", 0) != 0:
            pct_eligible += init_impacts["%Eligible/Total User Base"]["value"]
        if init_impacts.get("%Traffic/Eligible", {}).get("value", 0) != 0:
            pct_traffic += init_impacts["%Traffic/Eligible"]["value"]
        if init_impacts.get("%Submission/Traffic", {}).get("value", 0) != 0:
            pct_submission += init_impacts["%Submission/Traffic"]["value"]
        if init_impacts.get("%Approval rate", {}).get("value", 0) != 0:
            pct_approval += init_impacts["%Approval rate"]["value"]
        if init_impacts.get("Average Ticket Size", {}).get("value", 0) != 0:
            pct_ticket_growth += init_impacts["Average Ticket Size"]["value"]

        # Calculate forecasts using chain logic
        # ii. Total user base X+1 = Total user base X * (1 + %mom growth user base)
        total_user_base = current.get("Total User Base", 0) * (1 + pct_mom_growth / 100)
        forecast["Total User Base"] = {
            "current": current.get("Total User Base", 0),
            "baseline": total_user_base,
            "final": total_user_base,
            "avg_change": pct_mom_growth,
            "init_impact": 0,
            "init_notes": ""  # No direct init impact on user base
        }

        # iii. Eligible Base = %Eligible/Total User Base * Total User Base
        eligible_base = (pct_eligible / 100) * total_user_base
        forecast["Eligible Base For Cash Loan"] = {
            "current": current.get("Eligible Base For Cash Loan", 0),
            "baseline": eligible_base,
            "final": eligible_base,
            "avg_change": pct_eligible,
            "init_impact": init_impacts.get("%Eligible/Total User Base", {}).get("value", 0),
            "init_notes": init_impacts.get("%Eligible/Total User Base", {}).get("initiatives", "")
        }

        # iv. Traffic = %Traffic/Eligible * Eligible Base
        traffic = (pct_traffic / 100) * eligible_base
        forecast["Traffic to Landing Page"] = {
            "current": current.get("Traffic to Landing Page", 0),
            "baseline": traffic,
            "final": traffic,
            "avg_change": pct_traffic,
            "init_impact": init_impacts.get("%Traffic/Eligible", {}).get("value", 0),
            "init_notes": init_impacts.get("%Traffic/Eligible", {}).get("initiatives", "")
        }

        # v. Submission = %Submission/Traffic * Traffic
        submission = (pct_submission / 100) * traffic
        forecast["Submission"] = {
            "current": current.get("Submission", 0),
            "baseline": submission,
            "final": submission,
            "avg_change": pct_submission,
            "init_impact": init_impacts.get("%Submission/Traffic", {}).get("value", 0),
            "init_notes": init_impacts.get("%Submission/Traffic", {}).get("initiatives", "")
        }

        # vi. Approved = %Approval rate * Submission
        approved = (pct_approval / 100) * submission
        forecast["Approved"] = {
            "current": current.get("Approved", 0),
            "baseline": approved,
            "final": approved,
            "avg_change": pct_approval,
            "init_impact": init_impacts.get("%Approval rate", {}).get("value", 0),
            "init_notes": init_impacts.get("%Approval rate", {}).get("initiatives", "")
        }

        # vii. Average Ticket Size X+1 = Average Ticket Size X * (1 + %mom growth ticket size)
        avg_ticket = current.get("Average Ticket Size", 0) * (1 + pct_ticket_growth / 100)
        forecast["Average Ticket Size"] = {
            "current": current.get("Average Ticket Size", 0),
            "baseline": avg_ticket,
            "final": avg_ticket,
            "avg_change": pct_ticket_growth,
            "init_impact": init_impacts.get("Average Ticket Size", {}).get("value", 0),
            "init_notes": init_impacts.get("Average Ticket Size", {}).get("initiatives", "")
        }

        # Disbursement Volume = Approved * Average Ticket Size, scaled to match the
        # unit relationship observed in the current month's actuals (Approved and
        # Disbursement are stored in different units, so a raw product is off by
        # a constant factor).
        cur_approved = current.get("Approved", 0)
        cur_ticket = current.get("Average Ticket Size", 0)
        cur_disb = current.get("Disbursement Volume", 0)
        denom = cur_approved * cur_ticket
        scale = (cur_disb / denom) if denom else 1
        disbursement = approved * avg_ticket * scale
        forecast["Disbursement Volume"] = {
            "current": current.get("Disbursement Volume", 0),
            "baseline": disbursement,
            "final": disbursement,
            "avg_change": 0,
            "init_impact": 0,
            "init_notes": ""
        }

        return forecast

    def _build_display_df(self, forecast_df: pd.DataFrame) -> pd.DataFrame:
        """Build the clean, Metrics-formatted forecast frame (No, Unit, % signs,
        whole numbers). Forecast stores % metrics already scaled (e.g. 35.0)."""
        from .metrics_format import meta_for, fmt_value

        actual_col = next((c for c in forecast_df.columns if "(actual)" in str(c).lower()), None)
        fcast_col = next((c for c in forecast_df.columns if "(forecast)" in str(c).lower()), None)
        notes_col = next((c for c in forecast_df.columns if "note" in str(c).lower()), None)

        rows = []
        for i, (_, r) in enumerate(forecast_df.iterrows()):
            meta = meta_for(r.get("Metric", ""), i)
            unit = meta["unit"]
            row = {"No": meta["no"], "Metric": r.get("Metric", ""), "Unit": unit}
            if actual_col:
                row[actual_col] = fmt_value(r.get(actual_col), unit, pct_is_ratio=True)
            if fcast_col:
                row[fcast_col] = fmt_value(r.get(fcast_col), unit, pct_is_ratio=True)
            note = r.get(notes_col) if notes_col else None
            row["Initiative notes"] = "" if note is None or pd.isna(note) else str(note)
            rows.append(row)
        return pd.DataFrame(rows)

    def _save_forecast(self, forecast_df: pd.DataFrame, month: int, year: int):
        """Save forecast to Excel file (Metrics-formatted)."""
        forecast_file = config.DATA_DIR / "Forecast.xlsx"
        sheet_name = f"Forecast {config.get_month_name(month)} {year}"
        df_to_save = self._build_display_df(forecast_df)

        try:
            from .excel_io import save_sheet
            out = save_sheet(df_to_save, forecast_file, sheet_name)
            if out != forecast_file:
                self.log(f"{forecast_file.name} đang mở/khoá; ghi {out.name}", "warn")
        except Exception as e:
            self.log(f"Could not save forecast: {e}", "warn")


from datetime import datetime