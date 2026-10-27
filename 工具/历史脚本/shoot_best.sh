#!/usr/bin/env bash
# 批量渲染 25 张「最佳充能点」战术视图（斜视角，无 HUD）
set -u
cd "$(dirname "$0")"
CH="/c/Program Files/Google/Chrome/Application/chrome.exe"
BASE="http://127.0.0.1:8899/viewer/best.html"
for A in 001 002 003 004 005; do
  for S in 1 2 3 4 5; do
    OUT="F:\\Codex\\Nikke\\Nikke_Skills\\地图充能计算\\数据\\render\\bt_${A}_${S}.png"
    timeout 60 "$CH" --headless=new --no-sandbox --use-gl=angle --use-angle=swiftshader \
      --hide-scrollbars --screenshot="$OUT" --window-size=1600,900 --virtual-time-budget=13000 \
      "$BASE?arena=${A}&slot=${S}&w=1600&h=900&bright=1.25&orbit=1&hud=0&os=22&oh=10&ob=-14" \
      > /dev/null 2>&1
    echo "  bt_${A}_${S}.png"
  done
done
