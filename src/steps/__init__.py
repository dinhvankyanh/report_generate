"""
Steps package — the report-generation pipeline (6 build steps + 1 consistency check).
"""
from .base import BaseStep, StepResult
from .step1_email_or_manual import Step1GetInitiativesData
from .step2_status_change import Step2StatusChange
from .step3_performance_analysis import Step3PerformanceAnalysis
from .step4_forecast import Step4Forecast
from .step5_top_3_priorities import Step5TopPriorities
from .step6_generate_report import Step6GenerateReport
from .step7_consistency_check import Step7ConsistencyCheck


def get_all_steps(data_source):
    """Get all steps in order (6 build steps + 1 advisory consistency check)."""
    return [
        Step1GetInitiativesData(data_source),
        Step2StatusChange(data_source),
        Step3PerformanceAnalysis(data_source),
        Step4Forecast(data_source),
        Step5TopPriorities(data_source),
        Step6GenerateReport(data_source),
        Step7ConsistencyCheck(data_source),
    ]


__all__ = [
    "BaseStep",
    "StepResult",
    "Step1GetInitiativesData",
    "Step2StatusChange",
    "Step3PerformanceAnalysis",
    "Step4Forecast",
    "Step5TopPriorities",
    "Step6GenerateReport",
    "Step7ConsistencyCheck",
    "get_all_steps",
]
