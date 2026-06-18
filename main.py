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
from starlette.responses import HTMLResponse, FileResponse, PlainTextResponse

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


# Web UI served at GET / so the public endpoint shows a usable interface (not 404).
# Runs on the bundled Report_Sample data (cloud cannot access a local folder), via a
# Run button -> POST /invocations -> result + a download link for the .docx.
_WEB_UI = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Report Generate Agent — GreenNode AgentBase</title>
<style>
 body{font-family:Segoe UI,Roboto,Arial,sans-serif;max-width:780px;margin:32px auto;
 padding:0 16px;line-height:1.55;color:#1f2937;background:#f8fafc}
 h1{color:#1F4E79;margin-bottom:4px}.sub{color:#64748b;margin-top:0}
 .note{background:#ecfdf5;border-left:4px solid #16a34a;padding:8px 12px;margin:14px 0;font-size:14px}
 .row{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
 input{flex:1;min-width:260px;padding:10px;border:1px solid #cbd5e1;border-radius:8px;font-size:14px}
 button{padding:10px 18px;background:#1F4E79;color:#fff;border:0;border-radius:8px;font-size:14px;cursor:pointer}
 button:disabled{background:#94a3b8;cursor:not-allowed}
 #out{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-top:8px;min-height:40px}
 ol{margin:6px 0 6px 18px}a.dl{display:inline-block;margin-top:10px;color:#1F4E79;font-weight:600}
 .muted{color:#64748b;font-size:13px}
</style></head><body>
<h1>📊 Report Generate Agent</h1>
<p class="sub">Monthly Cash Loan business report — chạy trên GreenNode AgentBase.</p>
<div class="note">🤖 Bạn đang tương tác với một <b>tác nhân AI</b>. Báo cáo do AI tạo tự động — hãy rà soát trước khi dùng.</div>
<p class="muted">Demo chạy trên bộ dữ liệu mẫu đóng gói sẵn (<code>Report_Sample/</code>). Nhập tháng cần làm rồi bấm <b>Tạo report</b>.</p>
<div class="row">
  <input id="msg" value="lam report thang 6 nam 2026" placeholder="vd: lam report thang 6 nam 2026 / report for June 2026">
  <button id="btn" onclick="run()">Tạo report</button>
</div>
<div id="out">Chưa chạy. Bấm "Tạo report" (mất ~2 phút: chạy 7 bước + LLM).</div>
<script>
async function run(){
  const msg=document.getElementById('msg').value;
  const out=document.getElementById('out'), btn=document.getElementById('btn');
  btn.disabled=true; out.innerHTML='⏳ Đang chạy agent (~2 phút), vui lòng đợi…';
  try{
    const r=await fetch('/invocations',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg})});
    const d=await r.json();
    let h='<b>'+(d.status||'')+'</b> — '+(d.message||'');
    if(d.report){
      if(d.report.report_file) h+='<br>📄 File: <code>'+d.report.report_file+'</code>';
      if(d.report.top_priorities){h+='<br>Top priorities:<ol>'+d.report.top_priorities.map(p=>'<li>'+p+'</li>').join('')+'</ol>';}
      if('consistency_warnings' in d.report) h+='Cross-file consistency warnings: '+d.report.consistency_warnings;
      if(d.status==='success') h+='<br><a class="dl" href="/download">⬇ Tải report (.docx)</a>';
    }
    if(d.ai_notice) h+='<br><span class="muted">'+d.ai_notice+'</span>';
    out.innerHTML=h;
  }catch(e){ out.innerHTML='❌ Lỗi: '+e+' (thử lại — lần đầu sau khi idle có thể chậm).'; }
  btn.disabled=false;
}
</script>
<p class="muted">API: <code>POST /invocations</code> · <a href="/health">/health</a> ·
Repo: <a href="https://github.com/dinhvankyanh/report_generate">github.com/dinhvankyanh/report_generate</a></p>
</body></html>"""


def _root(request):
    return HTMLResponse(_WEB_UI)


def _download(request):
    """Serve the most recently generated report .docx."""
    try:
        docs = sorted(config.REPORT_DIR.glob("*.docx"), key=lambda p: p.stat().st_mtime)
        if docs:
            latest = docs[-1]
            return FileResponse(
                str(latest), filename=latest.name,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    except Exception:
        pass
    return PlainTextResponse("No report generated yet. Run the agent first.", status_code=404)


app.add_route("/", _root, methods=["GET"])
app.add_route("/download", _download, methods=["GET"])


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
