"""
AgentBase Custom Agent entrypoint + web UI.

Serves a usable web interface at GET / (file upload + required-files checklist +
a chat box to type "lam report thang X nam Y"), plus the AgentBase HTTP contract
(POST /invocations, GET /health) so the deployed runtime is callable.

Cloud cannot read a local folder, so instead of a folder picker the UI lets the
user UPLOAD the required input files into a server-side working folder. The folder
starts EMPTY (checklist all ✗); the user either uploads the files or clicks "Dung du
lieu mau" to load the bundled Report_Sample inputs (checklist flips to ✓). The LLM
runs via the GreenNode MaaS endpoint in config.py.
"""
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

os.environ.setdefault("DATA_SOURCE_MODE", "manual")  # headless: no Gmail OAuth
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext, PingStatus
from starlette.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse

from src import config

# Working data folder that uploads land in (and where outputs are written).
WORK = config.PROJECT_ROOT / "_workdir"
(WORK / "Initiatives tracker").mkdir(parents=True, exist_ok=True)
config.set_data_dir(WORK)

from src.agent import ReportGenerateAgent
from src.llm import llm_available

AI_NOTICE = ("You are interacting with an AI agent. This report is AI-generated - "
             "please review before use.")

app = GreenNodeAgentBaseApp()


# --------------------------------------------------------------------------- #
# Data helpers
# --------------------------------------------------------------------------- #
def _seed_sample(force=False):
    """Copy the bundled Report_Sample inputs into the working folder."""
    src = config.PROJECT_ROOT / "Report_Sample"
    if not src.exists():
        return
    for f in config.REQUIRED_INPUT_FILES:
        s = src / f
        d = config.DATA_DIR / f
        if s.exists() and (force or not d.exists()):
            shutil.copy2(s, d)
    st = src / "Initiatives tracker"
    if st.exists():
        for p in st.glob("*.xlsx"):
            if p.name.startswith("~$"):
                continue
            d = config.INITIATIVES_TRACKER_DIR / p.name
            if force or not d.exists():
                shutil.copy2(p, d)


def _prereqs():
    """(items, trackers, ready): the minimum files needed for a report."""
    import re
    items = [{"name": f, "kind": "file", "ok": (config.DATA_DIR / f).exists(),
              "detail": "required input file"} for f in config.REQUIRED_INPUT_FILES]

    def _tk(name):
        m = re.search(r'th[a-z\x00-\xff]*ng\s*(\d+)[-\s](\d{4})', name, re.IGNORECASE)
        return (int(m.group(2)), int(m.group(1))) if m else (0, 0)

    tdir = config.INITIATIVES_TRACKER_DIR
    trackers = sorted((p.name for p in tdir.glob("*.xlsx") if not p.name.startswith("~$")),
                      key=_tk) if tdir and tdir.exists() else []
    items.append({"name": "Initiatives tracker/", "kind": "folder", "ok": len(trackers) > 0,
                  "detail": (f"latest: {trackers[-1]}" if trackers
                             else "need >=1 prior-month tracker file (to clone the skeleton)")})
    return items, trackers, all(i["ok"] for i in items)


# NOTE: do NOT seed at startup — the working folder starts empty so the checklist
# shows all ✗, letting the user demo either uploading files OR clicking "Dung du
# lieu mau" (which seeds and flips the checklist to ✓).


def _summary(context: dict) -> dict:
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


