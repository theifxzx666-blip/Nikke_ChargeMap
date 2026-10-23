# -*- coding: utf-8 -*-
"""生成 H36-35 充能点位标注汇总页"""
import os, json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(BASE, "数据", "导出")
SCAN = os.path.join(EX, "h36-35_scan.json")

ARENA_NOTE = {
    "001": "开场区，公路与残楼，中近距离连续可破坏体最多",
    "002": "废车场，右侧斜坡密布集装箱与控制箱",
    "003": "积水洼地，飞机残骸与坦克形成长穿透链",
    "004": "断桥区，桥墩柱列是天然的多段穿透通道",
    "005": "密林深处，枯树与岩体交替，理想/保底几乎打平",
}

def build():
    d = json.load(open(SCAN, encoding="utf-8"))
    secs = []
    for a in ["001", "002", "003", "004", "005"]:
        t = d[a]["top"][0]
        rows = []
        for i, tk in enumerate(d[a]["top"]):
            star = " ★" if i == 0 else ""
            rows.append(
                "<tr%s><td class='num'>%d%s</td><td>x%+.1f</td><td>%+.1f°</td>"
                "<td class='hl'>%d</td><td>%d</td><td>%d</td><td>%d → %d</td></tr>"
                % (" class='best'" if i == 0 else "", i + 1, star,
                   tk["px"], tk["yaw"], tk["nHit"], tk["e0"], tk["e1"],
                   tk["shots0"], tk["shots1"]))
        secs.append("""
  <section>
    <div class="head">
      <h2>战场 %s<span class="bar"></span></h2>
      <p class="note">%s</p>
    </div>
    <figure><img src="数据/render/h36_%s_top1.png" alt="H36-35 战场 %s"></figure>
    <div class="tbl">
      <table>
        <thead><tr><th>点位</th><th>站位 x</th><th>朝向</th><th>穿透段数</th>
        <th>保底能量</th><th>理想能量</th><th>所需发数</th></tr></thead>
        <tbody>%s</tbody>
      </table>
    </div>
  </section>""" % (a, ARENA_NOTE.get(a, ""), a, a, "".join(rows)))

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>H36-35 小红帽穿透充能点位</title>
<style>
:root{--bg:#070b0a;--panel:#0d1413;--line:#1d2a27;--ink:#e8f2ee;--dim:#7d9691;--cy:#6cd8ff;--soft:#ffd660;--med:#ff983e;--hard:#ff6060}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#12201d 0%,#070b0a 60%);color:var(--ink);
font-family:"Microsoft YaHei UI","Microsoft YaHei",system-ui,-apple-system,sans-serif;line-height:1.65}
.wrap{max-width:1180px;margin:0 auto;padding:56px 26px 90px}
header{border-bottom:1px solid var(--line);padding-bottom:26px;margin-bottom:44px}
h1{font-size:34px;margin:0 0 10px;letter-spacing:.5px}
h1 em{font-style:normal;color:var(--cy)}
.sub{color:var(--dim);font-size:15px;margin:0}
.meta{display:flex;gap:26px;flex-wrap:wrap;margin-top:20px;font-size:13px;color:var(--dim)}
.meta b{color:var(--ink);font-weight:600}
section{margin:0 0 62px}
.head{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:16px}
h2{font-size:21px;margin:0;font-weight:600;white-space:nowrap}
.head .bar{display:inline-block;width:70px;height:1px;background:var(--line);margin-left:14px;vertical-align:middle}
.note{margin:0;color:var(--dim);font-size:13.5px}
figure{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#000;
box-shadow:0 18px 50px -20px rgba(0,0,0,.9)}
figure img{display:block;width:100%;height:auto}
.tbl{margin-top:16px;overflow-x:auto;border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:640px}
th,td{padding:11px 14px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{background:#0a1211;color:var(--dim);font-weight:500;font-size:12.5px;letter-spacing:.4px}
tbody tr:last-child td{border-bottom:none}
tbody tr.best{background:rgba(108,216,255,.055)}
tbody tr.best td{color:#dff4ff}
.num{font-variant-numeric:tabular-nums}
.hl{color:var(--cy);font-weight:600}
td.num,td.hl{font-variant-numeric:tabular-nums}
footer{border-top:1px solid var(--line);padding-top:26px;color:var(--dim);font-size:13px}
footer h3{font-size:14px;color:var(--ink);margin:0 0 12px;font-weight:600}
footer ul{margin:0;padding-left:20px}
footer li{margin:6px 0}
code{background:#101a18;border:1px solid var(--line);border-radius:4px;padding:1px 6px;font-size:12.5px;color:#a9d9cc}
</style></head><body><div class="wrap">
<header>
  <h1>H36-35 <em>小红帽穿透充能点位</em></h1>
  <p class="sub">沼泽丛林 · 用拆包原生贴片按战斗视角重建场景，标出可充能点位与速率</p>
  <div class="meta">
    <span>关卡 <b>H36-35</b>（stage 7035035）</span>
    <span>章节 <b>swamplandjungle / hard</b></span>
    <span>战场 <b>5 张</b></span>
    <span>每段 <b>280</b> 能量</span>
    <span>爆裂条 <b>10000</b></span>
  </div>
</header>
__SECTIONS__
<footer>
  <h3>读图与口径</h3>
  <ul>
    <li><b>青色圆点</b>是站位，<b>青色扇形</b>是角色朝向，<b>青色光带</b>是穿透弹道。</li>
    <li><b>彩色角括号</b>是这条弹道实际打穿的可破坏体，按硬度分色：<span style="color:var(--hard)">硬质</span> / <span style="color:var(--med)">中质</span> / <span style="color:var(--soft)">软质</span>。编号按距离由近到远。</li>
    <li><b>保底能量</b>＝只算地形可破坏体；<b>理想能量</b>＝再加上横向 0.55m 内的敌点。两者之差就是"有没有怪"带来的浮动。</li>
    <li><b>所需发数</b>＝<code>ceil(10000 / 每发能量)</code>，每发 = 段数 × 280。</li>
    <li>穿透判定按 hitbox 计，与伤害无关：一枪贯穿轨迹上所有判定体。</li>
    <li>每段 280 是 wiki／社区口径。若与实测有偏差，可用<b>爆裂条涨幅 ÷ 2.80%</b> 反推校准。</li>
  </ul>
</footer>
</div></body></html>"""
    html = html.replace("__SECTIONS__", "".join(secs))

    outp = os.path.join(BASE, "H36-35充能点位标注.html")
    open(outp, "w", encoding="utf-8").write(html)
    print("->", outp, len(html), "bytes")
    return outp

if __name__ == "__main__":
    build()
