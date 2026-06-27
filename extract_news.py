#!/usr/bin/env python3
"""Extract news from source HTML and generate JS arrays for the project."""

import re
import json

SOURCE_FILE = "/Users/bainian/Documents/软件测试/臻宝每日快讯_带摘要.html"
OUTPUT_FILE = "/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/extracted_news.json"

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
    sections = parse_source_html(SOURCE_FILE)
    
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
    js_file = "/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/generated_news_arrays.js"
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
    
    # Generate per-user exclusive news arrays
    print("\n--- Exclusive News Generation ---")
    exclusive_js = generate_exclusive_news(sections)
    if exclusive_js:
        exclusive_file = "/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/exclusive_news_arrays.js"
        with open(exclusive_file, 'w', encoding='utf-8') as f:
            f.write(exclusive_js)
        print(f"Exclusive news saved to: {exclusive_file}")


def generate_exclusive_news(sections):
    """Read exclusive_interests.json (multi-user format),
    match news across all sections, and generate per-user JS arrays."""
    interests_file = "/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/exclusive_interests.json"
    try:
        with open(interests_file, 'r', encoding='utf-8') as f:
            user_interests = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  WARNING: Cannot read exclusive_interests.json: {e}")
        return ""
    
    # Collect all news items from all sections
    all_news = []
    for section_id, items in sections.items():
        for item in items:
            item['_section'] = section_id
            all_news.append(item)
    
    if not all_news:
        print("  No news items to match against")
        return ""
    
    # Build per-user exclusive news
    # user_interests format: {"爸爸": ["刘德华"], "妈妈": []}
    user_exclusive = {}
    for username, interests in user_interests.items():
        if not interests:
            user_exclusive[username] = []
            print(f"  {username}: 0 interests, 0 matches")
            continue
        matched = []
        for item in all_news:
            title = item.get('title', '')
            summary = item.get('summary', '')
            for kw in interests:
                if kw in title or kw in summary:
                    matched.append({
                        'title': item['title'],
                        'source': item['source'],
                        'summary': item['summary'],
                        'matchTag': kw,
                        'time': '2026-06-26',
                    })
                    break  # One match per item per user
        user_exclusive[username] = matched[:10]  # Max 10 per user
        print(f"  {username}: {len(interests)} interests, {len(matched[:10])} matches")
    
    # Generate JS code
    lines = ["// === 按用户分组的专属新闻数组（由 extract_news.py 自动生成） ===", ""]
    
    for username, news_list in user_exclusive.items():
        safe_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', username)
        lines.append(f"const mockExclusiveNews_{safe_name} = [")
        for item in news_list:
            title = item['title'].replace('"', '\\"')
            summary = item['summary'].replace('"', '\\"')
            source = item['source'].replace('"', '\\"')
            match_tag = item['matchTag'].replace('"', '\\"')
            lines.append(f'  {{title:"{title}", source:"{source}", summary:"{summary}", matchTag:"{match_tag}", time:"{item["time"]}"}},')
        lines.append("];")
        lines.append("")
    
    # Also generate a lookup map for index.html to use
    lines.append("// 用户专属新闻查找映射")
    lines.append("var userExclusiveNewsMap = {")
    for username in user_exclusive.keys():
        safe_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', username)
        lines.append(f'  "{username}": mockExclusiveNews_{safe_name},')
    lines.append("};")
    
    return "\n".join(lines)

if __name__ == '__main__':
    main()