# --------------------------------------------------------------------------- #
# AgentBase contract
# --------------------------------------------------------------------------- #
@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Generate a report from a chat message like 'lam report thang 6 nam 2026'."""
    message = (payload or {}).get("message") or "lam report thang 6 nam 2026"

    items, _trackers, ready = _prereqs()
    if not ready:
        missing = [i["name"] for i in items if not i["ok"]]
        return {"status": "error",
                "message": "Missing required input file(s): " + ", ".join(missing)
                           + ". Please upload all files (or load the data sample) and try again.",
                "ai_notice": AI_NOTICE, "session_id": context.session_id}

    agent = ReportGenerateAgent()
    parsed = agent.parse_input(message)
    if not parsed:
        return {"status": "error",
                "message": "Could not parse month/year. Example: 'report for June 2026' "
                           "or 'lam report thang 6 nam 2026'.",
                "ai_notice": AI_NOTICE, "session_id": context.session_id}

    month, year = parsed
    try:
        result = agent.generate_report(month, year)
    except Exception as e:
        return {"status": "error", "message": f"Error generating report: {e}",
                "ai_notice": AI_NOTICE, "session_id": context.session_id}

    ok = bool(result.get("success"))
    if ok:
        _remember_outputs(result.get("context", {}), month, year)
    return {
        "status": "success" if ok else "error",
        "message": (f"Report for {month}/{year} generated." if ok
                    else f"Failed to generate report for {month}/{year}."),
        "report": _summary(result.get("context", {})),
        "ai_notice": AI_NOTICE,
        "timestamp": datetime.now().isoformat(),
        "session_id": context.session_id,
    }


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


# --------------------------------------------------------------------------- #
# Web UI routes
# --------------------------------------------------------------------------- #
_WEB_UI = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Report Generate Agent — GreenNode AgentBase</title>
<style>
 body{font-family:Segoe UI,Roboto,Arial,sans-serif;max-width:820px;margin:28px auto;padding:0 16px;
 line-height:1.55;color:#1f2937;background:#f8fafc}
 h1{color:#1F4E79;margin-bottom:2px}.sub{color:#64748b;margin-top:0}
 .card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:14px 0}
 .note{background:#ecfdf5;border-left:4px solid #16a34a;padding:8px 12px;font-size:14px;border-radius:6px}
 h3{margin:4px 0 8px}.req li{margin:2px 0}code{background:#f1f5f9;padding:1px 5px;border-radius:5px}
 .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}
 input[type=text]{flex:1;min-width:240px;padding:10px;border:1px solid #cbd5e1;border-radius:8px;font-size:14px}
 button{padding:9px 16px;background:#1F4E79;color:#fff;border:0;border-radius:8px;font-size:14px;cursor:pointer}
 button.sec{background:#475569}button:disabled{background:#94a3b8;cursor:not-allowed}
 .pq{margin:3px 0;font-size:14px}.ok{color:#16a34a}.no{color:#dc2626}
 #out{min-height:36px}ol{margin:6px 0 6px 18px}a.dl{display:inline-block;margin-top:8px;color:#1F4E79;font-weight:600}
 .muted{color:#64748b;font-size:13px}
</style></head><body>
<h1>📊 Report Generate Agent</h1>
<p class="sub">Monthly Cash Loan business report — running on GreenNode AgentBase.</p>
<div class="note">🤖 You are interacting with an <b>AI agent</b>. The report is AI-generated — please review before use.</div>

<div class="card">
  <h3>1) Required input files</h3>
  <ul class="req">
    <li><code>Metrics.xlsx</code> — required input file</li>
    <li><code>KPI.xlsx</code> — required input file</li>
    <li><code>Actual performance.xlsx</code> — required input file</li>
    <li><code>Annual planning.xlsx</code> — required input file</li>
    <li><code>Initiatives tracker thang (X-1).xlsx</code> — need &ge;1 prior-month tracker file (to clone the skeleton)</li>
  </ul>
  <div class="row">
    <input type="file" id="files" multiple accept=".xlsx">
    <button onclick="upload()">Upload files</button>
    <button class="sec" onclick="useSample()">Data Sample (use for demo)</button>
  </div>
  <div id="prereqs" class="muted">Loading status...</div>
</div>

<div class="card">
  <h3>2) Enter command</h3>
  <div class="row">
    <input type="text" id="msg" value=""
           placeholder='e.g. "report for June 2026"  or  "lam report thang 6 nam 2026"'>
    <button id="btn" onclick="run()">Generate report</button>
  </div>
  <div class="muted">Type the month to report on. Examples: <code>report for June 2026</code> ·
  <code>lam report thang 6 nam 2026</code></div>
  <div id="out" class="muted" style="margin-top:8px">Click "Generate report" (~2 min: 7-step pipeline + LLM).</div>
</div>
<p class="muted">API: <code>POST /invocations</code> · <a href="/health">/health</a> ·
Repo: <a href="https://github.com/dinhvankyanh/report_generate">github.com/dinhvankyanh/report_generate</a></p>
<script>
function renderPrereqs(d){
  const el=document.getElementById('prereqs');
  let h=(d.prereqs||[]).map(p=>`<div class="pq ${p.ok?'ok':'no'}">${p.ok?'✓':'✗'} ${p.name} <span class="muted">— ${p.detail||''}</span></div>`).join('');
  h+=`<div class="pq ${d.ready?'ok':'no'}">${d.ready?'✓ Ready — you can generate the report.':'✗ Not ready — upload the missing items (or use the data sample).'}</div>`;
  el.innerHTML=h;
  document.getElementById('btn').disabled=!d.ready;
}
async function loadCfg(){ try{renderPrereqs(await (await fetch('/api/config')).json());}catch(e){} }
async function upload(){
  const f=document.getElementById('files').files; if(!f.length){alert('Choose files first');return;}
  const fd=new FormData(); for(const x of f) fd.append('files',x);
  document.getElementById('prereqs').innerHTML='Uploading...';
  try{ renderPrereqs(await (await fetch('/api/upload',{method:'POST',body:fd})).json()); }
  catch(e){ document.getElementById('prereqs').innerHTML='Upload error: '+e; }
}
async function useSample(){
  document.getElementById('prereqs').innerHTML='Loading data sample...';
  try{ renderPrereqs(await (await fetch('/api/sample',{method:'POST'})).json()); }
  catch(e){ document.getElementById('prereqs').innerHTML='Error: '+e; }
}
async function run(){
  const msg=document.getElementById('msg').value, out=document.getElementById('out'), btn=document.getElementById('btn');
  if(!msg.trim()){ out.innerHTML='Please type a command, e.g. "report for June 2026".'; return; }
  btn.disabled=true; out.innerHTML='⏳ Running the agent (~2 min), please wait...';
  try{
    const d=await (await fetch('/invocations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})})).json();
    let h='<b>'+(d.status||'')+'</b> — '+(d.message||'');
    if(d.report){
      if(d.report.report_file) h+='<br>📄 File: <code>'+d.report.report_file+'</code>';
      if(d.report.top_priorities){h+='<br>Top priorities:<ol>'+d.report.top_priorities.map(p=>'<li>'+p+'</li>').join('')+'</ol>';}
      if('consistency_warnings' in d.report) h+='Cross-file consistency warnings: '+d.report.consistency_warnings;
      if(d.status==='success'){
        h+='<br><a class="dl" href="/download?type=report">⬇ Download report (.docx)</a>';
        h+=' &nbsp;&nbsp; <a class="dl" href="/download?type=tracker">⬇ Download Initiatives tracker, month X (.xlsx)</a>';
      }
    }
    if(d.ai_notice) h+='<br><span class="muted">'+d.ai_notice+'</span>';
    out.innerHTML=h;
  }catch(e){ out.innerHTML='❌ Error: '+e; }
  btn.disabled=false;
}
loadCfg();
</script>
</body></html>"""


