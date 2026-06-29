#!/usr/bin/env python3
"""Generate latest_push_news.json for the Mac notification wrapper."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOL_FILE = ROOT / "news_pool.json"
OUTPUT_FILE = ROOT / "latest_push_news.json"
REPORT_FILE = ROOT / "mac_push" / "latest_push_report.json"

HIGH_POLITICS = [
    "习近平", "国家主席", "中共中央总书记", "中央军委主席", "李强", "国务院总理",
    "国务院常务会议", "国务院", "中共中央", "全国人大常委会", "全国政协",
    "外交部", "中央军委", "七一勋章", "国家主席令",
]
BREAKING = ["突发", "地震", "台风", "暴雨", "火灾", "爆炸", "事故", "遇难", "伤亡", "救援", "预警"]
MARKET = ["A股", "美股", "港股", "暴涨", "暴跌", "跳水", "涨停", "跌停", "油价", "金价", "央行", "美联储"]
FOOTBALL = ["河南", "彩陶坊", "中超", "赛程", "比赛", "转会", "进球", "主教练"]
AUTH = ["新华社", "新华网", "央视", "人民日报", "人民网", "中国新闻网", "央广网", "中国政府网", "外交部", "国务院"]

SECTION_LABELS = {
    "domestic": "国内",
    "international": "国际",
    "ai": "AI科技",
    "stock": "财经",
    "henan": "足球",
    "csl": "足球",
    "entertainment": "娱乐",
}
SECTION_URLS = {
    "domestic": "index.html#hotnews",
    "international": "index.html#hotnews",
    "ai": "index.html#hotnews",
    "stock": "index.html#finance",
    "henan": "index.html#football",
    "csl": "index.html#football",
    "entertainment": "index.html#entertainment",
}


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%m-%d %H:%M"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt.startswith("%m"):
                dt = dt.replace(year=now().year)
            return dt
        except ValueError:
            pass
    return None


def has_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def clean_summary(summary: str, limit: int = 90) -> str:
    summary = re.sub(r"\s+", " ", (summary or "").strip())
    if len(summary) <= limit:
        return summary
    return summary[:limit].rstrip("，。；、 ") + "…"


def push_type(section: str, item: dict) -> tuple[str | None, int]:
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('source','')}"
    source = item.get("source", "")
    score = int(item.get("heat") or 0)
    if has_any(source, AUTH):
        score += 2
    if section == "domestic" and has_any(text, HIGH_POLITICS):
        return "high_politics", score + 20
    if has_any(text, BREAKING):
        return "breaking", score + 16
    if section in {"henan", "csl"} and has_any(text, FOOTBALL):
        return "football", score + 12
    if section == "stock" and has_any(text, MARKET):
        return "market", score + 10
    return None, score


def make_id(section: str, item: dict) -> str:
    raw = item.get("url") or item.get("title") or "news"
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", raw).strip("-")[:80]
    date = (parse_time(item.get("publishedAt")) or now()).strftime("%Y%m%d")
    return f"{date}-{section}-{slug}"


def main() -> None:
    current = now()
    pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    candidates = []
    for section, items in pool.items():
        if section not in SECTION_LABELS or not isinstance(items, list):
            continue
        for item in items[:30]:
            dt = parse_time(item.get("publishedAt")) or parse_time(item.get("time")) or parse_time(item.get("collectedAt"))
            if dt and dt > current + timedelta(minutes=10):
                continue
            if dt and current - dt > timedelta(hours=48):
                continue
            kind, score = push_type(section, item)
            if not kind:
                continue
            candidates.append((score, section, kind, dt, item))

    candidates.sort(key=lambda x: (x[0], x[3] or datetime.min), reverse=True)
    picked = []
    seen_titles = set()
    kind_count = {}
    for score, section, kind, dt, item in candidates:
        title = (item.get("title") or "").strip()
        if not title or title in seen_titles:
            continue
        if kind_count.get(kind, 0) >= (3 if kind == "high_politics" else 2):
            continue
        seen_titles.add(title)
        kind_count[kind] = kind_count.get(kind, 0) + 1
        priority = "high" if kind in {"high_politics", "breaking"} else "normal"
        picked.append({
            "id": make_id(section, item),
            "title": title,
            "summary": clean_summary(item.get("summary", "")),
            "section": SECTION_LABELS[section],
            "type": kind,
            "url": item.get("url") or SECTION_URLS[section],
            "open_url": SECTION_URLS[section],
            "priority": priority,
            "published_at": (dt or current).isoformat(sep=" "),
            "source": item.get("source", ""),
            "score": score,
        })
        if len(picked) >= 8:
            break

    payload = {
        "updated_at": current.isoformat(sep=" "),
        "source": "zhenbao-main-news",
        "max_daily_normal": 5,
        "items": picked,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_FILE.write_text(json.dumps({"generated_at": payload["updated_at"], "count": len(picked), "types": kind_count}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT_FILE), "count": len(picked), "types": kind_count}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
