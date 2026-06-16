# Agent Report Generate — Build Documentation (latest)

> Cập nhật: 2026-06-16. Tài liệu này phản ánh hệ thống **đã triển khai thực tế**
> (không chỉ là spec). Spec gốc theo tháng X/năm Y được giữ ở mục "Yêu cầu nghiệp vụ".

Agent tự động generate report tháng X/năm Y: đọc dữ liệu Excel + cào email (qua
LLM), tính toán, và xuất **report .docx phân tích** (bám mẫu `Report_05-2026.docx`)
+ các file phụ trợ. Có **giao diện chat web** để chạy.

---

## 1. Cách chạy

### Web UI (khuyến nghị)
- **Double-click `run_agent_reportgenerate.bat`** → tự cài deps lần đầu, chạy server, mở trình duyệt.
- Hoặc thủ công:
  ```bash
  pip install -r requirements.txt
  python app.py            # mở http://localhost:5000
  # LAN: $env:HOST="0.0.0.0"; python app.py  -> http://<IP-may>:5000
  ```
- Trên UI: **Chọn folder** dữ liệu (hộp thoại native hoặc dán path) → xem **checklist file prerequisites** (✓/✗) → gõ **"làm report tháng 6/2026 giúp tôi"** → xem tiến trình realtime → tải report **.docx**.

### CLI
```bash
python run_agent.py        # chạy cứng tháng 6/2026 (sửa trong file)
# hoặc dùng interactive chat:
python -c "from src.agent import ReportGenerateAgent; ReportGenerateAgent().chat()"
```

---

## 2. Cấu hình (`.env` ở project root)
```
DATA_SOURCE_MODE=email          # "email" (Gmail+LLM) hoặc "manual" (chỉ Excel)
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_API_KEY=<GreenNode key>     # bắt buộc cho email mode
LLM_MODEL=qwen/qwen3-5-27b      # model `path` từ aip.sh models
LLM_TIMEOUT=90
```
- **Gmail**: cần `credentials.json` + `gmail_token.pkl` ở **project root** (tách khỏi data folder). Lần đầu mở OAuth qua browser.
- **Data folder** (chứa Excel input + output): chọn runtime qua web (`config.set_data_dir`), mặc định = project root. Credentials KHÔNG nằm trong data folder.

---

## 3. Kiến trúc code
```
app.py                         # Flask web UI (chat + chọn folder + SSE stream + download)
run_agent.py                   # CLI runner
templates/index.html           # giao diện chat
run_agent_reportgenerate.bat   # launcher double-click
requirements.txt
src/
├── agent.py                   # ReportGenerateAgent: parse "tháng X năm Y" + chạy 7 step
├── config.py                  # paths, set_data_dir(), LLM_CONFIG, REQUIRED_INPUT_FILES, đọc .env
├── llm/
│   ├── extractor.py           # LLM email-thread → structured updates (OpenAI-compatible)
│   └── report_writer.py       # dựng số liệu + LLM viết narrative cho report .docx
├── data_sources/
│   ├── base.py                # interface
│   ├── manual_source.py       # đọc Excel; get_initiatives_raw (skeleton), get_initiatives_data
│   ├── email_source.py        # Gmail fetch (get_raw_emails) + parser regex (legacy/fallback)
│   └── gmail_service.py       # OAuth2 + search/get email
└── steps/
    ├── step1_email_or_manual.py   # build tracker từ skeleton X-1 + LLM updates
    ├── step2_status_change.py     # Status change Yes/No
    ├── step3_performance_analysis.py
    ├── step4_forecast.py
    ├── step5_top_3_priorities.py
    ├── step6_annual_progress.py
    ├── step7_generate_report.py   # render .docx phân tích (python-docx) — ACTIVE
    ├── step7_generate_pdf.py      # (legacy, không còn dùng)
    ├── tracker_writer.py          # writer chung giữ template tracker (lock-resilient)
    ├── excel_io.py                # save_sheet lock-resilient (Step 3 & 4)
    └── metrics_format.py          # No/Unit + format %/số làm tròn theo Metrics
```

