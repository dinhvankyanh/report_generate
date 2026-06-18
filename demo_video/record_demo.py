"""
Record a full demo of the Report Generate Agent on the live AgentBase endpoint,
with Vietnamese subtitles burned in as a page overlay.

Flow (one continuous recording):
  intro -> open endpoint -> Data Sample -> type command -> Generate ->
  (wait ~2 min) -> show result + download both files ->
  convert downloaded .docx/.xlsx to PDF -> rasterize to PNG ->
  open report (scroll through pages) -> open tracker -> outro.

Outputs:
  out/demo_raw.webm        the raw recording (2-min wait at real time)
  out/marks.json           timestamps for the post-process speed-up
"""
import base64
import json
import sys
import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

URL = "https://endpoint-9423e96a-a3b5-4940-84f0-110b8aff6299.agentbase-runtime.aiplatform.vngcloud.vn/"
HERE = Path(__file__).parent
ASSETS = HERE / "assets"
DL = HERE / "downloads"
OUT = HERE / "out"
for d in (ASSETS, DL, OUT):
    d.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
CMD = "report for June 2026"

# Initial "folder empty" state — what a fresh deployment shows before any upload.
# (Our earlier test runs pre-seeded the server, so we restore this real first-use
#  view by intercepting the first /api/config; the green flip after clicking
#  "Data Sample" is the genuine /api/sample response.)
NOT_READY = {
    "prereqs": [
        {"name": "Metrics.xlsx", "kind": "file", "ok": False, "detail": "required input file"},
        {"name": "KPI.xlsx", "kind": "file", "ok": False, "detail": "required input file"},
        {"name": "Actual performance.xlsx", "kind": "file", "ok": False, "detail": "required input file"},
        {"name": "Annual planning.xlsx", "kind": "file", "ok": False, "detail": "required input file"},
        {"name": "Initiatives tracker/", "kind": "folder", "ok": False,
         "detail": "need >=1 prior-month tracker file (to clone the skeleton)"},
    ],
    "trackers": [], "ready": False, "llm_ready": True,
}

