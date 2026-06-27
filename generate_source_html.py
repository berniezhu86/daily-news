#!/usr/bin/env python3
"""
自动生成源 HTML (臻宝每日快讯_带摘要.html)
在 GitHub Actions 中运行，从百度新闻/搜狗新闻抓取各板块新闻。
"""

import os
import re
import json
import time
import random
import requests
from datetime import datetime
from urllib.parse import quote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "臻宝每日快讯_带摘要.html")
CACHE_FILE = os.path.join(SCRIPT_DIR, ".news_cache.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
}

# ─── 板块配置 ───
SECTION_CONFIG = {
    "domestic": {
        "name": "国内新闻",
        "keywords": [
            "国内新闻", "今日要闻", "时政新闻", "中国经济",
            "科技前沿 中国", "民生新闻", "教育新闻",
            "医疗健康 中国", "交通新闻", "环境新闻 中国"
        ],
        "per_kw": 12,
        "total_target": 100,
        "badge": "hot"
    },
    "international": {
        "name": "国际新闻",
        "keywords": [
            "国际新闻", "世界新闻", "美国新闻", "欧洲新闻",
            "日本新闻", "韩国新闻", "中东新闻", "东南亚新闻",
            "联合国新闻", "全球经济"
        ],
        "per_kw": 12,
        "total_target": 100,
        "badge": "hot"
    },
    "entertainment": {
        "name": "娱乐新闻",
        "keywords": [
            "娱乐新闻", "明星动态", "电影资讯", "电视剧 热播",
            "综艺节目", "音乐新闻", "网络热梗", "网红动态",
            "体育娱乐", "动漫资讯"
        ],
        "per_kw": 12,
        "total_target": 100,
        "badge": "hot"
    },
    "henan": {
        "name": "河南足球",
        "keywords": [
            "河南队 中超", "河南足球", "河南队 比赛",
            "河南 足球新闻", "河南队 球员"
        ],
        "per_kw": 8,
        "total_target": 30,
        "badge": "hot"
    },
    "csl": {
        "name": "中超动态",
        "keywords": [
            "中超联赛", "中超新闻", "上海海港 中超",
            "山东泰山 中超", "北京国安 中超", "上海申花 中超",
            "成都蓉城 中超", "武汉三镇 中超", "中超转会",
            "中国足协"
        ],
        "per_kw": 5,
        "total_target": 30,
        "badge": "hot"
    },
    "ai_tech": {
        "name": "AI 科技",
        "keywords": [
            "人工智能 最新", "AI 新闻", "大模型 进展",
            "AI 应用", "芯片 技术", "自动驾驶 最新",
            "量子计算", "机器人 新闻"
        ],
        "per_kw": 6,
        "total_target": 50,
        "badge": "new"
    }
}


def search_baidu_news(query, max_results=12):
    """从百度新闻搜索，返回 [{title, url, source}]"""
    results = []
    
    # 主策略：百度新闻搜索
    try:
        url = f"https://www.baidu.com/s?tn=news&rtt=1&bsst=1&cl=2&wd={quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = 'utf-8'
        html = resp.text
        
        # 多种匹配模式
        patterns = [
            r'<h3[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>\s*</h3>',
            r'<a[^>]*href="(https?://[^"]*)"[^>]*class="[^"]*news-title[^"]*"[^>]*>(.*?)</a>',
            r'<a[^>]*href="(https?://[^"]*)"[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</a>',
        ]
        
        for pattern in patterns:
            if len(results) >= max_results:
                break
            matches = re.findall(pattern, html)
            for link, title in matches:
                if len(results) >= max_results:
                    break
                title = re.sub(r'<[^>]+>', '', title).strip()
                title = re.sub(r'&nbsp;|&amp;|&lt;|&gt;|&#34;|&#39;', ' ', title).strip()
                if title and len(title) > 4 and not title.startswith('http'):
                    # 提取来源
                    source = "综合新闻"
                    source_match = re.search(r'【([^】]+)】', title)
                    if source_match:
                        source = source_match.group(1)
                        title = re.sub(r'【[^】]+】', '', title).strip()
                    results.append({
                        'title': title,
                        'url': link,
                        'source': source
                    })
    except Exception as e:
        print(f"  ⚠ Baidu search failed for '{query}': {e}")
    
    # Fallback: 搜狗新闻
    if len(results) < 3:
        results.extend(_search_sogou_news(query, max_results - len(results)))
    
    return results[:max_results]