---

## 4. Quy trình 7 bước (đã triển khai)

**Step 1 — Build Initiatives tracker tháng X**
- Clone **skeleton từ tháng X-1** (giữ nguyên title row, hint row, header, dòng section
  "Strategic unlock"/"Incremental improvements", và 4 cột kế hoạch: No, Initiative Names,
  Timing, Expected impact).
- Cào email Gmail 6 tháng → in **banner nguồn dữ liệu** (">>> DATA SOURCE: LIVE GMAIL (N)"
  hoặc "sample_emails.json (N)"). Khi LIVE: tự ghi email (ẩn danh địa chỉ → personN@demo.local,
  lọc relevant) vào `sample_emails.json` để bản offline/BTC khớp live.
- Gom email theo **thread** (`normalize_subject` bỏ Re/Fwd + hậu tố "(...)"; sort tăng dần
  theo ngày; giữ ~4 message mới nhất/thread vì email quote nội dung cũ inline gây nhiễu recency).
- **2-pass thread→initiative mapping** (xử lý cross-thread / same-name):
  - **Pass 1** `_map_threads_to_initiatives`: LLM map mỗi thread → No(s). Cho phép 1 thread
    update NHIỀU init (modelling↔personalization) và NHIỀU thread cùng 1 init.
  - **Gộp hybrid**: thread map đúng **1 init** → gộp chronological (latest thắng) — vd
    "Partner 2 — onboarding" + "Onboard Partner A" → #2 (ra kế hoạch 2-phase mới nhất).
    Thread **đa-init** → giữ nguyên (tránh lẫn) → #3/#10 không nhiễu của nhau.
- **Pass 2** extract: LLM (`/no_think`, `seed=7`, `max_tokens=8000`) trả JSON theo `No`:
  {status, new_timing, **timing_start, timing_months**, details, confidence, pic, metric_claims}.
  - Prompt: **recency wins** (tin mới đảo tin cũ, kể cả reversal qua thread khác tên);
    **disambiguate same-name initiatives** theo planned timing/persona (vd 2 init "Add 1 partner").
  - **Tính tháng bằng CODE** (`_add_months`): LLM trích `timing_start`+`timing_months`,
    code cộng → "cuối T6 + 2 tháng" = Aug-26 (LLM tự tính tháng không đáng tin).
