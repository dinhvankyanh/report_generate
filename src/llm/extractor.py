"""
LLM-based extraction of initiative updates from email threads.

Email threads are Vietnamese conversations; the correct status / timing /
confidence for a month can only be reliably read by understanding the whole
thread (latest message wins, with the discussion as context). This module
sends the initiative list + the relevant email threads to an OpenAI-compatible
LLM (GreenNode AI Platform by default) and gets back structured updates.

Configure via environment (loaded from .env by config.py):
    LLM_BASE_URL  (default: GreenNode MAAS endpoint)
    LLM_API_KEY   (saved by `aip.sh api-keys create/get`)
    LLM_MODEL     (the model `path`, e.g. from `aip.sh models get <uuid>`)
"""
import json
import re
from typing import List, Dict, Optional

from .. import config

# Canonical vocabularies the model must stick to
STATUS_VOCAB = ["Not started", "On Track", "Delay", "Deprioritized", "Done", "Live"]
CONFIDENCE_VOCAB = ["High", "Medium", "Low"]

# Subject tags / keywords that mark a product/initiative thread (others dropped).
# Tolerant of tag variants: [Product] [CL] [Partnership]/[Partnerships], or the
# words "initiative"/"partner" anywhere in the subject.
RELEVANT_SUBJECT = re.compile(r"\[(product|cl|partnerships?)\]|\binitiative\b|\bpartner\b",
                              re.IGNORECASE)


def llm_available() -> bool:
    """True if an API key and model are configured."""
    return bool(config.LLM_CONFIG.get("api_key")) and bool(config.LLM_CONFIG.get("model"))


def _client():
    from openai import OpenAI
    return OpenAI(
        api_key=config.LLM_CONFIG["api_key"],
        base_url=config.LLM_CONFIG["base_url"],
        timeout=config.LLM_CONFIG.get("timeout", 90),
        max_retries=0,
    )


def _chat_json(messages, max_tokens=8000) -> str:
    """One LLM call returning raw text; tolerant of endpoints rejecting extra_body."""
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=config.LLM_CONFIG["model"], messages=messages,
            temperature=0, seed=7, max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    except Exception:
        resp = client.chat.completions.create(
            model=config.LLM_CONFIG["model"], messages=messages,
            temperature=0, max_tokens=max_tokens)
    return resp.choices[0].message.content or ""


def _json_obj(content: str):
    """Parse a JSON object from model output (strip <think>, salvage first {...})."""
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL).strip()
    try:
        return json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def normalize_subject(subject: str) -> str:
    """
    Strip reply/forward prefixes AND a trailing parenthetical annotation so
    near-duplicate subjects about the same initiative merge into one thread
    (e.g. "... new segments" and "... new segments (Sep-26)" -> same thread,
    so the latest message wins regardless of which subject it used).
    """
    s = subject or ""
    while True:
        s2 = re.sub(r"^\s*(re|fwd|fw)\s*:\s*", "", s, flags=re.IGNORECASE)
        if s2 == s:
            break
        s = s2
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)  # drop trailing "(...)"
    return s.strip()


_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def anonymize_and_filter(emails: List[dict]) -> List[dict]:
    """
    Keep only product/initiative threads and censor PII: every email address is
    replaced by a stable neutral alias (personN@demo.local). Returns dicts with
    {subject, date, sender, body} ready to persist as sample_emails.json.
    """
    alias = {}

    def repl(m):
        a = m.group(0).lower()
        if a not in alias:
            alias[a] = f"person{len(alias) + 1}@demo.local"
        return alias[a]

    out = []
    for e in emails:
        subject = e.get("subject", "") or ""
        if not RELEVANT_SUBJECT.search(subject):
            continue
        out.append({
            "subject": _EMAIL_RE.sub(repl, subject),
            "date": e.get("date", ""),
            "sender": _EMAIL_RE.sub(repl, e.get("sender", "") or ""),
            "body": _EMAIL_RE.sub(repl, e.get("body", "") or ""),
        })
    return out


