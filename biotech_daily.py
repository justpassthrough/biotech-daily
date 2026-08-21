"""
biotech-daily: RSS 24h items → Claude Sonnet 4.6 분석 → 누적 HTML 대시보드.

기능:
- Endpoints News, Fierce Biotech RSS에서 최근 24h 기사 수집
- 각 기사를 Claude API로 한국어 요약 + 카테고리 분류 + 본인 연구 관련성 점수 (0~10)
- 분석 결과는 link 기준 영구 캐시 (data/cache.json)
- 매 실행마다 KST 날짜 기준 스냅샷 저장 (data/history/YYYY-MM-DD.json)
- 최근 N일 히스토리를 한 페이지에서 날짜 셀렉터로 탐색 가능한 대시보드 생성
- 로컬 실행 시 자동 브라우저 오픈, CI(GitHub Actions) 환경에서는 스킵

사용법:
    pip install feedparser anthropic
    setx ANTHROPIC_API_KEY "sk-ant-..."   # 1회만, 새 cmd에서 적용
    python biotech_daily.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path

import feedparser

try:
    import anthropic
except ImportError:
    print("anthropic 패키지가 설치되어 있지 않습니다. 'pip install anthropic'을 실행하세요.")
    sys.exit(1)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


FEEDS = [
    "https://endpoints.news/feed",
    "https://www.fiercebiotech.com/rss/xml",
]
MODEL = "claude-sonnet-4-6"
CATEGORIES = ["임상결과", "M&A", "모달리티", "빅파마", "기타"]
HOURS = 24
SLEEP_BETWEEN_CALLS = 0.3

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_PATH = DATA_DIR / "cache.json"
HISTORY_DIR = DATA_DIR / "history"
DOCS_DIR = ROOT / "docs"
HTML_PATH = DOCS_DIR / "index.html"
DASHBOARD_HISTORY_DAYS = 30  # 대시보드에 노출할 최근 N일

KST = timezone(timedelta(hours=9))


SYSTEM_PROMPT = """You are a biotech industry analyst processing English biotech news for a Korean pharmacy PhD student.

USER RESEARCH PROFILE
=====================
The user is researching:
- Ferritin nanocage drug delivery systems
- Antibody-Drug Conjugates (ADC), especially linker chemistry
- De novo protein design and protein binders (RFdiffusion, ProteinMPNN, BindCraft, AlphaFold3)
- Tumor microenvironment masked antibodies
- Nanomedicine and drug delivery systems in general

OUTPUT FORMAT (CRITICAL)
========================
Output ONLY a valid JSON object with EXACTLY these 4 fields. No markdown fences. No explanation. First char must be `{`, last char must be `}`.

{
  "korean_summary": "3줄 한국어 요약, 줄바꿈은 \\n",
  "category": "임상결과 | M&A | 모달리티 | 빅파마 | 기타 중 정확히 하나",
  "relevance_score": 0~10 정수,
  "relevance_reason": "한 줄 한국어"
}

FIELD SPECIFICATIONS
====================

korean_summary (정확히 3줄, 각 줄은 \\n으로 구분):
  Line 1 — Who/What: 누가, 무엇을 발표/체결/공개했나
  Line 2 — 핵심: 임상 단계, 딜 사이즈, 메커니즘 등 구체적 숫자나 사실
  Line 3 — Why:  왜 중요한가, 산업적 의미
- 한국어로 작성. 영어 약어 (GLP-1, ADC, FDA, mRNA, P1/P2/P3, NDA, BLA, IND)는 그대로 사용.
- 마케팅성 표현 금지. 사실 중심.

category (정확히 다음 5개 중 하나):
  임상결과 — Phase 1/2/3 결과, 부작용 데이터, FDA approval, BLA/NDA/IND filing
  M&A — 인수, 합병, 라이선싱 딜, 옵션 계약, 마일스톤 페이먼트
  모달리티 — 신규 modality 기술 자체 (ADC, mRNA, gene therapy, cell therapy, CRISPR, protein degrader, AI drug discovery 등)
  빅파마 — Top 20 pharma의 전략/구조조정/파이프라인 동향
  기타 — 위에 해당하지 않는 모든 것 (펀딩, 인사, 정책, 학회 등)

