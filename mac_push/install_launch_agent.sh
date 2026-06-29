#!/bin/sh
set -eu
PROJECT_DIR="/Users/bainian/Workbuddy/2026-06-25-10-20-28/zhenbao-daily-news"
PLIST="$HOME/Library/LaunchAgents/com.zhenbao.news.push.plist"
PYTHON="/usr/bin/python3"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.zhenbao.news.push</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$PROJECT_DIR/mac_push/mac_notify_watcher.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$PROJECT_DIR/mac_push/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$PROJECT_DIR/mac_push/launchd.err.log</string>
</dict>
</plist>
PLIST
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed and started: $PLIST"