def _strip_quoted(body: str) -> str:
    """Drop quoted reply lines (> ...) and boilerplate to shrink the prompt."""
    lines = []
    for ln in (body or "").splitlines():
        s = ln.strip()
        if not s or s.startswith(">") or s.startswith("*Best") or s.startswith("Best regards"):
            continue
        if s.lower().startswith(("from:", "sent:", "to:", "cc:", "subject:", "vào thứ", "vào lúc")):
            continue
        lines.append(s)
    return "\n".join(lines).strip()


def _date_key(date_str: str):
    """Parse an RFC-2822 email date for sorting (oldest -> newest)."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def group_threads(emails: List[dict]) -> List[dict]:
    """Group relevant emails into threads keyed by normalized subject."""
    threads: Dict[str, dict] = {}
    for em in emails:
        subject = em.get("subject", "") or ""
        if not RELEVANT_SUBJECT.search(subject):
            continue
        body = _strip_quoted(em.get("body", ""))
        if not body:
            continue
        key = normalize_subject(subject)
        t = threads.setdefault(key, {"subject": key, "messages": []})
        t["messages"].append({
            "date": em.get("date", ""),
            "sender": em.get("sender", ""),
            "body": body,
        })
    # Sort each thread chronologically so the LAST message is the most recent,
    # then keep only the newest few messages. Emails quote prior content inline
    # (no '>' prefix), so older messages repeat stale facts and confuse "latest
    # wins"; the conclusion lives in the last message(s).
    for t in threads.values():
        dated = [m for m in t["messages"] if _date_key(m["date"]) is not None]
        if len(dated) == len(t["messages"]):
            t["messages"].sort(key=lambda m: _date_key(m["date"]))
        t["messages"] = t["messages"][-4:]
    return list(threads.values())


def _build_prompt(initiatives: List[dict], threads: List[dict], report_label: str,
                  email_by_no: dict = None) -> str:
    init_lines = []
    for it in initiatives:
        init_lines.append(
            f"- No {it['no']}: {it['name']} | planned timing: {it.get('timing','')} "
            f"| expected impact: {it.get('expected_impact','')} "
            f"| previous month status: {it.get('prev_status','') or '(none)'} "
            f"| previous new timing: {it.get('prev_new_timing','') or '(none)'} "
            f"| previous details: {it.get('prev_details','') or '(none)'}"
        )

    # Sort threads newest-first (by latest message) so recency is explicit;
    # the model must prefer the most recent statement about any initiative.
    def _latest(t):
        ds = [d for d in (_date_key(m["date"]) for m in t["messages"]) if d is not None]
        return max(ds) if ds else None

    threads_sorted = sorted(
        threads,
        key=lambda t: (_latest(t) is not None, _latest(t)),
        reverse=True) if all(_latest(t) for t in threads) else threads

    def _msg_line(m):
        body = m["body"]
        if len(body) > 1500:
            body = body[:1500] + " ...[truncated]"
        return f"  [{m['date']}] {body}"

    if email_by_no:
        # Messages already grouped per initiative (merged across threads, oldest->newest)
        blocks = []
        for it in initiatives:
            msgs = email_by_no.get(it["no"])
            if not msgs:
                continue
            blocks.append(f"#### Initiative #{it['no']} — {it['name']} ####\n"
                          + "\n".join(_msg_line(m) for m in msgs))
        email_section = (
            "EMAIL UPDATES PER INITIATIVE (Vietnamese; messages oldest->newest, may be "
            "merged from several threads — the LAST line is the current state):\n"
            + ("\n\n".join(blocks) if blocks else "(no email updates)"))
    else:
        thread_blocks = []
        for t in threads_sorted:
            hdr = f"### Thread: {t['subject']}  (latest msg: {_latest(t)})"
            thread_blocks.append(hdr + "\n" + "\n".join(_msg_line(m) for m in t["messages"]))
        email_section = (
            "EMAIL THREADS (Vietnamese; newest thread first; within a thread oldest->newest):\n"
            + "\n".join(thread_blocks))

    return f"""You are updating a monthly Initiatives Tracker for {report_label}.

