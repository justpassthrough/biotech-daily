"""Smoke test: render_html with mock data, no API key required."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))
import biotech_daily as bw

now = datetime.now(timezone.utc)
mock_items = [
    {
        "source": "Endpoints News",
        "title": "Gilead acquires Tubulis for $3.15 billion to expand ADC portfolio",
        "link": "https://example.com/1",
        "summary_en": "...",
        "published": now - timedelta(hours=2),
        "korean_summary": "Gilead가 ADC 전문 Tubulis를 31.5억 달러에 인수.\nTubulis 자체 P5 linker 플랫폼(cysteine-tag conjugation 기반) 확보가 핵심.\n빅파마의 ADC 강화, linker 기술 가치 상승 신호.",
        "category": "M&A",
        "relevance_score": 9,
        "relevance_reason": "ADC linker 기술 직접 관련, ferritin 컨주게이션 연구와 시사점 공유",
    },
    {
        "source": "Fierce Biotech",
        "title": "Lilly reports positive Phase 2 results for retatrutide in obesity",
        "link": "https://example.com/2",
        "summary_en": "...",
        "published": now - timedelta(hours=5),
        "korean_summary": "Lilly의 차세대 triple agonist retatrutide가 비만 P2에서 양호한 결과.\n24주 시점 평균 체중감소 24%.\nGLP-1 차세대 경쟁 심화.",
        "category": "임상결과",
        "relevance_score": 3,
        "relevance_reason": "비만 P2 결과, 본인 연구와 거리",
    },
    {
        "source": "Endpoints News",
        "title": "BindCraft enables one-shot de novo protein binder design",
        "link": "https://example.com/3",
        "summary_en": "...",
        "published": now - timedelta(hours=8),
        "korean_summary": "AlphaFold2 기반 BindCraft, one-shot de novo binder 설계 가능.\n실험 성공률 10-100배 향상, 스크리닝 없이 후보 도출.\n단백질 binder 분야 패러다임 전환.",
        "category": "모달리티",
        "relevance_score": 10,
        "relevance_reason": "de novo binder 직접 관련, 사용자 사용 도구",
    },
    {
        "source": "Fierce Biotech",
        "title": "Insilico Medicine raises $100M Series E",
        "link": "https://example.com/4",
        "summary_en": "...",
        "published": now - timedelta(hours=12),
        "korean_summary": "AI 신약개발 Insilico Medicine, 시리즈 E 1억 달러.\nIPO 보류 후 사모, 누적 투자 약 5억 달러.\nAI drug discovery 자금조달 환경 신호.",
        "category": "기타",
        "relevance_score": 4,
        "relevance_reason": "de novo design 인접 영역 트렌드 참고",
    },
]
overall = [
    "ADC 분야 빅딜: Gilead가 Tubulis 31.5억 달러 인수, linker 기술 가치 부각.",
    "비만약 차세대 경쟁: Lilly retatrutide P2 24% 체중감소.",
    "AI/de novo 영역 자금 흐름: Insilico $100M Series E, BindCraft 기술 진보 동반.",
]

html = bw.render_html(mock_items, overall)
out = Path(__file__).parent / "index.html"
out.write_text(html, encoding="utf-8")
print(f"OK rendered len={len(html)} bytes -> {out}")
