"""Fierce Biotech entry 1개의 모든 키와 시간 관련 필드 확인."""
import feedparser

p = feedparser.parse("https://www.fiercebiotech.com/rss/xml")
print("feed.bozo:", p.bozo)
if p.bozo:
    print("bozo_exception:", repr(p.bozo_exception))
print("entries count:", len(p.entries))
if not p.entries:
    raise SystemExit("no entries")

e = p.entries[0]
print("\n=== first entry keys ===")
print(sorted(e.keys()))

for k in ("published", "updated", "pubDate", "date", "dc_date", "created"):
    if k in e:
        print(f"\n  {k!r}: {e[k]!r}")
for k in ("published_parsed", "updated_parsed"):
    if k in e:
        print(f"\n  {k!r}: {e[k]!r}")