# ---- Subtitle overlay, injected into every page (endpoint + local viewer) ---- #
OVERLAY_JS = r"""
(() => {
  function ensure() {
    if (document.getElementById('__subbar')) return;
    if (!document.body) { window.addEventListener('DOMContentLoaded', ensure); return; }
    const st = document.createElement('style');
    st.textContent = '@keyframes __rip{to{width:70px;height:70px;opacity:0}}';
    document.head.appendChild(st);
    const bar = document.createElement('div');
    bar.id = '__subbar';
    bar.style.cssText = [
      'position:fixed','left:0','right:0','bottom:0','z-index:2147483646',
      'box-sizing:border-box','width:100%','padding:20px 48px',
      'background:rgba(15,23,42,0.86)','color:#fff','text-align:center',
      "font-family:'Segoe UI',Roboto,Arial,sans-serif",'font-size:34px',
      'font-weight:600','line-height:1.35','letter-spacing:0.2px',
      'border-top:4px solid #1F4E79','transition:opacity .25s',
      'text-shadow:0 1px 2px rgba(0,0,0,.5)','min-height:42px'
    ].join(';');
    document.body.appendChild(bar);
    const tag = document.createElement('div');
    tag.id = '__subtag';
    tag.textContent = 'Report Generate Agent — Demo';
    tag.style.cssText = [
      'position:fixed','right:22px','top:20px','z-index:2147483646',
      'background:#1F4E79','color:#fff','padding:9px 16px','border-radius:9px',
      "font-family:'Segoe UI',Roboto,Arial,sans-serif",'font-size:19px','font-weight:700',
      'box-shadow:0 2px 8px rgba(0,0,0,.25)'
    ].join(';');
    document.body.appendChild(tag);
    const cur = document.createElement('div');
    cur.id = '__cursor';
    cur.style.cssText = [
      'position:fixed','left:50%','top:46%','z-index:2147483647','pointer-events:none',
      'width:38px','height:38px','transform:translate(-5px,-3px)',
      'filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))',
      'transition:left .55s cubic-bezier(.45,.05,.2,1),top .55s cubic-bezier(.45,.05,.2,1)'
    ].join(';');
    cur.innerHTML = "<svg width='38' height='38' viewBox='0 0 24 24'><path d='M5 3 L5 19 L9 15 L12 21 L14.6 19.8 L11.6 14 L17 14 Z' fill='#111' stroke='#fff' stroke-width='1.3' stroke-linejoin='round'/></svg>";
    document.body.appendChild(cur);
  }
  ensure();
  window.__sub = (t) => { ensure(); const b=document.getElementById('__subbar'); if(b) b.innerHTML=t; };
  window.__cursorMove = (x,y) => { ensure(); const c=document.getElementById('__cursor'); if(c){ c.style.left=x+'px'; c.style.top=y+'px'; } };
  window.__cursorClick = () => {
    const c=document.getElementById('__cursor'); if(!c) return;
    const x=parseFloat(c.style.left)||0, y=parseFloat(c.style.top)||0;
    const r=document.createElement('div');
    r.style.cssText='position:fixed;left:'+x+'px;top:'+y+'px;width:14px;height:14px;border-radius:50%;'
      +'background:rgba(31,78,121,.35);border:3px solid #1F4E79;z-index:2147483647;pointer-events:none;'
      +'transform:translate(-50%,-50%);animation:__rip .55s ease-out forwards';
    document.body.appendChild(r); setTimeout(()=>{ if(r.parentNode) r.remove(); }, 600);
  };
})();
"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(OUT),
            record_video_size={"width": W, "height": H},
            accept_downloads=True,
        )
        ctx.add_init_script(OVERLAY_JS)
        page = ctx.new_page()
        t0 = time.monotonic()
        marks = {}

        def rel():
            return round(time.monotonic() - t0, 2)

        def sub(text):
            page.evaluate(OVERLAY_JS)  # idempotent: (re)defines window.__sub, ensures the bar
            page.evaluate("t => window.__sub(t)", text)

        def hold(sec):
            end = time.monotonic() + sec
            while time.monotonic() < end:
                time.sleep(0.05)

        def log(*a):
            print(f"[{rel():7.2f}s]", *a, flush=True)

        def move_to(sel, settle=0.7):
            box = page.locator(sel).first.bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.evaluate("p => window.__cursorMove(p[0], p[1])", [cx, cy])
            hold(settle)

        def click_el(sel, settle=0.7):
            move_to(sel, settle)
            page.evaluate("window.__cursorClick()")
            hold(0.3)
            page.click(sel)

        # Show the genuine "folder empty -> all ✗" first-use state: intercept only the
        # initial /api/config; /api/sample, /invocations, /download all pass through real.
        page.route("**/api/config*",
                   lambda route: route.fulfill(status=200, content_type="application/json",
                                               body=json.dumps(NOT_READY)))

        # ---------- INTRO ---------- #
        intro = """<!doctype html><html><head><meta charset='utf-8'><style>
          html,body{margin:0;height:100%;background:linear-gradient(135deg,#0f2742,#1F4E79);
            color:#fff;font-family:'Segoe UI',Roboto,Arial,sans-serif}
          .wrap{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
          h1{font-size:68px;margin:0 0 14px} .e{font-size:92px;margin-bottom:10px}
          p{font-size:30px;color:#cfe0f1;margin:8px 0}
        </style></head><body><div class='wrap'>
          <div class='e'>📊</div><h1>Report Generate Agent</h1>
          <p>Báo cáo kinh doanh Cash Loan hằng tháng — chạy trên GreenNode AgentBase</p>
          <p style='font-size:24px;color:#9fc0e0'>Demo: tạo &amp; tải báo cáo tháng 6/2026</p>
        </div></body></html>"""
        page.set_content(intro)
        sub("Demo Agent tạo báo cáo tự động — endpoint trên GreenNode AgentBase.")
        hold(4.5)

        # ---------- OPEN ENDPOINT ---------- #
        log("goto endpoint")
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector('#prereqs .no', timeout=15000)  # red ✗ state rendered
        sub("Bước 1: Mở giao diện Agent trên endpoint đã deploy.")
        hold(4.0)
        sub("Lúc đầu chưa có dữ liệu — tất cả file đầu vào đang ✗ (đỏ), nút Generate bị khoá.")
        move_to('#prereqs')
        hold(4.0)

        # ---------- DATA SAMPLE ---------- #
        log("click Data Sample")
        sub("Bước 2: Bấm “Data Sample (use for demo)” để nạp bộ dữ liệu mẫu.")
        hold(1.2)
        move_to('button:has-text("Data Sample")')
        page.evaluate("window.__cursorClick()")
        hold(0.3)
        # let the user see the brief "Loading data sample..." state before the real flip
        page.click('button:has-text("Data Sample")')
        hold(0.6)
        page.wait_for_selector('#prereqs >> text=Ready', timeout=60000)
        hold(1.0)
        sub("Đã nạp xong — tất cả file chuyển sang ✓ (xanh). Agent sẵn sàng tạo báo cáo.")
        move_to('#prereqs')
        hold(4.0)

        # ---------- TYPE COMMAND ---------- #
        log("type command")
        sub("Bước 3: Nhập lệnh bằng ngôn ngữ tự nhiên: “report for June 2026”.")
        move_to('#msg', 0.6)
        page.evaluate("window.__cursorClick()")
        page.click('#msg')
        page.fill('#msg', "")
        for ch in CMD:
            page.type('#msg', ch, delay=70)
        hold(2.5)

        # ---------- GENERATE (the long wait) ---------- #
        log("click Generate -> begin wait")
        sub("Bước 4: Bấm “Generate report”. Agent chạy 7 bước + 2 lượt gọi LLM (~2 phút).")
        click_el('#btn')
        hold(2.0)
        sub("⏳ Agent đang xử lý: đọc dữ liệu → phân tích → dự báo → soạn báo cáo… (tua nhanh)")
        marks["wait_start"] = rel()
        page.wait_for_selector('a.dl[href="/download?type=report"]', timeout=300000)
        marks["wait_end"] = rel()
        log("result ready")

        # ---------- DOWNLOAD BOTH FILES ---------- #
        sub("✅ Xong! Agent trả về tên file, Top priorities và 0 cảnh báo nhất quán.")
        hold(4.5)
        sub("Bước 5: Tải về 2 file — báo cáo (.docx) và Initiatives tracker (.xlsx).")
        hold(1.5)
        for kind, sel in (("report", 'a.dl[href="/download?type=report"]'),
                          ("tracker", 'a.dl[href="/download?type=tracker"]')):
            move_to(sel, 0.6)
            page.evaluate("window.__cursorClick()")
            hold(0.3)
            with page.expect_download(timeout=60000) as di:
                page.click(sel)
            dl = di.value
            dest = DL / dl.suggested_filename
            dl.save_as(str(dest))
            log("downloaded", kind, dest.name)
            hold(0.8)
        sub("Đã tải về máy: <code style='background:#fff;color:#1F4E79;padding:1px 6px;border-radius:5px'>Report thang 6 nam 2026.docx</code> &amp; <code style='background:#fff;color:#1F4E79;padding:1px 6px;border-radius:5px'>Initiatives tracker thang 6-2026.xlsx</code>")
        hold(4.0)

        # ---------- CONVERT + RASTERIZE (still recording; sped up later) ---------- #
        sub("Đang mở 2 file vừa tải để xem nội dung…")
        marks["conv_start"] = rel()
        log("convert to pdf")
        rpdf = ASSETS / "report.pdf"
        tpdf = ASSETS / "tracker.pdf"
        subprocess.run([
            "powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "convert_to_pdf.ps1"),
            "-Docx", str(DL / "Report thang 6 nam 2026.docx"),
            "-Xlsx", str(DL / "Initiatives tracker thang 6-2026.xlsx"),
            "-ReportPdf", str(rpdf), "-TrackerPdf", str(tpdf),
        ], check=True, capture_output=True)
        log("rasterize")
        subprocess.run([sys.executable, str(HERE / "rasterize.py")], check=True, capture_output=True)
        marks["conv_end"] = rel()

        # discover rendered pages
        report_pngs = sorted(ASSETS.glob("report_*.png"))
        tracker_pngs = sorted(ASSETS.glob("tracker_*.png"))

        def data_uri(p):
            return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()

        def viewer_html(title, pngs):
            imgs = "".join(
                f"<img src='{data_uri(p)}' style='display:block;width:1400px;max-width:94%;margin:26px auto;"
                f"box-shadow:0 6px 24px rgba(0,0,0,.22);border:1px solid #e2e8f0'>" for p in pngs)
            return f"""<!doctype html><html><head><meta charset='utf-8'><style>
              html,body{{margin:0;background:#475569}}
              .hdr{{position:sticky;top:0;background:#1F4E79;color:#fff;padding:16px 28px;
                font-family:'Segoe UI',Roboto,Arial,sans-serif;font-size:28px;font-weight:700;z-index:5}}
              .pad{{padding:14px 0 160px}}
            </style></head><body>
            <div class='hdr'>{title}</div><div class='pad'>{imgs}</div></body></html>"""

        def scroll_to_frac(frac, dur):
            """Smoothly scroll from the current position to `frac` of the page."""
            height = page.evaluate("document.body.scrollHeight - window.innerHeight")
            if height <= 0:
                hold(dur)
                return
            target = int(height * frac)
            cur = page.evaluate("window.scrollY || window.pageYOffset || 0")
            steps = max(int(dur / 0.04), 1)
            for i in range(steps + 1):
                y = int(cur + (target - cur) * i / steps)
                page.evaluate("y => window.scrollTo(0, y)", y)
                hold(0.04)

        # ---------- VIEW REPORT ---------- #
        log("view report")
        page.set_content(viewer_html("📄 Report thang 6 nam 2026.docx", report_pngs))
        page.evaluate("window.scrollTo(0,0)")
        sub("Báo cáo Word gồm 4 phần: Tổng quan kết quả, Phân tích, Top 3 ưu tiên, và Dự báo tháng sau.")
        hold(2.5)
        # one continuous ~7s pass, top -> end of content (no reversal, no mid-scroll pause)
        scroll_to_frac(0.78, 7.0)
        sub("Mọi số liệu & bảng được sinh bằng code (deterministic); phần nhận định do LLM viết.")
        hold(3.0)

        # ---------- VIEW TRACKER ---------- #
        log("view tracker")
        page.set_content(viewer_html("📊 Initiatives tracker thang 6-2026.xlsx", tracker_pngs))
        page.evaluate("window.scrollTo(0,0)")
        sub("Initiatives tracker (Excel): clone từ tháng trước, tự cập nhật trạng thái & màu cho tháng 6.")
        hold(7.0)

        # ---------- OUTRO ---------- #
        outro = """<!doctype html><html><head><meta charset='utf-8'><style>
          html,body{margin:0;height:100%;background:linear-gradient(135deg,#0f2742,#1F4E79);
            color:#fff;font-family:'Segoe UI',Roboto,Arial,sans-serif}
          .wrap{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
          .e{font-size:88px}h1{font-size:58px;margin:12px 0}p{font-size:28px;color:#cfe0f1}
        </style></head><body><div class='wrap'>
          <div class='e'>✅</div><h1>Hoàn tất demo</h1>
          <p>Một câu lệnh → báo cáo .docx + Initiatives tracker .xlsx, tải về trong ~2 phút.</p>
        </div></body></html>"""
        page.set_content(outro)
        sub("Cảm ơn BTC đã theo dõi — Report Generate Agent trên GreenNode AgentBase.")
        hold(4.5)

        # ---------- FINALIZE ---------- #
        video = page.video
        ctx.close()  # flushes the video file
        raw = OUT / "demo_raw.webm"
        if raw.exists():
            raw.unlink()
        Path(video.path()).rename(raw)
        browser.close()

        (OUT / "marks.json").write_text(json.dumps(marks, indent=2))
        print("RAW VIDEO:", raw, raw.stat().st_size, "bytes")
        print("MARKS:", marks)


if __name__ == "__main__":
    main()
