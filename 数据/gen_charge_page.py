# -*- coding: utf-8 -*-
"""生成充能点位标注汇总页。"""
import json, os, html

R = os.path.join("导出")
OUT = os.path.join("..", "H36-35充能点位标注.html")

SLOT_NAME = {"cover_1": "阵位 1", "cover_2": "阵位 2", "cover_3": "阵位 3",
             "cover_4": "阵位 4", "cover_5": "阵位 5"}
SLOTS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]
ARENAS = ["001", "002", "003", "004", "005"]

data = {a: json.load(open(os.path.join(R, "charge_%s.json" % a), encoding="utf-8"))
        for a in ARENAS}


def row_html(i, t):
    d = "<br>".join("· %s <span class=hp>%d</span>" % (html.escape(x["name"].replace("sbg_swamplandjungle_", "")), x["hp"])
                    for x in t["detail"][:8])
    more = "" if len(t["detail"]) <= 8 else "<br><span class=dim>… 另 %d 件</span>" % (len(t["detail"]) - 8)
    return ("<tr><td class=no>#%d</td><td class=big>%d 段</td><td class=pct>%.1f%%</td>"
            "<td class=big>%d 发</td><td>%+.1f° / %+.1f°</td><td>%.0f m</td>"
            "<td class=det>%s%s</td></tr>"
            % (i + 1, t["n"], t["pct"], t["shots"], t["yaw"], t["pitch"], t["first"], d, more))


def slot_block(a, sk):
    s = data[a]["slots"][sk]
    tops = s["top"]
    best = tops[0] if tops else None
    rows = "".join(row_html(i, t) for i, t in enumerate(tops))
    char = s["char"]; cam = s["cam"]
    return f"""
<article class=card>
  <header>
    <div class=ttl>{SLOT_NAME[sk]}</div>
    <div class=meta>角色 x={char[0]:.1f} z={char[2]:.1f} · 相机 x={cam[0]:.1f} z={cam[2]:.1f}</div>
  </header>
  <a class=shot href="数据/render/chg_{a}_{sk[-1]}.png" target=_blank>
    <img src="数据/render/chg_{a}_{sk[-1]}.png" loading=lazy alt="{a} {sk}">
  </a>
  <table>
    <thead><tr><th>点位</th><th>穿透</th><th>单发</th><th>充满</th><th>偏航/俯仰</th><th>首击</th><th>命中可破坏物</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div class=concl>最优：<b>{('瞄 %+.1f° 偏航 / %+.1f° 俯仰，一枪穿 %d 段 = %.1f%%，%d 发打满' % (best['yaw'], best['pitch'], best['n'], best['pct'], best['shots'])) if best else '无命中'}</b></div>
</article>"""


def arena_block(a):
    cards = "".join(slot_block(a, sk) for sk in SLOTS)
    # 该战场 5 阵位横向对比
    cmp_rows = []
    for sk in SLOTS:
        t = data[a]["slots"][sk]["top"][0]
        cmp_rows.append("<tr><td>%s</td><td class=big>%d</td><td class=pct>%.1f%%</td>"
                        "<td class=big>%d</td><td>%+.1f° / %+.1f°</td></tr>"
                        % (SLOT_NAME[sk], t["n"], t["pct"], t["shots"], t["yaw"], t["pitch"]))
    return f"""
<section class=arena>
  <h2>战场 {a} <span class=sub>sbg_swamplandjungle_{a}</span></h2>
  <table class=cmp>
    <thead><tr><th>阵位</th><th>最多穿透</th><th>单发能量</th><th>充满发数</th><th>偏航 / 俯仰</th></tr></thead>
    <tbody>{''.join(cmp_rows)}</tbody>
  </table>
  <div class=grid>{cards}</div>
</section>"""


body = "".join(arena_block(a) for a in ARENAS)

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>H36-35 充能点位标注 · 按游戏内配置</title>
<style>
:root{--bg:#f6f8f7;--card:#fff;--ink:#17241f;--dim:#6b7f76;--line:#dfe8e3;
      --acc:#0b7a5a;--hot:#d9482f;--gold:#b8860b}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
     padding:36px 28px 80px}
.wrap{max-width:1280px;margin:0 auto}
h1{font-size:27px;letter-spacing:-.3px;margin-bottom:6px}
.lead{color:var(--dim);font-size:14px;margin-bottom:22px}
h2{font-size:19px;margin:38px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--line)}
h2 .sub{font-size:12.5px;color:var(--dim);font-weight:400;font-family:Consolas,monospace}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;
      box-shadow:0 1px 2px rgba(20,40,32,.05)}
