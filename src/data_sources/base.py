"""
Base data source interface for Report Generate Agent
This allows flexible switching between email and manual input modes
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any
import pandas as pd
from datetime import datetime

class BaseDataSource(ABC):
    """
    Abstract base class for data sources.
    Implement this to add new data source types.
    """

    def log(self, message: str, level: str = "info"):
        """Print log message"""
        prefix = {
            "info": "[INFO]",
            "warn": "[WARNING]",
            "error": "[ERROR]"
        }.get(level, "[INFO]")
        print(f"{prefix} {message}")

    @abstractmethod
    def get_initiatives_data(self, month: int, year: int) -> pd.DataFrame:
        """
        Get initiatives data for a specific month/year

        Returns DataFrame with columns:
        - No
        - Initiative Names
        - Timing
        - Expected impact
        - PIC
        - Status
        - Status change
        - New timing (if applicable)
        - Details from that month
        - How confident
        - Actual impact (if lived)
        """
        pass

    @abstractmethod
    def get_performance_data(self) -> pd.DataFrame:
        """Get actual performance data"""
        pass

    @abstractmethod
    def get_kpi_data(self) -> pd.DataFrame:
        """Get KPI data"""
        pass

    def get_raw_emails(self, month: int, year: int, lookback_months: int = 6) -> list:
        """
        Return a list of raw emails ({id, subject, sender, date, body}) over the
        last `lookback_months` months. Default [] (no email access); overridden
        in EmailDataSource.
        """
        return []

    def get_email_updates(self, month: int, year: int, lookback_months: int = 6) -> list:
        """
        Return regex-parsed initiative updates (legacy). Default []; overridden
        in EmailDataSource. Step 1 prefers the LLM extractor.
        """
        return []

    def validate_month_year(self, month: int, year: int) -> bool:
        """Validate if month/year is valid"""
        if not (1 <= month <= 12):
            return False
        if year < 2020 or year > 2100:
            return False
        return True

    def get_previous_month(self, month: int, year: int) -> tuple:
        """Get previous month and year"""
        if month == 1:
            return 12, year - 1
        return month - 1, year

    def get_next_month(self, month: int, year: int) -> tuple:
        """Get next month and year"""
        if month == 12:
            return 1, year + 1
        return month + 1, year