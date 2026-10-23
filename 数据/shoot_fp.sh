#!/usr/bin/env bash
# 批量渲染 5 张「玩家视角 · 5 个最佳充能点」
set -u
cd "$(dirname "$0")"
CH="/c/Program Files/Google/Chrome/Application/chrome.exe"
BASE="http://127.0.0.1:8899/viewer/fp.html"
for A in 001 002 003 004 005; do
  OUT="F:\\Codex\\Nikke\\Nikke_Skills\\地图充能计算\\数据\\render\\fp_${A}.png"
  timeout 120 "$CH" --headless=new --no-sandbox --use-gl=angle --use-angle=swiftshader \
    --hide-scrollbars --screenshot="$OUT" --window-size=1600,900 --virtual-time-budget=15000 \
    "$BASE?arena=${A}&w=1600&h=900" 2>&1 | grep -o "bytes written to file"
  echo "  fp_${A}.png"
done
