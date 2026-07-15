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
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parent
POOL_FILE = ROOT / "news_pool.json"
ARRAYS_FILE = ROOT / "generated_news_arrays.js"
INDEX_FILE = ROOT / "index.html"
STATE_FILE = ROOT / "news_refresh_state.json"
REPORT_FILE = ROOT / "news_refresh_report.json"
NEWS_DATA_FILE = ROOT / "news_data.json"

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

REQUIRED_NONEMPTY_SECTIONS = {
    "stock": "财经市场",
}

AUTHORITY_PATTERNS = [
    "新华社", "新华网", "央视", "中央广播电视总台", "人民日报", "人民网",
    "中国新闻网", "中新社", "央广网", "中国政府网", "国务院", "外交部",
    "国防部", "商务部", "发改委", "财政部", "教育部", "国家能源局",
    "国家统计局", "应急管理部", "中国人大网", "人民政协报", "中国火箭军",
    "财联社", "证券时报", "中国证券报", "上海证券报", "第一财经",
    "21世纪经济报道", "经济参考报", "中新经纬", "国际金融报", "界面新闻",
]

LOW_QUALITY_PATTERNS = [
    "自媒体", "网红", "小红书", "X：", "公众号：", "综合", "转载", "佚名",
    "替补席看球", "体坛微侃球", "足球大腕", "球迷", "荐股", "牛股", "内幕",
    "我爱英超", "风电体育", "体坛面对面",
    "懒喵体育", "第十一人", "侧身凌空斩", "乒烧足篮排", "奥拜尔",
]

OFFICIAL_FOOTBALL_SOURCES = [
    "河南足球俱乐部", "中超联赛", "中国足协",
]

HIGH_POLITICS_PATTERNS = [
    "习近平", "国家主席", "中共中央总书记", "中央军委主席", "国家主席令",
    "国务院总理", "国务院常务会议", "国务院", "中共中央",
    "全国人大常委会", "赵乐际", "王沪宁", "丁薛祥", "韩正", "蔡奇",
    "中央军委", "全国政协", "外交部", "国台办", "中共中央政治局", "中央全面深化改革委员会",
]

TOP_LEADER_PATTERNS = [
    "习近平", "国家主席", "中央军委主席", "中共中央总书记",
]

DISASTER_PATTERNS = [
    "地震", "强震", "余震", "震级", "洪水", "暴雨", "台风", "山洪",
    "泥石流", "滑坡", "内涝", "灾害", "灾情", "预警", "应急响应",
    "救援", "伤亡", "死亡人数", "遇难", "受伤", "失踪", "火灾",
    "山火", "爆炸", "坍塌", "沉船", "矿难",
]

SERIOUS_DISASTER_PATTERNS = [
    "黄色预警", "橙色预警", "红色预警", "启动", "应急响应",
    "死亡人数", "遇难", "受伤", "失踪", "强震", "连发", "重大",
    "特大", "救援", "灾区", "防汛", "抗震救灾",
]

SPORTS_CONTEXT_PATTERNS = [
    "世界杯", "国际足联", "比赛", "球队", "球员", "足球", "中超",
    "NBA", "英格兰队", "墨西哥队", "vs",
]

LIFE_SAFETY_PATTERNS = [
    "死亡人数", "遇难", "受伤", "失踪", "预警", "应急响应", "救援",
    "防汛", "抗震救灾", "山洪", "泥石流", "坍塌", "沉船", "矿难",
]

STOCK_REQUIRED_PATTERNS = [
    "股", "A股", "港股", "美股", "基金", "债", "期货", "证券", "交易所",
    "上市", "财报", "业绩", "净利", "营收", "融资", "投资", "金融", "经济",
    "资本市场", "利率", "汇率", "央行", "关税", "贸易", "新能源汽车",
    "消费", "产业", "价格", "航线燃油", "数字金融",
]

FINANCE_SOURCE_PATTERNS = [
    "财联社", "证券时报", "中国证券报", "上海证券报", "第一财经",
    "21世纪经济报道", "经济参考报", "中新经纬", "国际金融报",
    "人民财讯", "证券日报", "每日经济新闻", "界面新闻", "澎湃财讯",
    "读创", "北京商报", "财新",
]

