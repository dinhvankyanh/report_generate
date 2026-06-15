"""
Data Sources Factory
Creates the appropriate data source based on configuration
"""
from .base import BaseDataSource
from .email_source import EmailDataSource, create_email_source
from .manual_source import ManualDataSource, create_manual_source
from .. import config


def create_data_source() -> BaseDataSource:
    """
    Factory function to create the appropriate data source

    Returns:
        BaseDataSource: Either EmailDataSource or ManualDataSource based on config
    """
    mode = config.DATA_SOURCE_MODE.lower()

    if mode == "email":
        print("[Phase 2] Using Email Data Source")
        try:
            return create_email_source()
        except Exception as e:
            print(f"[Warning] Email source failed: {e}")
            print("[Fallback] Using Manual Data Source")
            return create_manual_source()
    else:
        print("[Phase 1] Using Manual Data Source (Excel)")
        return create_manual_source()


# Export all classes
__all__ = [
    "BaseDataSource",
    "EmailDataSource",
    "ManualDataSource",
    "create_data_source",
    "create_email_source",
    "create_manual_source"
]