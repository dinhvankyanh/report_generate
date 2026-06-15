#!/usr/bin/env python
"""
Local web UI for the Report Generate Agent.

Run:
    python app.py
then open http://127.0.0.1:5000

Because a browser cannot read arbitrary local folders, this runs as a small
local server with full filesystem access. You pick a folder (native dialog or
by typing a path); the agent reads the Excel inputs there and writes the
report back into that folder.
"""
import io
import json
import queue
import sys
import threading
import subprocess
from pathlib import Path

from flask import Flask, request, Response, jsonify, render_template, send_file

from src import config
from src.agent import ReportGenerateAgent
from src.llm import llm_available

app = Flask(__name__)
_run_lock = threading.Lock()  # only one report generation at a time


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _prereqs():
    """Return (items, trackers, ready): the minimum files needed for a report."""
    items = []
    for f in config.REQUIRED_INPUT_FILES:
        items.append({"name": f, "kind": "file",
                      "ok": (config.DATA_DIR / f).exists(),
                      "detail": "file đầu vào bắt buộc"})

    import re

    def _tk(name):  # sort key by (year, month) parsed from the filename
        m = re.search(r'th[a-z\x00-\xff]*ng\s*(\d+)[-\s](\d{4})', name, re.IGNORECASE)
        return (int(m.group(2)), int(m.group(1))) if m else (0, 0)

    tdir = config.INITIATIVES_TRACKER_DIR
    trackers = []
    if tdir and tdir.exists():
        trackers = sorted((p.name for p in tdir.glob("*.xlsx")
                           if not p.name.startswith("~$")), key=_tk)
    items.append({
        "name": "Initiatives tracker/",
        "kind": "folder",
        "ok": len(trackers) > 0,
        "detail": (f"mới nhất: {trackers[-1]}" if trackers
                   else "cần ≥1 file tracker tháng trước (để clone skeleton)"),
    })
    ready = all(i["ok"] for i in items)
    return items, trackers, ready


def _list_outputs():
    """List generated output files (relative paths) for download links."""
    out = []
    for d in (config.REPORT_DIR, config.TOP_PRIORITIES_DIR, config.OVERALL_PROGRESS_DIR):
        if d and d.exists():
            for p in sorted(d.glob("*")):
                if p.is_file():
                    out.append(str(p.relative_to(config.DATA_DIR).as_posix()))
    return out


def _sse(event, data):
    return f"event: {event}\ndata: {data}\n\n"


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    items, trackers, ready = _prereqs()
    return jsonify({
        "data_dir": str(config.DATA_DIR),
        "mode": config.DATA_SOURCE_MODE,
        "llm_ready": llm_available(),
        "prereqs": items,
        "trackers": trackers,
        "ready": ready,
    })


@app.route("/api/folder", methods=["POST"])
def api_folder():
    path = (request.json or {}).get("path", "").strip()
    if not path:
        return jsonify({"error": "Chưa nhập đường dẫn folder."}), 400
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return jsonify({"error": f"Folder không tồn tại: {path}"}), 400
    config.set_data_dir(p)
    items, trackers, ready = _prereqs()
    return jsonify({
        "data_dir": str(config.DATA_DIR),
        "prereqs": items,
        "trackers": trackers,
        "ready": ready,
    })


@app.route("/api/pick-folder")
def api_pick_folder():
    """Open a native folder dialog in a separate process (reliable on Windows)."""
    code = (
        "import tkinter as tk;from tkinter import filedialog;"
        "r=tk.Tk();r.withdraw();r.attributes('-topmost',True);"
        "p=filedialog.askdirectory();print(p or '')"
    )
    try:
        res = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, timeout=180)
        path = (res.stdout or "").strip().splitlines()[-1] if res.stdout.strip() else ""
        return jsonify({"path": path})
    except Exception as e:
        return jsonify({"path": "", "error": str(e)})


@app.route("/api/parse", methods=["POST"])
def api_parse():
    message = (request.json or {}).get("message", "")
    parsed = ReportGenerateAgent().parse_input(message)
    if not parsed:
        return jsonify({"ok": False})
    month, year = parsed
    return jsonify({"ok": True, "month": month, "year": year,
                    "month_name": config.get_month_name(month)})


@app.route("/api/run")
def api_run():
    month = int(request.args.get("month"))
    year = int(request.args.get("year"))

    def stream():
        if not _run_lock.acquire(blocking=False):
            yield _sse("error", "Đang có một report khác chạy, vui lòng đợi.")
            return
        q: "queue.Queue" = queue.Queue()
        holder = {}

        class _Writer(io.TextIOBase):
            def write(self, s):
                if s:
                    q.put(("log", s))
                return len(s)

        def worker():
            old = sys.stdout
            sys.stdout = _Writer()
            try:
                holder["result"] = ReportGenerateAgent().generate_report(month, year)
            except Exception as e:
                holder["error"] = str(e)
            finally:
                sys.stdout = old
                q.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                kind, payload = q.get()
                if kind == "log":
                    for line in payload.splitlines():
                        if line.strip():
                            yield _sse("log", line.rstrip())
                else:
                    break
            res = holder.get("result", {}) or {}
            ctx = res.get("context", {}) or {}
            pdf_path = ctx.get("pdf_path")
            pdf_rel = None
            if pdf_path:
                try:
                    pdf_rel = str(Path(pdf_path).relative_to(config.DATA_DIR).as_posix())
                except Exception:
                    pdf_rel = None
            result = {
                "success": bool(res.get("success")),
                "error": holder.get("error"),
                "pdf": pdf_rel,
                "files": _list_outputs(),
            }
            yield _sse("result", json.dumps(result, ensure_ascii=False))
        finally:
            _run_lock.release()

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/download")
def api_download():
    rel = request.args.get("rel", "")
    target = (config.DATA_DIR / rel).resolve()
    # Prevent path traversal outside the data folder
    if not str(target).startswith(str(config.DATA_DIR.resolve())) or not target.is_file():
        return jsonify({"error": "File không hợp lệ."}), 400
    return send_file(target, as_attachment=True, download_name=target.name)


def _lan_ip():
    """Best-effort local network IP so other devices can reach the app."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


if __name__ == "__main__":
    import os
    # HOST=0.0.0.0 to allow access from other devices on the same network.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))

    print("=" * 56)
    print("  Report Generate Agent - web UI")
    print("=" * 56)
    print(f"  Tren may nay:     http://127.0.0.1:{port}")
    print(f"                    http://localhost:{port}")
    if host == "0.0.0.0":
        ip = _lan_ip()
        if ip:
            print(f"  Tu may khac (LAN): http://{ip}:{port}")
    else:
        print("  (de may khac trong mang truy cap: chay  HOST=0.0.0.0 python app.py)")
    print("=" * 56)

    app.run(host=host, port=port, debug=False, threaded=True)
