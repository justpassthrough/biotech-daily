"""각 RSS feed에서 몇 건이 들어오고, 24h 안은 몇 건인지 진단."""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import biotech_daily as bw

now = datetime.now(timezone.utc)

for url in bw.FEEDS:
    import feedparser
    parsed = feedparser.parse(url)
    title = parsed.feed.get("title", url)
    total = len(parsed.entries)
    print(f"\n=== {title} ===")
    print(f"  feed total: {total} entries")

    if not parsed.entries:
        continue

    times = []
    for e in parsed.entries:
        t = bw.parse_entry_time(e)
        times.append(t)

    valid = [t for t in times if t is not None]
    print(f"  valid timestamps: {len(valid)}/{total}")

    if valid:
        oldest = min(valid)
        newest = max(valid)
        hrs_oldest = (now - oldest).total_seconds() / 3600
        hrs_newest = (now - newest).total_seconds() / 3600
        print(f"  oldest: {oldest.isoformat()} ({hrs_oldest:.1f}h ago)")
        print(f"  newest: {newest.isoformat()} ({hrs_newest:.1f}h ago)")

    for hours in (24, 48, 72, 168):
        cutoff = now - timedelta(hours=hours)
        n = sum(1 for t in valid if t >= cutoff)
        print(f"  within {hours}h: {n}")
