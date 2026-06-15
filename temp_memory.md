# Temp Memory - Report Generate Agent

## Session: 2026-06-15
- User cloned repo report_generate.git
- Set up AgentBase skills in greennode-agentbase-skills/
- Built full Agent code in src/ (Phase 2 with email + manual fallback)
- Fixed KPI reading issue - column name was "Unnamed: 1" changed to "Metric"
- All 7 steps working correctly
- Test run: June 2026 report generated successfully

## Chat History
- "pull repo ... về folder này" → cloned report_generate.git
- "Tạo file settings.local.json..." → created config
- "git clone greennode-agentbase-skills..." → cloned skills
- "Đọc file Agent_build.md..." → read and understood agent requirements
- "Bạn có cần vào từng folder và file..." → Yes, read all Excel files
- "Hãy bắt đầu xây dựng Agent code..." → Started building Phase 2
- "mở file forecast để tôi check..." → User checked Forecast.xlsx
- "mở file Performance analysis..." → User checked Performance analysis
- "vì sao đang không đọc đúng KPI..." → Fixed KPI reading
- "bạn đã lưu tất cả thông tin chat của session này vào temp_memory.md chưa?" → Auto-saving now
- "mở file Forecast.xlsx để tôi check" → User checked Forecast output
- "mở file Performance analysis.xlsx để tôi check" → User checked Performance output
- "vì sao đang không đọc đúng KPI từ file KPI?..." → Fixed KPI reading in step3
- "bạn đã lưu tất cả thông tin chat của session này vào temp_memory.md chưa?..." → Auto-saving enabled
- "Bây giờ tôi muốn update lại file Agent_build.md..." → User updated Agent_build.md
- "Update lại file Agent_build.md mới và fix these 3 changes..." → Fixed step2, step3, step4

## Project Overview
- **Project**: Agent report generate hàng tháng cho VNG
- **Mục tiêu**: Tự động generate PDF report hàng tháng qua chat
- **Input**: "làm report tháng X năm Y"
- **Output**: PDF report trong folder Report/

## Files/Folders Structure
| File/Folder | Status | Description |
|-------------|--------|-------------|
| Metrics.xlsx | ✅ | 13 metrics template |
| KPI.xlsx | ✅ | KPI 12 tháng 2026 |
| Actual performance.xlsx | ✅ | Data Jan-Jun 2026 |
| Annual planning.xlsx | ✅ | 12 initiatives |
| Initiatives tracker/ | ✅ | File tháng 5-2026 |
| Top 3 priorities/ | ✅ | Generated |
| Overall progress/ | ✅ | Generated |
| Report/ | ✅ | PDF generated |
| greennode-agentbase-skills/ | ✅ | Skills để deploy lên cloud |

## Agent Workflow (7 Steps) - ✅ ALL WORKING
1. **Step 1**: Get Initiatives Data (from email or Excel)
2. **Step 2**: Update Status Change (compare with previous month)
3. **Step 3**: Performance Analysis (MoM vs KPI)
4. **Step 4**: Forecast (baseline + init-based)
5. **Step 5**: Top 3 Priorities
6. **Step 6**: Annual Planning Progress
7. **Step 7**: Generate PDF Report

## Design Decision
- **Phase 2** (Email integration) - code flexible, tự động fallback về Phase 1 (manual/excel) nếu không có email
- **Chat interface**: Agent nhận input dạng "lam report thang 6 nam 2026"
- **Interactive review**: User chat lại nếu cần sửa

## Current Status - ✅ COMPLETED
- Agent code hoàn chỉnh trong src/
- Test thành công với tháng 6 năm 2026
- Output files đã được tạo:
  - Report/Report_thang_6_nam_2026.pdf
  - Top 3 priorities/Top 3 priorities for month 7-2026.md
  - Overall progress/Overall progress June 2026.md
  - Performance analysis.xlsx
  - Forecast.xlsx

## Latest Fix (2026-06-15)
- **Fixed KPI reading**: Changed column name from "Unnamed: 1" to "Metric" in step3 and step4
- **Updated Agent_build.md**: User updated file with new specifications
- **Fixed Step 2**: Status change "No change" → "No"
- **Fixed Step 3**: Comments now "over/under/reach" instead of "On track/Over/Under"  
- **Fixed Step 4**: Column names now match Agent_build.md spec

