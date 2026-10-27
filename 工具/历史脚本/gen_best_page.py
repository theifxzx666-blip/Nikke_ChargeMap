# -*- coding: utf-8 -*-
"""生成「最佳充能点」汇总页。数据源：导出/best_00N.json + render/bt_*.png + render/best_*_heat.png"""
import json, os, math, html

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(ROOT), "H36-35最佳充能点.html")
ARENAS = ["001", "002", "003", "004", "005"]
KEYS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]

rows = []
meta = None
for a in ARENAS:
    d = json.load(open(os.path.join(ROOT, "导出", "best_%s.json" % a), encoding="utf-8"))
    meta = meta or d
    for k in KEYS:
        r = d["slots"][k]
        b = r["best"]
        rec = r.get("rec") or {}
        rows.append(dict(arena=a, slot=int(k.split("_")[1]), key=k,
                         n=r["n_max"], r1=r["n_r1"], r2=r["n_r2"],
                         pct=b["pct"], shots=b["shots"], yaw=b["yaw"], pitch=b["pitch"],
                         wy=b["win_y"], wp=b["win_p"], grid=b["grid_cells"],
                         first=b["first"], last=b["last"], detail=b["detail"],
                         rn=rec.get("n"), ryaw=rec.get("yaw"), rpitch=rec.get("pitch")))

rows.sort(key=lambda r: (-r["n"], -r["r1"], -(r["wy"] * r["wp"]), -r["grid"]))
for i, r in enumerate(rows, 1):
    r["rank"] = i

best = rows[0]


def f1(x):
    return "%.1f" % x


def badge(g):
    return {"soft": "S", "medium": "M", "hard": "H"}.get(g, "?")


def short(n):
    return n.replace("sbg_swamplandjungle_", "")


# ---------------- 卡片 ----------------
cards = []
for r in rows:
    cls = " best" if r is best else ""
    det = "".join(
        '<li><i class="t %s">%s</i><span>%s</span><b>%sm</b></li>' % (
            x["grp"], badge(x["grp"]), html.escape(short(x["name"])), f1(x["d"]))
        for x in r["detail"])
    cards.append(f'''
<div class="card{cls}">
  <div class="ch">
    <span class="rk">#{r["rank"]}</span>
    <span class="tt">战场 {r["arena"]} · 阵位 {r["slot"]}</span>
    <span class="nv">{r["n"]}<i>段</i></span>
  </div>
  <div class="imgs">
    <a href="数据/render/bt_{r["arena"]}_{r["slot"]}.png" target="_blank">
      <img src="数据/render/bt_{r["arena"]}_{r["slot"]}.png" loading="lazy" alt=""></a>
    <a class="hm" href="数据/render/best_{r["arena"]}_{r["key"]}_heat.png" target="_blank">
      <img src="数据/render/zoom_{r["arena"]}_{r["key"]}.png" loading="lazy" alt=""></a>
  </div>
  <div class="nums">
    <div><b>{f1(r["pct"])}%</b><span>单发</span></div>
    <div><b>{r["shots"]}</b><span>充满(发)</span></div>
    <div><b>{r["yaw"]:+.2f}°</b><span>yaw</span></div>
    <div><b>+{r["pitch"]:.2f}°</b><span>pitch</span></div>
    <div><b>{r["wy"]:.2f}×{r["wp"]:.2f}°</b><span>峰值窗口</span></div>
    <div><b>{r["r1"]} / {r["r2"]}</b><span>1°稳 / 2°稳</span></div>
  </div>
  <ol class="det">{det}</ol>
</div>''')

# ---------------- 表格 ----------------
trs = []
for r in rows:
    cls = ' class="hi"' if r is best else (' class="top"' if r["n"] >= best["n"] else "")
    trs.append(
        f'<tr{cls}><td class="rk">{r["rank"]}</td><td>{r["arena"]}</td><td>cover_{r["slot"]}</td>'
        f'<td class="nv">{r["n"]}</td><td>{f1(r["pct"])}%</td><td>{r["shots"]}</td>'
        f'<td class="mono">{r["yaw"]:+.2f}° / +{r["pitch"]:.2f}°</td>'
        f'<td class="mono">{r["wy"]:.2f}×{r["wp"]:.2f}°</td>'
        f'<td>{r["grid"]}</td><td>{r["r1"]}</td><td>{r["r2"]}</td>'
        f'<td class="mono">{f1(r["first"])}~{f1(r["last"])}m</td></tr>')

