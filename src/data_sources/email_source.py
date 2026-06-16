"""
Email Data Source (Phase 2)
Uses Gmail API (OAuth2) to fetch raw emails about initiatives. Parsing into
structured updates is done by the LLM extractor (src/llm/extractor.py); this
source only fetches raw emails and delegates the Excel reads to the manual source.
"""
import pandas as pd
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