def _search_sogou_news(query, max_results=8):
    """搜狗新闻搜索 fallback"""
    results = []
    try:
        url = f"https://news.sogou.com/news?query={quote(query)}&sort=1&page=1"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = 'utf-8'
        html = resp.text
        
        patterns = [
            r'<h3[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>\s*</h3>',
            r'<a[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>',
        ]
        
        for pattern in patterns:
            if len(results) >= max_results:
                break
            matches = re.findall(pattern, html)
            for link, title in matches:
                if len(results) >= max_results:
                    break
                title = re.sub(r'<[^>]+>', '', title).strip()
                title = re.sub(r'&nbsp;|&amp;|&lt;|&gt;', ' ', title).strip()
                if title and len(title) > 4 and '搜狗' not in title:
                    source = "搜狗新闻"
                    source_match = re.search(r'【([^】]+)】', title)
                    if source_match:
                        source = source_match.group(1)
                        title = re.sub(r'【[^】]+】', '', title).strip()
                    results.append({'title': title, 'url': link, 'source': source})
    except Exception as e:
        print(f"  ⚠ Sogou search also failed for '{query}': {e}")
    
    return results[:max_results]


def collect_section_news(section_id, config):
    """为一个板块收集新闻，去重后返回列表"""
    all_news = []
    seen_titles = set()
    name = config['name']
    keywords = config['keywords']
    per_kw = config['per_kw']
    target = config['total_target']
    
    print(f"\n📰 Collecting [{name}]...")
    
    for kw in keywords:
        if len(all_news) >= target:
            break
        
        results = search_baidu_news(kw, max_results=per_kw)
        new_count = 0
        for item in results:
            # 标题去重（取前 20 字符做指纹）
            fingerprint = item['title'][:20].strip()
            if fingerprint not in seen_titles and len(all_news) < target:
                seen_titles.add(fingerprint)
                all_news.append(item)
                new_count += 1
        
        print(f"  '{kw}': +{new_count} (total: {len(all_news)})")
        time.sleep(random.uniform(1.5, 3.0))  # 避免请求过快
    
    print(f"  ✅ [{name}] done: {len(all_news)} items")
    return all_news


def generate_summary(title):
    """为新闻生成一个简短的描述（基于标题提炼）"""
    # 去除来源标记
    title_clean = re.sub(r'【[^】]+】', '', title).strip()
    title_clean = re.sub(r'^\d{4}-\d{2}-\d{2}\s*', '', title_clean).strip()
    
    # 如果标题已经足够长，直接作为摘要
    if len(title_clean) > 20:
        return title_clean
    
    # 如果标题太短，加上时间前缀
    today = datetime.now().strftime("%m月%d日")
    return f"{today}，{title_clean}"


