"""
Step 5: Top 3 Priorities
Identify top 3 priorities for next month based on impact and timeline
"""
from typing import Dict, Any
import pandas as pd
from .base import BaseStep, StepResult
from .. import config


class Step5TopPriorities(BaseStep):
    """
    Step 5: Identify Top 3 Priorities

    Logic:
    1. Sort by impact uplift (high to low)
    2. Then filter by timeline (near to far)
    3. Take top 3
    """

    @property
    def name(self) -> str:
        return "Step 5: Top 3 Priorities"

    @property
    def description(self) -> str:
        return "Identify top 3 priorities for next month"

    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute step 5"""
        next_month, next_year = self.data_source.get_next_month(month, year)
        self.log(f"Finding top 3 priorities for {config.get_month_name(next_month)} {next_year}")

        # Get initiatives data
        initiatives_df = context.get("initiatives_data")

        if initiatives_df is None or initiatives_df.empty:
            return StepResult(
                success=False,
                error="No initiatives data available"
            ).__dict__

        # Parse impact scores. A "priority for next month" must still be
        # actionable, so skip section rows and already-finished / dropped items.
        excluded_status = {"live", "done", "deprioritized"}
        section_names = {"strategic unlock", "incremental improvements"}
        initiatives_with_impact = []

        for _, row in initiatives_df.iterrows():
            name = str(row.get("Initiative Names", "")).strip()
            status = str(row.get("Status", "")).strip()
            if not name or name.lower() in section_names:
                continue
            if status.lower() in excluded_status:
                continue

            impact = self._parse_impact_score(row.get("Expected impact", ""))
            # Effective timing = the agreed New timing if set, else the planned
            # Timing — so a slipped item shows its operative date (e.g. Sep-26),
            # consistent with the Escalations passage.
            new_timing = str(row.get("New timing (if applicable)", "") or "").strip()
            if new_timing.lower() in ("", "nan"):
                new_timing = ""
            planned_timing = str(row.get("Timing", "") or "").strip()
            initiatives_with_impact.append({
                "name": name,
                "timing": new_timing or planned_timing,
                "status": status,
                "impact": impact,
                "pic": row.get("PIC", ""),
                "expected_impact": row.get("Expected impact", "")
            })

        # Convert to DataFrame for easier sorting
        df = pd.DataFrame(initiatives_with_impact)

        # Top priorities = high impact first, then nearer timeline.
        # (Delayed / deprioritized high-impact items are surfaced separately in
        # the report's Escalations passage, not here.)
        df = df.sort_values(by=["impact", "timing"], ascending=[False, True])

        # Take top 3
        top_3 = df.head(3)

        # Save to context for the report (§3 Top Priorities). No markdown file is
        # exported — the report's Top Priorities table consumes this data directly.
        context["top_3_priorities"] = top_3

        self.log(f"Identified top 3 priorities for {config.get_month_name(next_month)}", "success")

        return StepResult(
            success=True,
            data={"priorities": top_3.to_dict("records")},
            message=f"Top 3 priorities identified for {config.get_month_name(next_month)}"
        ).__dict__

    def _parse_impact_score(self, impact_str: str) -> float:
        """Parse impact score from impact string"""
        import re

        if pd.isna(impact_str):
            return 0

        # Look for +XXpp or +XX%
        matches = re.findall(r'\+(\d+)\s*(?:pp|%)', str(impact_str))
        if matches:
            return max([float(m) for m in matches])

        return 0