- Điền 5 cột status; row không có update → **carry-forward** từ X-1.
- **Completeness sweep / roll-forward (Rule B)**: init không email + planned/new timing đã qua
  + prev "ready to pilot / deployed / done" → roll thành **Live** (vd #1 ready-pilot May → Live ở T6).
- `metric_claims` (level metric email khẳng định) → lưu context cho Rule 3 (Step 7 reconcile).
- Helper LLM dùng chung `_chat_json` / `_json_obj` (hỗ trợ cả model reasoning). ~3 LLM call/run.
- Vocab status: Not started / On Track / Delay / Deprioritized / Done / Live.
- Ghi file giữ template (`tracker_writer`, lock-resilient). Fallback `sample_emails.json` nếu không có Gmail.

**Step 2 — Status change**
- So Status tháng X vs X-1: khác → "Yes", giống → "No", mới → "Yes".
- **Giữ New timing đã chốt** kể cả khi Status change = No (vd item Deprioritized vẫn giữ Q4-2026).
- Ghi lại file tracker với cột Status change.

**Step 3 — Performance analysis** (sheet `Perf analysis {tháng} {năm}`)
- So MoM (tháng X vs X-1) và vs KPI (tháng X).
- 2 comment: **MoM Comment** (increase/decrease/same) + **KPI Comment** (over/under/reach).
- Cột: `No | Metric | Unit | {X-1} (Actual) | KPI {X} | {X} (Actual) | MoM change % | MoM Comment | Vs KPI | KPI Comment`.
- Tra cứu KPI theo tên **chuẩn hoá + fuzzy** (difflib) → chịu lệch tên metric giữa Actual/KPI (vd "use base" vs "user base"). Nên giữ tên metric nhất quán với Metrics.xlsx.

**Step 4 — Forecast tháng X+1** (sheet `Forecast {tháng X+1} {năm}`)
- Lấy %metric của tháng X làm run-rate; nếu có initiative **launch trong X+1** (On Track/Delay
  có new timing trỏ đúng X+1) → cộng impact uplift. Loại Live/Done/Deprioritized/Not started.
- Chain: Total User Base ×(1+%mom) → Eligible → Traffic → Submission → Approved; Avg Ticket ×(1+%mom);
  **Disbursement = Approved×AvgTicket× scale** (scale = tỷ lệ thực tháng hiện tại, tránh sai đơn vị).
- Cột: `No | Metric | Unit | {X} (actual) | {X+1} (forecast) | Initiative notes`.

**Step 5 — Top 3 priorities** (markdown trong `Top 3 priorities/`)
- Lọc bỏ Live/Done/Deprioritized + section → sắp xếp **impact giảm dần, rồi timeline gần→xa** → lấy 3.
- Initiative high-impact đang **Delay/Deprioritized** được liệt kê riêng ở đoạn **Escalations**
  trong report (xem Step 7), không trộn vào top-3.

**Step 6 — Overall progress vs Annual planning** (markdown)
- Tách (i) Strategic Unlock / (ii) Incremental Improvements.
- On Track/Done/Live → note trạng thái; Not started/Delay/Deprioritized → comment từ Details + New timing.

**Step 7 — Report .docx phân tích** (`Report/Report thang X nam Y.docx`)
- Bám layout/wording/logic của mẫu `Report_05-2026.docx`. Số liệu/bảng tính deterministic;
  **narrative do LLM viết** (`report_writer.generate_narrative`, qwen3 no_think, max_tokens 4000).
- Bố cục (mỗi phần tách Structural ceiling unlocks vs Incremental acquisition/retention):
  - **Header**: report code + dòng meta (Reporting month / Latest actual / Forecast month) + Data basis.
  - **KPI snapshot — funnel** (bảng `Metric | Unit | {X-1} | {X} | MoM | {X} Plan | vs Plan`) + đoạn "Read:".
  - **KPI snapshot** kèm dòng **"Movement check"** (Rule 7 — deterministic): metric tuyệt đối
    tăng nhưng rate đứng yên → MECHANICAL; rate cải thiện → REAL.
  - **1. Performance Overview**: Headline → MoM bridge (fact, phân rã có số) → Plan-miss bridge → bullet Structural/Incremental ánh xạ initiative.
  - **2. Next Month Run-Rate**: run-rate + structural/incremental.
  - **3. Top Priorities** (bảng `# | Objective/lever | Initiative & owner | Target & why`).
  - **4. Progress Toward Annual Plan**: bảng Structural (Confidence/Status) + Incremental (Impact/Status)
    + YTD vs plan & FY outlook + Risks + **Escalations** (bảng deterministic: initiative Delay/Deprioritized,
    impact giảm dần) + **To verify — source conflicts** (Rule 3: email vs actuals lệch quá ngưỡng).
- **Màu** (khớp mẫu): xanh `#1F4E79` cho title(18pt)/sub-heading(11pt)/Heading1/nền header bảng (chữ trắng); xám `#595959` cho subtitle + Data basis; bold nhãn dẫn (Headline./MoM bridge./Read:).
- Fallback đổi tên `(n).docx` nếu file đang mở; nếu LLM không cấu hình → render bảng + text tối thiểu.

---

## 5. Định dạng file calc (theo Metrics.xlsx)
- Mọi file calc tự sinh (Perf analysis, Forecast) có cột **No** + **Unit** (lấy từ `Metrics.xlsx`).
- Metric `Unit=%` → hiển thị có dấu **%**; metric số (`000`/`VNDm`) → **làm tròn không thập phân** + phân cách nghìn.
- **Lưu nội bộ % dạng tỷ lệ 0.35** ở cả 2 file (đồng nhất); hiển thị ra "35%".
- Module dùng chung: `src/steps/metrics_format.py`.
- Template Initiatives tracker = bản sao Annual Planning + 2 dòng phụ (title, hint) — 10 cột:
  `No | Initiative Names | Timing | Expected impact | PIC | Status | Status change | New timing (if applicable) | Details from that month | How confident`.

---

## 6. Lưu ý kỹ thuật quan trọng
- **qwen3 là model "thinking"** → với prompt lớn dễ treo (đã gặp 363s). Bắt buộc tắt thinking:
  thêm `/no_think` vào prompt + `extra_body={"chat_template_kwargs":{"enable_thinking":false}}`
  + `max_tokens` + `timeout` + `max_retries=0` + `seed`. Sau fix ~15–28s/run.
- **Đọc email đúng (2-pass)**: Pass-1 map thread→initiative No(s); **gộp** thread cùng 1 init
  (kể cả khác tên: "Partner 2 — onboarding" + "Onboard Partner A" → #2), **giữ riêng** thread
  đa-init (tránh lẫn #3↔#10). Giữ ~4 msg mới nhất/thread. Prompt: recency wins (đảo ngược qua
  thread khác tên), disambiguate same-name theo timing, completeness sweep (ready+past→Live).
  **Tính tháng bằng code** (`timing_start`+`timing_months`) vì LLM tính tháng sai.
- **Bộ lọc email** linh hoạt: `[Product]/[CL]/[Partnership(s)]` + từ khoá `initiative`/`partner`
  (tránh sót email tiêu đề biến thể). Nếu BTC dùng tag khác → nới `RELEVANT_SUBJECT`.
- Email Gmail trả **newest-first** → phải sort theo ngày để LLM lấy đúng message mới nhất.
- **Lock-resilient writes**: khi file output đang MỞ trong Excel (PermissionError), Step3/4
  (`excel_io.save_sheet`), tracker (`tracker_writer`) và step7 docx ghi đè sang bản "(n)" đầu
  tiên. **Không mở file output trong Excel khi chạy agent** — sẽ ghi sang bản phụ thay vì file gốc.
- Lọc bỏ file lock Excel `~$*.xlsx` khỏi finder tracker.
- Web local vì browser không truy cập được folder tuỳ ý; deploy cloud sẽ MẤT khả năng đọc folder local.
- **Skeleton tháng X-1**: lấy file tracker gần nhất ≤ X-1 (report T7 → clone T6; thiếu T6 → fallback T5).
- **Web UI prerequisites**: `/api/config` & `/api/folder` trả checklist 5 mục bắt buộc
  (Metrics, KPI, Actual performance, Annual planning + thư mục `Initiatives tracker/` có ≥1 file
  tháng trước). Thiếu bất kỳ mục nào → `ready=false`, UI chặn chạy và hiện ✗.

---

## 7. Yêu cầu nghiệp vụ gốc (spec tham chiếu)
Khi chạy report tháng X năm Y, agent dùng đúng file theo tháng (file "X" lấy tháng X; "X+1" lấy
tháng X+1). Quy trình: (1) cào email 6 tháng update Initiatives tracker tháng X; (2) so X-1 ra
Status change; (3) Performance analysis (MoM + KPI); (4) Forecast X+1; (5) Top 3 priorities;
(6) Overall progress vs Annual planning; (7) report .docx gồm 4 mục: Performance Overview &
Analysis / Next Month Run Rate & Key initiatives / Top priorities / Overall Progress toward
Annual Planning (tách Strategic Unlock & Incremental improvements).

Files sử dụng: Metrics, KPI, Annual planning, Actual performance, Initiatives tracker/ (nhiều
file theo tháng), Performance analysis (nhiều sheet), Forecast (nhiều sheet), Top 3 priorities/
(markdown), Overall progress toward Annual planning/ (markdown).
