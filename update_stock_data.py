#!/usr/bin/env python3
"""
股市行情数据自动更新脚本
从东方财富 API 获取实时行情，更新 index.html 中的 mockStockIndices 数据
"""

import json
import re
import urllib.request
import sys
import os
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(SCRIPT_DIR, "index.html")

APIS = {
    "cn": {
        "url": "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f2,f3,f4,f12,f14&secids=1.000001,0.399001,0.399006,1.000300",
        "expected_total": 4,
        "names": ["上证指数", "深证成指", "创业板指", "沪深300"],
        "secids_order": ["000001", "399001", "399006", "000300"],
    },
    "us": {
        "url": "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f2,f3,f4,f12,f14&secids=100.SPX,100.DJIA,100.NDX",
        "expected_total": 3,
        "names": ["标普500", "道琼斯", "纳斯达克"],
        "secids_order": ["SPX", "DJIA", "NDX"],
    },
    "global": {
        "url": "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f2,f3,f4,f12,f14&secids=100.HSI,100.N225,100.FTSE,100.GDAXI,100.KS11,100.SENSEX",
        "expected_total": 6,
        "names": ["日经225", "恒生指数", "英国富时", "德国DAX", "韩国KOSPI", "印度SENSEX"],
        "secids_order": ["HSI", "N225", "FTSE", "GDAXI", "KS11", "SENSEX"],
    },
}

# 合理值范围（防止 API 返回错误数据）
VALUE_RANGES = {
    "cn":     [(2500, 6000), (8000, 25000), (2000, 8000), (3000, 7000)],
    "us":     [(4000, 10000), (30000, 60000), (15000, 30000)],
    "global": [(10000, 40000), (20000, 80000), (5000, 15000), (10000, 30000), (2000, 10000), (40000, 90000)],
}


def fetch_api(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def validate_and_parse_response(market, data):
    """验证 API 返回数据并解析为统一格式"""
    if not data or data.get("rc") != 0:
        print(f"  [{market}] API 返回错误: rc={data.get('rc') if data else 'N/A'}")
        return None

    diff = data.get("data", {}).get("diff", [])
    total = data.get("data", {}).get("total", 0)
    expected = APIS[market]["expected_total"]

    if total < expected:
        print(f"  [{market}] 数据不完整: total={total}, expected={expected}")
        return None

    # 按 secids_order 排序
    secids_order = APIS[market]["secids_order"]
    ordered = []
    for secid_key in secids_order:
        found = None
        for item in diff:
            f12 = str(item.get("f12", ""))
            if secid_key in f12 or f12.endswith(secid_key):
                found = item
                break
        if found:
            ordered.append(found)

    if len(ordered) < expected:
        print(f"  [{market}] 无法匹配全部 {expected} 条数据，只找到 {len(ordered)} 条")
        return None

    # 验证合理值
    ranges = VALUE_RANGES[market]
    result = []
    for i, item in enumerate(ordered):
        f2 = item.get("f2", 0)
        f3 = item.get("f3", 0)
        name = APIS[market]["names"][i]

        if i < len(ranges):
            lo, hi = ranges[i]
            if f2 < lo or f2 > hi:
                print(f"  [{market}] {name} 数值异常: {f2} (合理范围 {lo}-{hi})")
                return None

        value_str = f"{f2:,.2f}" if isinstance(f2, (int, float)) else str(f2)
        change_str = f"{f3:+.2f}%" if isinstance(f3, (int, float)) else str(f3)
        direction = "up" if f3 >= 0 else "down"

        result.append({
            "name": name,
            "value": value_str,
            "change": change_str,
            "direction": direction,
        })

    return result


def build_new_block(new_data):
    """生成新的 mockStockIndices JS 代码块"""
    lines = ["const mockStockIndices = {"]
    for market in ["us", "cn", "global"]:
        items = new_data[market]
        lines.append(f"  {market}: [")
        for item in items:
            lines.append(
                f'    {{ name:"{item["name"]}", value:"{item["value"]}", '
                f'change:"{item["change"]}", direction:"{item["direction"]}" }},'
            )
        lines.append("  ],")
    lines.append("};")
    return "\n".join(lines)


def update_html(new_data):
    """替换 index.html 中的 mockStockIndices 块"""
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 找到 const mockStockIndices = { 的位置
    start_marker = "const mockStockIndices = {"
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print("错误: 找不到 mockStockIndices 定义")
        return False

    # 找到对应的结束 };
    # 从 start_idx 开始找最后一个 }; （在合理范围内）
    # 找下一个 standalone "};" 或 "}\n" 后面跟着空行的位置
    rest = content[start_idx:]
    # 找 ";}" 或 "};\n" 模式
    # 简单方法：找 "};" 且后面是换行或空格然后换行
    end_pattern = re.compile(r'^\};', re.MULTILINE)
    # 实际上更简单：从 start_idx 开始，找 "};" 且前面是换行
    # 用 brace counting 更准确
    brace_count = 0
    in_string = False
    end_idx = -1
    for i in range(start_idx + len(start_marker), len(content)):
        ch = content[i]
        prev = content[i-1] if i > 0 else ''
        if ch == '"' and prev != '\\':
            in_string = not in_string
        if in_string:
            continue
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            if brace_count == 0:
                # 这是最外层对象的结束
                # 检查后面是否是 ;
                if i + 1 < len(content) and content[i+1] == ';':
                    end_idx = i + 1  # 指向 ;
                else:
                    end_idx = i
                break
            brace_count -= 1

    if end_idx == -1:
        print("错误: 找不到 mockStockIndices 的结束位置")
        return False

    new_block = build_new_block(new_data)
    new_content = content[:start_idx] + new_block + content[end_idx + 1:]

    beijing_now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    new_content = re.sub(
        r'(const stockDataUpdateTime = ")[^"]+(";)',
        r'\g<1>' + beijing_now + r'\g<2>',
        new_content,
        count=1,
    )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  已更新 index.html 中的 mockStockIndices")
    return True


def main():
    print("开始更新股市行情数据...")
    print(f"目标文件: {HTML_PATH}")
    print()

    new_data = {}

    for market in ["cn", "us", "global"]:
        print(f"正在获取 [{market}] 数据...")
        try:
            data = fetch_api(APIS[market]["url"])
            parsed = validate_and_parse_response(market, data)
            if parsed is None:
                print(f"  [{market}] 数据验证失败，跳过更新")
                print()
                print("因数据验证失败，本次更新中止。")
                sys.exit(1)
            new_data[market] = parsed
            print(f"  [{market}] 获取成功: {len(parsed)} 条")
            for item in parsed:
                print(f"    {item['name']}: {item['value']} ({item['change']})")
        except Exception as e:
            print(f"  [{market}] 获取失败: {e}")
            print()
            print("因 API 请求失败，本次更新中止。")
            sys.exit(1)
        print()

    print("正在写入 index.html...")
    ok = update_html(new_data)
    if ok:
        print()
        print("股市行情数据更新完成！")
    else:
        print()
        print("写入失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()