## Verified Outputs (2026-06-15)
- Performance analysis.xlsx: Comment = reach/under/over ✅
- Forecast.xlsx: Columns = "July 2026 baseline forecast", "July 2026 init based forecast" ✅
- Column order fixed: May(Actual) → Jun(KPI) → Jun(Actual) → %MoM → %KPI → Comment ✅

## Next Steps (Optional)
1. Deploy lên AgentBase sử dụng greennode-agentbase-skills
2. Thêm email integration (Phase 2 đầy đủ)
3. Cải thiện UI (web-based)

---

# Session: 2026-06-15 → 2026-06-16 (MAJOR rework)

## Chat history (tóm tắt theo yêu cầu của user)
1. "Đọc file Agent_build.md và code đã viết để hiểu status hiện tại" → đọc toàn bộ src/, tóm tắt trạng thái + liệt kê bug.
2. "muốn aware template của Initiatives tracker tháng X" → xác nhận template = bản sao Annual Planning + 2 dòng (title, hint); 5 cột status (PIC, Status, New timing, Details, How confident) điền từ email (Step 1) + Status change Yes/No (Step 2). Phát hiện file tháng 6 cũ SAI template (dump mỗi email 1 dòng).
3. "Dùng tháng X-1 làm skeleton gốc cho khung dòng" → chốt: clone khung dòng (No, Initiative Names, Timing, Expected impact, sections) từ tháng X-1; chỉ điền 5 cột status.
4. User chỉ ra output tháng 6 sai ở #2,3,4,5,7,10,11 (giá trị đúng nằm trong toàn bộ email inbox, không chỉ 3 email mẫu) → kết luận regex không đọc nổi thread tiếng Việt, cần LLM.
5. AskUserQuestion → user chọn: (a) dùng **LLM extraction**, (b) qua **GreenNode platform LLM** (OpenAI-compatible).
6. User cung cấp LLM_API_KEY + LLM_MODEL=qwen/qwen3-5-27b → tạo .env, test thật.
7. "#11 giữ là No" + 2 quyết định logic: no-email initiative → LLM suy luận từ dòng X-1; off-track giữ New timing đã chốt (bỏ ràng buộc "No ⇒ rỗng").
8. "chạy lại agent từ đầu tới cuối xem còn lỗi" → tìm & fix loạt bug Step 3–7.
9. "đổi cột Perf analysis (May (Actual)/KPI Jun/Jun (Actual)) + mọi file calc copy format Metrics (No, Unit, % có dấu %, số làm tròn)".
10. "Forecast lưu % dạng tỷ lệ (0.35) giống Perf analysis".
11. "thêm interface chat box web-based + chọn folder local" → build Flask web app.
12. "làm sao biết đường link agent" → giải thích localhost/LAN/public + in banner link.
13. "Tạo file run_agent_reportgenerate.bat (double-click chạy + tự mở browser)".
14. "Lưu history vào temp_memory.md + update Agent_build.md".

## Thay đổi kiến trúc lớn
- **Email extraction chuyển từ regex → LLM** (OpenAI-compatible, GreenNode MAAS).
  - Endpoint: `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1`, key ở `.env` (`LLM_API_KEY`), model `qwen/qwen3-5-27b` (`LLM_MODEL`).
  - **QUAN TRỌNG**: qwen3 là model "thinking" → prompt lớn gây treo 363s. Fix: `/no_think` + `extra_body={chat_template_kwargs:{enable_thinking:false}}` + `max_tokens=2000` + `timeout=90` + `max_retries=0`. Sau fix: ~15–28s.
  - Email gom theo thread (subject chuẩn hoá), **sort theo ngày tăng dần** (Gmail trả newest-first → phải sort để lấy đúng message mới nhất), strip quoted lines để giảm token.
  - Gmail credentials/token để ở PROJECT_ROOT (tách khỏi DATA_DIR chọn được).
