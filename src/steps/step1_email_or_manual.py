"""
Step 1: Build the Initiatives Tracker for month X

Design (agreed):
- The row skeleton (No, Initiative Names, Timing, Expected impact, and the
  section rows "Strategic unlock" / "Incremental improvements") is cloned from
  the month X-1 tracker. We never invent rows from email content.
- The month-specific columns (PIC, Status, New timing, Details from that month,
  How confident) are filled by an LLM that reads the email threads (6-month
  lookback) and returns structured updates keyed by initiative No. Rows with no
  email evidence carry their status forward and have their month-specific notes
  cleared.
- The output file preserves the exact template of month X-1 (title row, hint
  row, header row, sections).
- "Status change" is left for Step 2.
"""
import json
from typing import Dict, Any, List

import pandas as pd

from .base import BaseStep, StepResult
from .. import config
from ..llm import extract_initiative_updates, llm_available


# Canonical tracker columns (must match the month X-1 header)
COL_NO = "No"
COL_NAME = "Initiative Names"
COL_TIMING = "Timing"
COL_IMPACT = "Expected impact"
COL_PIC = "PIC"
COL_STATUS = "Status"
COL_STATUS_CHANGE = "Status change"
COL_NEW_TIMING = "New timing (if applicable)"
COL_DETAILS = "Details from that month"
COL_CONFIDENCE = "How confident"

SECTION_NAMES = ("strategic unlock", "incremental improvements")


def _as_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _clean_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


