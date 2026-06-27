#!/usr/bin/env python3
"""Extract news from source HTML and generate JS arrays for the project."""

import os
import re
import json
import requests
from urllib.parse import quote

# Script's own directory (works both locally and in GitHub Actions)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SOURCE_FILE = os.path.join(SCRIPT_DIR, "臻宝每日快讯_带摘要.html")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "extracted_news.json")

def parse_source_html(filepath):
    """Parse the source HTML and extract news items by section."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    sections = {}
    
    # Find each section by id
    section_pattern = r'<section id="(\w+)"[^>]*>.*?<div class="news-grid">(.*?)</div>\s*</section>'
    matches = re.findall(section_pattern, content, re.DOTALL)
    
    for section_id, grid_content in matches:
        items = []
        # Parse each news-card
        card_pattern = r'<div class="news-card">\s*<a[^>]*class="news-title"[^>]*>(.*?)</a>\s*<div class="news-meta">【(.*?)】</div>\s*<p class="news-summary">(.*?)</p>\s*</div>'
        card_matches = re.findall(card_pattern, grid_content, re.DOTALL)
        
        for title, source, summary in card_matches:
            title = title.strip()
            source = source.strip()
            summary = summary.strip()
            items.append({
                'title': title,
                'source': source,
                'summary': summary
            })
        
        sections[section_id] = items
        print(f"Section '{section_id}': {len(items)} items")
    
    return sections

def fix_vague_time(text):
    """Replace vague time references with specific dates or remove them."""
    # Replace common vague time references
    replacements = [
        (r'今日', '6月26日'),
        (r'今日凌晨', '6月26日凌晨'),
        (r'今日上午', '6月26日上午'),
        (r'今日下午', '6月26日下午'),
        (r'今日晚间', '6月26日晚间'),
        (r'今日晚', '6月26日晚'),
        (r'昨日', '6月25日'),
        (r'昨天', '6月25日'),
        (r'明日', '6月27日'),
        (r'明天', '6月27日'),
        (r'前天', '6月24日'),
        (r'近日', '近期'),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text

def assign_heat_and_badge(rank, total, section):
    """Assign heat value and badge based on rank and section."""
    if rank <= 3:
        heat = 10
        badge = "hot"
    elif rank <= 6:
        heat = 9
        badge = "hot"
    elif rank <= 10:
        heat = 8
        badge = "hot" if rank <= 8 else ""
    elif rank <= 15:
        heat = 7
        badge = ""
    elif rank <= 20:
        heat = 6
        badge = ""
    else:
        # For extra items
        if rank <= 25:
            heat = 6
            badge = "rising"
        elif rank <= 30:
            heat = 5
            badge = "new"
        else:
            heat = 5
            badge = ""
    return heat, badge

def generate_domestic_js(items):
    """Generate JS for mockHotNewsDomestic (first 20) and mockHotNewsDomesticExtra (rest)."""
    main_items = items[:20]
    extra_items = items[20:]
    
    # Main array
    main_lines = ["const mockHotNewsDomestic = ["]
    for i, item in enumerate(main_items):
        rank = i + 1
        heat, badge = assign_heat_and_badge(rank, len(items), 'domestic')
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        # Escape quotes
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        main_lines.append(f'  {{rank:{rank}, title:"{title}", source:"{source}", summary:"{summary}", badge:"{badge}", heat:{heat}, time:"2026-06-26"}},')
    main_lines.append("];")
    
    # Extra array
    extra_lines = ["", "const mockHotNewsDomesticExtra = ["]
    for i, item in enumerate(extra_items):
        rank = i + 21
        heat, badge = assign_heat_and_badge(rank, len(items), 'domestic')
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        extra_lines.append(f'  {{rank:{rank}, title:"{title}", source:"{source}", badge:"{badge}", summary:"{summary}"}},')
    extra_lines.append("];")
    
    return '\n'.join(main_lines + extra_lines)

def generate_international_js(items):
    """Generate JS for mockHotNewsInternational and mockHotNewsInternationalExtra."""
    main_items = items[:20]
    extra_items = items[20:]
    
    main_lines = ["const mockHotNewsInternational = ["]
    for i, item in enumerate(main_items):
        rank = i + 1
        heat, badge = assign_heat_and_badge(rank, len(items), 'international')
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        main_lines.append(f'  {{rank:{rank}, title:"{title}", source:"{source}", badge:"{badge}", summary:"{summary}"}},')
    main_lines.append("];")
    
    extra_lines = ["", "const mockHotNewsInternationalExtra = ["]
    for i, item in enumerate(extra_items):
        rank = i + 21
        heat, badge = assign_heat_and_badge(rank, len(items), 'international')
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        extra_lines.append(f'  {{rank:{rank}, title:"{title}", source:"{source}", badge:"{badge}", summary:"{summary}"}},')
    extra_lines.append("];")
    
    return '\n'.join(main_lines + extra_lines)

def generate_entertainment_js(items):
    """Generate JS for mockEntertainment and mockEntertainmentExtra."""
    main_items = items[:20]
    extra_items = items[20:]
    
    main_lines = ["const mockEntertainment = ["]
    for i, item in enumerate(main_items):
        rank = i + 1
        heat, badge = assign_heat_and_badge(rank, len(items), 'entertainment')
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        main_lines.append(f'  {{rank:{rank}, title:"{title}", source:"{source}", summary:"{summary}", badge:"{badge}", heat:{heat}, time:"2026-06-26"}},')
    main_lines.append("];")
    
    extra_lines = ["", "const mockEntertainmentExtra = ["]
    for i, item in enumerate(extra_items):
        rank = i + 21
        heat, badge = assign_heat_and_badge(rank, len(items), 'entertainment')
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        extra_lines.append(f'  {{rank:{rank}, title:"{title}", source:"{source}", badge:"{badge}", summary:"{summary}"}},')
    extra_lines.append("];")
    
    return '\n'.join(main_lines + extra_lines)

def generate_henan_js(items):
    """Generate JS for mockHenanNews."""
    lines = ["const mockHenanNews = ["]
    for i, item in enumerate(items):
        rank = i + 1
        heat = 9 if rank <= 3 else (8 if rank <= 6 else (7 if rank <= 10 else 6))
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        lines.append(f'  {{team:"河南队", title:"{title}", source:"{source}", summary:"{summary}", time:"2026-06-26", heat:{heat}}},')
    lines.append("];")
    return '\n'.join(lines)

def generate_csl_js(items):
    """Generate JS for mockCslOtherTeams."""
    # Try to extract team name from title or source
    team_keywords = {
        '上海海港': ['海港', '上海海港'],
        '山东泰山': ['泰山', '山东泰山'],
        '北京国安': ['国安', '北京国安'],
        '天津津门虎': ['津门虎', '天津'],
        '武汉三镇': ['武汉', '三镇'],
        '成都蓉城': ['蓉城', '成都'],
        '青岛海牛': ['海牛', '青岛'],
        '上海申花': ['申花'],
        '浙江队': ['浙江'],
        '深圳新鹏城': ['深圳'],
        '大连英博': ['大连', '英博'],
        '辽宁铁人': ['辽宁', '铁人'],
        '重庆铜梁龙': ['重庆', '铜梁龙'],
        '云南玉昆': ['云南', '玉昆'],
        '中超': ['中超', '足协', '中国足协'],
    }
    
    lines = ["// === 中超联赛其他球队新闻 ===", "const mockCslOtherTeams = ["]
    for i, item in enumerate(items):
        rank = i + 1
        heat = 9 if rank <= 3 else (8 if rank <= 6 else (7 if rank <= 10 else (6 if rank <= 15 else 5)))
        title = fix_vague_time(item['title'])
        summary = fix_vague_time(item['summary'])
        
        # Determine team
        team = "中超"
        for team_name, keywords in team_keywords.items():
            for kw in keywords:
                if kw in title or kw in item['source']:
                    team = team_name
                    break
            if team != "中超":
                break
        
        title = title.replace('"', '\\"')
        summary = summary.replace('"', '\\"')
        source = item['source'].replace('"', '\\"')
        lines.append(f'  {{team:"{team}", title:"{title}", source:"{source}", summary:"{summary}", time:"2026-06-26", heat:{heat}}},')
    lines.append("];")
    return '\n'.join(lines)

def main():
    print("Parsing source HTML...")
    sections = {}
    try:
        sections = parse_source_html(SOURCE_FILE)
    except FileNotFoundError:
        print("Source HTML not found, skipping main news generation (GitHub Actions mode).")
    
    if sections:
        print("\nGenerating JS arrays...")
        
        # Generate each section
        domestic_js = generate_domestic_js(sections.get('domestic', []))
        international_js = generate_international_js(sections.get('international', []))
        entertainment_js = generate_entertainment_js(sections.get('entertainment', []))
        henan_js = generate_henan_js(sections.get('henan', []))
        csl_js = generate_csl_js(sections.get('csl', []))
        
        # Save to JSON for inspection
        output = {
            'domestic': sections.get('domestic', []),
            'international': sections.get('international', []),
            'entertainment': sections.get('entertainment', []),
            'henan': sections.get('henan', []),
            'csl': sections.get('csl', []),
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        # Save JS output
        js_output = "\n\n".join([domestic_js, international_js, entertainment_js, henan_js, csl_js])
        js_file = os.path.join(SCRIPT_DIR, "generated_news_arrays.js")
        with open(js_file, 'w', encoding='utf-8') as f:
            f.write(js_output)
        
        print(f"\nGenerated JS saved to: {js_file}")
        print(f"JSON data saved to: {OUTPUT_FILE}")
        print(f"\nCounts:")
        print(f"  Domestic: {len(sections.get('domestic', []))} items")
        print(f"  International: {len(sections.get('international', []))} items")
        print(f"  Entertainment: {len(sections.get('entertainment', []))} items")
        print(f"  Henan: {len(sections.get('henan', []))} items")
        print(f"  CSL: {len(sections.get('csl', []))} items")
    
    # Generate per-user exclusive news pending list (raw search results for Marvis to review)
    print("\n--- Exclusive News Search (raw candidates) ---")
    pending = generate_pending_exclusive_news(sections)
    if pending:
        pending_file = os.path.join(SCRIPT_DIR, "pending_exclusive_news.json")
        with open(pending_file, 'w', encoding='utf-8') as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
        print(f"Pending exclusive news saved to: {pending_file}")


def search_interest_news(query, max_results=5):
    """
    Search for news about a given query using Baidu News (primary) + Sogou (fallback).
    Returns list of {title, source, summary} dicts.
    """
    results = []
    search_url = f"https://www.baidu.com/s?tn=news&rtt=1&bsst=1&wd={quote(query)}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        resp.encoding = 'utf-8'
        html = resp.text
        
        # 百度新闻搜索结果：标题在 h3 > a 中
        pattern = r'<h3[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>\s*</h3>'
        matches = re.findall(pattern, html)
        
        for url, title in matches[:max_results]:
            title = re.sub(r'<[^>]+>', '', title).strip()
            if title and len(title) > 2:
                results.append({
                    'title': title,
                    'source': '百度新闻',
                    'url': url,
                    'summary': ''
                })
        
        if not results:
            print(f"  ⚠ Baidu pattern1 failed, trying pattern2...")
            pattern2 = r'<a[^>]*href="([^"]*)"[^>]*class="[^"]*news-title[^"]*"[^>]*>(.*?)</a>'
            matches2 = re.findall(pattern2, html)
            for url, title in matches2[:max_results]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                if title and len(title) > 2:
                    results.append({'title': title, 'source': '百度新闻', 'url': url, 'summary': ''})
    
    except Exception as e:
        print(f"  ⚠ Baidu search failed ({e}), falling back to Sogou...")
    
    # 百度失败或没结果，fallback 到搜狗
    if not results:
        results = search_sogou_news(query, max_results)
    
    return results


def search_sogou_news(query, max_results=5):
    """Sogou News fallback search."""
    results = []
    search_url = f"https://news.sogou.com/news?query={quote(query)}&sort=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        resp.encoding = 'utf-8'
        html = resp.text
        
        # 搜狗新闻结果
        pattern = r'<h3[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>\s*</h3>'
        matches = re.findall(pattern, html)
        for url, title in matches[:max_results]:
            title = re.sub(r'<[^>]+>', '', title).strip()
            if title and len(title) > 2:
                results.append({'title': title, 'source': '搜狗新闻', 'url': url, 'summary': ''})
    except Exception as e:
        print(f"  ⚠ Sogou search also failed: {e}")
    
    return results

def generate_pending_exclusive_news(sections):
    """Read exclusive_interests.json, search web for each interest,
    and generate a pending JSON with raw candidates (including URLs).
    This pending file will later be reviewed and enhanced by Marvis."""
    interests_file = os.path.join(SCRIPT_DIR, "exclusive_interests.json")
    try:
        with open(interests_file, 'r', encoding='utf-8') as f:
            user_interests = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  WARNING: Cannot read exclusive_interests.json: {e}")
        return None
    
    # Collect local news for matching
    all_news = []
    for section_id, items in sections.items():
        for item in items:
            item['_section'] = section_id
            all_news.append(item)
    
    pending = {
        "generated_at": "",
        "users": {}
    }
    
    from datetime import datetime
    pending["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for user, interests in user_interests.items():
        if not interests:
            pending["users"][user] = []
            continue
        
        user_candidates = []
        seen_titles = set()
        
        for kw in interests:
            kw_candidates = []
            
            # 1) Local match
            for item in all_news:
                title_lower = item['title'].lower()
                summary_lower = item['summary'].lower()
                kw_lower = kw.lower()
                if kw_lower in title_lower or kw_lower in summary_lower:
                    key = (item['title'], item['source'])
                    if key not in seen_titles:
                        seen_titles.add(key)
                        kw_candidates.append({
                            "title": item['title'],
                            "source": item['source'],
                            "url": item.get('url', ''),
                            "matchTag": kw,
                        })
            
            # 2) Web search supplement
            if len(kw_candidates) < 5:
                print(f"  🔍 Searching web for '{kw}' (only {len(kw_candidates)} local matches)...")
                web_results = search_interest_news(kw, max_results=8)
                for r in web_results:
                    if len(kw_candidates) >= 5:
                        break
                    key = (r['title'], r['source'])
                    if key not in seen_titles:
                        seen_titles.add(key)
                        kw_candidates.append({
                            "title": r['title'],
                            "source": r['source'],
                            "url": r['url'],
                            "matchTag": kw,
                        })
            
            user_candidates.extend(kw_candidates[:5])
        
        pending["users"][user] = user_candidates[:15]
        print(f"  {user}: {len(user_candidates[:15])} raw candidates generated")
    
    return pending

if __name__ == '__main__':
    main()
