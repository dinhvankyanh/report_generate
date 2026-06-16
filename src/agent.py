"""
Main Report Generate Agent
Chat-based interface for generating monthly reports
"""
import re
import sys
import unicodedata
from typing import Dict, Any, Optional
from datetime import datetime

from .data_sources import create_data_source
from .steps import get_all_steps
from . import config


def _strip_diacritics(s: str) -> str:
    """Remove Vietnamese diacritics so 'tháng'->'thang', 'năm'->'nam' (đ->d too).
    Lets the parser accept both accented and unaccented input."""
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


class ReportGenerateAgent:
    """
    Chat-based Agent for generating monthly reports

    Usage:
        agent = ReportGenerateAgent()
        agent.chat()
    """

    def __init__(self, data_source=None):
        self.data_source = data_source or create_data_source()
        self.context = {}
        self.conversation_history = []

    def parse_input(self, user_input: str) -> Optional[tuple]:
        """
        Parse user input to extract month and year

        Examples:
            - "lam report thang 6 nam 2026" -> (6, 2026)
            - "report thang 3/2024" -> (3, 2024)
            - "generate report for June 2026" -> (6, 2026)
            - "làm report tháng 6 năm 2026" (có dấu) -> (6, 2026)
        """
        user_input = _strip_diacritics(user_input.lower())

        # Pattern for Vietnamese
        # "lam report thang X nam Y"
        pattern_vn = r'thang\s*(\d+)\s*nam\s*(\d{4})'
        match = re.search(pattern_vn, user_input)
        if match:
            return int(match.group(1)), int(match.group(2))

        # Pattern for "thang X/Y" or "X/Y"
        pattern_short = r'thang\s*(\d+)[\/\-](\d{4})|(\d{1,2})[\/\-](\d{4})'
        match = re.search(pattern_short, user_input)
        if match:
            if match.group(1):
                return int(match.group(1)), int(match.group(2))
            elif match.group(3):
                return int(match.group(3)), int(match.group(4))

        # English pattern
        pattern_en = r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})'
        match = re.search(pattern_en, user_input)
        if match:
            month_name = match.group(1)
            year = int(match.group(2))
            month = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12
            }.get(month_name)
            return month, year

        return None

    def generate_report(self, month: int, year: int) -> Dict[str, Any]:
        """
        Execute all pipeline steps to generate the report

        Args:
            month: Target month (1-12)
            year: Target year

        Returns:
            Dict with results from all steps
        """
        print(f"\n{'='*60}")
        print(f"STARTING REPORT GENERATION FOR {config.get_month_name(month).upper()} {year}")
        print(f"{'='*60}\n")

        # Ensure directories exist
        config.ensure_directories()

        # Initialize context
        self.context = {
            "month": month,
            "year": year,
            "start_time": datetime.now()
        }

        # Get all steps
        steps = get_all_steps(self.data_source)

        results = []
        all_success = True

        # Execute each step
        for i, step in enumerate(steps, 1):
            print(f"\n{'='*50}")
            print(f"[{i}/{len(steps)}] {step.name}")
            print(f"{'='*50}")

            try:
                result = step.execute(month, year, self.context)
                results.append({
                    "step": step.name,
                    "result": result
                })

                if not result.get("success", False):
                    all_success = False
                    print(f"[FAIL] Step {i} failed: {result.get('error', 'Unknown error')}")
                    break

            except Exception as e:
                all_success = False
                print(f"[ERROR] Step {i} error: {str(e)}")
                results.append({
                    "step": step.name,
                    "result": {"success": False, "error": str(e)}
                })
                break

        # Summary
        print(f"\n{'='*60}")
        if all_success:
            print(f"[OK] REPORT GENERATION COMPLETE!")
            pdf_path = self.context.get("pdf_path", "Unknown")
            print(f"[PDF] Output: {pdf_path}")
        else:
            print(f"[FAIL] REPORT GENERATION FAILED")
        print(f"{'='*60}\n")

        return {
            "success": all_success,
            "month": month,
            "year": year,
            "results": results,
            "context": self.context
        }

    def chat(self):
        """
        Interactive chat loop
        """
        print("\n" + "="*60)
        print("REPORT GENERATE AGENT")
        print("="*60)
        print("\n[INFO] This agent generates monthly reports from Excel data.")
        print("[INFO] Type 'lam report thang X nam Y' to generate a report.")
        print("[INFO] Type 'help' for more commands, 'exit' to quit.")
        print("\n" + "="*60 + "\n")

        while True:
            try:
                user_input = input("[You] ").strip()

                if not user_input:
                    continue

                # Add to history
                self.conversation_history.append({"role": "user", "content": user_input})

                # Exit
                if user_input.lower() in ['exit', 'quit']:
                    print("\n[BYE] Goodbye! Thanks for using the Agent!")
                    break

                # Help
                if user_input.lower() == 'help':
                    self._show_help()
                    continue

                # Check for report generation request
                parsed = self.parse_input(user_input)

                if parsed:
                    month, year = parsed
                    print(f"\n[INFO] Received request: Report for {config.get_month_name(month)} {year}")

                    # Check if valid
                    if not self.data_source.validate_month_year(month, year):
                        print("[ERROR] Invalid month/year!")
                        continue

                    # Generate report
                    result = self.generate_report(month, year)

                    if result["success"]:
                        print(f"\n[OK] Report generated successfully!")
                        print(f"     Location: {result['context'].get('pdf_path', 'N/A')}")
                    else:
                        print("\n[ERROR] Report generation failed.")
                        print("        You can ask me to explain the details.")

                else:
                    # General conversation
                    print("\n[INFO] I don't understand. Please use:")
                    print("       'lam report thang X nam Y' to generate a report")

                # Add response to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": "Report generated" if parsed else "Unknown command"
                })

            except KeyboardInterrupt:
                print("\n\n[BYE] Goodbye!")
                break
            except Exception as e:
                print(f"\n[ERROR] {str(e)}")

    def _show_help(self):
        """Show help message"""
        print("""
[HELP] COMMAND REFERENCE

1. GENERATE REPORT:
   - "lam report thang 6 nam 2026"
   - "report thang 3/2024"
   - "generate report for June 2026"

2. DATA SOURCE:
""")
        mode = config.DATA_SOURCE_MODE.lower()
        print(f"   - Mode: {mode.upper()}")
        if mode == "email":
            print("   - Using Email (Phase 2)")
        else:
            print("   - Using Manual/Excel (Phase 1)")
        print("""
3. FILES NEEDED:
   - Metrics.xlsx
   - KPI.xlsx
   - Actual performance.xlsx
   - Annual planning.xlsx
   - Initiatives tracker/*.xlsx

4. OUTPUT:
   - Report/Report thang X nam Y.docx
   - Initiatives tracker/Initiatives tracker thang X-YYYY.xlsx
   - Performance analysis.xlsx, Forecast.xlsx

5. NOTES:
   - Agent automatically finds the latest initiatives tracker file
   - You can chat back to request modifications
""")


def main():
    """Main entry point"""
    agent = ReportGenerateAgent()
    agent.chat()


if __name__ == "__main__":
    main()