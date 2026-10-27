#!/bin/bash
# 批量出「充能点位标注」图：5 战场 × 5 阵位
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
OUT="F:/Codex/Nikke/Nikke_Skills/地图充能计算/数据/render"
for A in 001 002 003 004 005; do
  for S in 1 2 3 4 5; do
    F="$OUT/chg_${A}_${S}.png"
    timeout 70 "$CHROME" --headless=new --no-sandbox --use-gl=angle --use-angle=swiftshader \
      --hide-scrollbars --screenshot="$F" --window-size=1600,900 --virtual-time-budget=13000 \
      "http://127.0.0.1:8899/viewer/charge.html?arena=$A&slot=$S&cy=1.2&top=5&w=1600&h=900" \
      2>&1 | grep -c written
  done
done
echo "done"
ls -1 "$OUT"/chg_*.png | wc -l
