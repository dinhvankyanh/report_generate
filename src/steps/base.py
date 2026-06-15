"""
Base Step class for Report Generate Agent
All steps inherit from this base class
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import pandas as pd
from datetime import datetime


class BaseStep(ABC):
    """
    Abstract base class for each step in the report generation process
    """

    def __init__(self, data_source):
        self.data_source = data_source
        self.results = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Step name"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Step description"""
        pass

    @abstractmethod
    def execute(self, month: int, year: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the step

        Args:
            month: Target month (1-12)
            year: Target year
            context: Shared context from previous steps

        Returns:
            Dict containing step results
        """
        pass

    def validate_input(self, month: int, year: int) -> bool:
        """Validate month and year input"""
        if not self.data_source.validate_month_year(month, year):
            print(f"[ERROR] Invalid month/year: {month}/{year}")
            return False
        return True

    def log(self, message: str, level: str = "info"):
        """Log with step name prefix"""
        prefix = f"[{self.name}]"
        if level == "info":
            print(f"  {prefix} {message}")
        elif level == "warn":
            print(f"  [WARNING] {prefix} {message}")
        elif level == "error":
            print(f"  [ERROR] {prefix} {message}")
        elif level == "success":
            print(f"  [OK] {prefix} {message}")


class StepResult:
    """Container for step results"""

    def __init__(self, success: bool, data: Any = None, message: str = "", error: str = None):
        self.success = success
        self.data = data
        self.message = message
        self.error = error

    def __repr__(self):
        status = "[OK]" if self.success else "[ERROR]"
        return f"{status} StepResult: {self.message}"