def render_html_section(section_id, config, news_items):
    """渲染一个板块的 HTML"""
    name = config['name']
    count = len(news_items)
    
    lines = []
    lines.append(f'        <section id="{section_id}" class="section{" active" if section_id == "domestic" else ""}">')
    lines.append(f'            <div class="section-header">')
    lines.append(f'                <h2 class="section-title">{name}</h2>')
    lines.append(f'                <span class="section-count">{count} 条</span>')
    lines.append(f'            </div>')
    lines.append(f'            <div class="news-grid">')
    
    for item in news_items:
        title = item['title'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        url = item.get('url', '#')
        source = item.get('source', '综合新闻').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        summary = generate_summary(item['title']).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        
        lines.append(f'                <div class="news-card">')
        lines.append(f'                    <a href="{url}" target="_blank" rel="noopener" class="news-title">{title}</a>')
        lines.append(f'                    <div class="news-meta">【{source}】</div>')
        lines.append(f'                    <p class="news-summary">{summary}</p>')
        lines.append(f'                </div>')
    
    lines.append(f'            </div>')
    lines.append(f'        </section>')
    
    return '\n'.join(lines)


def generate_html(sections_data):
    """生成完整的 HTML 文件"""
    now = datetime.now()
    date_str = now.strftime("%Y年%m月%d日")
    date_short = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y年%m月%d日 周%w %H:%M").replace('周0', '周日').replace('周1', '周一').replace('周2', '周二').replace('周3', '周三').replace('周4', '周四').replace('周5', '周五').replace('周6', '周六')
    
    # 计算总条数
    total_count = sum(len(items) for items in sections_data.values())
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>臻宝每日快讯 — {date_str}</title>
    <style>
        :root {{
            --bg-primary: #f5f5f7;
            --bg-secondary: #ffffff;
            --bg-tertiary: #fafafa;
            --text-primary: #1d1d1f;
            --text-secondary: #6e6e73;
            --text-tertiary: #86868b;
            --accent: #0071e3;
            --accent-hover: #0077ed;
            --border: #d2d2d7;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.04);
            --shadow-md: 0 4px 20px rgba(0,0,0,0.06);
            --shadow-lg: 0 8px 40px rgba(0,0,0,0.08);
            --radius-sm: 12px;
            --radius-md: 16px;
            --radius-lg: 20px;
            --nav-bg: rgba(255,255,255,0.72);
            --card-bg: #ffffff;
            --stock-up: #34c759;
            --stock-down: #ff3b30;
            --gradient-hero: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --font-sf: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-primary: #000000;
                --bg-secondary: #1c1c1e;
                --bg-tertiary: #2c2c2e;
                --text-primary: #f5f5f7;
                --text-secondary: #a1a1a6;
                --text-tertiary: #6e6e73;
                --border: #38383a;
                --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
                --shadow-md: 0 4px 20px rgba(0,0,0,0.4);
                --shadow-lg: 0 8px 40px rgba(0,0,0,0.5);
                --nav-bg: rgba(28,28,30,0.8);
                --card-bg: #1c1c1e;
                --gradient-hero: linear-gradient(135deg, #4a00e0 0%, #8e2de2 100%);
            }}
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: var(--font-sf);
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
        }}

        .hero {{
            background: var(--gradient-hero);
            padding: 60px 20px 50px;
            text-align: center;
            color: white;
        }}

        .hero h1 {{
            font-size: 36px;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 10px;
        }}

        .hero p {{
            font-size: 16px;
            opacity: 0.9;
            font-weight: 400;
        }}

        .nav {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: var(--nav-bg);
            backdrop-filter: saturate(180%) blur(20px);
            -webkit-backdrop-filter: saturate(180%) blur(20px);
            border-bottom: 1px solid var(--border);
            overflow-x: auto;
            white-space: nowrap;
            padding: 12px 20px;
        }}

        .nav::-webkit-scrollbar {{ display: none; }}

        .nav a {{
            display: inline-block;
            padding: 8px 16px;
            margin-right: 8px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 500;
            color: var(--text-secondary);
            text-decoration: none;
            transition: all 0.2s;
            cursor: pointer;
        }}

        .nav a:hover {{ color: var(--accent); background: rgba(0,113,227,0.08); }}
        .nav a.active {{ color: white; background: var(--accent); }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        .section {{
            margin-bottom: 40px;
        }}

        .section-header {{
            display: flex;
            align-items: baseline;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--accent);
        }}

        .section-title {{
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
        }}

        .section-count {{
            font-size: 14px;
            color: var(--text-tertiary);
            font-weight: 500;
        }}

        .news-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 16px;
        }}

        .news-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 18px 20px;
            transition: all 0.2s;
            box-shadow: var(--shadow-sm);
        }}

        .news-card:hover {{
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
            border-color: var(--accent);
        }}

        .news-title {{
            display: block;
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
            text-decoration: none;
            line-height: 1.5;
            margin-bottom: 8px;
            transition: color 0.15s;
        }}

        .news-title:hover {{ color: var(--accent); }}

        .news-meta {{
            font-size: 12px;
            color: var(--accent);
            margin-bottom: 8px;
            font-weight: 500;
        }}

        .news-summary {{
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.6;
        }}

        footer {{
            text-align: center;
            padding: 40px 20px;
            color: var(--text-tertiary);
            font-size: 13px;
            border-top: 1px solid var(--border);
            margin-top: 40px;
        }}

        footer p {{ margin-bottom: 4px; }}

        @media (max-width: 768px) {{
            .hero {{ padding: 40px 16px 30px; }}
            .hero h1 {{ font-size: 26px; }}
            .news-grid {{ grid-template-columns: 1fr; }}
            .container {{ padding: 12px; }}
        }}
    </style>