relevance_score (0~10 정수, 엄격하게):
  9~10 — ferritin / 단백질 binder / de novo protein design / TME masking 직접 언급, 또는 ADC linker 신기술
  7~8  — ADC 일반, nanomedicine, drug delivery, protein engineering 직접 관련
  4~6  — 다른 modality이지만 학습 가치 있음 (단백질 치료제, 항체, conjugate)
  1~3  — bio 일반 뉴스, 사용자 분야와 거리
  0    — 사용자 분야와 완전 무관 (정책, 일반 금융, 임원 인사 등)
키워드만 살짝 스치는 정도로는 8을 주지 마세요. 직접 적용 가능한 기술/시장 신호일 때만 8 이상 부여.

relevance_reason: 점수 근거 한 줄 한국어.

EXAMPLES
========

Example 1:
INPUT TITLE: Gilead acquires Tubulis for $3.15 billion to expand ADC portfolio
INPUT SUMMARY: Gilead Sciences will pay up to $3.15 billion upfront and milestones to acquire German ADC specialist Tubulis. The deal centers on Tubulis' P5 linker platform that uses cysteine-tag conjugation, addressing ADC heterogeneity issues that have plagued earlier generations.

OUTPUT:
{"korean_summary": "Gilead가 ADC 전문 바이오테크 Tubulis를 31.5억 달러에 인수.\\nTubulis 자체 P5 linker 플랫폼(cysteine-tag conjugation 기반) 확보가 핵심.\\n빅파마의 ADC 강화 흐름, 특히 linker 기술 가치 상승을 보여주는 빅딜.", "category": "M&A", "relevance_score": 9, "relevance_reason": "ADC linker 기술 직접 관련, ferritin 컨주게이션 연구와 시사점 공유"}

Example 2:
INPUT TITLE: Lilly reports positive Phase 2 results for retatrutide in obesity
INPUT SUMMARY: Eli Lilly announced positive topline data from a Phase 2 trial of retatrutide, a triple GIP/GLP-1/glucagon receptor agonist, showing 24% mean weight loss vs placebo at 24 weeks with no new safety signals.

OUTPUT:
{"korean_summary": "Lilly의 차세대 triple agonist retatrutide가 비만 P2에서 양호한 결과.\\n24주 시점 평균 체중감소 24% (위약 대비), 신규 안전성 이슈 없음.\\nGLP-1 차세대 경쟁 심화, 비만치료제 시장 확장 지속.", "category": "임상결과", "relevance_score": 3, "relevance_reason": "비만 P2 결과, 본인 연구 분야와 거리. 빅파마 동향 참고용"}

Example 3:
INPUT TITLE: Insilico Medicine raises $100M Series E
INPUT SUMMARY: AI drug discovery company Insilico Medicine closed a $100 million Series E financing led by Value Partners Group, bringing total funding to about $500 million after pausing its IPO plans.

OUTPUT:
{"korean_summary": "AI 신약개발 기업 Insilico Medicine이 시리즈 E로 1억 달러 조달.\\nIPO 추진 보류 후 사모 라운드, 누적 투자 약 5억 달러.\\nAI drug discovery 섹터 자금조달 환경의 신호.", "category": "기타", "relevance_score": 4, "relevance_reason": "AI 신약 펀딩, de novo protein design 인접 영역 트렌드 참고"}

Example 4:
INPUT TITLE: BindCraft enables one-shot de novo design of functional protein binders
INPUT SUMMARY: A new AlphaFold2-based pipeline called BindCraft generates de novo binders against challenging targets without high-throughput screening, with experimental success rates 10–100x higher than prior methods.

