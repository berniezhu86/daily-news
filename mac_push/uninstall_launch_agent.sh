#!/bin/sh
set -eu
PLIST="$HOME/Library/LaunchAgents/com.zhenbao.news.push.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Uninstalled com.zhenbao.news.push"
