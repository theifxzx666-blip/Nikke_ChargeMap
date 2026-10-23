#!/bin/bash
# 批量渲染 5 张战场标准视图
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
BASE="http://127.0.0.1:8899/viewer/index.html"
OUT="F:/Codex/Nikke/Nikke_Skills/地图充能计算/数据/render"
cd "$OUT" || exit 1
for i in 001 002 003 004 005; do
  timeout 90 "$CHROME" --headless=new --no-sandbox --use-gl=angle --use-angle=swiftshader \
    --hide-scrollbars --screenshot="$OUT/v4_$i.png" --window-size=1600,900 \
    --virtual-time-budget=15000 \
    "$BASE?arena=$i&interactive=0&bright=1.05&hud=0" 2>&1 | grep -o "written to file.*" 
done
ls -la v4_00*.png
