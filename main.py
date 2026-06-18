"""
AgentBase Custom Agent entrypoint.

Wraps the existing 7-step report pipeline (ReportGenerateAgent) behind the
GreenNode AgentBase HTTP contract so the deployed runtime is callable:
  POST /invocations  {"message": "làm report tháng 6 năm 2026"}  -> JSON summary
  GET  /health       -> 200

Runs headless/offline (DATA_SOURCE_MODE=manual reads the bundled, anonymized
sample_emails.json) so it needs no Google OAuth in the container. The LLM still
runs via the GreenNode MaaS endpoint configured in src/config.py.

Local dev still uses app.py (Flask chat UI); this file is the cloud entrypoint.
"""
import os
import sys
from datetime import datetime

# Headless on the runtime: no folder picker, no Gmail OAuth — use bundled data.
os.environ.setdefault("DATA_SOURCE_MODE", "manual")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext, PingStatus
from starlette.responses import HTMLResponse

from src import config

# Use the bundled sample data folder shipped in the image.
_sample = config.PROJECT_ROOT / "Report_Sample"
if _sample.exists():
    config.set_data_dir(_sample)

from src.agent import ReportGenerateAgent

AI_NOTICE = ("Ban dang tuong tac voi mot tac nhan AI. Bao cao do AI tao tu dong - "
             "hay ra soat truoc khi su dung. (AI-generated; review before use.)")

app = GreenNodeAgentBaseApp()


def _summary(context: dict) -> dict:
    """Extract a concise, JSON-safe summary of the generated report."""
    out = {}
    rp = context.get("report_path")
    if rp:
        out["report_file"] = os.path.basename(str(rp))
    top = context.get("top_3_priorities")
    try:
        if top is not None and not top.empty:
            out["top_priorities"] = [str(r.get("name", "")) for _, r in top.iterrows()]
    except Exception:
        pass
    issues = context.get("consistency_issues")
    if isinstance(issues, list):
        out["consistency_warnings"] = len(issues)
    return out


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Generate a monthly report from a chat message like 'làm report tháng 6 năm 2026'."""
    message = (payload or {}).get("message") or "làm report tháng 6 năm 2026"

    agent = ReportGenerateAgent()
    parsed = agent.parse_input(message)
    if not parsed:
        return {
            "status": "error",
            "message": "Khong nhan ra thang/nam. Vi du: 'lam report thang 6 nam 2026'.",
            "ai_notice": AI_NOTICE,
            "session_id": context.session_id,
        }

    month, year = parsed
    try:
        result = agent.generate_report(month, year)
    except Exception as e:
        return {"status": "error", "message": f"Loi tao report: {e}",
                "ai_notice": AI_NOTICE, "session_id": context.session_id}

    ok = bool(result.get("success"))
    return {
        "status": "success" if ok else "error",
        "message": (f"Da tao report thang {month}/{year}." if ok
                    else f"Tao report thang {month}/{year} that bai."),
        "report": _summary(result.get("context", {})),
        "ai_notice": AI_NOTICE,
        "timestamp": datetime.now().isoformat(),
        "session_id": context.session_id,
    }


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


# Landing page at GET / so opening the endpoint URL in a browser returns 200
# (not 404) — judges/automated checks hit the root and must see the agent is live.
_LANDING_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Report Generate Agent — GreenNode AgentBase</title>
<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:760px;margin:40px auto;
padding:0 16px;line-height:1.55;color:#1f2937}code,pre{background:#f3f4f6;border-radius:6px}
pre{padding:12px;overflow:auto}h1{color:#1F4E79}.ok{color:#16a34a;font-weight:600}
.note{background:#1d2b1f0d;border-left:4px solid #16a34a;padding:8px 12px;margin:16px 0}</style>
</head><body>
<h1>Report Generate Agent</h1>
<p class="ok">Status: running on GreenNode AgentBase (PUBLIC).</p>
<div class="note">This is an <b>AI agent</b>. It auto-generates a monthly Cash Loan
business report (.docx) from Excel + email data. Output is AI-generated — review before use.</div>
<p>This endpoint is an <b>HTTP API</b>. Health: <a href="/health">/health</a>.</p>
<h3>Try it — POST /invocations</h3>
<pre>curl -X POST "$URL/invocations" -H "Content-Type: application/json" \\
  -d '{"message":"lam report thang 6 nam 2026"}' --max-time 300</pre>
<p>PowerShell one-liner (see <code>call_agent.ps1</code> in the repo):</p>
<pre>Invoke-RestMethod -Uri "$URL/invocations" -Method Post `
  -ContentType "application/json" -Body '{"message":"lam report thang 6 nam 2026"}' -TimeoutSec 300</pre>
<p>A call runs the full pipeline + LLM (~2 minutes). Accepts
<code>lam report thang 6 nam 2026</code>, <code>report for June 2026</code>, etc.</p>
<p>Repo: <a href="https://github.com/dinhvankyanh/report_generate">github.com/dinhvankyanh/report_generate</a></p>
</body></html>"""


def _root(request):
    return HTMLResponse(_LANDING_HTML)


app.add_route("/", _root, methods=["GET"])


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
