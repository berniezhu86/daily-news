#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_image_news.py —— 图片新闻轮播数据构建（四数据源）

数据源：
  A. 澎湃新闻热榜（第三方聚合接口 api.xcvts.cn/api/hotlist/thepaper）
     → 返回 {title, pic(CDN直链), link, time, type}
  B. 新华网「社会」+「国际」图片类目（www.news.cn/photo/gn.htm + gj.htm，静态可解析）
     → 条目含相对封面图路径 + <h3>标题 + c.html 详情链接，时间从图片路径日期推导
  C. 外交部带图新闻（www.mfa.gov.cn 首页，静态可解析）
     → 结构：<a href="..."><div class="thumb"><img src="..."/></div><div class="title">标题</div></a>
  D. 人民网图片频道（pic.people.com.cn 子栏目：国内 GB/165652、国际 GB/166071，静态可解析）
     → 结构：<div class="top-image"><a href="..."><img src="/NMediaFile/..."/></a></div>
             <span><a>标题</a></span><h4> 2026年07月10日 15:04  7张</h4>

过滤策略（内容安全底线）：
  - 通用敏感过滤 SENSITIVE_KW：剔除含中国最高领导职务/高层会议完整标题等硬性敏感表述，
    对所有源生效（项目铁律「杜绝敏感字眼」）
  - 国际类（新华国际、人民网国际）按用户要求不再额外过滤地缘/军事/外交表述，
    仅走通用过滤——即国际军事动态、外交表态、地缘冲突报道正常收录
  - 外交部/新华/人民网均为官方合规信源，内容本身合规

流程：分别抓取四源 → 通用过滤 → 多源交叉混排取前 TOTAL 条 → 封面图用远程 CDN 直链注入 imageNewsList

