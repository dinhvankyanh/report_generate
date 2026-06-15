"""
Email Data Source (Phase 2)
Uses Gmail API (OAuth2) to fetch emails about initiatives
"""
import re
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime
from .base import BaseDataSource
from .manual_source import create_manual_source
from .gmail_service import create_gmail_service
from .. import config


class EmailDataSource(BaseDataSource):
    """
    Fetches initiatives data from email using Gmail API.
    This is the Phase 2 implementation.
    """

    def __init__(self):
        self.email_config = config.EMAIL_CONFIG
        self.gmail_service = None

    def connect(self):
        """Connect to Gmail using OAuth2"""
        # Check if credentials.json exists (that's enough to try OAuth)
        credentials_file = config.CREDENTIALS_FILE
        if not credentials_file.exists():
            self.log("[WARNING] credentials.json not found!")
            self.log("   Please download from Google Cloud Console and place in project root.")
            return False

        # Try to authenticate
        try:
            self.gmail_service = create_gmail_service()
            if self.gmail_service.authenticate():
                self.log("[OK] Connected to Gmail")
                return True
            else:
                self.log("[WARNING] Could not authenticate with Gmail")
                return False
        except Exception as e:
            self.log(f"[WARNING] Gmail connection failed: {e}")
            return False

    def fetch_emails_for_month(self, month: int, year: int) -> List[Dict]:
        """
        Fetch relevant emails for the given month/year using Gmail API
        Look for emails with initiative updates, status changes, etc.
        """
        if not self.gmail_service:
            if not self.connect():
                return []

        # Build search query for Gmail
        # Filter by date range for the month
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year+1}-01-01"
        else:
            end_date = f"{year}-{month+1:02d}-01"

        # Search queries for initiative-related emails
        search_queries = [
            f"subject:initiative after:{start_date} before:{end_date}",
            f"subject:update after:{start_date} before:{end_date}",
            f"subject:status after:{start_date} before:{end_date}",
        ]

        emails = []
        for query in search_queries:
            try:
                results = self.gmail_service.search_emails(query, max_results=20)
                emails.extend(results)
            except Exception as e:
                self.log(f"[WARNING] Error searching emails: {e}")

        # Remove duplicates
        seen = set()
        unique_emails = []
        for email in emails:
            if email['id'] not in seen:
                seen.add(email['id'])
                unique_emails.append(email)

        self.log(f"Found {len(unique_emails)} emails for {month}/{year}")
        return unique_emails

    def parse_email_content(self, email_body: str, email_subject: str = "") -> Dict:
        """
        Parse email to extract initiative information
        Look for patterns in both subject and body
        """
        data = {
            "Initiative Names": "",
            "PIC": "",
            "Status": "",
            "Status change": "",
            "New timing": "",
            "Details from that month": "",
            "How confident": "",
            "Actual impact": ""
        }

        # Combine subject and body for parsing
        full_text = email_subject + "\n" + email_body

        # Extract initiative name from subject
        # Pattern: "Initiative name — details" or "Initiative name - details"
        name_match = re.search(r'Initiative\s+([^—\-]+)', full_text, re.IGNORECASE)
        if name_match:
            data["Initiative Names"] = name_match.group(1).strip()
        else:
            # Try to get from subject line
            subj_match = re.search(r'\[Product\]\s*(.+?)(?:\s*[-—]\s*)', full_text)
            if subj_match:
                data["Initiative Names"] = subj_match.group(1).strip()

        # Look for Status: Not started, On Track, Delay, Deprioritized, Done
        status_match = re.search(r'(Not started|On Track|Delay|Deprioritized|Done)', full_text, re.IGNORECASE)
        if status_match:
            data["Status"] = status_match.group(1)

        # Look for PIC (Persona 1, Persona 2, etc.)
        pic_match = re.search(r'(Persona\s*\d+)', full_text, re.IGNORECASE)
        if not pic_match:
            pic_match = re.search(r'PIC[:\s]+([^\n,]+)', full_text, re.IGNORECASE)
        if pic_match:
            data["PIC"] = pic_match.group(1).strip()

        # Look for Expected impact (+Xpp, +X%)
        impact_match = re.search(r'(\+\d+pp?|\+\d+%)', full_text, re.IGNORECASE)
        if impact_match:
            data["Expected impact"] = impact_match.group(1)

        # Look for Timing (Jul, Aug, Q3, etc.)
        timing_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Q[1-4])[\s-]*(\d{2,4})?', full_text, re.IGNORECASE)
        if timing_match:
            month = timing_match.group(1)
            year = timing_match.group(2) if timing_match.group(2) else "26"
            data["Timing"] = f"{month}-{year}"

        # Look for confidence level
        conf_match = re.search(r'(High|Medium|Low)\s*confidence', full_text, re.IGNORECASE)
        if conf_match:
            data["How confident"] = conf_match.group(1)

        # If no status found but email is about initiative, mark as update
        if not data["Status"] and data["Initiative Names"]:
            data["Status"] = "update"

        return data

    def get_initiatives_data(self, month: int, year: int) -> pd.DataFrame:
        """
        Get initiatives data from email for specific month/year
        Uses Gmail API to fetch emails
        """
        # Try to connect to Gmail if not already connected
        if not self.gmail_service:
            if not self.connect():
                print("[WARNING] Could not connect to Gmail. Falling back to manual mode.")
                return None

        emails = self.fetch_emails_for_month(month, year)

        if not emails:
            print("[WARNING] No emails found. Falling back to manual mode.")
            return None

        # Parse emails and create DataFrame
        initiatives = []
        for email_data in emails:
            parsed = self.parse_email_content(
                email_data.get("body", ""),
                email_data.get("subject", "")
            )
            parsed["Timing"] = email_data.get("date")
            initiatives.append(parsed)

        if initiatives:
            return pd.DataFrame(initiatives)

        return None

    def get_raw_emails(self, month: int, year: int, lookback_months: int = 6) -> list:
        """
        Fetch raw emails over the last `lookback_months` months ending at
        month/year. Returns a list of {id, subject, sender, date, body}.
        """
        if not self.gmail_service:
            if not self.connect():
                self.log("Could not connect to Gmail", "warn")
                return []

        # Date window: lookback_months back from the start of `month`
        start_year, start_month = year, month - (lookback_months - 1)
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        start_date = f"{start_year}-{start_month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        # A single date-bounded query; threads are grouped/filtered downstream
        query = f"after:{start_date} before:{end_date}"
        emails, seen = [], set()
        try:
            for em in self.gmail_service.search_emails(query, max_results=100):
                if em["id"] not in seen:
                    seen.add(em["id"])
                    emails.append(em)
        except Exception as e:
            self.log(f"Error searching emails: {e}", "warn")

        self.log(f"Fetched {len(emails)} emails ({start_date} -> {end_date})")
        return emails

    def get_email_updates(self, month: int, year: int, lookback_months: int = 6) -> list:
        """
        Regex-based parse of emails into update dicts (legacy / fallback).
        Step 1 prefers the LLM extractor over this.
        """
        emails = self.get_raw_emails(month, year, lookback_months)
        updates = [self._parse_email_update(em) for em in emails]
        return [u for u in updates if u.get("keywords")]

    def _parse_email_update(self, email: dict) -> dict:
        """Parse one email into an initiative-update dict (best-effort)."""
        subject = email.get("subject", "") or ""
        body = email.get("body", "") or ""
        full = f"{subject}\n{body}"

        # Keywords: the phrase after "Initiative" in the subject is the strongest
        # signal for which initiative this email is about.
        keywords = ""
        m = re.search(r'initiative\s+([^—\-\n]+)', subject, re.IGNORECASE)
        if m:
            keywords = m.group(1).strip()
        if not keywords:
            m = re.search(r'\]\s*([^—\-\n]+)', subject)  # after "[Product]"
            if m:
                keywords = m.group(1).strip()

        update = {
            "keywords": keywords,
            "status": "",
            "new_timing": "",
            "details": "",
            "confidence": "",
            "pic": "",
            "date": email.get("date", ""),
        }

        status_m = re.search(
            r'\b(Not started|On[ -]?Track|Delayed|Delay|Deprioritized|Done|Live)\b',
            full, re.IGNORECASE)
        if status_m:
            update["status"] = self._normalize_status(status_m.group(1))

        # New timing: an explicit month mention (Jul / Jul-26 / tháng 7)
        timing_m = re.search(
            r'(?:launch|target|timeline|new timing|tháng)\D{0,12}'
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{1,2})[\s\-]*?(\d{2,4})?',
            full, re.IGNORECASE)
        if timing_m:
            mon, yr = timing_m.group(1), timing_m.group(2)
            update["new_timing"] = f"{mon}-{yr}" if yr else mon

        conf_m = re.search(r'(High|Medium|Low)\s*confidence', full, re.IGNORECASE)
        if conf_m:
            update["confidence"] = conf_m.group(1).capitalize()

        pic_m = re.search(r'(Persona\s*\d+)', full, re.IGNORECASE)
        if pic_m:
            update["pic"] = pic_m.group(1)

        # Details: first non-empty, non-quoted line of the body as a summary
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith(">") and not line.lower().startswith("dear"):
                update["details"] = line[:200]
                break

        return update

    @staticmethod
    def _normalize_status(raw: str) -> str:
        """Map free-text status to the canonical tracker vocabulary."""
        s = raw.strip().lower()
        mapping = {
            "not started": "Not started",
            "on track": "On Track",
            "on-track": "On Track",
            "delay": "Delay",
            "delayed": "Delay",
            "deprioritized": "Deprioritized",
            "done": "Done",
            "live": "Live",
        }
        return mapping.get(s, raw.strip())

    def get_performance_data(self) -> pd.DataFrame:
        """Get actual performance from Excel file - delegate to manual source"""
        # Delegate to manual source for Excel reading
        manual = create_manual_source()
        return manual.get_performance_data()

    def get_kpi_data(self) -> pd.DataFrame:
        """Get KPI from Excel file - delegate to manual source"""
        manual = create_manual_source()
        return manual.get_kpi_data()

    def get_annual_planning_data(self) -> pd.DataFrame:
        """Get annual planning data - delegate to manual source"""
        manual = create_manual_source()
        return manual.get_annual_planning_data()


def create_email_source() -> EmailDataSource:
    """Factory function to create email data source"""
    return EmailDataSource()