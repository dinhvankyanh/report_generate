#!/usr/bin/env python
"""
Focused test for Step 1 (build tracker via LLM) + Step 2 (Status change).

Usage:
    python test_step1_2.py [month] [year]      # default 6 2026

Requires (for the LLM path) in .env or environment:
    DATA_SOURCE_MODE=email
    LLM_API_KEY=...        # GreenNode key (aip.sh api-keys create/get --save-env)
    LLM_MODEL=...          # model `path`
Without a key it falls back to carry-forward and warns.
"""
import sys
sys.path.insert(0, ".")

try:
    sys.stdout.reconfigure(encoding="utf-8")  # avoid cp1252 crash on Windows
except Exception:
    pass

import pandas as pd

from src.data_sources import create_data_source
from src.steps.step1_email_or_manual import Step1GetInitiativesData
from src.steps.step2_status_change import Step2StatusChange
from src import config

month = int(sys.argv[1]) if len(sys.argv) > 1 else 6
year = int(sys.argv[2]) if len(sys.argv) > 2 else 2026

ds = create_data_source()
ctx = {}
Step1GetInitiativesData(ds).execute(month, year, ctx)
Step2StatusChange(ds).execute(month, year, ctx)

df = ctx["initiatives_data"]
cols = ["No", "Initiative Names", "Status", "Status change",
        "New timing (if applicable)", "How confident", "Details from that month"]
print("\n" + "=" * 100)
print(f"Initiatives tracker {month}-{year}")
print("=" * 100)
for _, r in df.iterrows():
    no = r.get("No")
    if pd.isna(no):
        continue
    print(f"No {int(no):<2} | St={str(r.get('Status')):<14} "
          f"Chg={str(r.get('Status change')):<5} "
          f"NewT={str(r.get('New timing (if applicable)')):<9} "
          f"Cf={str(r.get('How confident')):<8}")
    det = r.get("Details from that month")
    if pd.notna(det) and str(det).strip() not in ("", "nan"):
        print(f"        details: {str(det)[:110]}")
