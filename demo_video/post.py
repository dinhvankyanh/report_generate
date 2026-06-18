"""Post-process the raw recording: speed up the wait + conversion segments,
keep everything else at 1x, and export a compatible MP4."""
import json
import subprocess
import sys
from pathlib import Path
import imageio_ffmpeg

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
OUT = HERE / "out"
RAW = OUT / "demo_raw.webm"
FINAL = OUT / "Report_Generate_Agent_Demo.mp4"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

marks = json.loads((OUT / "marks.json").read_text())

# (start, end, speed) for the two segments we compress; gaps stay at 1x.
fast = [
    (marks["wait_start"], marks["wait_end"], 12.0),   # the ~2 min agent run
    (marks["conv_start"], marks["conv_end"], 8.0),    # opening/converting the files
]
fast.sort()

# Build an ordered segment list covering [0 .. EOF]; last is open-ended.
segs = []  # (start, end_or_None, speed)
cur = 0.0
for s, e, spd in fast:
    if s > cur:
        segs.append((cur, s, 1.0))
    segs.append((s, e, spd))
    cur = e
segs.append((cur, None, 1.0))  # remainder to end of file

parts, labels = [], []
for i, (s, e, spd) in enumerate(segs):
    trim = f"trim={s}:{e}" if e is not None else f"trim={s}"
    pts = "PTS-STARTPTS" if spd == 1.0 else f"(PTS-STARTPTS)/{spd}"
    parts.append(f"[0:v]{trim},setpts={pts}[v{i}]")
    labels.append(f"[v{i}]")
filtergraph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(segs)}:v=1:a=0[out]"

cmd = [
    FFMPEG, "-y", "-i", str(RAW),
    "-filter_complex", filtergraph, "-map", "[out]",
    "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    str(FINAL),
]
print("segments:", segs)
print("running ffmpeg...")
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[-3000:])
    sys.exit(1)
print("FINAL:", FINAL, FINAL.stat().st_size, "bytes")