STOCK_CORE_PATTERNS = [
    "A股", "港股", "美股", "沪指", "深成指", "创业板", "科创板", "北交所",
    "交易所", "IPO", "上市", "财报", "业绩", "净利", "营收", "公告",
    "融资", "投资", "基金", "债券", "期货", "证券", "股东", "减持",
    "增持", "回购", "分红", "利率", "汇率", "央行", "资本市场",
]

STOCK_OFFTOPIC_PATTERNS = [
    "赛场", "足球", "世界杯", "友谊赛", "冠军赛", "温网", "NBA",
    "文旅", "旅游", "游艇", "美食", "演唱会", "音乐会", "电影",
    "电视剧", "综艺", "首店", "赏荷", "登山",
]

STOCK_MARKETING_PATTERNS = [
    "值得关注", "ETF基金日报", "强势上涨", "赛道景气度",
    "捕捉", "布局低利率时代", "稳健投资新机遇",
    "ETF平安", "ETF华夏", "ETF南方",
]

ENTERTAINMENT_OFFTOPIC_PATTERNS = [
    "足球", "中超", "世界杯", "F1", "赛车", "排球", "网球", "自行车",
    "NBA", "CBA", "夏联", "球员", "体育", "省运会", "体育+", "体育文化",
    "羽毛球", "男篮", "全国冠军赛", "国家队", "后卫",
    "体育旅游", "竞彩", "人工智能大会",
    "AI科技", "财经", "基金", "A股", "法治", "法院", "施工合同", "研学",
    "消费补贴", "文旅消费", "旅游季", "首发经济", "边境味道", "会客厅",
    "球衣", "卖淫", "融资", "订单", "美食", "炸货店",
    "切尔西", "沙特联", "金靴", "勇士旧将",
    "股价", "股东", "茶饮股",
    "探店", "推广遇套路", "布泽尔", "威尔逊初次交手",
    "青创大赛", "消费券", "循环经济", "新三样", "文旅", "旅游",
]

ENTERTAINMENT_HARD_OFFTOPIC_PATTERNS = [
    "国际足联", "世界杯", "西甲", "足球", "中超", "NBA", "CBA",
    "雷速体育", "体坛周报", "懂球帝", "CSL中超联赛",
    "羽毛球", "男篮", "新秀观察",
]

ENTERTAINMENT_CONTEXT_PATTERNS = [
    "电影", "电视剧", "剧集", "综艺", "音乐", "演唱会", "演员", "导演",
    "票房", "影院", "院线", "娱乐", "微电影", "团播", "舞台剧", "纪录片",
    "首映", "公映", "定档", "百花奖", "黑神话", "主角", "约翰·传奇",
]

SPORTS_EVENT_PATTERNS = [
    "中超", "河南队", "河南", "足协杯", "足球", "联赛", "积分榜", "赛程",
    "国安", "泰山", "海港", "津门虎", "新鹏城", "玉昆", "青岛西海岸",
    "梅州客家", "成都蓉城", "申花", "浙江队",
]

SPORTS_TRUSTED_SOURCES = [
    "中国新闻网", "新华社", "央视", "人民网", "金台资讯", "大河网",
    "北京日报", "新黄河", "体坛周报", "足球报", "懂球帝", "雷速体育",
    "正观新闻", "河南足球俱乐部", "中超联赛", "中国足协",
]

FOOTBALL_OFFTOPIC_PATTERNS = [
    "啤酒节", "演唱会", "音乐节", "文旅", "旅游", "美食", "会场",
    "开幕式", "电影", "电视剧", "综艺", "消费券",
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
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%m-%d %H:%M", "%m月%d日 %H:%M"):
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


def event_key(item: dict) -> str | None:
    title = item.get("title") or ""
    if "去世" in title:
        match = re.search(r"([\u4e00-\u9fa5·]{2,4})去世", title)
        if match:
            return "death:" + match.group(1)
    return None


def has_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def is_authoritative(item: dict) -> bool:
    text = f"{item.get('source','')} {item.get('url','')}"
    return has_any(text, AUTHORITY_PATTERNS)


def is_low_quality(item: dict) -> bool:
    text = f"{item.get('source','')} {item.get('title','')} {item.get('summary','')}"
    patterns = LOW_QUALITY_PATTERNS
    if has_any(str(item.get("source", "")), OFFICIAL_FOOTBALL_SOURCES):
        patterns = [p for p in LOW_QUALITY_PATTERNS if p != "球迷"]
    return has_any(text, patterns) or has_any(item.get("title", ""), GENERIC_TITLE_PATTERNS)


def is_high_politics(item: dict) -> bool:
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('source','')}"
    if has_any(text, HIGH_POLITICS_PATTERNS):
        return True
    if "李强" not in text:
        return False
    return has_any(text, ["国务院总理", "国务院常务会议", "主持召开", "会见", "出席"])


