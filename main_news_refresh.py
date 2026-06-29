#!/usr/bin/env python3
"""Refresh main-page news ordering without touching tracking topics.

Rules:
- pin domestic high-level politics to the first screen;
- boost authoritative sources;
- merge duplicates;
- rotate ordinary news exposure so users do not keep seeing the same list.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parent
POOL_FILE = ROOT / "news_pool.json"
ARRAYS_FILE = ROOT / "generated_news_arrays.js"
INDEX_FILE = ROOT / "index.html"
STATE_FILE = ROOT / "news_refresh_state.json"
REPORT_FILE = ROOT / "news_refresh_report.json"

MAIN_LIMITS = {
    "domestic": 20,
    "international": 20,
    "ai": 20,
    "entertainment": 20,
    "stock": 20,
    "henan": 30,
    "csl": 30,
}

ARRAY_MAP = {
    "domestic": ("mockHotNewsDomestic", "mockHotNewsDomesticExtra"),
    "international": ("mockHotNewsInternational", "mockHotNewsInternationalExtra"),
    "ai": ("mockHotNewsAI", "mockHotNewsAIExtra"),
    "entertainment": ("mockEntertainment", "mockEntertainmentExtra"),
    "stock": ("mockStockNews", "mockStockNewsExtra"),
    "henan": ("mockHenanNews", None),
    "csl": ("mockCslOtherTeams", None),
}

AUTHORITY_PATTERNS = [
    "新华社", "新华网", "央视", "中央广播电视总台", "人民日报", "人民网",
    "中国新闻网", "中新社", "央广网", "中国政府网", "国务院", "外交部",
    "国防部", "商务部", "发改委", "财政部", "教育部", "国家能源局",
    "国家统计局", "应急管理部", "中国人大网", "人民政协报",
]

LOW_QUALITY_PATTERNS = [
    "自媒体", "网红", "小红书", "X：", "公众号：", "综合", "转载", "佚名",
]

HIGH_POLITICS_PATTERNS = [
    "习近平", "国家主席", "中共中央总书记", "中央军委主席", "国家主席令",
    "李强", "国务院总理", "国务院常务会议", "国务院", "中共中央",
    "全国人大常委会", "赵乐际", "王沪宁", "丁薛祥", "韩正", "蔡奇",
    "中央军委", "全国政协", "外交部", "中共中央政治局", "中央全面深化改革委员会",
]

GENERIC_TITLE_PATTERNS = [
    "关注最新进展", "快讯：", "国际快讯", "财经快讯", "AI科技快讯",
]

# Old Codex global RSS imports should not remain on the main page while
# Workbuddy owns the regular news update pipeline.
BLOCKED_SOURCE_REGIONS = {"global"}
BLOCK_GLOBAL_SECTIONS = {"international", "ai", "stock"}


def now_local() -> datetime:
    return datetime.now().replace(microsecond=0)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%m-%d %H:%M"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt.startswith("%m"):
                dt = dt.replace(year=now_local().year)
            return dt
        except ValueError:
            continue
    return None


def norm_text(value: str | None) -> str:
    value = (value or "").lower()
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"[\s\u3000\|｜:：,，.。!！?？\-—_《》\[\]（）()\"'“”‘’]+", "", value)
    return value


def news_key(item: dict) -> str:
    url = (item.get("url") or "").strip()
    if url:
        return "url:" + url.split("?")[0].rstrip("/")
    return "title:" + norm_text(item.get("title"))[:80]


def has_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def is_authoritative(item: dict) -> bool:
    text = f"{item.get('source','')} {item.get('url','')}"
    return has_any(text, AUTHORITY_PATTERNS)


def is_low_quality(item: dict) -> bool:
    text = f"{item.get('source','')} {item.get('title','')} {item.get('summary','')}"
    return has_any(text, LOW_QUALITY_PATTERNS) or has_any(item.get("title", ""), GENERIC_TITLE_PATTERNS)


def is_high_politics(item: dict) -> bool:
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('source','')}"
    return has_any(text, HIGH_POLITICS_PATTERNS)


def age_hours(item: dict, now: datetime) -> float:
    dt = parse_time(item.get("publishedAt")) or parse_time(item.get("time")) or parse_time(item.get("collectedAt"))
    if not dt:
        return 999.0
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def title_similarity(a: dict, b: dict) -> float:
    ta, tb = norm_text(a.get("title")), norm_text(b.get("title"))
    if not ta or not tb:
        return 0.0
    if ta in tb or tb in ta:
        return 0.96
    return SequenceMatcher(None, ta, tb).ratio()


def item_quality(item: dict, now: datetime, state: dict, section: str) -> float:
    age = age_hours(item, now)
    freshness = max(0.0, 48.0 - min(age, 72.0)) / 48.0
    heat = float(item.get("heat") or 0)
    score = heat + freshness * 5.0

    if is_authoritative(item):
        score += 4.0
    if is_low_quality(item):
        score -= 5.0
    if section == "domestic" and is_high_politics(item):
        score += 18.0 if age <= 48 else 6.0
    if section == "domestic" and age > 48 and is_high_politics(item):
        score -= 4.0
    if len((item.get("summary") or "").strip()) >= 60:
        score += 1.2
    if len((item.get("summary") or "").strip()) < 24:
        score -= 2.5

    key = news_key(item)
    exposure = state.get("exposure", {}).get(key, {})
    front_count = int(exposure.get("front_count") or 0)
    # Rotate ordinary items out of the first screen after repeated exposure.
    if not (section == "domestic" and is_high_politics(item)):
        score -= min(6.0, front_count * 1.5)

    return score


def better_duplicate(a: dict, b: dict, now: datetime, state: dict, section: str) -> dict:
    sa = item_quality(a, now, state, section)
    sb = item_quality(b, now, state, section)
    if abs(sa - sb) > 0.2:
        return a if sa > sb else b
    # Tie-breaker: fuller summary, newer time.
    la, lb = len(a.get("summary") or ""), len(b.get("summary") or "")
    if la != lb:
        return a if la > lb else b
    return a if age_hours(a, now) <= age_hours(b, now) else b


def dedupe_section(items: list[dict], now: datetime, state: dict, section: str) -> tuple[list[dict], int]:
    kept: list[dict] = []
    duplicate_count = 0
    by_key: dict[str, int] = {}
    for raw in items:
        item = dict(raw)
        key = news_key(item)
        if key in by_key:
            idx = by_key[key]
            kept[idx] = better_duplicate(kept[idx], item, now, state, section)
            duplicate_count += 1
            continue
        similar_idx = None
        for idx, existing in enumerate(kept):
            if title_similarity(item, existing) >= 0.9:
                similar_idx = idx
                break
        if similar_idx is not None:
            kept[similar_idx] = better_duplicate(kept[similar_idx], item, now, state, section)
            duplicate_count += 1
            continue
        by_key[key] = len(kept)
        kept.append(item)
    return kept, duplicate_count


def sort_section(items: list[dict], now: datetime, state: dict, section: str) -> list[dict]:
    def sort_key(item: dict):
        score = item_quality(item, now, state, section)
        age = age_hours(item, now)
        politics_pin = 1 if section == "domestic" and is_high_politics(item) and age <= 48 else 0
        authority = 1 if is_authoritative(item) else 0
        return (politics_pin, score, authority, -age)

    ordered = sorted(items, key=sort_key, reverse=True)
    for idx, item in enumerate(ordered, start=1):
        item["rank"] = idx
        item["heat"] = max(1, min(10, int(round(item_quality(item, now, state, section) / 3.0 + 5))))
        if section == "domestic" and is_high_politics(item) and age_hours(item, now) <= 48 and idx <= 8:
            item["badge"] = "hot"
        elif idx <= 3 and is_authoritative(item):
            item["badge"] = item.get("badge") or "rising"
    return ordered


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"exposure": {}, "runs": []}


def save_state(state: dict, ordered_pool: dict[str, list[dict]], now: datetime) -> None:
    exposure = state.setdefault("exposure", {})
    for section, items in ordered_pool.items():
        for idx, item in enumerate(items[:12], start=1):
            key = news_key(item)
            rec = exposure.setdefault(key, {"title": item.get("title", ""), "section": section, "front_count": 0})
            rec["title"] = item.get("title", "")
            rec["section"] = section
            rec["last_rank"] = idx
            rec["last_seen"] = now.isoformat(sep=" ")
            if idx <= 8:
                rec["front_count"] = int(rec.get("front_count") or 0) + 1
    # Keep state bounded.
    if len(exposure) > 1200:
        kept = sorted(exposure.items(), key=lambda kv: kv[1].get("last_seen", ""), reverse=True)[:1000]
        state["exposure"] = dict(kept)
    runs = state.setdefault("runs", [])
    runs.append({"time": now.isoformat(sep=" ")})
    state["runs"] = runs[-30:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def js_string(value) -> str:
    return json.dumps("" if value is None else value, ensure_ascii=False)


def to_js_item(item: dict, rank: int) -> str:
    title = item.get("title", "")
    source = item.get("source", "")
    summary = item.get("summary", "")
    time = item.get("publishedAt") or item.get("time") or item.get("collectedAt") or ""
    url = item.get("url", "")
    badge = item.get("badge", "")
    heat = int(item.get("heat") or 0)
    collected = item.get("collectedAt", "")
    region = item.get("sourceRegion", "")
    team = item.get("team", "")
    parts = [
        f"rank:{rank}",
        f"title:{js_string(title)}",
        f"source:{js_string(source)}",
        f"summary:{js_string(summary)}",
        f"badge:{js_string(badge)}",
        f"heat:{heat}",
        f"time:{js_string(time)}",
        f"url:{js_string(url)}",
        f"collectedAt:{js_string(collected)}",
        f"sourceRegion:{js_string(region)}",
    ]
    if team:
        parts.append(f"team:{js_string(team)}")
    return "  {" + ", ".join(parts) + "}"


def to_js_array(var_name: str, items: list[dict]) -> str:
    if not items:
        return f"const {var_name} = [];"
    body = ",\n".join(to_js_item(item, idx) for idx, item in enumerate(items, start=1))
    return f"const {var_name} = [\n{body}\n];"


def replace_const_array(text: str, var_name: str, replacement: str) -> tuple[str, bool]:
    pattern = re.compile(rf"const\s+{re.escape(var_name)}\s*=\s*\[", re.M)
    m = pattern.search(text)
    if not m:
        return text, False
    start = m.start()
    pos = m.end() - 1
    depth = 0
    in_str = None
    escape = False
    for i in range(pos, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == ";":
                    end += 1
                return text[:start] + replacement + text[end:], True
    raise RuntimeError(f"Could not find end of array {var_name}")


def write_arrays_files(pool: dict[str, list[dict]]) -> dict[str, list[str]]:
    replacements: dict[str, str] = {}
    for section, (main_var, extra_var) in ARRAY_MAP.items():
        items = pool.get(section, [])
        limit = MAIN_LIMITS.get(section, 20)
        replacements[main_var] = to_js_array(main_var, items[:limit])
        if extra_var:
            replacements[extra_var] = to_js_array(extra_var, items[limit:])

    changed = {"generated_news_arrays.js": [], "index.html": []}
    for file in (ARRAYS_FILE, INDEX_FILE):
        text = file.read_text(encoding="utf-8")
        original = text
        for var_name, replacement in replacements.items():
            text, ok = replace_const_array(text, var_name, replacement)
            if ok:
                changed[file.name].append(var_name)
        if text != original:
            backup = file.with_suffix(file.suffix + ".bak-main-refresh")
            if not backup.exists():
                backup.write_text(original, encoding="utf-8")
            file.write_text(text, encoding="utf-8")
    return changed


def main() -> None:
    now = now_local()
    pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    state = load_state()
    report = {
        "runAt": now.isoformat(sep=" "),
        "sections": {},
        "duplicateMerged": 0,
        "domesticHighPoliticsTop8": 0,
        "changedArrays": {},
    }

    ordered_pool: dict[str, list[dict]] = {}
    for section, items in pool.items():
        if not isinstance(items, list):
            ordered_pool[section] = items
            continue
        if section in BLOCK_GLOBAL_SECTIONS:
            items = [x for x in items if str(x.get("sourceRegion", "")).lower() not in BLOCKED_SOURCE_REGIONS]
        deduped, dupes = dedupe_section(items, now, state, section)
        ordered = sort_section(deduped, now, state, section)
        ordered_pool[section] = ordered
        report["duplicateMerged"] += dupes
        report["sections"][section] = {
            "before": len(items),
            "after": len(ordered),
            "duplicates": dupes,
            "authoritativeTop10": sum(1 for x in ordered[:10] if is_authoritative(x)),
        }
        if section == "domestic":
            report["domesticHighPoliticsTop8"] = sum(1 for x in ordered[:8] if is_high_politics(x) and age_hours(x, now) <= 48)

    POOL_FILE.write_text(json.dumps(ordered_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = write_arrays_files(ordered_pool)
    save_state(state, ordered_pool, now)
    report["changedArrays"] = changed
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
