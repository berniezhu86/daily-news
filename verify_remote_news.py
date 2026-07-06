#!/usr/bin/env python3
"""
verify_remote_news.py — 推送后验证远程 authoritative_news.json 是否已更新

用法:
  python3 verify_remote_news.py
  
返回值:
  0 = 远程数据已更新（与本地一致或更新）
  1 = 远程数据未更新（旧版本）
  2 = 远程无法访问
"""
import json
import sys
import time
import urllib.request

LOCAL_FILE = "/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/authoritative_news.json"
REMOTE_URL = "https://berniezhu86.github.io/daily-news/authoritative_news.json"
MAX_RETRIES = 3
RETRY_INTERVAL = 30  # 秒


def fetch_remote(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def main():
    # 读取本地
    try:
        with open(LOCAL_FILE, "r") as f:
            local = json.load(f)
    except Exception as e:
        print(f"❌ 读取本地文件失败: {e}")
        return 1

    local_updated = local.get("updated", "")
    local_count = local.get("count", 0)
    print(f"本地数据: updated={local_updated}, count={local_count}")

    # 轮询远程
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"第 {attempt} 次检查远程...")
        remote = fetch_remote(REMOTE_URL)

        if "error" in remote:
            print(f"  ⚠️ 远程访问失败: {remote['error']}")
            if attempt < MAX_RETRIES:
                print(f"  等待 {RETRY_INTERVAL} 秒后重试...")
                time.sleep(RETRY_INTERVAL)
            continue

        remote_updated = remote.get("updated", "")
        remote_count = remote.get("count", 0)
        print(f"  远程数据: updated={remote_updated}, count={remote_count}")

        if remote_updated >= local_updated:
            print(f"✅ 远程已更新（{remote_updated}），与本地一致")
            return 0
        else:
            print(f"  ⚠️ 远程数据比本地旧")
            if attempt < MAX_RETRIES:
                print(f"  等待 {RETRY_INTERVAL} 秒后重试...")
                time.sleep(RETRY_INTERVAL)

    print(f"❌ 远程数据未更新（最���尝试后）")
    print(f"   本地: {local_updated}")
    print(f"   远程: {remote_updated}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
