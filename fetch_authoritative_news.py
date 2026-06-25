#!/usr/bin/env python3
"""
权威要闻采集脚本
数据源：新华网 (news.cn) 首页 + 人民网 (people.com.cn) 首页
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
MAX_NEWS = 15  # 每个源最多取15条

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

    # 按日期倒序
    news_list.sort(key=lambda x: x.get("date", ""), reverse=True)
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

    # 3. 去重
    all_news = deduplicate(all_news)
    print(f"  去重后共 {len(all_news)} 条权威要闻")

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
