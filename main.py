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

AI_NOTICE = ("Ban dang tuong tac voi mot tac nhan AI. Bao cao do AI tao tu dong - "
             "hay ra soat truoc khi su dung. (AI-generated; review before use.)")

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
              "detail": "file dau vao bat buoc"} for f in config.REQUIRED_INPUT_FILES]

    def _tk(name):
        m = re.search(r'th[a-z\x00-\xff]*ng\s*(\d+)[-\s](\d{4})', name, re.IGNORECASE)
        return (int(m.group(2)), int(m.group(1))) if m else (0, 0)

    tdir = config.INITIATIVES_TRACKER_DIR
    trackers = sorted((p.name for p in tdir.glob("*.xlsx") if not p.name.startswith("~$")),
                      key=_tk) if tdir and tdir.exists() else []
    items.append({"name": "Initiatives tracker/", "kind": "folder", "ok": len(trackers) > 0,
                  "detail": (f"moi nhat: {trackers[-1]}" if trackers
                             else "can >=1 file tracker thang truoc (de clone skeleton)")})
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
                "message": "Thieu file dau vao: " + ", ".join(missing) + ". Hay upload du file roi thu lai.",
                "ai_notice": AI_NOTICE, "session_id": context.session_id}

    agent = ReportGenerateAgent()
    parsed = agent.parse_input(message)
    if not parsed:
        return {"status": "error",
                "message": "Khong nhan ra thang/nam. Vi du: 'lam report thang 6 nam 2026'.",
                "ai_notice": AI_NOTICE, "session_id": context.session_id}

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


# --------------------------------------------------------------------------- #
# Web UI routes
# --------------------------------------------------------------------------- #
_WEB_UI = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
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
<p class="sub">Monthly Cash Loan business report — chay tren GreenNode AgentBase.</p>
<div class="note">🤖 Ban dang tuong tac voi mot <b>tac nhan AI</b>. Bao cao do AI tao tu dong — hay ra soat truoc khi dung.</div>

<div class="card">
  <h3>1) File dau vao bat buoc</h3>
  <ul class="req">
    <li><code>Metrics.xlsx</code> — file dau vao bat buoc</li>
    <li><code>KPI.xlsx</code> — file dau vao bat buoc</li>
    <li><code>Actual performance.xlsx</code> — file dau vao bat buoc</li>
    <li><code>Annual planning.xlsx</code> — file dau vao bat buoc</li>
    <li><code>Initiatives tracker thang (X-1).xlsx</code> — can &ge;1 file tracker thang truoc (de clone skeleton)</li>
  </ul>
  <div class="row">
    <input type="file" id="files" multiple accept=".xlsx">
    <button onclick="upload()">Tai file len</button>
    <button class="sec" onclick="useSample()">Dung du lieu mau</button>
  </div>
  <div id="prereqs" class="muted">Dang tai trang thai...</div>
</div>

<div class="card">
  <h3>2) Nhap lenh</h3>
  <div class="row">
    <input type="text" id="msg" value="lam report thang 6 nam 2026"
           placeholder="vd: lam report thang 6 nam 2026 / report for June 2026">
    <button id="btn" onclick="run()">Tao report</button>
  </div>
  <div id="out" class="muted">Bam "Tao report" (mat ~2 phut: chay 7 buoc + LLM).</div>
</div>
<p class="muted">API: <code>POST /invocations</code> · <a href="/health">/health</a> ·
Repo: <a href="https://github.com/dinhvankyanh/report_generate">github.com/dinhvankyanh/report_generate</a></p>
<script>
function renderPrereqs(d){
  const el=document.getElementById('prereqs');
  let h=(d.prereqs||[]).map(p=>`<div class="pq ${p.ok?'ok':'no'}">${p.ok?'✓':'✗'} ${p.name} <span class="muted">— ${p.detail||''}</span></div>`).join('');
  h+=`<div class="pq ${d.ready?'ok':'no'}">${d.ready?'✓ Da du dieu kien — co the tao report.':'✗ Chua du — tai len cac muc con thieu.'}</div>`;
  el.innerHTML=h;
  document.getElementById('btn').disabled=!d.ready;
}
async function loadCfg(){ try{renderPrereqs(await (await fetch('/api/config')).json());}catch(e){} }
async function upload(){
  const f=document.getElementById('files').files; if(!f.length){alert('Chon file truoc');return;}
  const fd=new FormData(); for(const x of f) fd.append('files',x);
  document.getElementById('prereqs').innerHTML='Dang tai len...';
  try{ renderPrereqs(await (await fetch('/api/upload',{method:'POST',body:fd})).json()); }
  catch(e){ document.getElementById('prereqs').innerHTML='Loi upload: '+e; }
}
async function useSample(){
  document.getElementById('prereqs').innerHTML='Dang nap du lieu mau...';
  try{ renderPrereqs(await (await fetch('/api/sample',{method:'POST'})).json()); }
  catch(e){ document.getElementById('prereqs').innerHTML='Loi: '+e; }
}
async function run(){
  const msg=document.getElementById('msg').value, out=document.getElementById('out'), btn=document.getElementById('btn');
  btn.disabled=true; out.innerHTML='⏳ Dang chay agent (~2 phut), vui long doi...';
  try{
    const d=await (await fetch('/invocations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})})).json();
    let h='<b>'+(d.status||'')+'</b> — '+(d.message||'');
    if(d.report){
      if(d.report.report_file) h+='<br>📄 File: <code>'+d.report.report_file+'</code>';
      if(d.report.top_priorities){h+='<br>Top priorities:<ol>'+d.report.top_priorities.map(p=>'<li>'+p+'</li>').join('')+'</ol>';}
      if('consistency_warnings' in d.report) h+='Cross-file consistency warnings: '+d.report.consistency_warnings;
      if(d.status==='success') h+='<br><a class="dl" href="/download">⬇ Tai report (.docx)</a>';
    }
    if(d.ai_notice) h+='<br><span class="muted">'+d.ai_notice+'</span>';
    out.innerHTML=h;
  }catch(e){ out.innerHTML='❌ Loi: '+e; }
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


def _download(request):
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
app.add_route("/api/config", _api_config, methods=["GET"])
app.add_route("/api/upload", _api_upload, methods=["POST"])
app.add_route("/api/sample", _api_sample, methods=["POST"])
app.add_route("/download", _download, methods=["GET"])


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
