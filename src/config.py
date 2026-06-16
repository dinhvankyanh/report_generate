"""
Configuration for Report Generate Agent
"""
import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Load .env if present (e.g. LLM_API_KEY saved by GreenNode aip.sh)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

# Data directory — where the Excel inputs live and outputs are written.
# Defaults to the project root; the web UI can repoint it to any local folder
# via set_data_dir().
DATA_DIR = PROJECT_ROOT

# Credentials / local-only files stay with the code (not the data folder)
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
GMAIL_TOKEN_FILE = PROJECT_ROOT / os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.pkl")
SAMPLE_EMAILS_FILE = PROJECT_ROOT / "sample_emails.json"

# These are (re)computed from DATA_DIR by _recompute_paths()
INITIATIVES_TRACKER_DIR = None
TOP_PRIORITIES_DIR = None
OVERALL_PROGRESS_DIR = None
REPORT_DIR = None
METRICS_FILE = None
KPI_FILE = None
ACTUAL_PERFORMANCE_FILE = None
ANNUAL_PLANNING_FILE = None


def _recompute_paths():
    """Recompute all DATA_DIR-relative paths."""
    global INITIATIVES_TRACKER_DIR, TOP_PRIORITIES_DIR, OVERALL_PROGRESS_DIR, REPORT_DIR
    global METRICS_FILE, KPI_FILE, ACTUAL_PERFORMANCE_FILE, ANNUAL_PLANNING_FILE
    INITIATIVES_TRACKER_DIR = DATA_DIR / "Initiatives tracker"
    TOP_PRIORITIES_DIR = DATA_DIR / "Top 3 priorities"
    OVERALL_PROGRESS_DIR = DATA_DIR / "Overall progress toward Annual planning"
    REPORT_DIR = DATA_DIR / "Report"
    METRICS_FILE = DATA_DIR / "Metrics.xlsx"
    KPI_FILE = DATA_DIR / "KPI.xlsx"
    ACTUAL_PERFORMANCE_FILE = DATA_DIR / "Actual performance.xlsx"
    ANNUAL_PLANNING_FILE = DATA_DIR / "Annual planning.xlsx"


def set_data_dir(path):
    """Point the agent at a different local data folder (used by the web UI)."""
    global DATA_DIR
    DATA_DIR = Path(path)
    _recompute_paths()
    return DATA_DIR


# Required input files (used to validate a selected folder)
REQUIRED_INPUT_FILES = [
    "Metrics.xlsx", "KPI.xlsx", "Actual performance.xlsx", "Annual planning.xlsx",
]

_recompute_paths()

# Data source mode
# Options: "email" (Phase 2 with Gmail API) or "manual" (Phase 1 fallback)
DATA_SOURCE_MODE = os.environ.get("DATA_SOURCE_MODE", "manual")

# Gmail API configuration (Phase 2)
# Get these from Google Cloud Console: https://console.cloud.google.com
GMAIL_API_CONFIG = {
    "client_id": os.environ.get("GMAIL_CLIENT_ID", ""),
    "client_secret": os.environ.get("GMAIL_CLIENT_SECRET", ""),
    "token_file": os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.pkl"),
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
}

# LLM configuration (GreenNode AI Platform — OpenAI-compatible endpoint)
# NOTE: the api_key default below is a shared GreenNode *platform* demo key bundled
# so the agent runs out-of-the-box for hackathon judging (no .env needed). It is a
# billable platform key (not personal data) — set a low quota and ROTATE after judging.
# Any env var (LLM_API_KEY / LLM_MODEL / LLM_BASE_URL / DATA_SOURCE_MODE) overrides these.
LLM_CONFIG = {
    "base_url": os.environ.get("LLM_BASE_URL",
                               "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"),
    "api_key": os.environ.get("LLM_API_KEY", "vn-K-A9-gp1_t9W2gJ17GsSB-5qJiw5vkacc18e09f8fc4ea5ae057898d1d0633a7Ddj9gB-J0_E2yJ_tdkY3_WRxUedY-b"),
    "model": os.environ.get("LLM_MODEL", "qwen/qwen3-5-27b"),
    "timeout": float(os.environ.get("LLM_TIMEOUT", "90")),
}

# Email configuration (Phase 2) - legacy IMAP (if not using Gmail API)
EMAIL_CONFIG = {
    "imap_server": os.environ.get("IMAP_SERVER", "imap.gmail.com"),
    "email": os.environ.get("EMAIL_ADDRESS", ""),
    "password": os.environ.get("EMAIL_PASSWORD", ""),
}

# Ensure directories exist
def ensure_directories():
    """Create necessary directories if they don't exist"""
    for dir_path in [INITIATIVES_TRACKER_DIR, TOP_PRIORITIES_DIR,
                     OVERALL_PROGRESS_DIR, REPORT_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)

# Month mapping
MONTHS = {
    "1": "January", "2": "February", "3": "March", "4": "April",
    "5": "May", "6": "June", "7": "July", "8": "August",
    "9": "September", "10": "October", "11": "November", "12": "December"
}

def get_month_name(month_num):
    """Convert month number to Vietnamese name"""
    return MONTHS.get(str(month_num), f"Th?ng {month_num}")