- **Step 1 viết lại**: clone skeleton X-1 (giữ title/hint/header/sections + No/Initiative Names/Timing/Expected impact), gọi LLM trả updates theo No, áp dụng; carry-forward cột khi không có update. Rule-B: no-email + timing đã qua + details "deployed/done" → roll sang Live (vd #5).
- **Step 2 viết lại**: Status change Yes/No so với X-1; GIỮ New timing kể cả khi No (theo quyết định user).
- **tracker_writer.py** (mới): writer chung giữ template, cả Step 1 & 2 dùng.

## Bug đã fix (Step 3–7 + wiring)
- Step 4: typo `%Submission/Trailffic`→`Traffic`; đọc nhầm cột `Initiative`→`Initiative Names`; status filter; match timing X+1 (effective timing, Delay chỉ tính khi có new timing đúng X+1, loại Live/Done/Deprioritized/Not started); **Disbursement scale** theo tỷ lệ thực tháng hiện tại (tránh sai ~1000×).
- Step 3: thêm **MoM Comment** (increase/decrease/same) cạnh **KPI Comment** (over/under/reach).
- Step 5: loại initiative Live/Done/Deprioritized + section khỏi top-3.
- Step 6: coi `Live` như On track/Done; No dạng int; lưu structured lists vào context cho PDF.
- Step 7 (PDF): viết lại bằng **fpdf2** (font Unicode `C:/Windows/Fonts/arial.ttf` → tiếng Việt OK); dùng `pdf.table()`; đọc đúng cột forecast `(actual)/(forecast)`; hiện đủ 13 dòng; set `context["pdf_path"]`; fallback ghi tên `(1)` khi file bị khoá; reset X về lề trái trước multi_cell/table (fix "Not enough horizontal space").
- LLM extraction trả về 7/7 initiative khớp 100% yêu cầu user (#1 Live/May-26, #2 Delay/Oct-26/Medium, #3 On Track/Sep-26/Medium, #4 Live/Jun-26, #5 Live/May-26 roll-forward, #7 Deprioritized/Q4-2026/Medium, #10 Delay/Low).

## Format file calc (theo Metrics)
- Perf analysis + Forecast: thêm cột **No** + **Unit** (từ Metrics.xlsx, map theo tên + fallback theo thứ tự).
- Metric `Unit=%` → hiển thị có dấu **%**; metric số → **làm tròn không thập phân** + phân cách nghìn; sửa `-0%`→`0%`.
- Perf analysis đổi cột động: `No|Metric|Unit|{X-1} (Actual)|KPI {X}|{X} (Actual)|MoM change %|MoM Comment|Vs KPI|KPI Comment`.
- **Cả 2 file giờ lưu % dạng tỷ lệ 0.35** (Forecast trước lưu 35.0, đã /100 khi build row). Module `metrics_format.py`.

## Web app (đóng gói)
- `app.py` (Flask): `/`, `/api/config`, `/api/folder`, `/api/pick-folder` (native tkinter qua subprocess), `/api/parse`, `/api/run` (SSE stream log + result), `/api/download`. Lock 1 run/lần.
- `templates/index.html`: chat box + folder picker + log panel realtime + nút tải PDF/file.
- `config.set_data_dir()` cho phép chọn data folder runtime (đã verify SSE end-to-end: 54 log events, success).
- `requirements.txt`, `run_agent_reportgenerate.bat` (double-click: tìm Python, pip install lần đầu, chạy server, tự mở http://localhost:5000). Link in banner; HOST=0.0.0.0 để LAN.
- Bug phụ đã fix: lọc file lock Excel `~$*.xlsx` khỏi finder + UI.

## Trạng thái cuối (đợt 1)
- Chạy full 7 step end-to-end OK (CLI + web). LLM ~15–28s/run.
- Lưu ý: lần đầu cần OAuth Gmail nếu chưa có `gmail_token.pkl`; cần `.env` có LLM_API_KEY + LLM_MODEL.

---

# Session: 2026-06-16 (đợt 2 — UI prereqs, fixes, .docx analytical report)

## Chat history
1. "chạy run_agent_reportgenerate.bat bị lỗi: No initiatives tracker file found for 5/2026" → folder chọn thiếu thư mục con `Initiatives tracker`/file X-1. Code đúng; thêm thông báo lỗi rõ + cảnh báo UI.
2. "Step 1 clone skeleton từ X-1, report T7 phải lấy file T6" → đổi sang exact, RỒI user đính chính: vẫn dùng "file gần nhất ≤ X-1" (exact=False, fallback). Revert giữ exact=False. Verify: T6→clone T5, T7→clone T6.
3. Phát hiện user đã tách dữ liệu sang folder riêng `Report_Sample/` (project root trống) — đúng workflow. `Report_Sample/Initiatives tracker/` có tháng 5 + 6.
4. "hiển thị UI các file prerequisites tối thiểu" → thêm checklist prereqs (4 Excel + thư mục Initiatives tracker ≥1 file) với ✓/✗; `ready` tính cả tracker → thiếu là chặn chạy. Sửa bug "mới nhất" sort theo tháng/năm (trước sort alphabet → nhầm).
5. "vì sao ô E3 (KPI Jun của %mom growth) trống?" → tên metric lệch giữa Actual ("use base") và KPI ("user base"). Sửa `_get_kpi_for_metric` match chuẩn hoá + fuzzy (difflib cutoff 0.8). E3 = 5%.
6. "Access Report_05-2026.docx, học wording/bố cục/visual/logic, generate report tương tự" → AskUserQuestion: chọn (a) output **.docx** theo mẫu (thay PDF), (b) **LLM viết narrative**. Build mới.
7. "xóa câu footer + chỉnh màu giống mẫu" → bỏ dòng footer; áp bảng màu mẫu.

## Lỗi đã fix
- Tracker finder: skeleton = file gần nhất ≤ X-1 (exact=False); bỏ qua file lock `~$*.xlsx`.
- KPI lookup (Step 3): match chuẩn hoá + fuzzy → chịu lệch tên metric giữa Actual/KPI (vd "use base" vs "user base"). Khuyến nghị giữ tên metric nhất quán với Metrics.xlsx.
- Tách credentials Gmail (credentials.json, gmail_token.pkl, sample_emails.json) về PROJECT_ROOT; data folder (Excel + output) chọn runtime qua `config.set_data_dir`.

## MAJOR: Report .docx phân tích (theo Report_05-2026.docx)
- Tham chiếu mẫu `Report_05-2026.docx` (CL – Biz – Report). Bố cục 4 phần cố định, mỗi phần tách Structural ceiling unlocks vs Incremental acquisition/retention.
- **`src/llm/report_writer.py`** (mới): `build_report_data()` dựng số liệu (KPI funnel table prev/cur/MoM/Plan/vsPlan, YTD+FY Disbursement, initiatives theo section, forecast) + `generate_narrative()` gọi LLM (qwen3, no_think, max_tokens=4000) viết narrative theo `STYLE_GUIDE`. Số liệu deterministic, văn do LLM.
- **`src/steps/step7_generate_report.py`** (mới, thay step7 PDF): render **.docx** (python-docx). Layout: Header (code + meta + Data basis) → KPI snapshot table + "Read:" → §1 Headline/MoM bridge(fact)/Plan-miss bridge(fact) + bullet Structural/Incremental → §2 Run-rate + bullets → §3 bảng Top Priorities → §4 bảng Structural(Confidence/Status)+Incremental(Impact/Status) + YTD/FY outlook + Risks bullets.
- Logic học từ mẫu: phân rã MoM/plan-miss bằng số (vd "Traffic ×1.38 ≈ +38%"), ánh xạ metric→initiative (persona/status/timing), tách Structural/Incremental, YTD + điều kiện FY, risks theo initiative.
- Wiring: `steps/__init__` dùng `Step7GenerateReport`; context["report_path"] (+pdf_path compat); UI nút "Tải report (.docx)"; requirements +python-docx (bỏ fpdf2); .bat check import docx.
- Output: `Report/Report thang X nam Y.docx`. Fallback đổi tên (n) nếu file đang mở.

## Màu sắc (khớp mẫu)
- Xanh đậm `#1F4E79`: title (18pt), sub-heading (11pt), Heading 1, **nền header bảng** (chữ trắng).
- Xám `#595959`: subtitle + Data basis.
- Nhãn dẫn (Headline./MoM bridge./Read:) bold phần nhãn.
- Đã xóa câu footer "Generated by…".

## Web UI prerequisites
- `/api/config` & `/api/folder` trả `prereqs` (list {name, kind, ok, detail}) + `ready`. UI render checklist ✓/✗ + dòng "Đã đủ điều kiện / Chưa đủ".
- 5 mục: Metrics.xlsx, KPI.xlsx, Actual performance.xlsx, Annual planning.xlsx, Initiatives tracker/ (≥1 file tháng trước).

## Trạng thái cuối (đợt 2)
- Full 7 step OK; deliverable chính giờ là **.docx phân tích** (thay PDF). 2 LLM call/run (cào email + viết narrative) → ~1–2 phút.
- Data folder demo: `D:\Hackathon2026\report_generate\Report_Sample` (có đủ Excel + Initiatives tracker tháng 5,6).
- Mẫu tham chiếu: `Report_05-2026.docx` ở project root.