def is_top_leader_politics(item: dict) -> bool:
    text = f"{item.get('title','')} {item.get('summary','')} {' '.join(item.get('keywords') or [])}"
    return is_high_politics(item) and has_any(text, TOP_LEADER_PATTERNS)


def is_priority_high_politics(item: dict) -> bool:
    return is_high_politics(item) and (
        bool(item.get("fromPoliticsTopPool"))
        or str(item.get("sourceRegion", "")) == "politics_top_pool"
        or is_authoritative(item)
    )


def is_breaking_disaster(item: dict) -> bool:
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('source','')}"
    if has_any(text, SPORTS_CONTEXT_PATTERNS) and not has_any(text, LIFE_SAFETY_PATTERNS):
        return False
    return has_any(text, DISASTER_PATTERNS) and has_any(text, SERIOUS_DISASTER_PATTERNS)


def numeric_score(item: dict, *names: str) -> float:
    for name in names:
        try:
            value = item.get(name)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


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
    if is_breaking_disaster(item) and is_authoritative(item):
        disaster_freshness = max(0.0, 48.0 - min(age, 96.0)) / 48.0
        score += (24.0 + disaster_freshness * 12.0) if age <= 48 else 4.0
    if section == "domestic" and is_priority_high_politics(item):
        score += 18.0 if age <= 48 else 6.0
        importance = numeric_score(item, "importanceScore", "importance_score")
        authority = numeric_score(item, "authorityScore", "authority_score")
        if importance:
            score += max(0.0, min(5.0, (importance - 80.0) / 3.0))
        if authority:
            score += max(0.0, min(2.0, (authority - 90.0) / 4.0))
    if section == "domestic" and is_top_leader_politics(item) and is_priority_high_politics(item) and age <= 48:
        score += 8.0
    if section == "domestic" and age > 48 and is_priority_high_politics(item):
        score -= 4.0
    if section == "domestic" and not is_high_politics(item) and not is_authoritative(item):
        score -= 8.0
    if section == "stock":
        text = f"{item.get('title','')} {item.get('summary','')} {item.get('source','')}"
        if has_any(text, FINANCE_SOURCE_PATTERNS):
            score += 6.0
        if has_any(text, STOCK_CORE_PATTERNS):
            score += 4.0
        if has_any(text, STOCK_OFFTOPIC_PATTERNS) and not has_any(text, STOCK_CORE_PATTERNS):
            score -= 10.0
    if len((item.get("summary") or "").strip()) >= 60:
        score += 1.2
    if len((item.get("summary") or "").strip()) < 24:
        score -= 2.5
    if section in {"henan", "csl"} and age > 96:
        score -= 12.0
    if section in {"henan", "csl"} and age > 168:
        score -= 12.0

    key = news_key(item)
    exposure = state.get("exposure", {}).get(key, {})
    front_count = int(exposure.get("front_count") or 0)
    # Rotate ordinary items out of the first screen after repeated exposure.
    if not (section == "domestic" and is_high_politics(item)):
        score -= min(6.0, front_count * 1.5)

    return score


