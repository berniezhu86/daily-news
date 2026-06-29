# Mac 本地新闻推送

这套脚本用于 Mac App 壳的本地通知底座：

- `generate_push_news.py`：从 `news_pool.json` 生成 `latest_push_news.json`
- `mac_notify_watcher.py`：轮询 `latest_push_news.json`，对未推过的高优先级新闻弹 macOS 通知
- `push_config.json`：通知开关、类型和频率限制
- `seen_push_ids.json`：已推送 ID，避免重复弹
- `install_launch_agent.sh`：安装为 macOS 后台 LaunchAgent

## 手动测试

```sh
python3 mac_push/generate_push_news.py
python3 mac_push/mac_notify_watcher.py --dry-run
python3 mac_push/mac_notify_watcher.py --once
```

## 后台运行

```sh
sh mac_push/install_launch_agent.sh
```

停止后台运行：

```sh
sh mac_push/uninstall_launch_agent.sh
```

后续如果做 Electron/Tauri 壳，可以保留 `latest_push_news.json` 和 `seen_push_ids.json` 的数据协议，把 `mac_notify_watcher.py` 替换为 App 内的 native notification 调用。

## 如果通知没有显示

本实现优先使用 `MacNotifier.app` 原生通知器。首次使用时，macOS 可能需要在系统设置中允许通知：

`系统设置 -> 通知 -> 臻宝每日快讯通知`

如果仍没有弹出，可先手动运行：

```sh
/Users/bainian/Workbuddy/2026-06-25-10-20-28/zhenbao-daily-news/mac_push/MacNotifier.app/Contents/MacOS/MacNotifier --title "臻宝每日快讯测试" --subtitle "原生通知器" --body "通知通道测试" --id "manual-test"
```
