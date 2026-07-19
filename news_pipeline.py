#!/usr/bin/env python3
"""Build rolling news pools and update index.html arrays.

This script is intentionally stdlib-only so it can run in GitHub Actions without
extra packages. It merges the local source HTML with selected RSS feeds, keeps a
48-hour rolling pool for fast-moving news, dedupes similar titles, and writes the
JS arrays consumed by index.html.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(SCRIPT_DIR, "index.html")
SOURCE_FILE = os.path.join(SCRIPT_DIR, "臻宝每日快讯_带摘要.html")
AUTHORITATIVE_FILE = os.path.join(SCRIPT_DIR, "authoritative_news.json")
POOL_FILE = os.path.join(SCRIPT_DIR, "news_pool.json")
GENERATED_FILE = os.path.join(SCRIPT_DIR, "generated_news_arrays.js")
TRANSLATION_CACHE_FILE = os.path.join(SCRIPT_DIR, "translation_cache.json")
REVIEW_DIR = "/Users/bainian/Documents/软件测试"
FOREIGN_REVIEW_FILE = os.path.join(REVIEW_DIR, "外网新闻抓取_带摘要.html")

BEIJING = timezone(timedelta(hours=8))
ROLLING_HOURS = 48
MAX_POOL_PER_SECTION = 140
TARGET_COUNTS = {
    "domestic": 100,
    "international": 100,
    "ai": 100,
    "entertainment": 100,
    "stock": 60,
    "henan": 30,
    "csl": 30,
}
MAIN_COUNT = 20

RSS_SOURCES = {
    "international": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("The Guardian World", "https://www.theguardian.com/world/rss"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
        ("DW World", "https://rss.dw.com/xml/rss-en-world"),
    ],
    "ai": [
        ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
        ("Wired", "https://www.wired.com/feed/rss"),
        ("Engadget", "https://www.engadget.com/rss.xml"),
        ("VentureBeat AI", "https://venturebeat.com/ai/feed/"),
        ("NVIDIA AI", "https://blogs.nvidia.com/blog/category/generative-ai/feed/"),
        ("The Decoder", "https://the-decoder.com/feed/"),
        ("IEEE Spectrum", "https://spectrum.ieee.org/rss/fulltext"),
        ("ScienceDaily AI", "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml"),
        ("Nature Machine Learning", "https://www.nature.com/subjects/machine-learning.rss"),
        ("OpenAI", "https://openai.com/news/rss.xml"),
        ("Google AI", "https://blog.google/technology/ai/rss/"),
    ],
    "stock": [
        ("CNBC Markets", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
        ("The Guardian Business", "https://www.theguardian.com/business/rss"),
        ("NPR Business", "https://feeds.npr.org/1006/rss.xml"),
    ],
}

SECTION_ALIASES = {
    "ai_tech": "ai",
    "henan": "henan",
    "csl": "csl",
    "domestic": "domestic",
    "international": "international",
    "entertainment": "entertainment",
}

BAD_TITLE_PATTERNS = [
    r"中俄数字经济合作年启动",
    r"广告", r"彩票", r"优惠券", r"开奖", r"\.\.\.", r"视频\s*$", r"组图",
    r"天气", r"星座", r"测试", r"招聘", r"直播入口",
]

AI_TECH_KEYWORDS = [
    "ai", "artificial intelligence", "openai", "anthropic", "machine learning",
    "large language", "llm", "model", "chip", "semiconductor", "nvidia",
    "quantum", "robot", "robotics", "autonomous", "data center", "datacenter",
    "cloud", "gpu", "compute", "microsoft", "google", "apple intelligence",
    "deepmind", "agent", "neural", "startup", "cybersecurity"
]

AI_TECH_REJECT = ["game", "gaming", "kindle", "streaming", "trailer", "console"]

def is_ai_tech_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    if any(x in text for x in AI_TECH_REJECT) and not any(x in text for x in ["ai", "chip", "nvidia", "model"]):
        return False
    return any(x in text for x in AI_TECH_KEYWORDS)

SOURCE_AUTHORITY = {
    "新华社": 20, "人民日报": 20, "央视": 18, "BBC": 18, "Reuters": 20,
    "Associated Press": 20, "AP": 20, "The Guardian": 17, "Al Jazeera": 16,
    "NPR": 16, "DW": 16, "TechCrunch": 15, "MIT Technology Review": 18,
    "The Verge": 15, "OpenAI": 18, "Google AI": 18, "CNBC": 17,
    "MarketWatch": 16, "Yahoo Finance": 14, "河南足球俱乐部": 18,
    "中国足协": 18, "中超": 16, "正观新闻": 15, "懂球帝": 14,
}

@dataclass
class NewsItem:
    section: str
    title: str
    source: str
    summary: str
    url: str = ""
    publishedAt: str = ""
    collectedAt: str = ""
    sourceRegion: str = "cn"
    heat: int = 5
    badge: str = ""
    team: str = ""
    rawTitle: str = ""
    rawSummary: str = ""

    def key_text(self) -> str:
        if self.url and self.sourceRegion == "global":
            try:
                parsed = urllib.parse.urlparse(self.url)
                return (parsed.netloc.replace("www.", "") + parsed.path).lower().rstrip("/")[:120]
            except Exception:
                pass
        normalized = normalize_text(self.title)
        # Chinese headlines often describe the same event with small wording changes;
        # a shorter fingerprint collapses duplicates without wiping unrelated stories.
        if re.search(r"[\u4e00-\u9fff]", self.title):
            return normalized[:12]
        return normalized[:42]


def now_bj() -> datetime:
    return datetime.now(BEIJING)


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING)
        return dt.astimezone(BEIJING)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=BEIJING)
        except Exception:
            continue
    return None


def iso_minute(dt: datetime) -> str:
    return dt.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M")


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_text(value: str) -> str:
    value = clean_text(value).lower()
    value = re.sub(r"[\s\u3000]+", "", value)
    value = re.sub(r"[，。！？、；：“”‘’（）()【】\[\]《》<>\"'.,!?;:|\-—_]", "", value)
    value = re.sub(r"(最新|刚刚|突发|快讯|重磅|官宣|消息称|报道称|breaking|live)", "", value)
    return value


def is_bad_url(url: str) -> bool:
    return bool(re.search(r"VIDEXyZaBcDeFgHiJkLmNoPqRs|DeFgHiJkLmNoPqRs", url or ""))


def is_bad_title(title: str) -> bool:
    if len(clean_text(title)) < 6:
        return True
    return any(re.search(p, title, re.I) for p in BAD_TITLE_PATTERNS)


def authority_score(source: str) -> int:
    for key, score in SOURCE_AUTHORITY.items():
        if key.lower() in source.lower():
            return score
    return 8


def heat_for(item: NewsItem, rank_hint: int = 99) -> int:
    base = 5
    base += min(3, authority_score(item.source) // 7)
    published = parse_dt(item.publishedAt) or parse_dt(item.collectedAt)
    if published:
        age_h = (now_bj() - published).total_seconds() / 3600
        if age_h <= 6:
            base += 2
        elif age_h <= 24:
            base += 1
    if rank_hint <= 5:
        base += 1
    return max(5, min(10, base))


def badge_for(heat: int, published: str) -> str:
    dt = parse_dt(published)
    if heat >= 9:
        return "hot"
    if dt and (now_bj() - dt).total_seconds() <= 6 * 3600:
        return "new"
    if heat >= 8:
        return "rising"
    return ""


class SourceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.section = ""
        self.in_h2 = False
        self.h2 = ""
        self.in_title = False
        self.in_meta = False
        self.in_summary = False
        self.current: Optional[dict] = None
        self.items: Dict[str, List[NewsItem]] = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "section" and attrs.get("id"):
            self.section = SECTION_ALIASES.get(attrs.get("id", ""), attrs.get("id", ""))
        if tag == "h2" and "section-title" in cls:
            self.in_h2 = True
            self.h2 = ""
        if tag == "a" and "news-title" in cls:
            self.in_title = True
            self.current = {"title": "", "url": attrs.get("href", ""), "source": "", "summary": ""}
        if tag == "div" and "news-meta" in cls and self.current is not None:
            self.in_meta = True
        if tag == "p" and "news-summary" in cls and self.current is not None:
            self.in_summary = True

    def handle_endtag(self, tag):
        if tag == "h2" and self.in_h2:
            name = clean_text(self.h2)
            name_map = {"国内新闻": "domestic", "国际新闻": "international", "娱乐新闻": "entertainment", "河南足球": "henan", "中超动态": "csl", "AI 科技": "ai", "AI科技": "ai"}
            self.section = name_map.get(name, self.section)
            self.in_h2 = False
        if tag == "a":
            self.in_title = False
        if tag == "div":
            self.in_meta = False
        if tag == "p" and self.in_summary:
            self.in_summary = False
            if self.current and self.current.get("title") and self.section:
                src = clean_text(self.current.get("source", "")).strip("【】") or "综合新闻"
                item = NewsItem(
                    section=self.section,
                    title=clean_text(self.current.get("title", "")),
                    source=src,
                    summary=clean_text(self.current.get("summary", "")),
                    url=self.current.get("url", ""),
                    collectedAt=iso_minute(now_bj()),
                    publishedAt=infer_published_at(self.current.get("title", ""), self.current.get("summary", ""), self.current.get("url", "")),
                    sourceRegion="cn",
                )
                self.items.setdefault(self.section, []).append(item)
            self.current = None

    def handle_data(self, data):
        if self.in_h2:
            self.h2 += data
        if self.current is not None:
            if self.in_title:
                self.current["title"] += data
            elif self.in_meta:
                self.current["source"] += data
            elif self.in_summary:
                self.current["summary"] += data


def infer_date_from_text(text: str) -> str:
    text = text or ""
    today = now_bj()
    m = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if m:
        try:
            return iso_minute(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 8, 0, tzinfo=BEIJING))
        except Exception:
            pass
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        try:
            dt = datetime(today.year, int(m.group(1)), int(m.group(2)), 8, 0, tzinfo=BEIJING)
            if dt - today > timedelta(days=7):
                dt = dt.replace(year=today.year - 1)
            return iso_minute(dt)
        except Exception:
            pass
    return ""


def infer_date_from_url(url: str) -> str:
    url = url or ""
    patterns = (
        r"/(20\d{2})/(\d{1,2})/(\d{1,2})/",
        r"/(20\d{2})/(\d{2})(\d{2})(?:/|$)",
        r"/(20\d{2})(\d{2})(\d{2})/",
        r"(?:A|/)(20\d{2})(\d{2})(\d{2})[A-Z0-9]",
        r"(20\d{2})(\d{2})(\d{2})",
    )
    for pattern in patterns:
        m = re.search(pattern, url)
        if not m:
            continue
        try:
            return iso_minute(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 8, 0, tzinfo=BEIJING))
        except Exception:
            continue
    return ""


def infer_published_at(title: str, summary: str, url: str) -> str:
    return infer_date_from_text((summary or "") + " " + (title or "")) or infer_date_from_url(url)


TRUSTED_DOMESTIC_SOURCE_KEYS = (
    "新华社", "人民日报", "央视", "中国政府网", "国务院", "外交部",
    "国防部", "国家统计局", "商务部", "国家航天局", "生态环境部",
    "最高检", "中国足协", "河南足球俱乐部",
)

TRUSTED_DOMESTIC_DOMAINS = (
    "news.cn", "people.com.cn", "cctv.cn", "cntv.cn", "gov.cn",
    "mfa.gov.cn", "mod.gov.cn", "stats.gov.cn", "moe.gov.cn",
    "mofcom.gov.cn", "cnsa.gov.cn",
)

def is_trusted_domestic_item(item: NewsItem) -> bool:
    source = item.source or ""
    url = item.url or ""
    return any(k in source for k in TRUSTED_DOMESTIC_SOURCE_KEYS) or any(d in url for d in TRUSTED_DOMESTIC_DOMAINS)

def load_authoritative_domestic() -> List[NewsItem]:
    if not os.path.exists(AUTHORITATIVE_FILE):
        return []
    try:
        with open(AUTHORITATIVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    items: List[NewsItem] = []
    collected = data.get("updated_display") or iso_minute(now_bj())
    for raw in data.get("news", []):
        title = clean_text(raw.get("title", ""))
        if not title:
            continue
        source = clean_text(raw.get("source", "新华社")) or "新华社"
        published = raw.get("date") or ""
        item = NewsItem(
            section="domestic",
            title=title,
            source=source,
            summary=clean_text(raw.get("summary", "")) or f"{source}报道：{title}。",
            url=raw.get("url", ""),
            publishedAt=published,
            collectedAt=collected,
            sourceRegion="cn",
        )
        if is_trusted_domestic_item(item):
            items.append(item)
    return items


def parse_source_html() -> Dict[str, List[NewsItem]]:
    if not os.path.exists(SOURCE_FILE):
        return {}
    parser = SourceHTMLParser()
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        parser.feed(f.read())
    return parser.items


def parse_rss_datetime(node: ET.Element) -> str:
    for child_name in ("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"):
        child = node.find(child_name)
        if child is not None and child.text:
            raw = child.text.strip()
            try:
                return iso_minute(parsedate_to_datetime(raw))
            except Exception:
                dt = parse_dt(raw)
                if dt:
                    return iso_minute(dt)
    return iso_minute(now_bj())


def child_text(node: ET.Element, names: Iterable[str]) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return clean_text(child.text)
    return ""


def link_text(node: ET.Element) -> str:
    link = child_text(node, ("link", "{http://www.w3.org/2005/Atom}link"))
    if link:
        return link
    atom_link = node.find("{http://www.w3.org/2005/Atom}link")
    if atom_link is not None:
        return atom_link.attrib.get("href", "")
    return ""


def fetch_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=18) as resp:
        return resp.read()


STATIC_TRANSLATIONS = {
    "Europe heatwave: drought fears in Italy as records tumble around Europe – as it happened": "欧洲热浪持续：意大利干旱担忧加剧，多地气温刷新纪录",
    "Hezbollah rejects Israel-Lebanon agreement as Israeli attacks hit south": "真主党拒绝以黎协议，以色列袭击黎巴嫩南部",
    "JD Vance claims US holds all the cards in Iran and will win ‘either way’": "万斯称美国在伊朗问题上掌握主动，‘无论如何都会赢’",
    "With water cuts looming in Arizona in US, locals fight data centres": "美国亚利桑那面临限水，当地居民反对数据中心耗水",
    "Germany and Italy swelter in heatwave as records tumble across Europe": "德国和意大利遭遇热浪，欧洲多地高温纪录被刷新",
    "Lebanon-Israel deal may stop war crime victims seeking justice, experts say": "专家称黎以协议可能阻碍战争罪受害者寻求正义",
    "Lebanon-Israel deal may block war crime victims from seeking justice, experts warn": "专家警告：黎以协议或阻碍战争罪受害者寻求正义",
    "Sabalenka defends Wimbledon prize protest, says it’s for struggling players": "萨巴伦卡为温网奖金抗议辩护，称是为困难球员发声",
    "‘It’s become a litmus test’: wins for Israel critics shine light on key issue for Democrats": "以色列批评者胜选，凸显民主党内部关键议题",
    "Bodycam shows driver offering armed police a lift mid-chase": "执法记录仪显示：追捕中司机曾向武装警察提出搭车",
    "Toxic Bielsa leaves ‘nothing good’ behind as Uruguay suffer World Cup shock": "乌拉圭世界杯遭遇冷门，贝尔萨执教争议再起",
    "In Caracas, this feels like the hardest moment in Venezuela's modern history": "加拉加斯现场：委内瑞拉正经历现代史上最艰难时刻",
    "Burkina Faso severs diplomatic ties with France": "布基纳法索宣布与法国断绝外交关系",
    "Cape Verde break record as smallest nation to reach World Cup knockouts": "佛得角创纪录，成晋级世界杯淘汰赛人口最少国家",
    "Israel-Lebanon deal ties ceasefire to Hezbollah disarmament: Will it work?": "以黎协议将停火与真主党解除武装挂钩，能否奏效？",
    "Uzbekistan makes its World Cup debut, a first for Central Asia": "乌兹别克斯坦首次亮相世界杯，中亚足球迎来突破",
    "Venezuela leader jeered as rescue efforts hampered": "委内瑞拉救援受阻，领导人现场遭民众嘘声",
    "‘Pick up the phone’: IRGC appears to rebuff US Strait of Hormuz ‘hotline’": "伊朗革命卫队疑似拒绝美国霍尔木兹海峡热线提议",
    "Newborn baby rescued from Venezuela earthquake rubble": "委内瑞拉地震废墟中救出一名新生儿",
    "Australia to double penalty for social media ban breaches to $99m as tech giants accused of ‘not doing enough’": "澳大利亚拟将社媒禁令违规罚款翻倍至9900万美元",
    "The Kindle app for iOS has features your aging Kindle doesn't": "iOS 版 Kindle 应用新增老款 Kindle 没有的功能",
    "Half of Claude users say AI can already handle half their work according to Anthropic survey": "Anthropic 调查：半数 Claude 用户称 AI 已能处理一半工作",
    "The Guardian’s Kai Wright refuses to buy a new phone": "《卫报》Kai Wright 表示暂不购买新手机",
    "Indie developers got tired of waiting for a new Star Fox, so they’re making their own": "独立开发者等不到新《星际火狐》，决定自己开发替代作品",
    "The fittest founder in the room got cancer. Here’s how he used AI to fight back.": "一位创业者患癌后，如何借助 AI 辅助抗癌决策",
    "Engadget review recap: MSI Claw 8 EX AI+, Sony A7R VI, Ray-Ban Meta Optics and more": "Engadget 评测汇总：MSI Claw 8 EX AI+、索尼 A7R VI 等新品",
    "Why is Apple asking me to pay more for Big Tech’s AI obsession?": "苹果为何让用户为科技巨头的 AI 投入支付更多成本？",
    "J.P. Morgan sees a pile of red flags in the AI market": "摩根大通警告：AI 市场出现多重风险信号",
    "The companies most likely to automate your job are now funding a $1 billion program to retrain you": "最可能自动化岗位的公司，正资助10亿美元再培训计划",
    "Asian AI startups launch Mythos-like models as Anthropic’s export ban drags on": "Anthropic 出口限制持续，亚洲 AI 初创公司推出类 Mythos 模型",
    "A sidescrolling roguelite platformer, Steam Deck air hockey and other new indie games worth checking out": "横版 Roguelite、Steam Deck 冰球等独立游戏新品值得关注",
    "Security News This Week: LastPass Users Had Their Data Stolen—Again": "本周安全新闻：LastPass 用户数据再次遭窃",
    "The 37 Best Outdoor Deals From the REI 4th of July Sale": "REI 独立日促销：37 款户外装备折扣推荐",
    "Apple is reportedly looking to buy chips from a US-blacklisted Chinese company": "报道称苹果考虑向一家被美国列入黑名单的中国公司采购芯片",
    "Anthropic gets US approval to bring back Claude Mythos 5": "Anthropic 获美国批准，恢复 Claude Mythos 5 供应",
    "OpenAI's new flagship model GPT-5.6 Sol cheats on software tests more than any model before it": "OpenAI 新旗舰模型 GPT-5.6 Sol 被指在软件测试中作弊率更高",
    "ByteDance's \"iLLaDA\" is a diffusion language model that keeps up with Qwen2.5": "字节跳动 iLLaDA 扩散语言模型表现接近 Qwen2.5",
    "Apple executive in charge of Vision Pro is reportedly leaving for OpenAI": "报道称苹果 Vision Pro 负责人将离职加盟 OpenAI",
    "OpenAI launches a limited preview of GPT-5.6 for a 'small group of trusted partners'": "OpenAI 面向少数可信合作伙伴开启 GPT-5.6 限量预览",
    "Prime Day is almost over, but these are still the best Apple deals I’ve seen": "Prime Day 临近结束，这些苹果产品折扣仍值得关注",
    "I had gallbladder surgery. After I got home, the hospital asked me for a financial donation. Is this ethical?": "患者术后收到医院捐款请求，引发医疗伦理讨论",
    "The Average Dividend Yield is 1%. Want More Income? These 3 Stocks Offer Yields of Up 5.9%": "平均股息率仅1%，这3只股票收益率最高约5.9%",
    "Michael Burry Just Bet Big Microsoft Will More Than Double by 2028": "迈克尔·伯里重仓押注微软，预计2028年前股价或翻倍",
    "What Savara Investors Should Know About This 580,187-Option Exercise and FDA Timeline": "Savara 投资者需关注期权行权与 FDA 时间表",
    "Is NVIDIA Corporation (NVDA) One of the Best Brain-Computer Interface Stocks to Buy?": "英伟达是否是值得关注的脑机接口概念股？",
    "Abbott Laboratories (ABT) must face a Lawsuit over PediaSure, Statements about Children’s Growth": "雅培因 PediaSure 儿童成长相关表述面临诉讼",
    "Medtronic plc (MDT) CEO Discloses the Impacts of Tariffs on the Company": "美敦力 CEO 披露关税对公司的影响",
    "Snap Inc. (SNAP) Launches Specs Augmented-Reality Glasses": "Snap 发布 Specs 增强现实眼镜",
    "JPMorgan Maintains an “Overweight rating” on Bruker Corporation (BRKR)": "摩根大通维持 Bruker 股票‘增持’评级",
    "Butterfly Network, Inc. (BFLY) Comments on Midjourney’s Ultrasound Scanner Announcement": "Butterfly Network 回应 Midjourney 超声扫描仪消息",
    "NeuroPace, Inc. (NPCE) Reveals FDA Approval of ECoG Assistant™": "NeuroPace 宣布 ECoG Assistant 获 FDA 批准",
    "Is CeriBell, Inc. (CBLL) Among the Best Brain-Computer Interface Stocks to Buy?": "CeriBell 是否属于值得关注的脑机接口概念股？",
    "Another plane company enters bankruptcy, will liquidate": "又一家飞机公司进入破产程序并将清算",
    "Does AMD pay dividends? How the chipmaker spends its money": "AMD 是否分红？这家芯片公司如何使用现金",
    "What This $405,000 BJ's Restaurants Insider Sale Means After 7 Straight Growth Quarters": "BJ's Restaurants 内部人士减持40.5万美元，市场关注增长持续性",
    "Is This the Best Tech ETF to Buy With $1,000 Right Now?": "现在投入1000美元，这只科技 ETF 是否值得关注？",
    "Inflation flips Wall Street's Fed interest-rate bets": "通胀变化扭转华尔街对美联储利率路径的押注",
    "Fast-food chain closes 70 restaurants, even bigger cuts coming": "快餐连锁关闭70家门店，后续削减规模或更大",
    "Why investors may want to prioritize bond markets outside the U.S.": "为什么投资者可能应优先关注美国以外债券市场",
    "The AI bubble has further to run despite the looming crash": "尽管回调风险临近，AI 泡沫可能仍未结束",
    "‘Tech firms are losing the public’: social media age bans near tipping point": "社交媒体年龄禁令接近临界点，科技公司正在失去公众信任",
    "'Tech firms are losing the public': social media age bans near tipping point": "社交媒体年龄禁令接近临界点，科技公司正在失去公众信任",
    "With 'Operation Purgatory,' Magyar moves to demolish Orban system": "匈牙利反对派发起“炼狱行动”，试图瓦解欧尔班政治体系",
    "Between English and mother tongue: Kenya’s education language dilemma": "肯尼亚教育语言陷入两难：英语和母语该如何取舍",
    "Between English and mother tongue: Kenya's education language dilemma": "肯尼亚教育语言陷入两难：英语和母语该如何取舍",
    "Why Kim Jong Un never talks about his mother - or her controversial bloodline": "金正恩为何很少谈及母亲及其存在争议的血统背景",
    "Trump's face is added to select US passports for America's 250th birthday": "美国250周年纪念版护照加入特朗普头像引发关注",
    "Snow and ice on Swiss glaciers melting at alarming rate amid heatwave, expert says": "专家称热浪下瑞士冰川积雪和冰层正以惊人速度融化",
    "Europe Is Fed Up and Wants Its Own AI": "欧洲对依赖美国科技感到不满，推动建设自己的 AI 体系",
    "The Download: brain-melting heatwaves and unprecedented OpenAI restrictions": "MIT 科技评论：极端热浪影响大脑健康，OpenAI 限制措施引关注",
    "Ocado boss Tim Steiner’s near £100m in pay raises ‘serious concerns’": "Ocado 老板近1亿英镑薪酬引发严重争议",
    "Ocado boss Tim Steiner's near £100m in pay raises 'serious concerns'": "Ocado 老板近1亿英镑薪酬引发严重争议",
    "Lost your crypto access code? Be wary, there‘s a scam for that too": "加密资产访问码丢失骗局增多，用户求助时也可能被骗",
    "Lost your crypto access code? Be wary, there’s a scam for that too": "加密资产访问码丢失骗局增多，用户求助时也可能被骗",
    "SpaceX to join the Nasdaq-100 in a fast-tracked process that will drive huge ETF buying demand": "SpaceX 将快速纳入纳斯达克100，或带来大量 ETF 买盘需求",
    "Americans’ 401(k) balances hit record levels last year. See how you compare.": "美国人401(k)退休账户余额去年创纪录，个人差距引关注",
    "Americans' 401(k) balances hit record levels last year. See how you compare.": "美国人401(k)退休账户余额去年创纪录，个人差距引关注",
    "They put thousands into a savings app that promised safety and a free lottery — when it fell apart, some got $0.75 back": "储蓄应用承诺安全和抽奖后崩盘，有用户投入数千美元仅拿回75美分",
    "World Cup fans are missing games after their resale tickets fall through": "世界杯球迷因转售票失效错过比赛，二级票务风险受关注",
    "Paul Hogan has reportedly called Pauline Hanson a ‘pelican’. Please explain?": "澳大利亚演员保罗·霍根称政客汉森为“鹈鹕”，澳式俚语引发讨论",
    "Paul Hogan has reportedly called Pauline Hanson a 'pelican'. Please explain?": "澳大利亚演员保罗·霍根称政客汉森为“鹈鹕”，澳式俚语引发讨论",
    "Heatwave breaks records in Germany, Denmark and Czech Republic": "德国、丹麦和捷克高温纪录被热浪打破",
    "Serbia’s President Aleksandar Vucic says will resign within ‘weeks’": "塞尔维亚总统武契奇称将在数周内辞职",
    "Serbia's President Aleksandar Vucic says will resign within 'weeks'": "塞尔维亚总统武契奇称将在数周内辞职",
    "Why is the US targeting Germany's drug industry?": "美国为何将矛头指向德国制药业？",
    "China Defies US Restrictions and Builds the World’s Fastest Supercomputer": "中国突破美国限制建成全球最快超级计算机",
    "China Defies US Restrictions and Builds the World's Fastest Supercomputer": "中国突破美国限制建成全球最快超级计算机",
    "Sina's open model VibeThinker-3B aims to show reasoning compresses well but factual knowledge doesn't": "新浪开源 VibeThinker-3B：展示推理能力可压缩，事实知识难压缩",
    "SoftBank’s CEO isn’t the only one with questions about Elon Musk’s orbital data center hype": "软银 CEO 质疑马斯克太空数据中心热潮，行业也有疑问",
    "SoftBank's CEO isn't the only one with questions about Elon Musk's orbital data center hype": "软银 CEO 质疑马斯克太空数据中心热潮，行业也有疑问",
    "Margaret Atwood says the problem with AI is ‘garbage in, garbage out’": "作家玛格丽特·阿特伍德称 AI 最大问题是“垃圾进，垃圾出”",
    "Margaret Atwood says the problem with AI is 'garbage in, garbage out'": "作家玛格丽特·阿特伍德称 AI 最大问题是“垃圾进，垃圾出”",
    "Labour has abandoned the missions that brought it to power. Here's how Burnham could revive them. | Mariana Mazzucato": "英国工党被指放弃执政使命，伯纳姆路线或可重启政策议程",
    "This disease is more expensive than cancer and heart disease combined. And it’s only going to get worse.": "这种疾病成本超过癌症和心脏病总和，未来负担可能继续加重",
    "This disease is more expensive than cancer and heart disease combined. And it's only going to get worse.": "这种疾病成本超过癌症和心脏病总和，未来负担可能继续加重",
    "Berkshire CEO Greg Abel sworn in as U.S. citizen at baseball game": "伯克希尔 CEO 格雷格·阿贝尔在棒球赛现场宣誓成为美国公民",
    "Missouri dad stashes stocks in a coffee can for his 3 daughters. He says with time, they’ll grow to $500 million": "密苏里父亲为三个女儿长期持股，称未来或增长至5亿美元",
    "Missouri dad stashes stocks in a coffee can for his 3 daughters. He says with time, they'll grow to $500 million": "密苏里父亲为三个女儿长期持股，称未来或增长至5亿美元",
    "Rising cost of insuring against climate crisis will have wider knock-on effects for UK economy | Heather Stewart": "气候危机保险成本上升，或对英国经济产生连锁冲击"
}


_TRANSLATION_CACHE: Optional[Dict[str, str]] = None
_TRANSLATION_CACHE_DIRTY = False


def load_translation_cache() -> Dict[str, str]:
    global _TRANSLATION_CACHE
    if _TRANSLATION_CACHE is not None:
        return _TRANSLATION_CACHE
    try:
        _TRANSLATION_CACHE = json.load(open(TRANSLATION_CACHE_FILE, "r", encoding="utf-8"))
    except Exception:
        _TRANSLATION_CACHE = {}
    return _TRANSLATION_CACHE


def save_translation_cache() -> None:
    global _TRANSLATION_CACHE_DIRTY
    if not _TRANSLATION_CACHE_DIRTY or _TRANSLATION_CACHE is None:
        return
    with open(TRANSLATION_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_TRANSLATION_CACHE, f, ensure_ascii=False, indent=2, sort_keys=True)
    _TRANSLATION_CACHE_DIRTY = False


def translate_with_google_gtx(text: str) -> str:
    query = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "en",
        "tl": "zh-CN",
        "dt": "t",
        "q": text,
    })
    url = "https://translate.googleapis.com/translate_a/single?" + query
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 zhenbao-news-pipeline"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    data = json.loads(raw)
    pieces = []
    for part in data[0] or []:
        if part and part[0]:
            pieces.append(part[0])
    return clean_text("".join(pieces))


def translate_text_optional(text: str, section: str) -> str:
    """Translate external RSS text to Chinese with cache and graceful fallback."""
    text = clean_text(text)
    if not text or re.search(r"[\u4e00-\u9fff]", text):
        return text
    static = STATIC_TRANSLATIONS.get(text)
    if static:
        return static
    cache = load_translation_cache()
    cache_key = section + "|" + text
    cached = cache.get(cache_key)
    if cached:
        return cached
    api = os.environ.get("TRANSLATION_API_URL", "").strip()
    try:
        if api:
            payload = urllib.parse.urlencode({"text": text, "section": section}).encode("utf-8")
            req = urllib.request.Request(api, data=payload, headers={
                "User-Agent": "zhenbao-news-pipeline/1.0",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read().decode("utf-8", "ignore").strip()
            try:
                data = json.loads(raw)
                translated = clean_text(data.get("text") or data.get("translation") or "")
            except Exception:
                translated = clean_text(raw)
        elif os.environ.get("ENABLE_ONLINE_TRANSLATION") == "1":
            translated = translate_with_google_gtx(text)
        else:
            translated = ""
        if translated and re.search(r"[\u4e00-\u9fff]", translated):
            cache[cache_key] = translated
            global _TRANSLATION_CACHE_DIRTY
            _TRANSLATION_CACHE_DIRTY = True
            return translated
    except Exception as exc:
        print(f"  WARN translation failed: {exc}")
    return text


GENERIC_TITLE_RE = re.compile(r"^(国际|财经|AI科技)快讯[:：].*(关注最新进展|关注市场新变化|关注产业新动态)|^(国际|财经|AI科技)快讯[:：]", re.I)

SLUG_TITLE_TRANSLATIONS = {
    "australian-man-charged-thailand-teenage-girl-body-found-in-suitcase-pattaya-city": "澳大利亚男子在泰国被控谋杀，少女遗体在芭堤雅行李箱中被发现",
    "with-operation-purgatory-magyar-moves-to-demolish-orban-system": "匈牙利反对派发起“炼狱行动”，试图瓦解欧尔班政治体系",
    "polls-open-in-new-caledonias-first-provincial-elections-since-2019": "新喀里多尼亚举行2019年以来首次省级选举",
    "reporters-notebook-what-its-like-to-report-from-an-ebola-outbreak": "记者手记：在埃博拉疫情现场报道是什么体验",
    "this-is-the-most-detailed-image-yet-of-the-milky-ways-center": "银河系中心最新高清图像发布，细节达到迄今最高水平",
    "tmd-smart-keyless-bike-lock-review": "TMD 智能无钥匙自行车锁评测：便捷性与安全性受关注",
    "indian-payments-chief-thinks-ai-will-be-heavily-involved-in-next-era-of-digital-payment-growth": "印度支付行业负责人：AI 将深度参与下一阶段数字支付增长",
    "heres-your-daily-reminder-that-you-dont-own-digital-content": "数字内容所有权再引争议：用户购买后仍可能失去访问权",
    "product-lifecycle-ajay-prasad": "产品生命周期管理专家谈硬件研发与工程流程升级",
    "an-ai-model-programmed-nonstop-for-19-days-on-a-single-mirrorcode-task-that-cost-2600-to-run": "AI 模型连续19天编程完成单个 MirrorCode 任务，运行成本达2600美元",
    "andy-burnham-nationalisation-pm-chancellor-thames-water": "英国泰晤士水务国有化争议升温，政界要求首相和财政大臣表态",
    "protein-coffee-cbd-soda-starbucks-functional-beverage-boom": "蛋白咖啡和 CBD 苏打走红，星巴克等公司押注功能饮料热潮",
    "how-to-work-in-retirement-without-seeing-your-social-security-checks-slashed": "退休后继续工作如何避免社保金被大幅削减",
    "paycheck-not-key-independence-nearly": "近三成年轻成年人仍与父母同住，就业并未带来真正独立",
    "4-ways-get-creative-with-your-leftovers-save-money-on-food": "四种剩菜再利用方法：在食品开支上涨时帮家庭省钱",
}

WORD_TRANSLATIONS = {
    "trump": "特朗普", "iran": "伊朗", "israel": "以色列", "lebanon": "黎巴嫩", "gaza": "加沙",
    "venezuela": "委内瑞拉", "earthquake": "地震", "rescue": "救援", "heatwave": "热浪",
    "election": "选举", "elections": "选举", "polls": "投票", "charged": "被控", "murder": "谋杀",
    "ai": "AI", "model": "模型", "openai": "OpenAI", "anthropic": "Anthropic", "claude": "Claude",
    "chip": "芯片", "chips": "芯片", "data": "数据", "security": "安全", "startup": "初创公司",
    "stocks": "股票", "stock": "股票", "market": "市场", "markets": "市场", "fed": "美联储",
    "inflation": "通胀", "rate": "利率", "bond": "债券", "bonds": "债券", "dividend": "股息",
    "retirement": "退休", "social-security": "社保", "starbucks": "星巴克", "water": "水务",
}


def is_generic_chinese_title(title: str) -> bool:
    return bool(GENERIC_TITLE_RE.search(clean_text(title or "")))


def slug_from_url(url: str) -> str:
    try:
        path = urllib.parse.urlparse(url or "").path.strip("/")
    except Exception:
        return ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    slug = parts[-1]
    if slug in ("articles", "news", "story") and len(parts) > 1:
        slug = parts[-2]
    slug = re.sub(r"\.(html|shtml|xml|rss)$", "", slug, flags=re.I)
    return slug


def title_from_slug(url: str) -> str:
    slug = slug_from_url(url)
    if not slug:
        return ""
    for key, value in SLUG_TITLE_TRANSLATIONS.items():
        if key in slug:
            return value
    words = [w for w in re.split(r"[-_]+", slug.lower()) if w and not w.isdigit()]
    mapped = [WORD_TRANSLATIONS.get(w, "") for w in words]
    mapped = [x for x in mapped if x]
    if len(mapped) >= 2:
        return "、".join(mapped[:5]) + "相关动态"
    return ""


def original_signal(title: str, url: str) -> str:
    title = clean_text(title)
    if title and not is_generic_chinese_title(title):
        return title
    return title_from_slug(url)


def make_specific_summary(section: str, zh_title: str, source: str, raw_title: str = "", raw_summary: str = "", url: str = "") -> str:
    raw_title = clean_text(raw_title)
    raw_summary = clean_text(raw_summary)
    if raw_summary and re.search(r"[\u4e00-\u9fff]", raw_summary):
        return raw_summary[:220]
    core = zh_title or title_from_slug(url) or raw_title
    if section == "ai":
        return f"科技媒体 {source} 报道：{core}。重点看它涉及的产品、技术路线、公司动作和产业影响，尤其是对 AI 应用、硬件生态或数据安全的后续影响。"
    if section == "stock":
        return f"财经媒体 {source} 报道：{core}。重点看事件对公司经营、行业竞争、市场预期或投资者情绪的影响；相关信息仅作资讯参考，不构成投资建议。"
    return f"外媒 {source} 报道：{core}。重点看事件发生的地点、涉及对象、最新进展和可能影响；后续需继续核验官方通报和更多信源。"


def improve_global_item(item: NewsItem) -> NewsItem:
    if item.section not in ("international", "ai", "stock"):
        return item
    signal = original_signal(item.rawTitle or "", item.url) or original_signal(item.title, item.url)
    if is_generic_chinese_title(item.title):
        translated_signal = translate_text_optional(signal, item.section) if signal else ""
        if translated_signal and re.search(r"[\u4e00-\u9fff]", translated_signal) and not is_generic_chinese_title(translated_signal):
            item.title = translated_signal
        else:
            better = title_from_slug(item.url)
            if better:
                item.title = better
    if not item.summary or "关注最新进展" in item.summary or "关注市场新变化" in item.summary or "关注产业新动态" in item.summary or "这则财经快讯" in item.summary or "这则科技快讯" in item.summary:
        item.summary = make_specific_summary(item.section, item.title, item.source, signal, item.rawSummary, item.url)
    return item

def fallback_chinese_title(section: str, title: str, source: str) -> str:
    text = title.lower()
    if section == "ai":
        if any(k in text for k in ("openai", "anthropic", "claude", "gpt")):
            return "AI模型与大模型公司动态更新"
        if any(k in text for k in ("apple", "kindle", "phone", "chip")):
            return "AI硬件与消费科技动态更新"
        if any(k in text for k in ("security", "lastpass")):
            return "网络安全与数据风险动态更新"
        return f"AI科技快讯：{source}关注产业新动态"
    if section == "stock":
        if any(k in text for k in ("fed", "inflation", "rate")):
            return "美联储利率预期与通胀动态更新"
        if any(k in text for k in ("nvidia", "amd", "microsoft", "tech", "ai")):
            return "科技股与AI概念市场动态更新"
        if any(k in text for k in ("dividend", "yield", "bond")):
            return "股息收益与债券市场动态更新"
        return f"财经快讯：{source}关注市场新变化"
    if any(k in text for k in ("ukraine", "russia")):
        return "俄乌局势出现新进展"
    if any(k in text for k in ("iran", "hormuz", "strait")):
        return "美伊紧张局势与霍尔木兹海峡动态更新"
    if any(k in text for k in ("venezuela", "earthquake")):
        return "委内瑞拉地震救援与灾情动态更新"
    if any(k in text for k in ("world cup", "fifa", "ronaldo", "football")):
        return "世界杯赛场与球队动态更新"
    if any(k in text for k in ("gaza", "israel", "lebanon", "netanyahu")):
        return "中东局势与地区政治动态更新"
    if any(k in text for k in ("trump", "tariff", "digital tax")):
        return "美国关税与国际贸易摩擦动态更新"
    return f"国际快讯：{source}关注最新进展"


def fallback_chinese_summary(section: str, title: str, source: str) -> str:
    if section == "ai":
        subject = title if re.match(r"[\u4e00-\u9fff]", title) else "这则科技快讯"
        return f"科技媒体 {source} 报道：{subject}。内容涉及 AI 技术、产品变化、公司动态或产业趋势，后续影响值得继续观察。"
    if section == "stock":
        subject = title if re.match(r"[\u4e00-\u9fff]", title) else "这则财经快讯"
        return f"财经媒体 {source} 报道：{subject}。内容涉及公司表现、市场预期、资金动向或宏观变量，供资讯参考，不构成投资建议。"
    subject = title if re.match(r"[\u4e00-\u9fff]", title) else "这则国际快讯"
    return f"外媒 {source} 报道：{subject}。重点关注事件最新进展、相关背景和可能影响，后续变化仍需持续跟踪。"


def chinese_digest(section: str, title: str, summary: str, source: str) -> Tuple[str, str]:
    title = clean_text(title)
    summary = clean_text(summary)
    if re.search(r"[\u4e00-\u9fff]", title):
        return title, summary or title

    translated_title = translate_text_optional(title, section)
    translated_summary = translate_text_optional(summary, section) if summary and os.environ.get("TRANSLATE_SUMMARIES") == "1" else ""
    if re.search(r"[\u4e00-\u9fff]", translated_title):
        if translated_summary and re.search(r"[\u4e00-\u9fff]", translated_summary):
            return translated_title, translated_summary
        return translated_title, fallback_chinese_summary(section, translated_title, source)

    if translated_summary and re.search(r"[\u4e00-\u9fff]", translated_summary):
        return translated_title, translated_summary[:180]
    fallback_title = fallback_chinese_title(section, translated_title, source)
    return fallback_title, fallback_chinese_summary(section, fallback_title, source)[:180]


def fetch_rss_section(section: str) -> List[NewsItem]:
    items: List[NewsItem] = []
    for source, url in RSS_SOURCES.get(section, []):
        try:
            root = ET.fromstring(fetch_url(url))
        except Exception as exc:
            print(f"  WARN rss failed: {source} {exc}")
            continue
        nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for node in nodes[:35]:
            title = child_text(node, ("title", "{http://www.w3.org/2005/Atom}title"))
            if not title or is_bad_title(title):
                continue
            summary = child_text(node, ("description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"))
            if section == "ai" and not is_ai_tech_relevant(title, summary):
                continue
            published = parse_rss_datetime(node)
            link = link_text(node)
            zh_title, zh_summary = chinese_digest(section, title, summary, source)
            item = NewsItem(
                section=section,
                title=zh_title,
                source=source,
                summary=zh_summary,
                url=link,
                publishedAt=published,
                collectedAt=iso_minute(now_bj()),
                sourceRegion="global",
                rawTitle=clean_text(title),
                rawSummary=clean_text(summary),
            )
            items.append(improve_global_item(item))
    return items


def load_pool() -> Dict[str, List[NewsItem]]:
    if not os.path.exists(POOL_FILE):
        return {}
    try:
        data = json.load(open(POOL_FILE, "r", encoding="utf-8"))
    except Exception:
        return {}
    result: Dict[str, List[NewsItem]] = {}
    field_names = set(NewsItem.__dataclass_fields__.keys())
    for section, items in data.items():
        cleaned = []
        for x in items:
            if not x.get("title"):
                continue
            payload = {k: v for k, v in x.items() if k in field_names}
            cleaned.append(NewsItem(**payload))
        result[section] = cleaned
    return result


def save_pool(pool: Dict[str, List[NewsItem]]) -> None:
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump({k: [asdict(x) for x in v] for k, v in pool.items()}, f, ensure_ascii=False, indent=2)


def is_recent(item: NewsItem, hours: int = ROLLING_HOURS, require_published: bool = False) -> bool:
    dt = parse_dt(item.publishedAt)
    if not dt and not require_published:
        dt = parse_dt(item.collectedAt)
    if not dt:
        return False if require_published else True
    age = now_bj() - dt
    return timedelta(0) <= age <= timedelta(hours=hours)


def merge_dedupe(section: str, chunks: Iterable[NewsItem], old: Iterable[NewsItem]) -> List[NewsItem]:
    best: Dict[str, NewsItem] = {}
    all_items = list(chunks) + list(old)
    for item in all_items:
        item.section = section
        if section in ("international", "ai", "stock"):
            item = improve_global_item(item)
        if not item.title or is_bad_title(item.title) or is_bad_url(item.url):
            continue
        if section == "ai" and not is_ai_tech_relevant(item.title, item.summary):
            continue
        require_published_time = section in ("domestic", "entertainment")
        if section in ("domestic", "international", "ai", "stock", "entertainment") and not is_recent(item, require_published=require_published_time):
            continue
        key = item.key_text()
        item.heat = heat_for(item)
        item.badge = badge_for(item.heat, item.publishedAt)
        current = best.get(key)
        if not current:
            best[key] = item
            continue
        score_new = authority_score(item.source) + len(item.summary) / 60 + item.heat
        score_old = authority_score(current.source) + len(current.summary) / 60 + current.heat
        if score_new > score_old:
            best[key] = item
    items = list(best.values())
    items.sort(key=lambda x: (
        parse_dt(x.publishedAt) or parse_dt(x.collectedAt) or datetime(1970, 1, 1, tzinfo=BEIJING),
        x.heat,
        authority_score(x.source),
    ), reverse=True)
    return items[:MAX_POOL_PER_SECTION]


def split_main_extra(items: List[NewsItem], total: int) -> Tuple[List[NewsItem], List[NewsItem]]:
    chosen = items[:total]
    return chosen[:MAIN_COUNT], chosen[MAIN_COUNT:]


def js_escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def js_array(name: str, items: List[NewsItem], with_team: bool = False) -> str:
    lines = [f"const {name} = ["]
    for i, item in enumerate(items, 1):
        heat = heat_for(item, i)
        badge = badge_for(heat, item.publishedAt)
        fields = []
        if with_team:
            fields.append(f'team:"{js_escape(item.team or infer_team(item.title))}"')
        else:
            fields.append(f"rank:{i}")
        fields.extend([
            f'title:"{js_escape(item.title)}"',
            f'source:"{js_escape(item.source)}"',
            f'summary:"{js_escape(item.summary)}"',
            f'badge:"{badge}"',
            f"heat:{heat}",
            f'time:"{js_escape(item.publishedAt or item.collectedAt)}"',
        ])
        if item.url:
            fields.append(f'url:"{js_escape(item.url)}"')
        fields.append(f'collectedAt:"{js_escape(item.collectedAt)}"')
        fields.append(f'sourceRegion:"{js_escape(item.sourceRegion)}"')
        lines.append("  {" + ", ".join(fields) + "},")
    lines.append("];" )
    return "\n".join(lines)

TRACKING_STOPWORDS = set("""
中国 美国 日本 英国 法国 德国 欧洲 国际 国内 最新 快讯 新闻 动态 更新 关注 报道 表示 宣布 进行 持续 出现 影响 市场 公司 相关 事件 可能 今日 昨日 今年 目前 以及 一个 这个 这些 外媒 媒体 重点 背景 后续 变化 仍需 跟踪 内容 涉及 资讯 参考 构成 投资 建议 财经 科技 产业 趋势 信源 权威 观察 their from with after about into says said will more than over under amid live latest news update world china us eu ai the and for are was were has have not new
""".split())

TRACKING_SECTION_LABELS = {
    "domestic": "国内",
    "international": "国际",
    "ai": "AI科技",
    "stock": "股市",
    "entertainment": "娱乐",
}

TRACKING_TOPIC_RULES = [
    ("国家元首政务", ("习近平", "国家主席", "主席令", "慰问电", "会见"), ["跟进权威原文", "观察政策落点", "核验后续会议"]),
    ("中东局势", ("伊朗", "以色列", "黎巴嫩", "加沙", "霍尔木兹", "真主党", "netanyahu", "israel", "iran", "gaza", "lebanon", "hormuz"), ["停火条件", "能源价格", "外交声明"]),
    ("俄乌局势", ("俄乌", "乌克兰", "俄罗斯", "ukraine", "russia"), ["前线变化", "外交谈判", "制裁与援助"]),
    ("AI与科技股", ("OpenAI", "Anthropic", "Claude", "GPT", "英伟达", "NVIDIA", "芯片", "AI", "人工智能", "半导体"), ["模型发布", "芯片供应", "财报验证"]),
    ("金融监管与A股", ("A股", "金融", "监管", "美联储", "通胀", "利率", "Fed", "inflation", "rate"), ["政策文件", "资金反应", "行业影响"]),
    ("灾害与公共安全", ("地震", "救援", "热浪", "高温", "干旱", "earthquake", "heatwave", "rescue"), ["伤亡与救援", "政府响应", "次生风险"]),
    ("影视娱乐热点", ("电影", "电视剧", "综艺", "演员", "影视", "票房", "白玉兰", "festival"), ["榜单变化", "播出反馈", "行业评价"]),
]

TRACKING_RULE_LABELS = {label for label, _, _ in TRACKING_TOPIC_RULES}


def item_time(item: NewsItem) -> datetime:
    return parse_dt(item.publishedAt) or parse_dt(item.collectedAt) or datetime(1970, 1, 1, tzinfo=BEIJING)


def tracking_tokens(text: str) -> List[str]:
    text = clean_text(text)
    for phrase in (
        "动态更新", "关注最新进展", "重点关注事件", "相关背景",
        "可能影响", "后续变化", "持续跟踪", "供资讯参考",
        "不构成投资建议", "内容涉及", "外媒", "财经媒体", "科技媒体",
    ):
        text = text.replace(phrase, " ")
    tokens: List[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}|[\u4e00-\u9fff]{2,6}", text):
        low = token.lower()
        if low in TRACKING_STOPWORDS or token in TRACKING_STOPWORDS:
            continue
        if any(noise in token for noise in ("态更新", "最新进", "后续变", "持续跟", "重点关", "相关背", "能影响")):
            continue
        if re.fullmatch(r"\d+", token):
            continue
        tokens.append(low if re.search(r"[A-Za-z]", token) else token)
    seen = set()
    result = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result[:18]


def tracking_topic_for(item: NewsItem) -> Tuple[str, List[str], List[str]]:
    text = f"{item.title} {item.summary} {item.source}"
    lower = text.lower()
    for label, keywords, next_steps in TRACKING_TOPIC_RULES:
        if any(k.lower() in lower for k in keywords):
            return label, list(keywords), next_steps
    return TRACKING_SECTION_LABELS.get(item.section, "热点"), tracking_tokens(text)[:8], ["核验信源", "跟进最新进展", "观察后续影响"]




def generic_tracking_title(title: str) -> bool:
    title = clean_text(title)
    generic_patterns = (
        r"^(国际|财经|AI科技)快讯[:：].*关注最新进展$",
        r"^(国际|财经|AI科技)快讯[:：]",
        r"^科技股与AI概念市场动态更新$",
        r"^财经快讯[:：]",
    )
    return any(re.search(p, title) for p in generic_patterns)


def matched_topic_keywords(item: NewsItem, topic_label: str) -> set:
    text = f"{item.title} {item.summary} {item.source}".lower()
    for label, keywords, _ in TRACKING_TOPIC_RULES:
        if label == topic_label:
            return {k.lower() for k in keywords if k.lower() in text}
    return set()

def tracking_score(item: NewsItem) -> float:
    age_h = (now_bj() - item_time(item)).total_seconds() / 3600
    recency = max(0, 24 - min(age_h, 24)) / 24 * 12
    return heat_for(item) * 10 + authority_score(item.source) + recency + min(len(item.summary), 180) / 45


def tracking_similarity(a: NewsItem, b: NewsItem) -> float:
    if generic_tracking_title(a.title) or generic_tracking_title(b.title):
        return 0.0
    title_a = set(tracking_tokens(a.title))
    title_b = set(tracking_tokens(b.title))
    ta = set(tracking_tokens(a.title + " " + a.summary))
    tb = set(tracking_tokens(b.title + " " + b.summary))
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    title_overlap = len(title_a & title_b)
    topic_a = tracking_topic_for(a)[0]
    topic_b = tracking_topic_for(b)[0]
    explicit_same_topic = topic_a == topic_b and topic_a in TRACKING_RULE_LABELS
    shared_topic_keywords = matched_topic_keywords(a, topic_a) & matched_topic_keywords(b, topic_b) if explicit_same_topic else set()
    # Generic fallback topics are too broad; require headline-level overlap.
    # Explicit broad topics still need a shared core keyword, otherwise “earthquake”
    # and “heatwave” or unrelated market briefs get incorrectly fused.
    if title_overlap == 0 and (not explicit_same_topic or not shared_topic_keywords):
        return 0.0
    topic_bonus = 0.25 if explicit_same_topic and shared_topic_keywords else 0
    title_bonus = 0.28 if title_overlap >= 2 else (0.14 if title_overlap == 1 else 0)
    return overlap / max(5, min(len(ta), len(tb))) + topic_bonus + title_bonus


def related_news_js(items: List[NewsItem]) -> str:
    lines = ["["]
    for item in items[:4]:
        fields = [
            f'title:"{js_escape(item.title)}"',
            f'source:"{js_escape(item.source)}"',
            f'time:"{js_escape(item.publishedAt or item.collectedAt)}"',
            f'summary:"{js_escape(item.summary)}"',
        ]
        if item.url:
            fields.append(f'url:"{js_escape(item.url)}"')
        lines.append("      {" + ", ".join(fields) + "},")
    lines.append("    ]")
    return "\n".join(lines)


def js_tracking_events(name: str, events: List[dict]) -> str:
    lines = [f"const {name} = ["]
    for event in events:
        lines.append("  {")
        lines.append(f'    title:"{js_escape(event["title"])}",')
        lines.append(f'    status:"{js_escape(event["status"])}", statusClass:"{js_escape(event["statusClass"])}",')
        lines.append(f'    oneLine:"{js_escape(event["oneLine"])}",')
        lines.append(f'    intro:"{js_escape(event.get("intro", event["oneLine"]))}",')
        lines.append("    keywords:[" + ", ".join(f'"{js_escape(k)}"' for k in event["keywords"][:10]) + "],")
        lines.append("    timeline:[")
        for label, text in event["timeline"][:4]:
            lines.append(f'      ["{js_escape(label)}", "{js_escape(text)}"],')
        lines.append("    ],")
        lines.append("    voices:[")
        for role, text in event["voices"][:3]:
            lines.append(f'      ["{js_escape(role)}", "{js_escape(text)}"],')
        lines.append("    ],")
        lines.append("    next:[" + ", ".join(f'"{js_escape(x)}"' for x in event["next"][:5]) + "],")
        lines.append("    related:" + related_news_js(event["related"]) + ",")
        lines.append("  },")
    lines.append("];" )
    return "\n".join(lines)


def tracking_date_label(item: NewsItem) -> str:
    dt = item_time(item)
    if dt.year < 2000:
        return "近日"
    return dt.strftime("%Y年%m月%d日%H时")


def clean_tracking_summary(item: NewsItem) -> str:
    text = clean_text(item.summary)
    text = re.sub(r"^(外媒|财经媒体|科技媒体)\s*[^：:]{0,40}[：:]", "", text).strip()
    text = re.sub(r"重点关注事件最新进展、相关背景和可能影响，后续变化仍需持续跟踪。?", "", text).strip()
    text = re.sub(r"内容涉及[^。]{0,80}。?", "", text).strip()
    if not text or text == item.title or generic_tracking_title(text):
        return item.title
    return text[:140]


def tracking_fact_terms(cluster: List[NewsItem], patterns: Iterable[str]) -> List[str]:
    text = " ".join([x.title + " " + x.summary for x in cluster])
    found: List[str] = []
    for pattern in patterns:
        for m in re.findall(pattern, text, flags=re.I):
            value = m if isinstance(m, str) else "".join(m)
            value = clean_text(value)
            if value and value not in found:
                found.append(value)
    return found[:4]


def event_intro_text(topic: str, lead: NewsItem, cluster: List[NewsItem]) -> str:
    date = tracking_date_label(lead)
    title = lead.title
    summary = clean_tracking_summary(lead)
    joined = " ".join(x.title + " " + x.summary for x in cluster)
    if "委内瑞拉" in joined and ("地震" in joined or "earthquake" in joined.lower()):
        facts = tracking_fact_terms(cluster, [r"\d+(?:\.\d+)?级", r"\d+人(?:死亡|遇难|受伤)", r"救出[一二三四五六七八九十\d]+名[^。；，,\s]{1,8}"])
        fact_text = "；已捕捉到的公开线索包括" + "、".join(facts) if facts else "；震级、伤亡和受灾范围仍以权威通报为准"
        return f"{date}前后，委内瑞拉发生地震并进入救援与灾情核查阶段{fact_text}。"
    if topic == "中东局势":
        return f"{date}前后，围绕{title}的地区安全风险升温，相关报道集中在军事行动、外交表态、能源通道和市场风险上。"
    if "世界杯" in joined or "world cup" in joined.lower():
        return f"{date}前后，世界杯赛场出现新的比赛结果或出线形势变化，专题关注赛果、球队表现以及后续赛程影响。"
    if topic == "AI与科技股":
        return f"{date}前后，AI产业与科技股相关消息升温，专题关注模型、芯片、公司动态和资本市场反馈之间的联动。"
    if topic == "金融监管与A股" or lead.section == "stock":
        return f"{date}前后，市场和政策层面出现新的财经信号，专题关注资金反应、行业影响和风险变化。"
    if lead.section == "domestic" and ("数据" in title or "增长" in title or "统计" in joined):
        return f"{date}，{summary}"
    if "蓝洞" in joined or "调查报告" in joined:
        return f"{date}，{summary}"
    return f"{date}，{summary}"


def event_latest_text(latest: NewsItem, lead: NewsItem, cluster: List[NewsItem]) -> str:
    latest_summary = clean_tracking_summary(latest)
    specific = None
    for item in cluster:
        if item.title != lead.title and not generic_tracking_title(item.title):
            specific = item
            break
    if latest.title == lead.title and specific:
        return f"目前已有更具体的补充线索：“{specific.title}”。{clean_tracking_summary(specific)}"
    if latest.title == lead.title:
        return f"截至{tracking_date_label(latest)}，{latest.source}的公开信息主要集中在“{latest.title}”；更具体的数据、处置进展或影响评估仍需等待权威信源补充。"
    return f"最新线索是“{latest.title}”：{latest_summary}"


def event_impact_text(topic: str, lead: NewsItem, cluster: List[NewsItem]) -> str:
    joined = " ".join(x.title + " " + x.summary for x in cluster)
    if "委内瑞拉" in joined and "地震" in joined:
        return "重点看救援进度、伤亡统计、基础设施受损情况，以及是否有国际援助和次生灾害风险。"
    if topic == "中东局势":
        return "重点看冲突是否外溢、外交斡旋是否推进，以及原油、航运和避险资产是否受到影响。"
    if "世界杯" in joined or "world cup" in joined.lower():
        return "重点看小组排名、晋级形势、核心球员状态和下一场对阵变化。"
    if lead.section == "domestic" and ("数据" in lead.title or "增长" in lead.title):
        return "重点看数据是否会影响宏观政策判断、消费和工业恢复节奏，以及市场预期变化。"
    if "蓝洞" in joined:
        return "重点看调查报告后续是否补充生态保护、科研价值和海洋环境监测结论。"
    if lead.section == "stock":
        return "重点看市场反应、资金流向和相关公司基本面变化；相关内容仅作资讯参考。"
    return "重点看事件是否持续更新、是否出现权威数据，以及影响范围是否扩大。"


def build_tracking_events(pool: Dict[str, List[NewsItem]], max_events: int = 6) -> List[dict]:
    sections = ("domestic", "international", "ai", "stock", "entertainment")
    candidates: List[NewsItem] = []
    for section in sections:
        for item in pool.get(section, []):
            if not is_recent(item):
                continue
            if is_bad_title(item.title) or is_bad_url(item.url) or generic_tracking_title(item.title):
                continue
            candidates.append(item)
    candidates.sort(key=tracking_score, reverse=True)

    clusters: List[List[NewsItem]] = []
    used_keys = set()
    for seed in candidates[:80]:
        seed_key = seed.key_text()
        if seed_key in used_keys:
            continue
        related = [seed]
        for item in candidates:
            if item is seed or item.key_text() in used_keys:
                continue
            if tracking_similarity(seed, item) >= 0.62:
                related.append(item)
            if len(related) >= 5:
                break
        # A single exceptionally hot/authoritative story can still be tracked,
        # but normal topics need at least one companion signal.
        if len(related) == 1 and tracking_score(seed) < 105:
            continue
        for item in related:
            used_keys.add(item.key_text())
        related.sort(key=lambda x: (item_time(x), tracking_score(x)), reverse=True)
        clusters.append(related)
        if len(clusters) >= max_events:
            break

    events: List[dict] = []
    for cluster in clusters:
        lead = max(cluster, key=tracking_score)
        latest = max(cluster, key=item_time)
        topic, keywords, next_steps = tracking_topic_for(lead)
        sources = []
        for item in cluster:
            if item.source and item.source not in sources:
                sources.append(item.source)
        status = "发酵中" if len(cluster) >= 3 or heat_for(lead) >= 9 else "观察"
        status_class = "hot" if status == "发酵中" else "watch"
        intro = event_intro_text(topic, lead, cluster)
        one_line = intro
        timeline = [
            ("起因", intro),
            ("最新", event_latest_text(latest, lead, cluster)),
        ]
        if len(cluster) > 1 and cluster[1].title != latest.title:
            timeline.append(("补充", f"另一条值得看的线索是“{cluster[1].title}”：{clean_tracking_summary(cluster[1])}"))
        timeline.append(("影响", event_impact_text(topic, lead, cluster)))
        voices = [
            ("主要信源", "、".join(sources[:3]) or lead.source),
            ("事件看点", "关注事实进展、影响范围和是否出现连续更新。"),
        ]
        if lead.section == "stock":
            voices.append(("风险提示", "市场资讯仅供参考，不构成投资建议。"))
        events.append({
            "title": lead.title,
            "status": status,
            "statusClass": status_class,
            "oneLine": one_line,
            "intro": intro,
            "keywords": keywords or tracking_tokens(lead.title + " " + lead.summary)[:8],
            "timeline": timeline,
            "voices": voices,
            "next": next_steps,
            "related": cluster,
        })
    return events


def infer_team(title: str) -> str:
    teams = ["河南", "上海海港", "上海申花", "北京国安", "山东泰山", "成都蓉城", "浙江", "天津津门虎", "武汉三镇", "青岛海牛", "深圳新鹏城", "中超"]
    for team in teams:
        if team in title:
            return "河南队" if team == "河南" else team
    return "中超"


def replace_const_array(content: str, name: str, new_block: str) -> str:
    starts = [content.find(f"const {name} = ["), content.find(f"var {name} = ["), content.find(f"let {name} = [")]
    starts = [x for x in starts if x != -1]
    if not starts:
        print(f"  WARN missing array {name}")
        return content
    start = min(starts)
    end = content.find("\n];", start)
    if end == -1:
        print(f"  WARN missing array end {name}")
        return content
    end += 3
    return content[:start] + new_block + "\n" + content[end:]


def write_index_arrays(blocks: Dict[str, str]) -> None:
    content = open(INDEX_FILE, "r", encoding="utf-8").read()
    for name, block in blocks.items():
        content = replace_const_array(content, name, block)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(content)

def review_time_label() -> str:
    return now_bj().strftime("%Y年%m月%d日 %H:%M")


def source_domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url or "").netloc.replace("www.", "")
    except Exception:
        return ""


def render_review_item(item: NewsItem, index: int) -> str:
    title = html.escape(item.title or "")
    summary = html.escape(item.summary or "")
    source = html.escape(item.source or "")
    url = html.escape(item.url or "")
    domain = html.escape(source_domain(item.url))
    published = html.escape(item.publishedAt or item.collectedAt or "")
    collected = html.escape(item.collectedAt or "")
    heat = heat_for(item, index)
    raw_title = html.escape(item.rawTitle or "")
    if url:
        title_html = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
    else:
        title_html = title
    raw_html = ""
    if raw_title and raw_title != title:
        raw_html = f'<div class="raw-title">原文：{raw_title}</div>'
    domain_html = f'<span>{domain}</span>' if domain else ""
    return (
        '<article class="news-item">'
        '<div class="item-top">'
        f'<span class="rank">{index:02d}</span>'
        '<div class="item-main">'
        f'<h3>{title_html}</h3>'
        f'{raw_html}'
        f'<p>{summary}</p>'
        f'<div class="meta"><span>{source}</span>{domain_html}<span>发布：{published}</span><span>收录：{collected}</span><span>热度：{heat}</span></div>'
        '</div></div></article>'
    )


def render_review_section(section_id: str, title: str, desc: str, items: List[NewsItem], color: str) -> str:
    body = "\n".join(render_review_item(item, i) for i, item in enumerate(items, 1))
    if not body:
        body = '<div class="empty">本次没有抓取到可展示的新闻。</div>'
    return (
        f'<section class="section-block" id="{section_id}">'
        f'<div class="section-title" style="border-left-color:{color}">'
        f'<div><h2>{html.escape(title)}</h2><div class="section-desc">{html.escape(desc)}</div></div>'
        f'<span class="count">{len(items)}条</span></div>'
        f'{body}</section>'
    )


def write_foreign_news_review_html(pool: Dict[str, List[NewsItem]]) -> None:
    os.makedirs(REVIEW_DIR, exist_ok=True)
    sections = [
        ("international", "国际新闻", "非中国本地新闻网站抓取，已过滤未整理好的模板标题", pool.get("international", [])[:TARGET_COUNTS["international"]], "#0071e3"),
        ("ai", "AI 科技", "海外科技、AI、芯片、机器人等信源抓取整理，已过滤未整理好的模板标题", pool.get("ai", [])[:TARGET_COUNTS["ai"]], "#5e5ce6"),
        ("stock", "财经新闻", "海外财经、市场、公司与宏观新闻抓取整理，已过滤未整理好的模板标题", pool.get("stock", [])[:TARGET_COUNTS["stock"]], "#34c759"),
    ]
    sections = [(sid, title, desc, [improve_global_item(x) for x in items if not is_generic_chinese_title(improve_global_item(x).title)], color) for sid, title, desc, items, color in sections]
    total = sum(len(items) for _, _, _, items, _ in sections)
    nav = "\n".join(f'<a href="#{sid}">{title}<span>{len(items)}</span></a>' for sid, title, _, items, _ in sections)
    content = "\n".join(render_review_section(sid, title, desc, items, color) for sid, title, desc, items, color in sections)
    generated_at = review_time_label()
    html_doc = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>外网新闻抓取 - {generated_at}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Helvetica Neue","PingFang SC",Arial,sans-serif;background:#f5f5f7;color:#1d1d1f;line-height:1.6;-webkit-font-smoothing:antialiased}}
.container{{max-width:960px;margin:0 auto;padding:20px 24px 44px}}
header{{text-align:center;padding:36px 20px 22px;background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(255,255,255,.82));border-radius:20px;margin-bottom:18px;box-shadow:0 2px 12px rgba(0,0,0,.04)}}
h1{{font-size:30px;font-weight:800;letter-spacing:-.4px;margin-bottom:6px}}
.update-time{{font-size:13px;color:#86868b;font-weight:500}}
.summary{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:14px}}
.summary span{{font-size:12px;color:#515154;background:rgba(0,0,0,.04);padding:5px 10px;border-radius:999px}}
nav{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-bottom:24px;padding:14px;background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,.04);position:sticky;top:12px;z-index:10}}
nav a{{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:#6e6e73;text-decoration:none;padding:6px 13px;border-radius:999px;background:rgba(0,0,0,.03);font-weight:600;white-space:nowrap}}
nav a:hover{{background:rgba(0,113,227,.1);color:#0071e3}}
nav a span{{font-size:11px;color:inherit;opacity:.72}}
.section-block{{margin-bottom:34px}}
.section-title{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px;padding-left:14px;border-left:4px solid #c0c0c0}}
.section-title h2{{font-size:21px;font-weight:800}}
.section-desc{{font-size:12px;color:#86868b;margin-top:2px}}
.count{{font-size:12px;color:#86868b;background:rgba(0,0,0,.04);padding:3px 10px;border-radius:999px;font-weight:600;white-space:nowrap}}
.news-item{{background:#fff;border-radius:13px;padding:15px 18px;margin-bottom:9px;box-shadow:0 1px 3px rgba(0,0,0,.04);transition:box-shadow .2s ease,transform .2s ease}}
.news-item:hover{{box-shadow:0 5px 18px rgba(0,0,0,.08);transform:translateY(-1px)}}
.item-top{{display:flex;align-items:flex-start;gap:12px}}
.rank{{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:#f2f2f7;color:#6e6e73;font-size:12px;font-weight:800;font-variant-numeric:tabular-nums}}
.item-main{{min-width:0;flex:1}}
h3{{font-size:16px;line-height:1.45;margin-bottom:6px;font-weight:750}}
h3 a{{color:#1d1d1f;text-decoration:none}}
h3 a:hover{{color:#0071e3}}
p{{font-size:13px;color:#515154;line-height:1.65;margin-bottom:9px}}
.raw-title{{font-size:12px;color:#86868b;line-height:1.45;margin:-2px 0 7px}}
.meta{{display:flex;flex-wrap:wrap;gap:6px 10px;font-size:11px;color:#86868b}}
.meta span{{white-space:nowrap}}
.empty{{background:#fff;border-radius:13px;padding:18px;color:#86868b;font-size:13px;text-align:center}}
footer{{text-align:center;padding:26px 0 0;color:#86868b;font-size:12px}}
@media(max-width:640px){{.container{{padding:14px 14px 34px}}header{{padding:28px 16px 18px}}h1{{font-size:25px}}.item-top{{gap:9px}}.rank{{width:28px;height:28px;border-radius:9px}}.news-item{{padding:13px 14px}}h3{{font-size:15px}}}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>外网新闻抓取</h1>
  <div class="update-time">同步时间：{generated_at}</div>
  <div class="summary"><span>共 {total} 条</span><span>来源：国际 / AI 科技 / 财经 RSS</span><span>只展示已整理为可读中文的条目</span></div>
</header>
<nav>
{nav}
</nav>
{content}
<footer>臻宝每日简讯 · 外网新闻审核页 · 每次执行 news_pipeline.py 自动同步</footer>
</div>
</body>
</html>
'''
    with open(FOREIGN_REVIEW_FILE, "w", encoding="utf-8") as f:
        f.write(html_doc)


def build() -> Dict[str, List[NewsItem]]:
    old_pool = load_pool()
    source = parse_source_html()
    # Domestic uses the user-provided source as the main feed, plus curated
    # authoritative supplements. International, AI and stock intentionally prefer
    # non-China/global RSS sources.
    incoming: Dict[str, List[NewsItem]] = {
        "domestic": list(source.get("domestic", [])) + load_authoritative_domestic(),
        "entertainment": list(source.get("entertainment", [])),
        "henan": list(source.get("henan", [])),
        "csl": list(source.get("csl", [])),
    }
    for section in ("international", "ai", "stock"):
        incoming[section] = fetch_rss_section(section)

    pool: Dict[str, List[NewsItem]] = {}
    for section in TARGET_COUNTS:
        old_items = old_pool.get(section, [])
        if section == "domestic":
            # Domestic may be supplemented, but only by recent trusted/authoritative
            # items. This prevents low-quality or stale manual pool entries from
            # reappearing while still allowing us to add high-value sources.
            old_items = [x for x in old_items if x.sourceRegion == "cn" and is_recent(x, require_published=True) and is_trusted_domestic_item(x)]
        elif section in ("international", "ai", "stock"):
            old_items = [x for x in old_items if x.sourceRegion == "global" and is_recent(x)]
        pool[section] = merge_dedupe(section, incoming.get(section, []), old_items)
    return pool


def main() -> None:
    print("Building rolling news pools...")
    pool = build()
    save_pool(pool)
    blocks: Dict[str, str] = {}

    dom_main, dom_extra = split_main_extra(pool.get("domestic", []), TARGET_COUNTS["domestic"])
    int_main, int_extra = split_main_extra(pool.get("international", []), TARGET_COUNTS["international"])
    ai_main, ai_extra = split_main_extra(pool.get("ai", []), TARGET_COUNTS["ai"])
    ent_main, ent_extra = split_main_extra(pool.get("entertainment", []), TARGET_COUNTS["entertainment"])
    stock_main, stock_extra = split_main_extra(pool.get("stock", []), TARGET_COUNTS["stock"])

    blocks["mockHotNewsDomestic"] = js_array("mockHotNewsDomestic", dom_main)
    blocks["mockHotNewsDomesticExtra"] = js_array("mockHotNewsDomesticExtra", dom_extra)
    blocks["mockHotNewsInternational"] = js_array("mockHotNewsInternational", int_main)
    blocks["mockHotNewsInternationalExtra"] = js_array("mockHotNewsInternationalExtra", int_extra)
    blocks["mockHotNewsAI"] = js_array("mockHotNewsAI", ai_main)
    blocks["mockHotNewsAIExtra"] = js_array("mockHotNewsAIExtra", ai_extra)
    blocks["mockEntertainment"] = js_array("mockEntertainment", ent_main)
    blocks["mockEntertainmentExtra"] = js_array("mockEntertainmentExtra", ent_extra)
    blocks["mockStockNews"] = js_array("mockStockNews", stock_main)
    blocks["mockStockNewsExtra"] = js_array("mockStockNewsExtra", stock_extra)
    blocks["mockHenanNews"] = js_array("mockHenanNews", pool.get("henan", [])[:TARGET_COUNTS["henan"]], with_team=True)
    blocks["mockCslOtherTeams"] = js_array("mockCslOtherTeams", pool.get("csl", [])[:TARGET_COUNTS["csl"]], with_team=True)
    tracking_events = build_tracking_events(pool)
    blocks["mockTrackingEvents"] = js_tracking_events("mockTrackingEvents", tracking_events)

    with open(GENERATED_FILE, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks.values()))
    write_index_arrays(blocks)
    write_foreign_news_review_html(pool)
    print(f"  foreign review: {FOREIGN_REVIEW_FILE}")
    for section, items in pool.items():
        print(f"  {section}: {len(items)} in pool")
    save_translation_cache()
    print(f"  tracking: {len(tracking_events)} events")
    print("Done.")


if __name__ == "__main__":
    main()