def section_item_allowed(item: dict, section: str) -> bool:
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('source','')}"
    if section == "stock":
        if age_hours(item, now_local()) > 168:
            return False
        if has_any(text, STOCK_OFFTOPIC_PATTERNS) and not has_any(text, STOCK_CORE_PATTERNS):
            return False
        if has_any(text, STOCK_MARKETING_PATTERNS):
            return False
        return has_any(text, STOCK_REQUIRED_PATTERNS)
    if section in {"henan", "csl"}:
        if is_low_quality(item):
            return False
        if has_any(text, ["航运", "绿色燃料", "港口", "船舶"]):
            return False
        if has_any(text, FOOTBALL_OFFTOPIC_PATTERNS) and not has_any(text, ["中超", "足球", "河南队", "河南足球", "赛程", "积分榜", "联赛"]):
            return False
        if age_hours(item, now_local()) > 168:
            return False
        if not has_any(str(item.get("source", "")), SPORTS_TRUSTED_SOURCES):
            return False
        if section == "henan":
            return has_any(text, ["河南队", "河南足球", "河南俱乐部", "河南球迷", "三镇vs河南", "武汉三镇vs河南"])
        return has_any(text, SPORTS_EVENT_PATTERNS)
    if section == "entertainment":
        if age_hours(item, now_local()) > 168:
            return False
        title_source = f"{item.get('title','')} {item.get('source','')}"
        if has_any(title_source, ENTERTAINMENT_HARD_OFFTOPIC_PATTERNS):
            return False
        if has_any(text, ENTERTAINMENT_OFFTOPIC_PATTERNS) and not has_any(text, ENTERTAINMENT_CONTEXT_PATTERNS):
            return False
    return True


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
        event = event_key(item)
        if event and event in by_key:
            idx = by_key[event]
            kept[idx] = better_duplicate(kept[idx], item, now, state, section)
            duplicate_count += 1
            continue
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
        if event:
            by_key[event] = len(kept)
        kept.append(item)
    return kept, duplicate_count


def sort_section(items: list[dict], now: datetime, state: dict, section: str) -> list[dict]:
    def sort_key(item: dict):
        score = item_quality(item, now, state, section)
        age = age_hours(item, now)
        politics_pin = 1 if section == "domestic" and is_priority_high_politics(item) and age <= 48 else 0
        top_leader_pin = 1 if section == "domestic" and is_top_leader_politics(item) and is_priority_high_politics(item) and age <= 48 else 0
        disaster_pin = 1 if is_breaking_disaster(item) and is_authoritative(item) and age <= 48 else 0
        authority = 1 if is_authoritative(item) else 0
        return (top_leader_pin, politics_pin, disaster_pin, score, authority, -age)

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


def source_section_count(section: str) -> int:
    """Count fresh Workbuddy items for a section when news_data.json exists."""
    if not NEWS_DATA_FILE.exists() or section not in ARRAY_MAP:
        return 0
    try:
        data = json.loads(NEWS_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    sections = data.get("sections", {})
    main_var, extra_var = ARRAY_MAP[section]
    count = len(sections.get(main_var, []) or [])
    if extra_var:
        count += len(sections.get(extra_var, []) or [])
    return count


def js_array_count(text: str, var_name: str) -> int:
    pattern = re.compile(rf"const\s+{re.escape(var_name)}\s*=\s*\[", re.M)
    m = pattern.search(text)
    if not m:
        return -1
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
                return text[pos : i + 1].count("{rank:")
    return -1


def validate_required_sections(pool: dict[str, list[dict]], stage: str) -> None:
    for section, label in REQUIRED_NONEMPTY_SECTIONS.items():
        pool_count = len(pool.get(section, []) or [])
        fresh_count = source_section_count(section)
        if (pool_count > 0 or fresh_count > 0) and pool_count == 0:
            raise RuntimeError(
                f"{label}新闻源/新闻池有数据，但最终池为 0；停止发布，避免远程栏目清空。"
            )
        if stage != "written" or pool_count == 0:
            continue
        for file in (ARRAYS_FILE, INDEX_FILE):
            text = file.read_text(encoding="utf-8")
            main_var, extra_var = ARRAY_MAP[section]
            written_count = js_array_count(text, main_var)
            if extra_var:
                extra_count = js_array_count(text, extra_var)
                if extra_count > 0:
                    written_count += extra_count
            if written_count <= 0:
                raise RuntimeError(
                    f"{label}新闻池有 {pool_count} 条，但 {file.name} 输出为 0；停止发布。"
                )


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
        items = [x for x in items if section_item_allowed(x, section)]
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
            report["domesticHighPoliticsTop8"] = sum(1 for x in ordered[:8] if is_priority_high_politics(x) and age_hours(x, now) <= 48)

    validate_required_sections(ordered_pool, "ordered")
    POOL_FILE.write_text(json.dumps(ordered_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = write_arrays_files(ordered_pool)
    validate_required_sections(ordered_pool, "written")
    save_state(state, ordered_pool, now)
    report["changedArrays"] = changed
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    push_script = ROOT / "mac_push" / "generate_push_news.py"
    if push_script.exists():
        subprocess.run(["python3", str(push_script)], cwd=str(ROOT), check=False)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
