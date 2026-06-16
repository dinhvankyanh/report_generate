"""
Step 2: Update "Status change"

Compare each initiative's Status in month X against month X-1:
- changed   -> "Yes"
- unchanged -> "No"
- not present in X-1 -> "Yes" (new this month)

Constraint: if Status change == "No", there cannot be a New timing, so it is
cleared. If "Yes", New timing may or may not exist (left as filled by Step 1).
"""
from typing import Dict, Any

import pandas as pd

from .base import BaseStep, StepResult
from .. import config

COL_NAME = "Initiative Names"
COL_STATUS = "Status"
COL_STATUS_CHANGE = "Status change"
COL_NEW_TIMING = "New timing (if applicable)"
SECTION_NAMES = ("strategic unlock", "incremental improvements")


def _norm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


class Step2StatusChange(BaseStep):
    """Step 2: Fill the Status change column (Yes/No)."""

    @property
    def name(self) -> str:
        return "Step 2: Update Status Change"

    @property
    def description(self) -> str:
        return "Compare with month X-1 and set Status change (Yes/No)"

    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"Starting for {config.get_month_name(month)} {year}")

        current = context.get("initiatives_data")
        previous = context.get("previous_initiatives_data")

        if current is None or current.empty:
            return StepResult(success=False, error="No initiatives data in context").__dict__

        # Build a name -> previous status lookup
        prev_status = {}
        if previous is not None and not previous.empty:
            for _, r in previous.iterrows():
                name = _norm(r.get(COL_NAME))
                if name and name.lower() not in SECTION_NAMES:
                    prev_status[name] = _norm(r.get(COL_STATUS))

        if COL_STATUS_CHANGE not in current.columns:
            current[COL_STATUS_CHANGE] = None

        changed = 0
        for idx, row in current.iterrows():
            name = _norm(row.get(COL_NAME))
            if not name or name.lower() in SECTION_NAMES:
                current.at[idx, COL_STATUS_CHANGE] = None
                continue

            cur_status = _norm(row.get(COL_STATUS))
            if name not in prev_status:
                change = "Yes"  # new initiative this month
            else:
                change = "Yes" if cur_status != prev_status[name] else "No"

            current.at[idx, COL_STATUS_CHANGE] = change

            # Note: an operative New timing is kept even when change == "No"
            # (e.g. a still-pending Deprioritized item keeps its revised target).
            if change == "Yes":
                changed += 1

        context["initiatives_data"] = current

        # Persist Status change back into the tracker file
        raw = context.get("tracker_raw")
        header_idx = context.get("tracker_header_idx")
        if raw is not None and header_idx is not None:
            try:
                from .tracker_writer import write_tracker
                out_path = write_tracker(raw, header_idx, current, month, year,
                                         template_path=context.get("tracker_template_path"))
                self.log(f"Updated tracker with Status change: {out_path.name}")
            except Exception as e:
                self.log(f"Could not re-write tracker: {e}", "warn")

        self.log(f"{changed} initiative(s) with status change = Yes", "success")

        return StepResult(
            success=True,
            data={"changed_count": changed},
            message=f"Status change computed ({changed} changed)"
        ).__dict__