.card header{padding:11px 14px 9px;border-bottom:1px solid var(--line);display:flex;
      justify-content:space-between;align-items:baseline;gap:10px}
.card .ttl{font-weight:700;font-size:14.5px;color:var(--acc)}
.card .meta{font-size:11px;color:var(--dim);font-family:Consolas,monospace}
.shot{display:block;line-height:0;background:#111}
.shot img{width:100%;height:auto;display:block}
.card table{width:100%;border-collapse:collapse;font-size:11.5px}
.card th{background:#eef4f1;color:var(--dim);font-weight:600;text-align:left;padding:6px 8px;
      border-bottom:1px solid var(--line);white-space:nowrap}
.card td{padding:6px 8px;border-bottom:1px solid #f0f4f2;vertical-align:top}
.card tr:last-child td{border-bottom:none}
.no{color:var(--dim);font-weight:700;white-space:nowrap}
.big{font-weight:700;color:var(--acc);white-space:nowrap}
.pct{font-weight:700;color:var(--hot);white-space:nowrap}
.det{color:#3d5148;font-size:10.5px;line-height:1.5;max-width:330px}
.hp{color:var(--dim);font-family:Consolas,monospace}
.dim{color:var(--dim)}
.concl{padding:9px 14px;background:#f1f8f5;border-top:1px solid var(--line);font-size:12.5px;color:#2c4a3e}
.concl b{color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(560px,1fr));gap:20px}
table.cmp{width:100%;border-collapse:collapse;font-size:13px;background:#fff;
      border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:20px}
table.cmp th{background:#eef4f1;color:var(--dim);font-weight:600;text-align:left;padding:9px 12px;
      border-bottom:1px solid var(--line)}
table.cmp td{padding:9px 12px;border-bottom:1px solid #f0f4f2}
table.cmp tr:last-child td{border-bottom:none}
.note{background:#fff;border:1px solid var(--line);border-left:3px solid var(--gold);
      border-radius:8px;padding:14px 16px;font-size:13px;margin:14px 0}
.note b{color:var(--gold)}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin:14px 0 4px}
.kv div{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:12.5px}
.kv span{display:block;color:var(--dim);font-size:11px;margin-bottom:2px}
code{font-family:Consolas,monospace;background:#eef4f1;padding:1px 5px;border-radius:4px;font-size:12px}
footer{margin-top:44px;color:var(--dim);font-size:12px;border-top:1px solid var(--line);padding-top:16px}
</style></head><body><div class="wrap">

<h1>H36-35 充能点位标注</h1>
<div class="lead">按游戏内装配配置计算 · 5 个阵位各自一套视野 · 小红帽 SR 穿透口径</div>

<div class="kv">
  <div><span>爆裂条上限</span>burst_energy_max = 1,000,000（显示口径 10,000）</div>
  <div><span>每发命中基础</span>ulti_gauge_shot_hit = 4</div>
  <div><span>小红帽单发</span>2.80% → 280 能量（内部 28,000）</div>
  <div><span>相机</span>FOV 60 · near 0.1 · far 300</div>
  <div><span>可破坏物 HP</span>soft 100 / medium 500 / hard 1000</div>
  <div><span>阵位来源</span>cover_1~5 各自的 camera_position</div>
</div>

<div class="note">
<b>5 个阵位为什么视野不同</b>：拆包显示 <code>cover_1~5</code> 是 5 个独立阵位根，
每个根下各挂一个 <code>character_position</code> 与一个 <code>camera_position</code>。
5 个阵位的朝向完全相同（rotation 全是 identity），差别在<b>横向位置</b>——
相机随角色横移 3.9~13m，因此同一个战场上，每个阵位能穿到的可破坏物组合都不一样。
</div>

""" + body + """

<footer>
口径与局限：穿透段数按「射线命中的不同可破坏物数量」计，一件物算一段；
未计入 static_object 的遮挡（游戏内子弹不与静态模型判定）；未计入敌人本体（波次由服务端下发，bundle 内无）；
pitch 为射线相对水平面的仰角，正值向上。数据表由 <code>数据/scan_charge.py</code> 生成。
</footer>
</div></body></html>
"""

open(OUT, "w", encoding="utf-8").write(HTML)
print("->", OUT, len(HTML), "chars")
