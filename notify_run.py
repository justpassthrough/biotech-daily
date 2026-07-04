"""
Actions 성공 시 오늘 biotech briefing 요약을 텔레그램으로 전송한다.
가장 최근 data/history/*.json을 읽어 '관련 기사 N건 + 상위 3건'을 보낸다.
이 메시지가 오는 것 자체가 '오늘 파이프라인이 끝까지 돌았다'는 신호.
(repo 루트에서 실행됨 — Actions 기본 작업 디렉터리)
"""
import glob
import json
import os

from notify_telegram import send


def main():
    files = sorted(glob.glob("data/history/*.json"))
    if not files:
        send("🧬 biotech-daily 완료 — 오늘 관련 기사 0건(또는 history 없음)")
        return
    path = files[-1]
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        send(f"🧬 biotech-daily 완료 — 결과 읽기 실패: {e}")
        return

    items = data.get("items", [])
    day = data.get("date") or os.path.basename(path)[:-5]
    lines = [f"🧬 biotech-daily 완료 ({day})", f"관련 기사 {len(items)}건"]
    for a in sorted(items, key=lambda x: x.get("relevance_score", 0), reverse=True)[:3]:
        lines.append(f"[{a.get('relevance_score', '?')}] {a.get('title', '')[:52]}")
    send("\n".join(lines))


if __name__ == "__main__":
    main()