OUTPUT:
{"korean_summary": "AlphaFold2 기반 새 파이프라인 BindCraft, 고난도 타깃에 대한 de novo binder 1-shot 설계 가능.\\n실험적 성공률 기존 방법 대비 10-100배 향상, 스크리닝 없이 후보 도출.\\n단백질 binder 분야의 패러다임 전환, 즉시 사용 가능한 도구 등장.", "category": "모달리티", "relevance_score": 10, "relevance_reason": "de novo protein binder 직접 관련, 사용자가 실제 사용 중인 도구"}
"""


# ─────────────────────────────────────────────
# RSS 수집
# ─────────────────────────────────────────────

def _parse_fierce_format(s: str):
    """Fierce Biotech 식 'May 7, 2026 11:01am' 포맷. 시간대는 UTC로 가정."""
    s = s.strip()
    s = re.sub(r"(\d)([aApP][mM])$", r"\1 \2", s).upper()
    try:
        return datetime.strptime(s, "%b %d, %Y %I:%M %p").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    for key in ("published", "updated"):
        s = entry.get(key)
        if not s:
            continue
        try:
            dt = parsedate_to_datetime(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (TypeError, ValueError):
            pass
        dt = _parse_fierce_format(s)
        if dt is not None:
            return dt
    return None


def clean_html_text(text, max_len=600):
    """HTML 태그 제거 + 엔티티 디코딩 + 공백 정규화 + 길이 제한."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return text


# 하위 호환
clean_summary = clean_html_text


def fetch_recent(feed_urls, hours=HOURS):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for url in feed_urls:
        parsed = feedparser.parse(url)
        if parsed.bozo:
            print(f"[경고] {url} 파싱 문제: {parsed.bozo_exception}")
        source = parsed.feed.get("title", url)
        for entry in parsed.entries:
            published = parse_entry_time(entry)
            if published is None or published < cutoff:
                continue
            items.append({
                "source": source,
                "title": clean_html_text(entry.get("title", "(제목 없음)"), max_len=300),
                "link": entry.get("link", ""),
                "summary_en": clean_html_text(entry.get("summary", "")),
                "published": published,
            })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items


# ─────────────────────────────────────────────
# 분석 캐시 (link 기준)
# ─────────────────────────────────────────────