INITIATIVES (each carries last month's status / new timing / details as context):
{chr(10).join(init_lines)}

{email_section}

How to read the emails:
- A thread (and even a single message) may discuss MORE THAN ONE initiative.
  Apply each fact to the initiative it concerns. Example: a "new modelling" thread
  that also sets the start/launch date of the dependent "personalization" initiative
  updates BOTH initiatives.
- DISAMBIGUATE same-named initiatives: some rows share an IDENTICAL name and differ
  only by planned timing / persona (e.g. two "Add 1 partner with higher risk appetite",
  one planned May-26, one Aug-26). Match each email to the correct row using the
  planned timing and clues in the email (the target/committed month, partner name,
  persona). All the partner-onboarding emails here (Partner 2 / Onboard Partner A,
  which were committed for Aug) concern the **Aug-planned** partner row — NOT the
  May-planned one. Do not assign a partner's email to the wrong row.
- RECENCY WINS: when the same initiative is mentioned in several threads/messages,
  the statement with the LATEST date is authoritative — override older ones.
  (e.g. an older thread saying "Gini ~0.2, below expectation" is superseded by a
  newer one saying "Gini up to 0.3, near the expected threshold".)
- A NEWER decision OVERRIDES an older one — including REVERSALS, even across two
  differently-titled threads about the same initiative. Use the latest; treat an old
  blocker/refusal as resolved if a newer message resolves it. Examples:
  * older "DS busy, cannot start personalization" -> newer "model ready, can kick off
    end June, needs 2 months" => write the NEWER (kick off end June, slips ~2 months).
  * older "partner REFUSED phased rollout, slip to Oct" -> newer "partner AGREED to
    phased rollout: phase 1 (no new feature, ~1M users) go-live ~Sep, phase 2 full
    base later, no firm date" => write the NEWER (phased plan), NOT "Oct / refused".
  When two threads about one initiative conflict, the one with the LATER date wins.
- RELATIVE TIMING — do NOT do the month math yourself. If the timing is expressed
  as "kick off in <month> and take <N> months", just EXTRACT the parts: set
  "timing_start" to that kickoff month as "Mon-YY" (e.g. "cuối tháng 6" -> "Jun-26")
  and "timing_months" to N (e.g. "2 tháng" -> 2). The system computes new_timing.
  Use each initiative's OWN kickoff/duration — never a month mentioned for a
  different initiative. If the timing is already an absolute month, put it in
  "new_timing" and leave timing_start empty.

Produce an update for an initiative when EITHER of these is true:
 (A) some email (in any thread) gives news about it — read the LATEST relevant statement; OR
 (B) it has NO email this month, BUT last month's row shows it should have completed by now:
   previous details indicate it was ready / about-to-launch / deployed / launched / done
   (e.g. "ready to pilot", "go-live", "deployed"), OR its **planned timing OR previous new
   timing month is now in the PAST** relative to {report_label}. In that case roll the
   status to "Live" (or "Done"), keeping the timing. You MUST check every no-email
   initiative against rule B — an item still "On Track" for a month that has already
   passed is wrong; if it was ready, it is now Live.
If neither applies, OMIT the initiative (it carries forward unchanged).

Examples of rule (B):
- prev status "Delay", prev new timing "May-26", prev details "Model deployed May", report month June -> "Live", new_timing "May-26".
- prev status "On Track", planned timing "May-26", prev details "Integration & UAT done, ready to pilot mid-May", report month June -> "Live" (May has passed and it was ready), keep timing "May-26".

Field rules:
- "status": exactly one of {STATUS_VOCAB}. deprioritized/paused/revisit later -> "Deprioritized";
  deployed/went live/in production -> "Live"; finished/closed -> "Done".
  A planned initiative that will miss or is at risk of missing its planned timing -> "Delay"
  (use "Delay" even if work has not started yet, as long as the launch was planned and is now slipping/blocked).
  Reserve "Not started" only for items not yet due with NO slippage and NO blocker mentioned.
- "new_timing": the agreed timing (format like "Oct-26" or "Q4-2026"). Keep the previous new timing if it is still the operative target; else "".
- "details": one concise Vietnamese sentence summarizing the situation as of {report_label} (key decision/blocker/outcome).
- "confidence": one of {CONFIDENCE_VOCAB}. Use the stated level if given (e.g. "confident level: medium").
  If not explicitly stated, INFER it: done/live or committed with a clear plan -> "High";
  some uncertainty or "sẽ cố gắng nhưng không chắc" -> "Medium"; no commitment / timeline unconfirmed / blocked / cannot start -> "Low".
  Leave "" only when there is genuinely no signal at all.
- "pic": "Persona N" only if explicitly identifiable; else "".
- "metric_claims": list of CURRENT-LEVEL metric values the email explicitly asserts
  (for cross-checking vs the actuals sheet). Each = {{"metric": "<metric name>",
  "level": "<value, e.g. 65% or 30000>"}}. ONLY actual current levels (e.g.
  "approval rate ~65%"); do NOT include promises/uplifts like "+10pp". Empty list if none.
- Never invent facts not supported by the email thread or last month's row.

BEFORE RETURNING — completeness sweep (do NOT omit these): scan EVERY initiative,
including ones with NO email. Any initiative whose planned timing (or previous new
timing) month is EARLIER than {report_label}, and whose previous status/details show
it was ready-to-pilot / deployed / launched / done, MUST be returned as "Live"
(keep its timing). Example: #1 "Add 1 partner" planned May-26, prev "ready to pilot
mid-May", report month June -> MUST output #1 as "Live", new_timing "May-26".

Return ONLY valid JSON, no prose:
{{"updates": [{{"no": <int>, "status": "", "new_timing": "", "timing_start": "", "timing_months": 0, "details": "", "confidence": "", "pic": "", "metric_claims": []}}]}}"""


def _map_threads_to_initiatives(initiatives: List[dict], threads: List[dict]) -> dict:
    """
    Pass 1: ask the LLM which initiative No(s) each thread concerns. Returns
    {thread_index: [no, ...]}. Lets differently-titled threads about the same
    initiative be merged in code (recency then handled per-initiative).
    """
    init_lines = [f"No {it['no']}: {it['name']} | planned {it.get('timing','') or '?'}"
                  f" | {it.get('pic','') or ''}" for it in initiatives]
    th_lines = []
    for i, t in enumerate(threads):
        last = t["messages"][-1]["body"][:280] if t["messages"] else ""
        th_lines.append(f"[{i}] {t['subject']}\n    latest: {last}")
    prompt = f"""Assign each email thread to the initiative number(s) it concerns.
INITIATIVES:
{chr(10).join(init_lines)}
THREADS:
{chr(10).join(th_lines)}
Rules:
- A thread may concern MULTIPLE initiatives (e.g. a model thread that also sets a
  dependent initiative's start/launch date) -> list all relevant No.
- DIFFERENT-titled threads can concern the SAME initiative (e.g. "Partner 2 -
  onboarding" and "Onboard Partner A" are the same partner) -> give the same No.
- Disambiguate same-named initiatives by planned timing / persona / partner.
- A thread matching no initiative -> [].
Return ONLY JSON: {{"map":[{{"thread":<int>,"nos":[<int>...]}}]}}
/no_think"""
    try:
        data = _json_obj(_chat_json(
            [{"role": "system", "content": "Return strict JSON only."},
             {"role": "user", "content": prompt}], max_tokens=3000))
        out = {}
        for row in (data or {}).get("map", []):
            i = row.get("thread")
            if not isinstance(i, int):
                continue
            nos = []
            for x in (row.get("nos") or []):
                try:
                    nos.append(int(x))
                except (TypeError, ValueError):
                    pass
            out[i] = nos
        return out
    except Exception as e:
        print(f"[WARNING] thread->initiative mapping failed: {e}")
        return {}


def extract_initiative_updates(initiatives: List[dict], emails: List[dict],
                               report_label: str = "the report month") -> List[dict]:
    """
    Return a list of update dicts keyed by initiative number:
        {"no", "status", "new_timing", "details", "confidence", "pic"}

    Returns [] if the LLM is not configured or the call fails.
    """
    if not llm_available():
        return []

    threads = group_threads(emails)
    if not threads:
        return []

    # Pass 1: map threads -> initiative No(s), then MERGE only the threads that
    # concern exactly ONE (same) initiative — e.g. "Partner 2 — onboarding" and
    # "Onboard Partner A" both -> #2 are merged chronologically so the latest wins.
    # Threads that concern several initiatives (e.g. a modelling thread that also
    # mentions personalization) are LEFT AS-IS to avoid cross-contaminating them.
    try:
        mapping = _map_threads_to_initiatives(initiatives, threads)
        if mapping:
            from collections import defaultdict
            single = defaultdict(list)
            kept = []
            for i, t in enumerate(threads):
                nos = mapping.get(i, [])
                if len(nos) == 1:
                    single[nos[0]].append(t)
                else:
                    kept.append(t)
            for no, ts in single.items():
                if len(ts) == 1:
                    kept.append(ts[0])
                    continue
                msgs, subs = [], []
                for t in ts:
                    msgs.extend(t["messages"]); subs.append(t["subject"])
                if msgs and all(_date_key(m["date"]) for m in msgs):
                    msgs.sort(key=lambda m: _date_key(m["date"]))
                kept.append({"subject": " / ".join(subs), "messages": msgs[-6:]})
            threads = kept
    except Exception as e:
        print(f"[WARNING] thread merge failed, using raw threads: {e}")

    # Pass 2: write the structured update. "/no_think" keeps reasoning models terse.
    prompt = _build_prompt(initiatives, threads, report_label) + "\n\n/no_think"
    try:
        content = _chat_json(
            [{"role": "system", "content": "You extract structured data and return strict JSON only. Do not think out loud."},
             {"role": "user", "content": prompt}], max_tokens=8000)
    except Exception as e:
        print(f"[WARNING] LLM extraction failed: {e}")
        return []

    return _parse_updates(content)


def _parse_updates(content: str) -> List[dict]:
    """Parse the model output into a clean list of update dicts."""
    # Strip any qwen <think>...</think> block that slipped through
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    data = None
    try:
        data = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict):
        return []

    raw = data.get("updates", [])
    updates = []
    for u in raw if isinstance(raw, list) else []:
        try:
            no = int(u.get("no"))
        except (TypeError, ValueError):
            continue
        status = (u.get("status") or "").strip()
        if status and status not in STATUS_VOCAB:
            status = _coerce_status(status)
        conf = (u.get("confidence") or "").strip().capitalize()
        if conf and conf not in CONFIDENCE_VOCAB:
            conf = ""
        claims = u.get("metric_claims") or []
        claims = [c for c in claims if isinstance(c, dict) and c.get("metric") and c.get("level")]
        # Deterministic relative-timing: compute kickoff month + duration in code
        new_timing = (u.get("new_timing") or "").strip()
        ts = (u.get("timing_start") or "").strip()
        try:
            tm = int(u.get("timing_months") or 0)
        except (TypeError, ValueError):
            tm = 0
        if ts and tm > 0:
            computed = _add_months(ts, tm)
            if computed:
                new_timing = computed
        updates.append({
            "no": no,
            "status": status,
            "new_timing": new_timing,
            "details": (u.get("details") or "").strip(),
            "confidence": conf,
            "pic": (u.get("pic") or "").strip(),
            "metric_claims": claims,
        })
    return updates


_MON_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MON_ABBR = {v: k.capitalize() for k, v in _MON_NUM.items()}


def _parse_month(s):
    """Parse 'Jun-26' / 'June 2026' / 'tháng 6 2026' -> (month, year) or None."""
    s = str(s).lower()
    m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s/]*(\d{2,4})?', s)
    if not m:
        return None
    mon = _MON_NUM[m.group(1)]
    yr = m.group(2)
    yr = (2000 + int(yr) if int(yr) < 100 else int(yr)) if yr else None
    return mon, yr


def _add_months(start_str, n: int):
    """'Jun-26' + 2 -> 'Aug-26' (deterministic; LLM month math is unreliable)."""
    p = _parse_month(start_str)
    if not p or p[1] is None:
        return None
    mon, yr = p
    total = (mon - 1) + int(n)
    ny, nm = yr + total // 12, total % 12 + 1
    return f"{_MON_ABBR[nm]}-{str(ny)[-2:]}"


def _coerce_status(s: str) -> str:
    sl = s.lower()
    for v in STATUS_VOCAB:
        if v.lower() in sl:
            return v
    return ""
