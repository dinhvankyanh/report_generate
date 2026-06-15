"""
Steps package - All 7 steps for report generation
"""
from .base import BaseStep, StepResult
from .step1_email_or_manual import Step1GetInitiativesData
from .step2_status_change import Step2StatusChange
from .step3_performance_analysis import Step3PerformanceAnalysis
from .step4_forecast import Step4Forecast
from .step5_top_3_priorities import Step5TopPriorities
from .step6_annual_progress import Step6AnnualProgress
from .step7_generate_report import Step7GenerateReport


def get_all_steps(data_source):
    """Get all 7 steps in order"""
    return [
        Step1GetInitiativesData(data_source),
        Step2StatusChange(data_source),
        Step3PerformanceAnalysis(data_source),
        Step4Forecast(data_source),
        Step5TopPriorities(data_source),
        Step6AnnualProgress(data_source),
        Step7GenerateReport(data_source),
    ]


__all__ = [
    "BaseStep",
    "StepResult",
    "Step1GetInitiativesData",
    "Step2StatusChange",
    "Step3PerformanceAnalysis",
    "Step4Forecast",
    "Step5TopPriorities",
    "Step6AnnualProgress",
    "Step7GenerateReport",
    "get_all_steps"
]