def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def extract_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def analyze_item(client, item: dict, cache: dict) -> tuple[dict, bool]:
    """Return (analysis, cache_hit)."""
    link = item["link"]
    if link and link in cache:
        return cache[link], True

    user_msg = (
        f"INPUT TITLE: {item['title']}\n"
        f"INPUT SUMMARY: {item['summary_en'] or '(요약 없음)'}\n\n"
        f"OUTPUT:"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text if resp.content else ""
    parsed = extract_json(text)
    if parsed is None:
        parsed = {
            "korean_summary": item["title"],
            "category": "기타",
            "relevance_score": 0,
            "relevance_reason": "(파싱 실패)",
        }

    if parsed.get("category") not in CATEGORIES:
        parsed["category"] = "기타"
    try:
        parsed["relevance_score"] = max(0, min(10, int(parsed.get("relevance_score", 0))))
    except (TypeError, ValueError):
        parsed["relevance_score"] = 0
    parsed["processed_at"] = datetime.now(timezone.utc).isoformat()

    if link:
        cache[link] = parsed
    return parsed, False


def summarize_overall(client, items: list[dict]) -> list[str]:
    if not items:
        return ["(24시간 내 기사 없음)"]

    lines = [
        f"- [{it['relevance_score']}점/{it['category']}] {it['title']}"
        for it in items
    ]
    summary_input = "\n".join(lines)

    prompt = (
        "다음은 최근 24시간 biotech 뉴스의 제목/카테고리/관련성 점수 리스트입니다.\n"
        "전체를 종합해서 '오늘의 산업 흐름'을 정확히 3개의 한국어 bullet으로 정리하세요.\n"
        "각 bullet은 한 줄, 구체적 사실(회사명/숫자/딜 사이즈 등)과 함께. 일반론 금지.\n"
        "응답 형식: 각 줄을 '- '로 시작하는 3줄. 다른 텍스트 없음.\n\n"
        f"{summary_input}\n\n"
        "오늘의 흐름:"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text if resp.content else ""
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("-", "•", "*")):
            bullets.append(line.lstrip("-•* ").strip())
    return bullets[:3] or [text.strip() or "(요약 실패)"]


# ─────────────────────────────────────────────
# 일별 스냅샷 (히스토리)
# ─────────────────────────────────────────────

def _serialize_item(it: dict) -> dict:
    out = dict(it)
    p = out.get("published")
    if isinstance(p, datetime):
        out["published"] = p.isoformat()
    return out


def _deserialize_item(d: dict) -> dict:
    out = dict(d)
    p = out.get("published")
    if isinstance(p, str):
        try:
            out["published"] = datetime.fromisoformat(p)
        except ValueError:
            out["published"] = None
    return out


def save_daily_snapshot(items: list[dict], overall: list[str]) -> tuple[str, Path]:
    """KST 날짜 기준으로 data/history/YYYY-MM-DD.json 저장 (덮어쓰기)."""
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    payload = {
        "date": today_kst,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": [_serialize_item(it) for it in items],
        "overall": overall,
    }
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{today_kst}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return today_kst, path


def load_history(limit: int | None = None) -> list[dict]:
    """data/history/*.json을 최신순으로 로드."""
    if not HISTORY_DIR.exists():
        return []
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    if limit:
        files = files[:limit]
    out = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["items"] = [_deserialize_item(it) for it in data.get("items", [])]
            out.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return out


# ─────────────────────────────────────────────
# 렌더링
# ─────────────────────────────────────────────

def score_class(score: int) -> str:
    if score >= 9:
        return "score-high"
    if score >= 7:
        return "score-mid"
    if score >= 4:
        return "score-low"
    return "score-zero"


def _kr_weekday(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
    except ValueError:
        return ""


def _format_ts(it: dict) -> str:
    p = it.get("published")
    if isinstance(p, datetime):
        return p.astimezone(KST).strftime("%m-%d %H:%M")
    return ""


def _render_card(it: dict) -> str:
    return (
        '<div class="card">'
        '<div class="card-header">'
        f'<span class="score {score_class(it["relevance_score"])}">{it["relevance_score"]}</span>'
        f'<div class="card-title">{escape(it.get("title", ""))}</div>'
        "</div>"
        f'<div class="card-summary">{escape(it.get("korean_summary", ""))}</div>'
        f'<div class="card-reason">→ {escape(it.get("relevance_reason", ""))}</div>'
        f'<div class="card-meta">📍 {escape(it.get("source", ""))} · {_format_ts(it)} · '
        f'<a href="{escape(it.get("link", ""))}" target="_blank" rel="noopener">원문 →</a>'
        "</div>"
        "</div>"
    )


def _render_mini(it: dict) -> str:
    return (
        '<div class="mini-item">'
        f'<span class="score {score_class(it["relevance_score"])}">{it["relevance_score"]}</span>'
        f'<a href="{escape(it.get("link", ""))}" target="_blank" rel="noopener">{escape(it.get("title", ""))}</a>'
        f'<span style="color:var(--fg-muted);font-size:0.85rem;">· {escape(it.get("source", ""))} · {_format_ts(it)}</span>'
        "</div>"
    )


def _render_day_block(date_str: str, items: list[dict], overall: list[str]) -> str:
    weekday_kr = _kr_weekday(date_str)
    pretty_date = date_str.replace("-", ".") + (f" ({weekday_kr})" if weekday_kr else "")
    total = len(items)
    relevant = sum(1 for it in items if it.get("relevance_score", 0) >= 7)

    overall_html = "".join(f"<li>{escape(b)}</li>" for b in overall)

    high_items = sorted(
        (it for it in items if it.get("relevance_score", 0) >= 7),
        key=lambda x: x["relevance_score"], reverse=True,
    )
    if high_items:
        cards_html = "".join(_render_card(it) for it in high_items)
    else:
        cards_html = (
            '<div class="card" style="text-align:center;color:var(--fg-muted);">'
            "관련성 7점 이상 기사가 없습니다."
            "</div>"
        )

    cat_count = {c: 0 for c in CATEGORIES}
    cat_items = {c: [] for c in CATEGORIES}
    for it in items:
        c = it.get("category", "기타")
        if c in cat_count:
            cat_count[c] += 1
            cat_items[c].append(it)

    max_count = max(cat_count.values(), default=1) or 1
    bars = []
    for c in CATEGORIES:
        n = cat_count[c]
        width = int(20 + (n / max_count) * 480) if n else 20
        bars.append(
            f'<div class="cat-bar"><span class="cat-name">{escape(c)}</span>'
            f'<div class="cat-count-bar" style="width:{width}px">{n}</div></div>'
        )
    cat_bars_html = "".join(bars)

    cat_details = []
    for c in CATEGORIES:
        if not cat_items[c]:
            continue
        cat_items[c].sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        mini = "".join(_render_mini(it) for it in cat_items[c])
        cat_details.append(
            f"<details><summary>{escape(c)} ({cat_count[c]})</summary>{mini}</details>"
        )
    cat_details_html = "".join(cat_details)

    return (
        f'<div class="day-meta">{escape(pretty_date)} · 24h: <strong>{total}</strong>건 · 관련성 7+: <strong>{relevant}</strong>건</div>'
        f'<section class="overall"><h2>▣ 흐름 요약</h2><ul>{overall_html}</ul></section>'
        f'<section><h2>▣ 본인 연구 관련 (관련성 ≥ 7)</h2>{cards_html}</section>'
        f'<section><h2>▣ 카테고리별</h2><div class="cat-bars">{cat_bars_html}</div>{cat_details_html}</section>'
    )


def render_html(history: list[dict]) -> str:
    """history: 최신순 list of {date, items, overall, generated_at}."""
    if not history:
        return _HTML_TEMPLATE.format(
            latest_date="—",
            history_count=0,
            last_updated="—",
            date_options='<option value="">(데이터 없음)</option>',
            day_blocks='<div class="day-view"><div class="card" style="text-align:center;color:var(--fg-muted);padding:40px;">아직 누적된 기록이 없습니다.</div></div>',
        )

    options = []
    for snap in history:
        d = snap.get("date", "")
        wd = _kr_weekday(d)
        n = len(snap.get("items", []))
        rel7 = sum(1 for it in snap.get("items", []) if it.get("relevance_score", 0) >= 7)
        label = f'{d} ({wd}) — {n}건 / ≥7: {rel7}'
        options.append(f'<option value="{escape(d)}">{escape(label)}</option>')
    options_html = "".join(options)

    blocks = []
    for i, snap in enumerate(history):
        attrs = "" if i == 0 else " hidden"
        block = _render_day_block(
            snap.get("date", ""),
            snap.get("items", []),
            snap.get("overall", []),
        )
        blocks.append(
            f'<div class="day-view" data-date="{escape(snap.get("date", ""))}"{attrs}>{block}</div>'
        )
    blocks_html = "".join(blocks)

    last_updated = history[0].get("generated_at", "")
    if last_updated:
        try:
            dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            last_updated = dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
        except ValueError:
            pass

    return _HTML_TEMPLATE.format(
        latest_date=escape(history[0].get("date", "")),
        history_count=len(history),
        last_updated=escape(last_updated),
        date_options=options_html,
        day_blocks=blocks_html,
    )


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Biotech Daily — {latest_date}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #fafafa;
  --bg-card: #ffffff;
  --fg: #1a1a1a;
  --fg-muted: #666;
  --border: #e0e0e0;
  --accent: #2563eb;
  --score-high: #dc2626;
  --score-mid: #ea580c;
  --score-low: #94a3b8;
  --score-zero: #cbd5e1;
  --shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
[data-theme="dark"] {{
  --bg: #0f0f0f;
  --bg-card: #1a1a1a;
  --fg: #e5e5e5;
  --fg-muted: #999;
  --border: #2a2a2a;
  --accent: #60a5fa;
  --shadow: 0 1px 3px rgba(0,0,0,0.4);
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg);
  color: var(--fg);
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 20px 60px;
  line-height: 1.6;
  transition: background 0.2s, color 0.2s;
}}
header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 28px;
  padding-bottom: 20px;
  border-bottom: 2px solid var(--border);
  flex-wrap: wrap;
}}
.header-left h1 {{ margin: 0; font-size: 1.5rem; font-weight: 700; }}
.header-left .meta-info {{ color: var(--fg-muted); margin-top: 6px; font-size: 0.85rem; }}
.header-right {{
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}}
select#date-selector {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--fg);
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-family: inherit;
  min-width: 220px;
}}
select#date-selector:hover {{ border-color: var(--accent); }}
button#theme-toggle {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--fg);
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-family: inherit;
  flex-shrink: 0;
}}
button#theme-toggle:hover {{ border-color: var(--accent); }}
.day-meta {{
  color: var(--fg-muted);
  font-size: 0.95rem;
  margin-bottom: 24px;
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}}
section {{ margin-bottom: 36px; }}
h2 {{
  font-size: 1.1rem;
  margin: 0 0 14px;
  padding-left: 10px;
  border-left: 4px solid var(--accent);
}}
.overall ul {{
  background: var(--bg-card);
  border-radius: 12px;
  padding: 18px 24px 18px 36px;
  box-shadow: var(--shadow);
  border: 1px solid var(--border);
  margin: 0;
}}
.overall li {{ margin-bottom: 8px; }}
.overall li:last-child {{ margin-bottom: 0; }}
.card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 12px;
  box-shadow: var(--shadow);
}}
.card-header {{
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}}
.score {{
  display: inline-block;
  padding: 3px 10px;
  border-radius: 16px;
  font-weight: 700;
  font-size: 0.85rem;
  color: white;
  flex-shrink: 0;
  min-width: 28px;
  text-align: center;
}}
.score-high {{ background: var(--score-high); }}
.score-mid {{ background: var(--score-mid); }}
.score-low {{ background: var(--score-low); }}
.score-zero {{ background: var(--score-zero); }}
.card-title {{
  font-weight: 500;
  font-size: 1rem;
  flex: 1;
  word-break: break-word;
}}
.card-summary {{
  white-space: pre-line;
  margin: 8px 0;
  color: var(--fg);
  font-size: 0.95rem;
}}
.card-reason {{
  font-size: 0.85rem;
  color: var(--fg-muted);
  font-style: italic;
  margin: 6px 0 10px;
}}
.card-meta {{ font-size: 0.85rem; color: var(--fg-muted); }}
.card-meta a {{ color: var(--accent); text-decoration: none; }}
.card-meta a:hover {{ text-decoration: underline; }}
.cat-bars {{ margin-bottom: 16px; }}
.cat-bar {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}}
.cat-name {{ width: 100px; font-weight: 500; flex-shrink: 0; }}
.cat-count-bar {{
  height: 24px;
  background: var(--accent);
  border-radius: 4px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  color: white;
  font-size: 0.85rem;
  font-weight: 500;
}}
details {{
  margin-top: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}}
