# biotech-daily

매일 오전 8시 KST에 Endpoints News + Fierce Biotech RSS를 가져와 Claude Sonnet 4.6으로 한국어 요약/카테고리/관련성 분석한 뒤 누적 대시보드를 빌드합니다.

대시보드: https://justpassthrough.github.io/biotech-daily/

## 분석 항목

각 기사마다 JSON으로:
- `korean_summary` — Who/What, 핵심 사실, Why 3줄 한국어 요약
- `category` — 임상결과 / M&A / 모달리티 / 빅파마 / 기타
- `relevance_score` — 0~10, 사용자 연구 분야(ferritin, ADC, de novo binder, TME masking) 직접 관련도
- `relevance_reason` — 점수 근거 한 줄

## 자동화

- GitHub Actions cron `0 23 * * *` (UTC) = 매일 08:00 KST
- 수동 실행: Actions 탭 → "Daily biotech briefing" → Run workflow
- `data/history/YYYY-MM-DD.json`에 일별 누적
- `data/cache.json`은 link 기준 분석 결과 영구 캐시 (재분석 비용 0)

## 로컬 실행

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # Windows: setx ANTHROPIC_API_KEY "..."
python biotech_daily.py
```

또는 Windows에서는 `run.bat` 더블클릭.

## 비용

- Sonnet 4.6 + prompt caching, 항목당 ~$0.005
- 일 15-20건 신규 분석 → 일 ~$0.08, 월 ~$2.4
