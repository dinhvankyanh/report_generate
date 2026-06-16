# Report Generate Agent — Hướng dẫn chạy thử (cho Ban tổ chức)

Agent tự động sinh **báo cáo kinh doanh hàng tháng** (Cash Loan) dạng `.docx` từ dữ liệu
Excel + email cập nhật initiative. Bản submit này chạy **hoàn toàn offline** — không cần
tài khoản Google của tác giả.

> Dữ liệu trong bản nộp là **tổng hợp/ẩn danh** (công ty, đối tác, persona, số liệu, email
> đều là giả lập). Không có dữ liệu thật hay credential cá nhân nào được kèm theo.

---

## 1. Yêu cầu
- Python 3.10+ (đã test 3.14) trên Windows.
- 1 **LLM API key** (OpenAI-compatible). Bản demo dùng GreenNode AI Platform.
  → Ban tổ chức dùng key **tạm** do tác giả cấp riêng (gửi ngoài repo), điền vào `.env`.

## 2. Cấu hình `.env`
Tạo file `.env` ở thư mục gốc (copy từ `.env.example`) với nội dung:
```
DATA_SOURCE_MODE=manual
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_API_KEY=<key tạm do tác giả cấp>
LLM_MODEL=qwen/qwen3-5-27b
```
- `DATA_SOURCE_MODE=manual` → agent đọc email từ `sample_emails.json` (email tổng hợp),
  **không cần Google credentials**.
- Không cần `credentials.json` / `gmail_token.pkl` (đã loại khỏi bản nộp).

## 3. Chạy
**Cách 1 — Web UI (khuyến nghị):**
```
pip install -r requirements.txt
python app.py
```
→ Mở http://localhost:5000 → bấm **Chọn folder** trỏ vào thư mục `Report_Sample/`
(đi kèm bản nộp, đã có đủ file đầu vào) → kiểm tra checklist hiện ✓ đủ điều kiện →
gõ **"làm report tháng 6/2026"** → xem tiến trình → tải file `.docx`.

> Trên Windows có thể double-click `run_agent_reportgenerate.bat` (tự cài deps + mở trình duyệt).

**Cách 2 — CLI:**
```python
python -c "from src import config; config.set_data_dir('Report_Sample'); \
from src.agent import ReportGenerateAgent; ReportGenerateAgent().generate_report(6,2026)"
```

## 4. Kết quả
Sinh trong `Report_Sample/`:
- `Report/Report thang 6 nam 2026.docx` — **báo cáo chính** (4 phần phân tích).
- `Initiatives tracker/Initiatives tracker thang 6-2026.xlsx`, `Performance analysis.xlsx`,
  `Forecast.xlsx`, `Top 3 priorities/*.md`, `Overall progress.../*.md`.

Thời gian: ~1–2 phút (2 lần gọi LLM: trích xuất email + viết narrative).

## 5. Thư mục dữ liệu (`Report_Sample/`)
Cần tối thiểu (đã kèm sẵn):
```
Report_Sample/
├── Metrics.xlsx, KPI.xlsx, Actual performance.xlsx, Annual planning.xlsx
└── Initiatives tracker/Initiatives tracker thang 5-2026.xlsx   (tháng X-1, làm skeleton)
```

## 6. Ghi chú kiến trúc
Chi tiết 7 bước, kiến trúc code, và quy tắc tính toán: xem `Agent_build.md`.
Bản chạy live (cào Gmail thật) dùng `DATA_SOURCE_MODE=email` + `credentials.json` của Google —
KHÔNG kèm trong bản nộp vì lý do bảo mật; bản offline này tái lập đầy đủ kết quả từ
`sample_emails.json`.
