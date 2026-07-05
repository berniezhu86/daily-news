#!/usr/bin/env python3
"""
权威要闻采集脚本
数据源：新华网 (news.cn) 首页 + 人民网 (people.com.cn) 首页 + 中国地震台网
输出：authoritative_news.json
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

# 输出目录（脚本所在目录）
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(OUT_DIR, "authoritative_news.json")
MAX_NEWS = 10  # 每个源最多取10条（只保留重要新闻）

# 中国地震台网数据源
CEIC_URL = "https://data.earthquake.cn/datashare/report.shtml?PAGEID=earthquake_subao"
EARTHQUAKE_MAX = 1  # 灾害/地震等突发只取最新一条

# 权威发布只承载两类内容：国家元首/政府高层，或突发重大事件。
HEAD_OF_STATE_KEYWORDS = [
    "习近平", "国家主席", "中华人民共和国主席", "国家元首", "主席令",
    "总统", "国家总统", "副总统", "国王", "女王", "天皇", "埃米尔",
]

BREAKING_EVENT_TOPICS = [
    "地震", "海啸", "台风", "洪水", "山洪", "泥石流", "滑坡", "暴雨", "龙卷风",
    "火灾", "爆炸", "坍塌", "事故", "空难", "坠机", "列车脱轨", "沉船",
    "袭击", "枪击", "爆炸袭击", "战争", "冲突", "导弹", "空袭", "恐袭",
    "疫情", "传染病", "核事故", "泄漏",
]

BREAKING_EVENT_SIGNALS = [
    "突发", "快讯", "刚刚", "已致", "造成", "死亡", "遇难", "伤亡", "受伤", "失踪",
    "被困", "救援", "疏散", "停运", "关闭", "预警", "紧急", "进入紧急状态",
    "多少级", "级地震", "人死亡", "人遇难", "人受伤",
]

# 请求头（模拟浏览器）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def fetch_html(url):
    """抓取网页 HTML"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            # 尝试从 charset 解码
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            for part in content_type.split(";"):
                if "charset" in part:
                    charset = part.split("=")[-1].strip().lower()
                    break
            raw = resp.read()
            # 先尝试 UTF-8
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("gbk", errors="replace")
    except Exception as e:
        print(f"  ⚠️ 抓取失败: {e}", file=sys.stderr)
        return ""


def is_head_of_state_news(title):
    """国家元首/中央政府高层新闻。"""
    return any(kw in title for kw in HEAD_OF_STATE_KEYWORDS)


def is_major_breaking_event(title):
    """突发重大事件：事件主题 + 强后果/应急信号同时命中。"""
    has_topic = any(kw in title for kw in BREAKING_EVENT_TOPICS)
    has_signal = any(kw in title for kw in BREAKING_EVENT_SIGNALS)
    return has_topic and has_signal


def get_authoritative_priority(title):
    """返回权威发布优先级；0 表示不进入权威发布卡片。"""
    if is_head_of_state_news(title):
        return 2
    if is_major_breaking_event(title):
        return 1
    return 0


def is_important_news(title):
    """仅保留国家元首/政府高层，或突发重大事件。"""
    return get_authoritative_priority(title) > 0


