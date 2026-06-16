# Report Generate Agent — Hướng dẫn chạy thử (cho Ban tổ chức)

Agent tự động sinh **báo cáo kinh doanh hàng tháng** (Cash Loan) dạng `.docx` từ dữ liệu
Excel + email cập nhật initiative. Bản submit này chạy **hoàn toàn offline** — không cần
tài khoản Google của tác giả.

> Dữ liệu trong bản nộp là **tổng hợp/ẩn danh** (công ty, đối tác, persona, số liệu, email
> đều là giả lập). Không có dữ liệu thật hay credential cá nhân nào được kèm theo.

---

## 1. Yêu cầu
- Python 3.10+ (đã test 3.14).
- **Chạy ngay, không cần cấu hình gì** — LLM key (GreenNode platform) + chế độ `manual`
  đã đặt sẵn làm mặc định trong code (`src/config.py`). Không cần `.env`, không cần
  tài khoản/credentials Google. Dữ liệu mẫu đi kèm trong `Report_Sample/`.

> Dù chấm qua **clone GitHub** hay **giải nén ZIP**, các bước ở mục 2 đều chạy được luôn.

## 2. Chạy (chọn 1 trong 2)

**Cách 1 — CLI, nhanh nhất:**
```
pip install -r requirements.txt
python run_agent.py            # mặc định report tháng 6/2026; hoặc: python run_agent.py 6 2026
```
→ Báo cáo `.docx` xuất ra `Report_Sample/Report/`.

**Cách 2 — Web UI (chat):**
```
pip install -r requirements.txt
python app.py
```
→ Mở http://localhost:5000 → **Chọn folder** trỏ vào `Report_Sample/` → checklist hiện ✓
→ gõ **"làm report tháng 6/2026"** → tải file `.docx`.
> Windows: double-click `run_agent_reportgenerate.bat` (tự cài deps + mở trình duyệt).

## (Tùy chọn) Dùng LLM key riêng của bạn
Agent OpenAI-compatible. Tạo `.env` (override mặc định trong code):
```
LLM_BASE_URL=...   LLM_API_KEY=...   LLM_MODEL=...
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