class Step1GetInitiativesData(BaseStep):
    """Step 1: Build month X tracker from month X-1 skeleton + LLM email updates."""

    @property
    def name(self) -> str:
        return "Step 1: Build Initiatives Tracker"

    @property
    def description(self) -> str:
        return "Clone month X-1 skeleton and fill status columns from email via LLM"

    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log(f"Starting for {config.get_month_name(month)} {year}")

        from ..data_sources import create_manual_source
        manual = create_manual_source()

        prev_month, prev_year = self.data_source.get_previous_month(month, year)

        # 1. Load the month X-1 skeleton: the most recent tracker at/before X-1
        #    (so a missing exact month falls back to the latest earlier file)
        raw, header_idx, _sheet = manual.get_initiatives_raw(prev_month, prev_year)
        prev_df = manual.get_initiatives_data(prev_month, prev_year)

        if raw is None or header_idx is None or prev_df is None or prev_df.empty:
            return StepResult(
                success=False,
                error=(f"Không tìm thấy/đọc được file Initiatives tracker tháng "
                       f"{prev_month}-{prev_year} (tháng X-1) trong folder "
                       f"'{config.INITIATIVES_TRACKER_DIR}'. Hãy đảm bảo folder dữ liệu "
                       f"có thư mục con 'Initiatives tracker' chứa file tháng {prev_month}-{prev_year}.")
            ).__dict__

        prev_df.columns = [str(c).strip() for c in prev_df.columns]
        self.log(f"Skeleton from {prev_month}/{prev_year}: {len(prev_df)} rows")

        # Keep an untouched copy of month X-1 for Step 2 comparison
        context["previous_initiatives_data"] = prev_df.copy()

        # 2. Start month X frame from the skeleton. Everything carries forward by
        #    default (Status, New timing, Details, How confident, PIC); the LLM
        #    overrides where it has evidence. Only Status change is recomputed.
        current = prev_df.copy()
        if COL_STATUS_CHANGE in current.columns:
            current[COL_STATUS_CHANGE] = None

        # 3. Build initiative list (with previous status) for the LLM
        initiatives = self._build_initiative_list(current)

        # 4. Harvest raw emails (6-month lookback) and extract updates via LLM
        emails = self._get_raw_emails(month, year)
        updates = []
        if not llm_available():
            self.log("LLM not configured (set LLM_API_KEY and LLM_MODEL). "
                     "Carrying statuses forward without email enrichment.", "warn")
        elif not emails:
            self.log("No emails found; carrying statuses forward.", "warn")
        else:
            report_label = f"{config.get_month_name(month)} {year}"
            updates = extract_initiative_updates(initiatives, emails, report_label)
        self.log(f"LLM returned {len(updates)} update(s)")

        # 5. Apply updates by initiative No
        updates_by_no = {u["no"]: u for u in updates if u.get("no") is not None}
        matched = 0
        for idx, row in current.iterrows():
            no = _as_int(row.get(COL_NO))
            name = _clean_str(row.get(COL_NAME))
            if no is None or not name or name.lower() in SECTION_NAMES:
                continue
            u = updates_by_no.get(no)
            if not u:
                continue
            matched += 1
            if u.get("status"):
                current.at[idx, COL_STATUS] = u["status"]
            if u.get("pic"):
                current.at[idx, COL_PIC] = u["pic"]
            if u.get("confidence"):
                current.at[idx, COL_CONFIDENCE] = u["confidence"]
            if u.get("details"):
                current.at[idx, COL_DETAILS] = u["details"]
            if u.get("new_timing"):
                current.at[idx, COL_NEW_TIMING] = u["new_timing"]

        self.log(f"Applied email updates to {matched} initiative(s)", "success")

        # Collect metric claims from email (Rule 3: reconcile vs actuals later)
        name_by_no = {_as_int(r.get(COL_NO)): _clean_str(r.get(COL_NAME))
                      for _, r in current.iterrows() if _as_int(r.get(COL_NO)) is not None}
        claims = []
        for u in updates:
            for c in (u.get("metric_claims") or []):
                claims.append({
                    "no": u.get("no"),
                    "initiative": name_by_no.get(u.get("no"), ""),
                    "owner": u.get("pic", ""),
                    "metric": c.get("metric", ""),
                    "level": c.get("level", ""),
                })
        context["email_metric_claims"] = claims
        if claims:
            self.log(f"Captured {len(claims)} email metric claim(s) for reconciliation")

        # 6. Save to context (sections kept; Step 6 needs them)
        context["initiatives_data"] = current
        context["tracker_raw"] = raw
        context["tracker_header_idx"] = header_idx

        # 7. Write the month X tracker preserving the template
        try:
            from .tracker_writer import write_tracker
            out_path = write_tracker(raw, header_idx, current, month, year)
            self.log(f"Saved tracker: {out_path.name}", "success")
        except Exception as e:
            self.log(f"Could not write tracker file: {e}", "warn")

        n_initiatives = len(initiatives)
        return StepResult(
            success=True,
            data={"initiatives_count": n_initiatives, "email_matched": matched},
            message=f"Built tracker for {config.get_month_name(month)} {year}"
        ).__dict__

    # ------------------------------------------------------------------ #
    def _build_initiative_list(self, current: pd.DataFrame) -> List[dict]:
        """Extract the non-section initiatives as dicts for the LLM prompt."""
        items = []
        for _, row in current.iterrows():
            no = _as_int(row.get(COL_NO))
            name = _clean_str(row.get(COL_NAME))
            if no is None or not name or name.lower() in SECTION_NAMES:
                continue
            items.append({
                "no": no,
                "name": name,
                "timing": _clean_str(row.get(COL_TIMING)),
                "expected_impact": _clean_str(row.get(COL_IMPACT)),
                "prev_status": _clean_str(row.get(COL_STATUS)),
                "prev_new_timing": _clean_str(row.get(COL_NEW_TIMING)),
                "prev_details": _clean_str(row.get(COL_DETAILS)),
            })
        return items

    def _get_raw_emails(self, month: int, year: int) -> List[dict]:
        """
        Get raw emails. If live Gmail returns data, use it AND refresh
        sample_emails.json (anonymized) so the offline/manual run mirrors live.
        Otherwise fall back to sample_emails.json.
        """
        emails = []
        try:
            emails = self.data_source.get_raw_emails(month, year) or []
        except Exception as e:
            self.log(f"Email fetch failed: {e}", "warn")

        if emails:
            self.log("=" * 56)
            self.log(f">>> DATA SOURCE: LIVE GMAIL ({len(emails)} emails)")
            self.log("=" * 56)
            self._refresh_sample_file(emails)
        else:
            emails = self._load_sample_emails()
            self.log("=" * 56)
            self.log(f">>> DATA SOURCE: sample_emails.json ({len(emails)} emails)")
            self.log("=" * 56)
        return emails

    def _refresh_sample_file(self, live_emails: List[dict]):
        """Persist live emails (anonymized + filtered) to sample_emails.json so a
        later manual/offline run reproduces the same updated data."""
        try:
            from ..llm.extractor import anonymize_and_filter
            cleaned = anonymize_and_filter(live_emails)
            if not cleaned:
                return
            config.SAMPLE_EMAILS_FILE.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
            self.log(f"Refreshed sample_emails.json ({len(cleaned)} anonymized emails) "
                     f"for offline/BTC parity")
        except Exception as e:
            self.log(f"Could not refresh sample_emails.json: {e}", "warn")

    def _load_sample_emails(self) -> List[dict]:
        """Fallback raw-email source for local testing without Gmail."""
        sample = config.SAMPLE_EMAILS_FILE
        if not sample.exists():
            return []
        try:
            data = json.loads(sample.read_text(encoding="utf-8"))
        except Exception:
            return []
        emails = []
        for i, em in enumerate(data):
            emails.append({
                "id": em.get("id", f"sample-{i}"),
                "subject": em.get("subject", ""),
                "sender": em.get("sender", em.get("from", "")),
                "date": em.get("date", ""),
                "body": em.get("body", ""),
            })
        return emails
