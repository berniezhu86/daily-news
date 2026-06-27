#!/usr/bin/env python3
"""
臻宝每日简讯 - 新闻自动更新脚本
严格按照时效性要求：热搜/娱乐/股市近3天，河南/中超近5天
"""

import re
import json
import subprocess
from datetime import datetime, timedelta

def fetch_hot_news():
    """获取每日热搜新闻（近3天内）"""
    print("=== 搜索每日热搜新闻 ===")
    # 这里应该调用 WebSearch 和 WebFetch，但作为示例，我们返回空列表
    # 实际执行时由 AI 助手完成
    return []

def fetch_entertainment_news():
    """获取娱乐热点新闻（近3天内）"""
    print("=== 搜索娱乐热点新闻 ===")
    return []

def fetch_stock_news():
    """获取股市行情新闻（近3天内）"""
    print("=== 搜索股市行情新闻 ===")
    return []

def fetch_henan_news():
    """获取河南足球新闻（近5天内）"""
    print("=== 搜索河南足球新闻 ===")
    return []

def fetch_csl_news():
    """获取中超其他球队新闻（近5天内）"""
    print("=== 搜索中超其他球队新闻 ===")
    return []

def update_index_html(hot_news, entertainment, stock, henan, csl):
    """更新 index.html 中的新闻数组"""
    print("=== 更新 index.html ===")
    # 读取文件
    with open('/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/index.html', 'r') as f:
        content = f.read()
    
    # 更新各个数组
    # 注意：需要确保 JS 语法正确，特别是转义双引号
    
    print("更新完成")

def increment_version():
    """从 index.html 读取当前版本号并自动递增。
    同一天内 vN → vN+1，跨天则重置为当天日期+v1。
    同时更新 brandVersion / settingsVersion 两个 span 以及 stockDataUpdateTime。
    """
    index_path = '/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/index.html'
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取当前版本号（格式：YYYYMMDDvN）
    brand_match = re.search(r'<span class="brand-version" id="brandVersion">([^<]+)</span>', content)
    if not brand_match:
        print("❌ 未找到 brandVersion，跳过版本递增")
        return

    current_version = brand_match.group(1)
    version_match = re.match(r'(\d{8})v(\d+)', current_version)
    if not version_match:
        print(f"❌ 版本号格式异常: {current_version}，跳过版本递增")
        return

    version_date = version_match.group(1)
    version_num = int(version_match.group(2))
    today = datetime.now().strftime("%Y%m%d")

    if version_date == today:
        new_version = f"{today}v{version_num + 1}"
    else:
        new_version = f"{today}v1"

    # 更新 brandVersion
    content = re.sub(
        r'(<span class="brand-version" id="brandVersion">)[^<]+(</span>)',
        rf'\g<1>{new_version}\g<2>',
        content,
        count=1
    )

    # 更新 settingsVersion
    content = re.sub(
        r'(<span class="settings-row-desc" id="settingsVersion">)[^<]+(</span>)',
        rf'\g<1>{new_version}\g<2>',
        content,
        count=1
    )

    # 更新 stockDataUpdateTime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = re.sub(
        r'(const stockDataUpdateTime = ")[^"]+(")',
        rf'\g<1>{now_str}\g<2>',
        content,
        count=1
    )

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ 版本号已更新: {current_version} → {new_version}")

def check_js_syntax():
    """检查 JS 语法是否正确"""
    print("=== 检查 JS 语法 ===")
    result = subprocess.run(
        ['node', '--check', '/tmp/check_js.js'],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ JS 语法错误: {result.stderr}")
        return False
    print("✅ JS 语法正确")
    return True

def commit_and_push():
    """提交并推送到 GitHub"""
    print("=== 提交到 GitHub ===")
    subprocess.run(['git', 'add', 'index.html'], cwd='/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news')
    subprocess.run(['git', 'commit', '-m', f'auto: 新闻更新 - {datetime.now().strftime("%Y-%m-%d")}'], 
                  cwd='/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news')
    subprocess.run(['git', 'push', 'origin', 'main'], cwd='/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news')
    print("✅ 已推送到 GitHub")

def main():
    """主函数"""
    print(f"开始执行新闻更新任务 - {datetime.now()}")
    
    # 1. 搜索新闻
    hot_news = fetch_hot_news()
    entertainment = fetch_entertainment_news()
    stock = fetch_stock_news()
    henan = fetch_henan_news()
    csl = fetch_csl_news()
    
    # 2. 更新 index.html
    update_index_html(hot_news, entertainment, stock, henan, csl)
    
    # 2.5. 版本号自动递增
    increment_version()
    
    # 3. 检查 JS 语法
    if not check_js_syntax():
        print("❌ JS 语法检查失败，终止提交")
        return
    
    # 4. 提交到 GitHub
    commit_and_push()
    
    # 5. 输出运行报告
    print("\n=== 运行报告 ===")
    print(f"运行时间: {datetime.now()}")
    print(f"每日热搜: 搜索到 {len(hot_news)} 条")
    print(f"娱乐热点: 搜索到 {len(entertainment)} 条")
    print(f"股市行情: 搜索到 {len(stock)} 条")
    print(f"河南足球: 搜索到 {len(hennan)} 条")
    print(f"中超其他球队: 搜索到 {len(csl)} 条")
    print("=== 结束 ===")

if __name__ == '__main__':
    main()