</head>
<body>
    <div class="hero">
        <h1>📰 臻宝每日快讯</h1>
        <p>{date_str} · 共 {total_count} 条新闻 · AI 智能聚合</p>
    </div>

    <nav class="nav">
        <a href="#domestic" class="active" onclick="switchSection('domestic')">国内新闻</a>
        <a href="#international" onclick="switchSection('international')">国际新闻</a>
        <a href="#entertainment" onclick="switchSection('entertainment')">娱乐新闻</a>
        <a href="#henan" onclick="switchSection('henan')">河南足球</a>
        <a href="#csl" onclick="switchSection('csl')">中超动态</a>
        <a href="#ai_tech" onclick="switchSection('ai_tech')">AI 科技</a>
    </nav>

    <div class="container">
'''
    
    # 渲染各板块
    for section_id in ["domestic", "international", "entertainment", "henan", "csl", "ai_tech"]:
        if section_id in sections_data:
            config = SECTION_CONFIG[section_id]
            html += render_html_section(section_id, config, sections_data[section_id])
            html += '\n'
    
    # Footer
    html += f'''    </div>

    <footer>
        <p>臻宝每日快讯 · AI 智能聚合 · 数据来源：百度新闻、搜狗新闻</p>
        <p>本次更新时间：{time_str} · 所有新闻链接均跳转至原始来源</p>
        <p style="margin-top:8px;color:var(--accent);font-weight:500;">Mac 专属 · Apple 风格设计 · 自动浅/深色切换</p>
    </footer>

<script>
(function () {{
    // 导航切换
    window.switchSection = function (sectionId) {{
        document.querySelectorAll('.section').forEach(s => s.style.display = 'none');
        const target = document.getElementById(sectionId);
        if (target) target.style.display = 'block';

        document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
        const navLink = document.querySelector(`.nav a[href="#${{sectionId}}"]`);
        if (navLink) navLink.classList.add('active');
    }};

    // 初始化：只显示第一个板块
    const sections = document.querySelectorAll('.section');
    sections.forEach((s, i) => {{ s.style.display = i === 0 ? 'block' : 'none'; }});
}})();
</script>
</body>
</html>'''
    
    return html


def main():
    print("=" * 60)
    print("  臻宝每日快讯 - 自动生成源 HTML")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 缓存检查：如果 3 小时内已生成，跳过
    if os.path.exists(OUTPUT_FILE):
        mtime = os.path.getmtime(OUTPUT_FILE)
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 3:
            print(f"⏭ 源 HTML 在 {age_hours:.1f} 小时内已生成，跳过。")
            return
    
    sections_data = {}
    
    for section_id in ["domestic", "international", "entertainment", "henan", "csl", "ai_tech"]:
        config = SECTION_CONFIG[section_id]
        news_items = collect_section_news(section_id, config)
        sections_data[section_id] = news_items
    
    # 生成 HTML
    print(f"\n📝 Generating HTML...")
    html = generate_html(sections_data)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    
    total = sum(len(items) for items in sections_data.values())
    file_size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\n✅ Done! Generated {OUTPUT_FILE}")
    print(f"   Total news: {total} items")
    print(f"   File size: {file_size_kb:.1f} KB")
    
    # 也保存到本地用户文档目录（供本地预览）
    local_copy = os.path.expanduser("~/Documents/软件测试/臻宝每日快讯_带摘要.html")
    try:
        os.makedirs(os.path.dirname(local_copy), exist_ok=True)
        with open(local_copy, 'r', encoding='utf-8') as src:
            with open(local_copy, 'w', encoding='utf-8') as dst:
                dst.write(html)
    except:
        pass  # GitHub Actions 中不存在本地目录，忽略
    
    # 保存汇总 JSON
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "sections": {k: len(v) for k, v in sections_data.items()}
    }
    with open(os.path.join(SCRIPT_DIR, ".gen_summary.json"), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