def extract_xinhua_news(html):
    """从新华网首页提取新闻标题和链接"""
    news_list = []
    seen = set()

    skip_words = [
        "首页", "登录", "注册", "设为首页", "客户端", "更多",
        "新华网首页", "english", "手机版", "微信公众号", "微博",
        "APP", "下载", "进入频道", "新华访谈", "新华全媒+",
        "新华视点", "新华网_", "查看更多",
    ]

    # 策略1：匹配所有 c.html 的 <a> 标签（通用）
    def process_match(href, title):
        if not title or len(title) < 6 or len(title) > 250:
            return
        if any(w in title for w in skip_words):
            return
        if len(title) <= 6 and not any(c in title for c in '，。！？'):
            return
        # ★ 仅保留"重要新闻"
        if not is_important_news(title):
            return
        if href.startswith("/"):
            href = urljoin("https://www.news.cn", href)
        key = title[:25]
        if key in seen:
            return
        seen.add(key)
        date_match = re.search(r'/(\d{8})/', href)
        d = date_match.group(1) if date_match else ""
        if d:
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        news_list.append({
            "title": title, "url": href, "source": "新华社", "date": d,
        })

    # 策略1：标准 <a> 标签含纯文本（双引号href）
    text_link = re.compile(
        r'''<a[^>]*href=["']((?:https?://www\.news\.cn)?/[^"']*?/c\.html)["'][^>]*>'''
        r'([^<]+)</a>',
        re.IGNORECASE,
    )
    for m in text_link.finditer(html):
        process_match(m.group(1), m.group(2).strip())

    # 策略2：div.tit > a 结构（含内嵌标签如 <i>，单/双引号）
    tit_link = re.compile(
        r'''<div[^>]*class=["'][^"']*tit[^"']*["'][^>]*>\s*'''
        r'''<a[^>]*href=["']((?:https?://www\.news\.cn)?/[^"']*?/c\.html)["'][^>]*>'''
        r'(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    for m in tit_link.finditer(html):
        raw = m.group(2)
        title = re.sub(r"<[^>]+>", "", raw)
        title = re.sub(r"\s+", " ", title).strip()
        process_match(m.group(1), title)

    # 策略3：兜底 - 所有 c.html 的 <a> 标签（单/双引号，含内嵌HTML）
    all_link = re.compile(
        r'''<a[^>]*href=["']((?:https?://www\.news\.cn)?/[^"']*?/c\.html)["'][^>]*>'''
        r'(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    for m in all_link.finditer(html):
        raw = m.group(2)
        # 跳过纯图片链接
        if "<img" in raw and not re.sub(r"<[^>]+>", "", raw).strip():
            continue
        title = re.sub(r"<[^>]+>", "", raw)
        title = re.sub(r"\s+", " ", title).strip()
        process_match(m.group(1), title)

    # 高层时政优先，其次突发重大事件；同级按日期倒序。
    news_list.sort(key=lambda x: (get_authoritative_priority(x.get("title", "")), x.get("date", "")), reverse=True)
    return news_list[:MAX_NEWS]


def extract_people_news(html):
    """从人民网首页提取新闻标题和链接"""
    news_list = []
    # 人民网新闻链接格式: http://xxx.people.com.cn/n1/2026/0625/...
    link_pattern = re.compile(
        r'<a[^>]*href="(https?://[^"]*?people\.com\.cn/n\d+/(\d{4})/(\d{4})/[^"]*?)"[^>]*>'
        r'(.*?)</a>',
        re.DOTALL,
    )
    seen = set()
    for m in link_pattern.finditer(html):
        href = m.group(1)
        year, md = m.group(2), m.group(3)  # 2026, 0625
        inner = m.group(4).strip()
        title = re.sub(r"<[^>]+>", "", inner)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 10 or len(title) > 200:
            continue
        skip_words = [
            "首页", "登录", "注册", "人民网", "English", "手机版",
            "客户端", "微博", "微信", "更多", "人民网>>", "copyright",
            "人民网版权所有", "关于我们", "人民日报社简介", "RSS",
        ]
        if any(w in title for w in skip_words):
            continue
        # ★ 仅保留"重要新闻"
        if not is_important_news(title):
            continue
        key = title[:25]
        if key in seen:
            continue
        seen.add(key)
        try:
            d = f"{year}-{md[:2]}-{md[2:]}"
        except:
            d = ""
        news_list.append({
            "title": title,
            "url": href,
            "source": "人民日报",
            "date": d,
        })
    news_list.sort(key=lambda x: (get_authoritative_priority(x.get("title", "")), x.get("date", "")), reverse=True)
    return news_list[:MAX_NEWS]


def deduplicate(news_list):
    """基于标题相似度去重，保留首次出现的来源"""
    result = []
    seen_titles = set()
    for item in news_list:
        # 取标题前20字做简单去重
        key = item["title"][:20].replace(" ", "").replace("　", "")
        if key in seen_titles:
            continue
        seen_titles.add(key)
        result.append(item)
    return result


def fetch_ceic_earthquake():
    """
    从中国地震台网中心 (data.earthquake.cn) 获取最新地震数据
    返回格式与权威发布一致: [{title, url, source, date}]
    """
    print("  抓取中国地震台网地震数据...")
    html = fetch_html(CEIC_URL)
    if not html:
        print("  ❌ 中国地震台网抓取失败")
        return []

    # 解析表格数据
    tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL)
    if len(tables) < 2:
        print("  ⚠️ 未找到地震数据表格")
        return []

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tables[1], re.DOTALL)
    earthquake_list = []

    for row in rows[1:]:  # 跳过表头
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 7:
            continue

        # 从每个 td 中提取纯文本（去掉 div 标签）
        def extract_text(html_cell):
            return re.sub(r'<[^>]+>', '', html_cell).strip()

        # cell索引: 0=序号, 1=(空隐藏列), 2=发震时刻, 3=经度, 4=纬度, 5=深度, 6=震级, 7=参考位置, 8=事件类型
        eq_time = extract_text(cells[2])   # 发震时刻
        depth = extract_text(cells[5])     # 深度(km)
        mag = extract_text(cells[6])       # 震级(M)
        location = extract_text(cells[7])  # 参考位置

        if not eq_time or not mag or not location:
            continue

        try:
            mag_float = float(mag)
        except ValueError:
            continue

        # 过滤：国内有感地震 (M >= 3.0)
        if mag_float < 3.0:
            continue

        # 提取日期（格式: "2026-7-05 23:20:13"）
        date_str = ""
        date_match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', eq_time)
        if date_match:
            y, m, d = date_match.group(1), date_match.group(2).zfill(2), date_match.group(3).zfill(2)
            date_str = f"{y}-{m}-{d}"

        # 构建标题
        title = f"{location}发生{mag}级地震 震源深度{depth}千米"

        earthquake_list.append({
            "title": title,
            "url": CEIC_URL,
            "source": "中国地震台网",
            "date": date_str,
            "mag": mag_float,
            "_eq_time": eq_time,
        })

    # 按时序倒序（最新在前），取前 EARTHQUAKE_MAX 条
    earthquake_list.sort(key=lambda x: x.get("_eq_time", ""), reverse=True)
    result = earthquake_list[:EARTHQUAKE_MAX]

    print(f"  ✅ 获取 {len(result)} 条地震数据")
    for eq in result:
        print(f"     M{eq['mag']} {eq['title']}")

    # 清理内部字段（打印之后）
    for item in result:
        item.pop("mag", None)
        item.pop("_eq_time", None)
    return result


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    tz = timezone(timedelta(hours=8))

    all_news = []

    # 1. 新华网
    print(f"[{now.strftime('%H:%M:%S')}] 抓取新华网首页...")
    html = fetch_html("https://www.news.cn/")
    if html:
        xinhua = extract_xinhua_news(html)
        print(f"  ✅ 获取 {len(xinhua)} 条")
        all_news.extend(xinhua)
    else:
        print("  ❌ 新华网抓取失败")

    # 2. 人民网
    print(f"[{now.strftime('%H:%M:%S')}] 抓取人民网首页...")
    html = fetch_html("http://www.people.com.cn/")
    if html:
        people = extract_people_news(html)
        print(f"  ✅ 获取 {len(people)} 条")
        all_news.extend(people)
    else:
        print("  ❌ 人民网抓取失败")

    # 3. 中国地震台网（地震实时消息）
    print(f"[{now.strftime('%H:%M:%S')}] 抓取中国地震台网...")
    earthquakes = fetch_ceic_earthquake()
    all_news.extend(earthquakes)

    # 4. 去重 + 最终过滤排序
    all_news = [n for n in deduplicate(all_news) if is_important_news(n.get("title", ""))]
    all_news.sort(key=lambda x: (get_authoritative_priority(x.get("title", "")), x.get("date", "")), reverse=True)
    print(f"  去重过滤后共 {len(all_news)} 条权威要闻")

    # 4. 输出 JSON
    output = {
        "updated": now.isoformat(),
        "updated_display": now.strftime("%m月%d日 %H:%M"),
        "count": len(all_news),
        "news": all_news,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  📁 已保存至 {OUT_FILE}")


if __name__ == "__main__":
    main()