def _root(request):
    return HTMLResponse(_WEB_UI)


def _api_config(request):
    items, trackers, ready = _prereqs()
    return JSONResponse({"prereqs": items, "trackers": trackers, "ready": ready,
                         "llm_ready": llm_available()})


async def _api_upload(request):
    form = await request.form()
    saved = []
    for f in form.getlist("files"):
        fn = getattr(f, "filename", None)
        if not fn:
            continue
        fn = os.path.basename(fn)
        dest = (config.INITIATIVES_TRACKER_DIR / fn) if "tracker" in fn.lower() \
            else (config.DATA_DIR / fn)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await f.read())
        saved.append(fn)
    items, trackers, ready = _prereqs()
    return JSONResponse({"saved": saved, "prereqs": items, "trackers": trackers, "ready": ready})


def _api_sample(request):
    _seed_sample(force=True)
    items, trackers, ready = _prereqs()
    return JSONResponse({"prereqs": items, "trackers": trackers, "ready": ready})


# Remember the files produced by the latest run so they can be downloaded.
_LAST_OUTPUTS = {}
_MIME = {
    "report": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "tracker": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _remember_outputs(ctx: dict, month: int, year: int):
    rp = ctx.get("report_path")
    if rp:
        _LAST_OUTPUTS["report"] = Path(rp)
    tr = config.INITIATIVES_TRACKER_DIR / f"Initiatives tracker thang {month}-{year}.xlsx"
    if tr.exists():
        _LAST_OUTPUTS["tracker"] = tr


def _latest(dirp, pattern):
    files = [p for p in dirp.glob(pattern) if not p.name.startswith("~$")] if dirp and dirp.exists() else []
    files.sort(key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _download(request):
    """Download a generated file: ?type=report (.docx, default) or ?type=tracker (.xlsx)."""
    kind = request.query_params.get("type", "report")
    if kind not in ("report", "tracker"):
        kind = "report"
    p = _LAST_OUTPUTS.get(kind)
    if not p or not Path(p).exists():
        p = _latest(config.REPORT_DIR, "*.docx") if kind == "report" \
            else _latest(config.INITIATIVES_TRACKER_DIR, "*.xlsx")
    if p and Path(p).exists():
        p = Path(p)
        return FileResponse(str(p), filename=p.name, media_type=_MIME[kind])
    return PlainTextResponse("Not generated yet. Run the agent first.", status_code=404)


app.add_route("/", _root, methods=["GET"])
app.add_route("/api/config", _api_config, methods=["GET"])
app.add_route("/api/upload", _api_upload, methods=["POST"])
app.add_route("/api/sample", _api_sample, methods=["POST"])
app.add_route("/download", _download, methods=["GET"])


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
