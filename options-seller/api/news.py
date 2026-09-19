"""Attributed RSS headlines, per-source stale fallback, and editorial product ideas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

SOURCES = [
    ("Cboe Insights", "Options", "https://www.cboe.com/insights/rss/"),
    ("CNBC", "Markets", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Federal Reserve", "Markets", "https://www.federalreserve.gov/feeds/press_all.xml"),
]
CACHE = Path(__file__).resolve().parents[1] / "data" / "news_cache.json"
LOCK = threading.Lock()


def parse_feed(body, source, category):
    root = ET.fromstring(body)
    rows = []
    for item in root.findall(".//item")[:40]:
        title = html.unescape(item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or urlparse(url).scheme not in ("https", "http"):
            continue
        raw = item.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            published = dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            published = None
        rows.append({"id": hashlib.sha256(url.encode()).hexdigest()[:16], "title": title,
                     "url": url, "source": source, "category": category, "published": published})
    return rows


def fetch_source(spec):
    source, category, url = spec
    req = Request(url, headers={"User-Agent": "PulsePaperDashboard/1.0 (RSS reader)", "Accept": "application/rss+xml, application/xml, text/xml"})
    with urlopen(req, timeout=7) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000: raise ValueError("Feed too large")
    rows = parse_feed(body, source, category)
    if not rows: raise ValueError("No headlines in feed")
    return rows


def ideas(items):
    themes = [
        ("event-risk", "Event risk beside every position", "earn|fed|rate|inflation", "Place earnings, Fed decisions and ex-dividend dates beside open positions, with a plain-language explanation of the exposure.", "Measure how often paper trades cross a flagged event without a review.", "Medium"),
        ("volatility-lab", "A volatility stress lab", "volatil|vix|option|0dte", "Let users test a price move, volatility jump and one day of time decay against their paper book before opening a trade.", "Measure whether stress previews reduce outsized paper losses.", "Large"),
        ("trade-journal", "Turn news into a trade journal", "market|stock|trade", "Attach a headline and a short thesis to a paper trade; revisit the thesis when the position closes.", "Track journal completion and results by thesis tag.", "Small"),
    ]
    out = []
    for key, title, pattern, detail, measure, effort in themes:
        related = next((x for x in items if re.search(pattern, x["title"], re.I)), None)
        out.append({"id": key, "title": title, "detail": detail, "measure": measure, "effort": effort,
                    "related_title": related["title"] if related else None, "related_url": related["url"] if related else None})
    out.append({"id": "data-trust", "title": "Make every number traceable", "detail": "Add a source and mark timestamp to each position, plus portable portfolio backups. Separate demo, stale and quoted values throughout the app.", "measure": "Track stale-mark coverage and successful restore checks.", "effort": "Medium", "related_title": None, "related_url": None})
    return out


def news_feed(refresh=False):
    now = datetime.now(timezone.utc)
    with LOCK:
        try: cache = json.loads(CACHE.read_text())
        except (OSError, ValueError): cache = {"sources": {}}
        if now.timestamp() - cache.get("checked", 0) >= (10 if refresh else 600):
            def get(spec):
                name = spec[0]
                try: return name, {"items": fetch_source(spec), "fetched": now.isoformat(), "stale": False}
                except Exception:
                    old = cache["sources"].get(name, {"items": [], "fetched": None})
                    return name, {**old, "stale": True}
            with ThreadPoolExecutor(max_workers=3) as pool:
                cache["sources"] = dict(pool.map(get, SOURCES))
            cache["checked"] = now.timestamp()
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache)); tmp.replace(CACHE)
        sources = cache["sources"]
        unique = {}
        for status in sources.values():
            for row in status["items"]:
                unique.setdefault(row["url"], {**row, "stale": status["stale"]})
        items = sorted(unique.values(), key=lambda x: x["published"] or "", reverse=True)[:75]
        return {"checked_at": datetime.fromtimestamp(cache["checked"], timezone.utc).isoformat(),
                "items": items, "ideas": ideas(items),
                "sources": [{"name": name, "fetched": value["fetched"], "stale": value["stale"]} for name, value in sources.items()]}