由本项目 Agent 维护（不走 Codex）。可接进 7/13/19 点新闻自动化。
"""

import os
import re
import json
import html as HTMLLIB
import urllib.request
import urllib.error
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE, "index.html")

# ---------- 数据源地址 ----------
THP_API = "https://api.xcvts.cn/api/hotlist/thepaper"
XHUA_SOC = "https://www.news.cn/photo/gn.htm"           # 新华「社会」
XHUA_GJ = "https://www.news.cn/photo/gj.htm"            # 新华「国际」
XHUA_IMG = "https://www.news.cn/photo/"
MFA_URL = "https://www.mfa.gov.cn/"                       # 外交部首页
MFA_BASE = "https://www.mfa.gov.cn"
PEOPLE_DOMESTIC = "http://pic.people.com.cn/GB/165652/"   # 人民图片·国内
PEOPLE_WORLD = "http://pic.people.com.cn/GB/166071/"     # 人民图片·国际
PEOPLE_IMG_BASE = "https://www.people.com.cn"
PEOPLE_LINK_BASE = "https://www.people.com.cn"

# ---------- 数量控制 ----------
TP_TOP = 5          # 澎湃最多
XH_PER = 4          # 新华每个类目最多
MFA_TOP = 5         # 外交部最多
PEOPLE_PER = 3      # 人民图片每个子栏目最多
TOTAL = 12          # 最终轮播条数

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 通用敏感词（铁律硬过滤，对所有源生效）：中国最高领导职务 / 高层会议完整标题等
SENSITIVE_KW = ["总书记", "国家主席", "主席", "政治局", "人大", "政协",
                "军委", "落马", "反腐打虎"]


def log(msg):
    print("[img-news] " + msg, flush=True)


def norm(s):
    """折叠所有空白（换行/回车/连续空格）为单个空格，杜绝标题内嵌换行破坏 JS 字符串字面值。"""
    return re.sub(r"\s+", " ", (s or "")).strip()


def is_sensitive(title):
    t = (title or "")
    for w in SENSITIVE_KW:
        if w in t:
            return True
    return False


def abs_url(u, base):
    if u.startswith("http"):
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("./"):
        u = u[2:]
    if u.startswith("/"):
        return base.rstrip("/") + u
    return base.rstrip("/") + "/" + u


def fetch_text(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                    "Accept-Language": "zh-CN"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception as e:
        log("  抓取失败 %s : %s" % (url[:60], e))
        return ""


def fetch_json(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception as e:
        log("  接口抓取失败: %s" % e)
        return None


def fmt_date(d8):
    """YYYYMMDD / YYYYMMDD 字符串 → 今天/昨天/M月D日。空则返回空。"""
    if not d8 or len(d8) < 8:
        return ""
    try:
        dt = datetime.strptime(d8[:8], "%Y%m%d")
    except Exception:
        return ""
    now = datetime.now()
    if dt.date() == now.date():
        return "今天"
    if dt.date() == (now - timedelta(days=1)).date():
        return "昨天"
    return dt.strftime("%m月%d日")


# ---------- 数据源 A：澎湃热榜 ----------
def get_thepaper():
    data = fetch_json(THP_API)
    if not data or data.get("code") != 200:
        log("  澎湃接口返回异常，跳过该源")
        return []
    res = []
    for it in data.get("data", []):
        if len(res) >= TP_TOP:
            break
        if it.get("type") in {"澎湃防务", "打虎记", "大国外交", "澎湃世界观"}:
            continue
        title = norm(it.get("title"))
        pic = (it.get("pic") or "").strip()
        link = (it.get("link") or "").strip()
        if not (title and link and pic):
            continue
        if is_sensitive(title):
            continue
        res.append({
            "title": title,
            "url": link,
            "img": pic,
            "timeAgo": (it.get("time") or "").strip(),
        })
    return res


# ---------- 数据源 B：新华网「社会」+「国际」----------
def _parse_xh_page(url):
    """按『同一图集 folder id』配对 h3 标题 / 链接 / 主图，杜绝图文错位。

    新华图库每个条目是 <div class="product_list">，内部 <h3> 链接与 <img> 共用
    同一个图集 ID（如 f6ecaff80c004eabaa7627bf17294af7），但 DOM 中 h3 与 img
    的相对前后顺序不固定。因此先分别收集『标题表』和『主图表』，再用 folder id
    关联，保证 title / url / img 同属一个图集。
    """
    h = fetch_text(url)
    if not h:
        return []
    # 1) 标题表：folder id -> {title, url, date}
    entries = {}
    for m in re.finditer(
            r'<h3>\s*<a\s+href="/(?:photo/)?(\d{8})/([0-9a-z]+)/c\.html"[^>]*>(.*?)</a>\s*</h3>',
            h, re.S):
        date8, fid, title = m.group(1), m.group(2), m.group(3)
        title = norm(HTMLLIB.unescape(re.sub(r"<[^>]+>", "", title)))
        entries[fid] = {
            "title": title,
            "url": "https://www.news.cn/photo/%s/%s/c.html" % (date8, fid),
            "date": date8,
        }
    # 2) 主图表：folder id -> img_url（跳过 icon 等小图标）
    imgs = {}
    for m in re.finditer(
            r'<img\s+src="((?:\d{8}/)?[0-9a-z]+/[0-9a-z]+_[^"]+\.(?:JPG|jpg|jpeg|png))"',
            h):
        src = m.group(1)
        if "icon" in src.lower():
            continue
        fm = re.search(r'/([0-9a-z]{16,})/', src) or re.search(r'^([0-9a-z]{16,})/', src)
        if not fm:
            continue
        fid = fm.group(1)
        if fid in imgs:
            continue
        imgs[fid] = src if src.startswith("http") else XHUA_IMG + src.lstrip("/")
    # 3) 按 folder id 配对
    res = []
    for fid, e in entries.items():
        if fid not in imgs:
            continue
        if is_sensitive(e["title"]):
            continue
        res.append({
            "title": e["title"],
            "url": e["url"],
            "img": imgs[fid],
            "timeAgo": fmt_date(e["date"]),
        })
        if len(res) >= XH_PER:
            break
    log("  新华：配对成功 %d 条" % len(res))
    return res


def get_xinhua():
    """社会 + 国际 两页，内部交替混排（国际类已放宽，不额外过滤）。"""
    soc = _parse_xh_page(XHUA_SOC)
    gj = _parse_xh_page(XHUA_GJ)
    merged = []
    for i in range(max(len(soc), len(gj))):
        if i < len(soc):
            merged.append(soc[i])
        if i < len(gj):
            merged.append(gj[i])
    log("  新华：社会 %d 条，国际 %d 条" % (len(soc), len(gj)))
    return merged


# ---------- 数据源 C：外交部带图新闻 ----------
def get_mfa():
    h = fetch_text(MFA_URL)
    if not h:
        log("  外交部页面抓取失败，跳过该源")
        return []
    res = []
    pat = re.compile(
        r'<a\s+href="(\./[^\"]+\.shtml)"[^>]*>\s*'
        r'<div class="thumb"><img\s+src="(\./[^\"]+\.(?:jpg|jpeg|png|JPG|JPEG|PNG))"[^>]*>\s*</div>\s*'
        r'<div class="title"[^>]*>([^<]*)</div>', re.S)
    for m in pat.finditer(h):
        if len(res) >= MFA_TOP:
            break
        href = abs_url(m.group(1), MFA_BASE)
        img = abs_url(m.group(2), MFA_BASE)
        title = norm(HTMLLIB.unescape(m.group(3)))
        if not title or is_sensitive(title):
            continue
        if len(title) > 100:
            continue
        dm = re.search(r't(\d{8})_', m.group(1)) or re.search(r'/(\d{6})/', m.group(1))
        date = dm.group(1) if dm else ""
        res.append({
            "title": title,
            "url": href,
            "img": img,
            "timeAgo": fmt_date(date),
        })
    log("  外交部：%d 条" % len(res))
    return res


# ---------- 数据源 D：人民网图片频道 ----------
def get_people_pics():
    res = []
    for url in (PEOPLE_DOMESTIC, PEOPLE_WORLD):
        h = fetch_text(url)
        if not h:
            continue
        pat = re.compile(
            r'<div class="top-image">\s*'
            r'<a\s+href="([^"]+\.html)"[^>]*>\s*'
            r'<img\s+src="([^"]+\.(?:jpg|jpeg|png))"[^>]*alt="([^"]*)"[^>]*></a>.*?'
            r'<span><a[^>]*>([^<]+)</a></span>', re.S)
        for m in pat.finditer(h):
            if len(res) >= PEOPLE_PER * 2:
                break
            link = abs_url(m.group(1), PEOPLE_LINK_BASE)
            img = abs_url(m.group(2), PEOPLE_IMG_BASE)
            alt = norm(HTMLLIB.unescape(m.group(3)))
            title = norm(HTMLLIB.unescape(m.group(4)))
            if not title:
                title = alt
            if not title or is_sensitive(title):
                continue
            dm = re.search(r'/(\d{4})/(\d{2})(\d{2})/', m.group(1))
            date = (dm.group(1) + dm.group(2) + dm.group(3)) if dm else ""
            res.append({
                "title": title,
                "url": link,
                "img": img,
                "timeAgo": fmt_date(date),
            })
    log("  人民网图片：%d 条" % len(res))
    return res[:PEOPLE_PER * 2]


# ---------- 多源交叉混排 ----------
def merge_multi(sources, total):
    seen = set()
    out = []
    mx = max((len(s) for s in sources), default=0)
    for i in range(mx):
        for s in sources:
            if i >= len(s):
                continue
            key = s[i]["title"][:20]
            if key in seen:
                continue
            seen.add(key)
            out.append(s[i])
            if len(out) >= total:
                return out
    return out


def src_tag(url):
    if "thepaper.cn" in url:
        return "澎湃"
    if "news.cn" in url:
        return "新华"
    if "mfa.gov.cn" in url:
        return "外交部"
    if "people.com.cn" in url or "people.cn" in url:
        return "人民网"
    return "?"


# ---------- 注入 ----------
def inject_html(items):
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    lines = ["var imageNewsList = ["]
    for it in items:
        lines.append('  { title: %s, url: %s, img: %s, timeAgo: %s },' % (
            json.dumps(norm(it["title"]), ensure_ascii=False),
            json.dumps(norm(it["url"]), ensure_ascii=False),
            json.dumps(norm(it["img"]), ensure_ascii=False),
            json.dumps(norm(it["timeAgo"]), ensure_ascii=False),
        ))
    lines.append("];")
    new_block = "\n".join(lines)
    pat = re.compile(r'var imageNewsList\s*=\s*\[[\s\S]*?\n\];', re.M)
    if not pat.search(html):
        log("未在 index.html 找到 imageNewsList，跳过注入")
        return False
    html2 = pat.sub(new_block, html, count=1)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html2)
    return True


def main():
    log("开始构建图片新闻（澎湃 + 新华 + 外交部 + 人民网 四源）...")
    tp = get_thepaper()
    xh = get_xinhua()
    mfa = get_mfa()
    pp = get_people_pics()
    log("各源可用：澎湃 %d / 新华 %d / 外交部 %d / 人民网 %d"
        % (len(tp), len(xh), len(mfa), len(pp)))
    items = merge_multi([tp, xh, mfa, pp], TOTAL)
    if not items:
        log("无可用条目，终止")
        return
    if inject_html(items):
        log("已注入 %d 条到 index.html" % len(items))
        for i, it in enumerate(items, 1):
            log("  %d.[%s] %s | %s" % (i, it["timeAgo"], it["title"][:24], src_tag(it["url"])))
    else:
        log("注入失败")


if __name__ == "__main__":
    main()
