#!/usr/bin/env python
"""
Quick test script to generate a report
"""
import sys
sys.path.insert(0, '.')

from src.agent import ReportGenerateAgent

if __name__ == "__main__":
    agent = ReportGenerateAgent()

    # Test with month 6, year 2026
    month = 6
    year = 2026

    result = agent.generate_report(month, year)

    if result["success"]:
        print("\n[OK] Success! Report generated at:")
        print(f"     {result['context'].get('pdf_path', 'N/A')}")
    else:
        print("\n[FAIL] Failed!")
        for r in result.get("results", []):
            if not r["result"].get("success", False):
                print(f"     - {r['step']}: {r['result'].get('error')}")