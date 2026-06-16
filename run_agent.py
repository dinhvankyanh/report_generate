#!/usr/bin/env python
"""
CLI runner — generate a report with zero config.

Usage:
    python run_agent.py [month] [year]      # default 6 2026

Reads data from the bundled "Report_Sample/" folder if present (so it works
out-of-the-box for a submission bundle); otherwise uses the project root.
"""
import sys
sys.path.insert(0, ".")

from src import config

# Use the bundled sample data folder if it exists
_sample = config.PROJECT_ROOT / "Report_Sample"
if _sample.exists():
    config.set_data_dir(_sample)

from src.agent import ReportGenerateAgent

if __name__ == "__main__":
    month = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2026

    print(f"[INFO] Data folder: {config.DATA_DIR}")
    result = ReportGenerateAgent().generate_report(month, year)

    if result["success"]:
        print("\n[OK] Success! Report generated at:")
        print(f"     {result['context'].get('report_path', 'N/A')}")
    else:
        print("\n[FAIL] Failed!")
        for r in result.get("results", []):
            if not r["result"].get("success", False):
                print(f"     - {r['step']}: {r['result'].get('error')}")
