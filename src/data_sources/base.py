"""
Base data source interface for Report Generate Agent
This allows flexible switching between email and manual input modes
"""
from abc import ABC, abstractmethod
import pandas as pd


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

    def get_initiatives_data(self, month: int, year: int) -> pd.DataFrame:
        """
        Read the month's Initiatives tracker as a DataFrame. Implemented by the
        manual source (which reads the Excel skeleton); the email source inherits
        this default since Step 1 always reads the X-1 skeleton via the manual source.
        """
        return None

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