# 各战场最佳
per_arena = []
for a in ARENAS:
    sub = [r for r in rows if r["arena"] == a]
    b = max(sub, key=lambda r: (r["n"], r["r1"]))
    per_arena.append(f'<tr><td>{a}</td><td>cover_{b["slot"]}</td><td class="nv">{b["n"]}</td>'
                     f'<td>{f1(b["pct"])}%</td><td>{b["shots"]}</td>'
                     f'<td class="mono">{b["yaw"]:+.2f}° / +{b["pitch"]:.2f}°</td>'
                     f'<td>{b["r1"]}</td></tr>')

bestdet = "".join(
    '<tr><td><i class="t %s">%s</i>%s</td><td class="mono">%sm</td></tr>' % (
        x["grp"], badge(x["grp"]), html.escape(short(x["name"])), f1(x["d"]))
    for x in best["detail"])

HTML = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>H36-35 最佳充能点 · 全角度覆盖扫描</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#08110e;--pn:#0d1b16;--bd:#1d3a30;--fg:#d8e9df;--mu:#7b9e8e;--gd:#ffcf6b;--gn:#63e0ac}}
body{{background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
  padding:44px 40px 80px;max-width:1560px;margin:0 auto}}
h1{{font-size:29px;font-weight:700;letter-spacing:.5px;margin-bottom:8px}}
h1 em{{font-style:normal;color:var(--gd)}}
.sub{{color:var(--mu);font-size:13.5px;margin-bottom:30px;line-height:1.85}}
h2{{font-size:19px;font-weight:600;margin:44px 0 14px;padding-left:11px;border-left:3px solid var(--gd)}}
h2 span{{color:var(--mu);font-size:13px;font-weight:400;margin-left:10px}}
.note{{color:var(--mu);font-size:13px;margin-bottom:14px}}
b.gd{{color:var(--gd)}}
/* hero */
.hero{{display:grid;grid-template-columns:1.55fr 1fr;gap:18px;align-items:start}}
.hero .box{{background:var(--pn);border:1px solid var(--bd);border-radius:14px;overflow:hidden}}
.hero img{{width:100%;display:block}}
.hero .cap{{padding:10px 14px;color:var(--mu);font-size:12px;border-top:1px solid #14261f}}
.kpi{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--bd);border-radius:14px;overflow:hidden;margin-bottom:14px}}
.kpi div{{background:var(--pn);padding:16px 18px}}
.kpi span{{display:block;color:var(--mu);font-size:11.5px;letter-spacing:.4px;margin-bottom:2px}}
.kpi b{{font-size:26px;font-weight:700;color:var(--gd);line-height:1.15}}
.kpi b i{{font-style:normal;font-size:13px;color:#c8a95f;margin-left:2px}}
.kpi b.sm{{font-size:20px;color:var(--fg)}}
table.det2{{width:100%;border-collapse:collapse;font-size:12.5px}}
table.det2 td{{padding:5px 10px;border-bottom:1px solid #12231d}}
table.det2 td.mono{{text-align:right;color:var(--gd);font-variant-numeric:tabular-nums}}
/* tables */
table.main{{width:100%;border-collapse:collapse;font-size:13px;background:var(--pn);
  border:1px solid var(--bd);border-radius:12px;overflow:hidden}}
table.main th{{background:#0a1611;color:var(--mu);font-weight:500;font-size:11.5px;
  text-align:left;padding:10px 9px;border-bottom:1px solid var(--bd);white-space:nowrap}}
table.main td{{padding:8px 9px;border-bottom:1px solid #11211b}}
table.main tr:last-child td{{border-bottom:none}}
table.main tr.hi td{{background:rgba(255,207,107,.09);color:#fff3d4}}
table.main tr.hi td.nv{{color:var(--gd)}}
table.main tr.top td{{color:#eafaf1}}
table.main td.nv{{color:var(--gd);font-weight:700}}
table.main td.rk{{color:var(--mu);width:44px}}
table.main td.mono{{font-variant-numeric:tabular-nums;color:#a9c9ba;white-space:nowrap}}
/* cards */
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
.card{{background:var(--pn);border:1px solid var(--bd);border-radius:13px;overflow:hidden;
  display:flex;flex-direction:column}}
.card.best{{border-color:var(--gd);box-shadow:0 0 0 1px rgba(255,207,107,.35),0 10px 34px -18px #ffcf6b}}
.ch{{display:flex;align-items:center;gap:9px;padding:10px 12px;border-bottom:1px solid #14261f}}
.ch .rk{{color:var(--mu);font-size:11.5px;font-variant-numeric:tabular-nums}}
.ch .tt{{font-size:12.5px;color:#cfe3d8}}
.ch .nv{{margin-left:auto;color:var(--gd);font-weight:700;font-size:17px}}
.ch .nv i{{font-style:normal;font-size:11px;color:#c8a95f;margin-left:1px}}
.imgs{{position:relative;background:#050b09}}
.imgs img{{width:100%;display:block}}
.imgs a.hm{{display:block;border-top:1px solid #14261f}}
.nums{{display:grid;grid-template-columns:repeat(3,1fr);font-size:11px;background:#0a1611;
  border-top:1px solid #14261f;border-bottom:1px solid #14261f}}
.nums div{{padding:7px 10px;border-right:1px solid #14261f}}
.nums div:nth-child(3n){{border-right:none}}
.nums b{{display:block;color:#eafaf1;font-size:13px;font-variant-numeric:tabular-nums}}
.nums span{{color:var(--mu);font-size:10px}}
ol.det{{list-style:none;padding:8px 12px 11px;font-size:11.5px;color:#a9c9ba;flex:1}}
ol.det li{{display:flex;align-items:center;gap:6px;padding:1.5px 0;line-height:1.5}}
ol.det li span{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
ol.det li b{{color:var(--gd);font-weight:600;font-variant-numeric:tabular-nums}}
i.t{{display:inline-block;width:14px;height:14px;line-height:14px;text-align:center;
  border-radius:4px;font-size:9px;font-style:normal;font-weight:700;flex:none}}
i.t.soft{{background:#1d4033;color:#8ce0b6}} i.t.medium{{background:#3d3620;color:#e8c96a}}
i.t.hard{{background:#42231f;color:#ff9d8a}}
/* method */
.mth{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.mth .p{{background:var(--pn);border:1px solid var(--bd);border-radius:12px;padding:16px 18px;font-size:13px;color:#b6cfc2}}
.mth .p h3{{font-size:13.5px;color:var(--gd);font-weight:600;margin-bottom:8px}}
.mth .p code{{background:#0a1611;padding:1px 5px;border-radius:4px;color:#8ce0b6;font-size:12px}}
.mth .p ul{{margin:8px 0 0 18px}}
.mth .p li{{margin:3px 0}}
footer{{margin-top:46px;color:#54786a;font-size:12px;border-top:1px solid #12231d;padding-top:14px}}
</style></head><body>

<h1>H36-35 最佳充能点 <em>全角度覆盖扫描</em></h1>
<div class="sub">
不再采样、不再截断：把每个可充能物体反投影到 (yaw, pitch) 角度域，按 <b class="gd">0.25°</b> 栅格做
点在三角形内判定，逐格统计一颗子弹能穿透的<b class="gd">不同可破坏物数量</b>。
共 <b class="gd">5 个战场 × 5 个阵位 × 33,573 个瞄准方向</b>，无候选上限、无角距间隔约束。<br>
相机 FOV 60° / near 0.1 / far 300 取自 <code>spotcameracontrol</code>；阵位取自 <code>cover_1~5</code> 的
<code>character_position</code>；充能取小红帽 SR 攻击充能 2.80% × 10000 = 280 能量/发。
</div>

<div class="hero">
  <div class="box">
    <a href="数据/render/bt_{best["arena"]}_{best["slot"]}.png" target="_blank">
      <img src="数据/render/bt_{best["arena"]}_{best["slot"]}.png" alt=""></a>
    <div class="cap">战术斜视角 · 金线为射线，圆环为命中点，编号对应下表距离（同距离的命中竖排标注）</div>
  </div>
  <div>
    <div class="kpi">
      <div><span>穿透段数（全场最高）</span><b>{best["n"]}<i>段</i></b></div>
      <div><span>单发充能</span><b>{f1(best["pct"])}<i>%</i></b></div>
      <div><span>充满爆裂条</span><b>{best["shots"]}<i>发</i></b></div>
      <div><span>峰值角度窗口</span><b class="sm">{best["wy"]:.2f}° × {best["wp"]:.2f}°</b></div>
      <div><span>战场 / 阵位</span><b class="sm">{best["arena"]} · cover_{best["slot"]}</b></div>
      <div><span>瞄准 yaw / pitch</span><b class="sm">{best["yaw"]:+.2f}° / +{best["pitch"]:.2f}°</b></div>
    </div>
    <div class="box">
      <a href="数据/render/best_{best["arena"]}_{best["key"]}_heat.png" target="_blank">
        <img src="数据/render/zoom_{best["arena"]}_{best["key"]}.png" alt=""></a>
      <div class="cap">瞄准空间局部放大（峰值 ±13°）：横轴 yaw、纵轴 pitch，颜色 = 穿透段数；白十字为峰值角度，点开看完整 ±45° 图</div>
    </div>
  </div>
</div>

<h2>最优点穿透的 8 件物体<span>按距离排序，全部为拆包 hitbox 分组 soft/medium/hard</span></h2>
<table class="det2">{bestdet}</table>

<h2>全部 25 组排名<span>按「穿透段数 → 1° 窗口稳健值 → 窗口面积」排序</span></h2>
<div class="note">
「1°稳」= 在最优点 ±0.5° 范围内都能保住的最少段数，代表<b class="gd">能不能瞄准</b>；
「峰值窗口」= 仍然保持最高段数的角度区域大小，小于 0.3° 的点实战几乎打不出来。
</div>
<table class="main">
<thead><tr><th>#</th><th>战场</th><th>阵位</th><th>穿透</th><th>单发</th><th>充满</th>
<th>瞄准 yaw / pitch</th><th>峰值窗口</th><th>峰值格数</th><th>1°稳</th><th>2°稳</th><th>命中距离</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table>

<h2>每个战场的最佳阵位</h2>
<table class="main">
<thead><tr><th>战场</th><th>最佳阵位</th><th>穿透</th><th>单发</th><th>充满</th><th>瞄准</th><th>1°稳</th></tr></thead>
<tbody>{"".join(per_arena)}</tbody></table>

<h2>逐组明细<span>上：战术斜视角 · 下：该阵位瞄准空间（峰值附近 ±13° 放大，点开看完整 ±45°）</span></h2>
<div class="grid">{"".join(cards)}</div>

<h2>方法与口径</h2>
<div class="mth">
  <div class="p"><h3>为什么改成覆盖而不是采样</h3>
  旧脚本是从 1° 网格里挑射线、只留 top-6、还强制候选之间至少差 5°/2.5°。
  这套约束是为了「标注好看」，代价是会漏掉真实峰值，也无法回答某个点的角度容差。
  现在把每个三角形的三个顶点反投影成 (yaw, pitch)，直接在角度域做点在三角形内判定，
  得到<b class="gd">整张穿透段数图</b>，峰值由数据自己给出。
  </div>
  <div class="p"><h3>为什么还要算「稳健值」</h3>
  0.25° 的窄缝峰值理论存在，但 40m 外 0.25° 只有 17cm，手指根本稳定不住。
  所以用 <code>k×k 邻域最小值</code> 求出「某角度 ±0.5° 内都能保住的段数」，
  把理论峰值和能打出来的值分开报。
  </div>
  <div class="p"><h3>充能口径</h3>
  <ul>
    <li>爆裂条 <code>burst_energy_max = 1,000,000</code>，显示口径 ÷100 = <b class="gd">10000</b></li>
    <li>小红帽 SR 攻击充能 2.80% → <b class="gd">280 能量/发</b></li>
    <li>穿透 N 件 → 单发 N × 280，充满发数 = <code>ceil(10000 / (N×280))</code></li>
  </ul>
  </div>
  <div class="p"><h3>计入与排除</h3>
  <ul>
    <li>✅ 计入：<code>soft</code>(100HP) / <code>medium</code>(500) / <code>hard</code>(1000)</li>
    <li>❌ 排除：<code>cover_object</code>（自家掩体）、<code>static_object</code>、<code>noncol_object</code></li>
    <li>❌ 排除：bbox 最大边长 &gt; 60m 的远景底板</li>
    <li>同一物体多个三角形只算 1 段</li>
  </ul>
  </div>
</div>

<h2>已知偏差</h2>
<div class="note">
① 反射/遮挡未计入 <code>static_object</code>（游戏内子弹不与纯装饰判定），段数可能偏乐观；
② 敌人本体未计入（波次由服务端 <code>wavedata</code> 下发，bundle 内没有），实战段数只会更高；
③ 枪口高度取角色脚底 +1.45m，属表现参数；
④ 射程表未拆出（在未提取的 nikke 表里），当前不设距离上限，命中普遍落在 35~65m；
   若后续确认武器有效射程更短，最优点会向近景移动；
⑤ 关卡→战场映射未解决（<code>spot_id</code> 服务端下发），五个战场全部出图。
</div>

<footer>
数据：<code>数据/scan_best.py</code> → <code>导出/best_00N.json</code> ·
视图：<code>数据/viewer/best.html?arena=001&amp;slot=5</code> ·
热力：<code>数据/render/best_00N_coverN_heat.png</code>（完整） / <code>zoom_00N_coverN.png</code>（放大）<br>
全部参数来自国际服拆包，无手写几何常量。
</footer>
</body></html>'''

open(OUT, "w", encoding="utf-8").write(HTML)
print("生成:", OUT, len(HTML), "字符")
print("冠军:", best["arena"], "cover_%d" % best["slot"], best["n"], "段", best["pct"], "%", best["shots"], "发")
