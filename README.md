# Report Generate Agent

> 🤖 **AI disclosure.** This is an **AI agent**. It reads your data and produces the
> monthly business report and analysis **automatically using an LLM** — review the
> output before use.

An agent that auto-generates the **monthly Cash Loan business report** for a product
team: it reads the source Excel files + the last 6 months of email updates, computes
every figure deterministically, and writes an analytical **`.docx` report** plus the
supporting Initiatives tracker, Performance analysis, and Forecast.

---

## Use case (≤300 words)

**Problem.** Each month a product/biz team hand-builds a Cash Loan report: read dozens
of initiative-update emails, reconcile them against the KPI / actual-performance
sheets, recompute the funnel, decide what's on track vs delayed, pick next month's
priorities, and write the narrative. It takes hours, is error-prone, and a single
confident-but-wrong number in a leadership report is costly.

**User.** The product manager / business analyst who owns the monthly Cash Loan
report (and their leadership readers).

**Solution.** A 7-step agent that, from one chat message ("làm report tháng 6/2026"):
1. Builds the month's Initiatives tracker from the previous month + 6 months of email
   (LLM extraction, 2-pass thread→initiative mapping, recency-aware).
2. Computes Status changes, Performance analysis (MoM + vs KPI), and next-month Forecast.
3. Selects Top-3 priorities (deterministic rule).
4. Renders an analytical `.docx` report — figures + tables computed deterministically,
   narrative written by an LLM, with built-in quality-rule checks (expected-vs-realized
   per initiative, real-vs-mechanical movement, unaddressed plan gaps, source-conflict
   flags) and a cross-file consistency check.

**Value.** Hours → ~2 minutes per month. Numbers trace to source (no invented figures);
quality rules catch the mistakes a human reviewer would. Consistent, leadership-ready
output every month.

---

## Tech & models

- **LLM:** GreenNode MaaS — `qwen/qwen3-5-27b` (OpenAI-compatible endpoint). No external
  (non-platform) models are used.
- Python + Flask (chat web UI) · pandas / openpyxl / python-docx.
- Email reading via Gmail API (live) with an anonymized offline sample fallback.

## Run

```bash
pip install -r requirements.txt
python run_agent.py            # CLI, generates June 2026 report from Report_Sample/
# or: python app.py            # web chat UI at http://localhost:5000
```
Zero-config: the GreenNode MaaS key + offline mode are baked in, and sample data ships
in `Report_Sample/` — a fresh clone runs immediately.

## Data & privacy

Uses only **synthetic / anonymized** data (`sample_emails.json` has all addresses masked
to `personN@demo.local`). No customer data, PII, or confidential internal data is
committed. Google credentials / tokens are git-ignored and not part of the repo.

## Docs

- `Agent_build.md` — full architecture, the 6-step pipeline + consistency check, calc rules.
- `quality_rules.md` — the trustworthiness rules the report must satisfy.
- `SUBMISSION.md` — how to run the offline submission build.