details summary {{ cursor: pointer; font-weight: 500; padding: 2px 0; }}
details[open] summary {{ margin-bottom: 8px; }}
.mini-item {{
  padding: 8px 0;
  border-top: 1px solid var(--border);
  font-size: 0.92rem;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.mini-item:first-of-type {{ border-top: none; }}
.mini-item a {{ color: var(--accent); text-decoration: none; word-break: break-word; }}
.mini-item a:hover {{ text-decoration: underline; }}
@media (max-width: 600px) {{
  body {{ padding: 16px 14px 40px; }}
  .header-left h1 {{ font-size: 1.25rem; }}
  .cat-name {{ width: 80px; font-size: 0.9rem; }}
  select#date-selector {{ min-width: 180px; }}
}}
</style>
</head>
<body>
<header>
  <div class="header-left">
    <h1>Biotech Daily</h1>
    <div class="meta-info">{history_count}일 누적 · 마지막 업데이트: {last_updated}</div>
  </div>
  <div class="header-right">
    <select id="date-selector" aria-label="날짜 선택">{date_options}</select>
    <button id="theme-toggle">🌙 다크</button>
  </div>
</header>

<main>{day_blocks}</main>

<script>
(function() {{
  const root = document.documentElement;
  const themeBtn = document.getElementById('theme-toggle');
  function applyTheme(t) {{
    root.setAttribute('data-theme', t);
    themeBtn.textContent = t === 'dark' ? '☀️ 라이트' : '🌙 다크';
  }}
  applyTheme(localStorage.getItem('biotech-theme') || 'light');
  themeBtn.addEventListener('click', function() {{
    const cur = root.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem('biotech-theme', next);
  }});

  const sel = document.getElementById('date-selector');
  function showDate(d) {{
    document.querySelectorAll('.day-view').forEach(function(v) {{
      v.hidden = v.dataset.date !== d;
    }});
  }}
  sel.addEventListener('change', function(e) {{ showDate(e.target.value); }});
}})();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

def write_html(html: str) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html, encoding="utf-8")


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[에러] ANTHROPIC_API_KEY 환경변수가 설정되어 있지 않습니다.")
        print("       console.anthropic.com 에서 키 발급 후:")
        print('         setx ANTHROPIC_API_KEY "sk-ant-..."')
        print("       cmd 새로 열고 다시 실행하세요.")
        sys.exit(1)

    is_ci = bool(os.environ.get("CI"))
    client = anthropic.Anthropic()

    print("RSS 가져오는 중...")
    items = fetch_recent(FEEDS, hours=HOURS)
    print(f"  → 24h 내 {len(items)}건 발견\n")

    if not items:
        print("최근 24시간 내 새 기사가 없습니다. 기존 히스토리만으로 대시보드 재생성.")
        history = load_history(DASHBOARD_HISTORY_DAYS)
        write_html(render_html(history))
        return

    cache = load_cache()
    hits = 0
    for i, it in enumerate(items, 1):
        analysis, hit = analyze_item(client, it, cache)
        it.update(analysis)
        if hit:
            hits += 1
            marker = "[캐시]"
        else:
            marker = "[API ]"
        title_short = it["title"][:60] + ("..." if len(it["title"]) > 60 else "")
        print(f"  [{i:2d}/{len(items)}] {marker} score={it['relevance_score']:2d} | {title_short}")
        if not hit:
            time.sleep(SLEEP_BETWEEN_CALLS)
    save_cache(cache)
    print(f"\n캐시 hit: {hits}/{len(items)}")

    print("\n오늘의 흐름 종합 중...")
    overall = summarize_overall(client, items)

    print("\n일별 스냅샷 저장 중...")
    today_kst, snapshot_path = save_daily_snapshot(items, overall)
    print(f"  → {snapshot_path}")

    print("\n히스토리 로드 + HTML 생성 중...")
    history = load_history(DASHBOARD_HISTORY_DAYS)
    html = render_html(history)
    write_html(html)
    print(f"  → {HTML_PATH}")

    if is_ci:
        print("\nCI 환경 감지 — 브라우저 오픈 스킵.")
    else:
        print("\n브라우저로 여는 중...")
        webbrowser.open(HTML_PATH.as_uri())
    print("완료.")


if __name__ == "__main__":
    main()
